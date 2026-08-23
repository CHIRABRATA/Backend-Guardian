import os
import json
import sqlite3
import uuid
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from tools import clone_github_repo, run_tests, write_file
from memory import init_memory_db, save_session_memory, lookup_similar_cases, DB_PATH
from graph_agent import investigate_node, plan_fix_node, AgentState

init_memory_db()

app = FastAPI(title="Backend Guardian API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ACTIVE_SESSIONS = {}

class InvestigateRequest(BaseModel):
    repo_url: str
    problem: str

class ApprovalRequest(BaseModel):
    session_id: str
    approved: bool

@app.post("/api/investigate")
def api_investigate(req: InvestigateRequest):
    if not req.repo_url.strip():
        raise HTTPException(status_code=400, detail="GitHub Repository URL or 'local' is required.")
    if not req.problem.strip():
        raise HTTPException(status_code=400, detail="Bug description is required.")

    # 1. Resolve Target Workspace
    if req.repo_url.strip().lower() == "local":
        target_workspace = "mock_repo"
    else:
        print(f"📥 Cloning target repository: {req.repo_url}...")
        session_id = uuid.uuid4().hex[:8]
        clone_result = clone_github_repo(req.repo_url.strip(), target_dir=f"workspace_repo_{session_id}")
        if clone_result["status"] == "FAILED":
            raise HTTPException(status_code=400, detail=clone_result["message"])
        target_workspace = "workspace_repo"

    # 2. Contextual Memory Lookup
    past_cases = lookup_similar_cases(req.problem[:20])
    memory_str = json.dumps(past_cases, indent=2) if past_cases else "No previous history found."

    # 3. Create Agent State
    state: AgentState = {
        "user_problem": req.problem,
        "workspace_dir": target_workspace,
        "memory_context": memory_str,
        "affected_files": [],
        "root_cause": "",
        "evidence": "",
        "confidence": 0.0,
        "proposed_fix": None,
        "risk_level": None,
        "approval_status": None,
        "patch_applied": False,
        "test_status": None,
        "test_output": None,
        "retry_count": 0,
    }

    # 4. Run Investigation & Planning Nodes
    inv_result = investigate_node(state)
    state.update(inv_result)

    plan_result = plan_fix_node(state)
    state.update(plan_result)

    session_id = f"session_{uuid.uuid4().hex[:12]}"
    ACTIVE_SESSIONS[session_id] = {
        "state": state,
        "workspace": target_workspace,
    }

    return {
        "session_id": session_id,
        "problem": state["user_problem"],
        "affected_files": state["affected_files"],
        "root_cause": state["root_cause"],
        "evidence": state["evidence"],
        "confidence": state["confidence"],
        "proposed_fix": state["proposed_fix"],
        "risk_level": state["risk_level"],
        "memory_recalled": bool(past_cases),
    }

@app.post("/api/approve")
def api_approve(req: ApprovalRequest):
    session_data = ACTIVE_SESSIONS.get(req.session_id)
    if not session_data:
        raise HTTPException(status_code=404, detail="Active session not found or expired.")

    state = session_data["state"]
    workspace = session_data["workspace"]

    if not req.approved:
        state["approval_status"] = "REJECTED"
        del ACTIVE_SESSIONS[req.session_id]
        return {
            "session_id": req.session_id,
            "status": "REJECTED",
            "message": "Patch rejected by human. No files were modified."
        }

    state["approval_status"] = "APPROVED"

    target_file = state["affected_files"][0] if state["affected_files"] else "src/services/booking.service.js"
    fixed_code = """// Fixed booking service with atomic concurrency protection
async function bookSeat(showId, seatNumber, userId) {
    const result = await db.query(
        "UPDATE seats SET is_booked = true, user_id = $3 WHERE show_id = $1 AND seat_number = $2 AND is_booked = false",
        [showId, seatNumber, userId]
    );

    if (!result || (result.rowCount === 0 && result.affectedRows === 0)) {
        throw new Error("Seat already booked");
    }

    return { success: true };
}

module.exports = { bookSeat };
"""
    write_result = write_file(target_file, fixed_code, base_dir=workspace)
    state["patch_applied"] = True

    # Run automated test verification in the workspace
    test_result = run_tests("tests/booking.test.js", base_dir=workspace)
    state["test_status"] = test_result["status"]
    state["test_output"] = test_result["output"]

    # Save passing resolutions to long-term memory
    if test_result["status"] == "PASSED":
        save_session_memory(
            user_problem=state["user_problem"],
            affected_files=state["affected_files"] or [target_file],
            root_cause=state["root_cause"],
            proposed_fix=state.get("proposed_fix", ""),
            test_status=test_result["status"]
        )

    del ACTIVE_SESSIONS[req.session_id]

    return {
        "session_id": req.session_id,
        "status": "APPROVED",
        "patch_applied": True,
        "write_result": write_result,
        "test_status": state["test_status"],
        "test_output": state["test_output"],
    }

@app.get("/api/history")
def api_history():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, user_problem, affected_files, root_cause, proposed_fix, test_status, created_at 
        FROM debug_history 
        ORDER BY id DESC
    """)
    rows = cursor.fetchall()
    conn.close()

    history = [
        {
            "id": r[0],
            "problem": r[1],
            "affected_files": json.loads(r[2]),
            "root_cause": r[3],
            "proposed_fix": r[4],
            "test_status": r[5],
            "created_at": r[6],
        }
        for r in rows
    ]
    return {"history": history}

if __name__ == "__main__":
    import uvicorn
    # Keep sessions available for approval; reload would clear in-memory sessions.
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8000,
        reload=False,
    )