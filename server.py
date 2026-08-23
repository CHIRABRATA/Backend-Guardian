import os
import json
import sqlite3
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from tools import clone_github_repo, run_tests, push_fix_to_github
from memory import init_memory_db, save_session_memory, lookup_similar_cases, DB_PATH
from graph_agent import investigate_node, plan_fix_node, apply_code_fix_node, AgentState

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

    if req.repo_url.strip().lower() == "local":
        target_workspace = "mock_repo"
    else:
        print(f"📥 Cloning target repository: {req.repo_url}...")
        clone_result = clone_github_repo(req.repo_url.strip(), target_dir="workspace_repo")
        if clone_result["status"] == "FAILED":
            raise HTTPException(status_code=400, detail=clone_result["message"])
        target_workspace = "workspace_repo"

    past_cases = lookup_similar_cases(req.problem[:20])
    memory_str = json.dumps(past_cases, indent=2) if past_cases else "No previous history found."

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

    inv_result = investigate_node(state)
    state.update(inv_result)

    plan_result = plan_fix_node(state)
    state.update(plan_result)

    session_id = f"session_{len(ACTIVE_SESSIONS) + 1}"
    ACTIVE_SESSIONS[session_id] = {
        "state": state,
        "workspace": target_workspace,
        "repo_url": req.repo_url.strip()
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
    repo_url = session_data.get("repo_url", "local")

    if not req.approved:
        state["approval_status"] = "REJECTED"
        return {
            "session_id": req.session_id,
            "status": "REJECTED",
            "message": "Modification rejected by human. No files were changed."
        }

    state["approval_status"] = "APPROVED"

    # 1. Apply code fix using the LLM agent
    patch_result = apply_code_fix_node(state)
    state.update(patch_result)

    # 2. Run automated test suite
    test_result = run_tests(base_dir=workspace)
    state["test_status"] = test_result["status"]
    state["test_output"] = test_result["output"]

    # 3. Push to GitHub if remote repository
    push_result = {"status": "SKIPPED", "message": "Local repository target."}
    if repo_url != "local":
        push_result = push_fix_to_github(
            repo_url=repo_url,
            base_dir=workspace,
            branch_name=f"fix/guardian-{req.session_id}",
            commit_message=f"fix: {state['root_cause'][:60]}"
        )

    # 4. Save to persistent memory
    if test_result["status"] in ["PASSED", "SKIPPED"]:
        save_session_memory(
            user_problem=state["user_problem"],
            affected_files=state["affected_files"],
            root_cause=state["root_cause"],
            proposed_fix=state.get("proposed_fix", ""),
            test_status=test_result["status"]
        )

    return {
        "session_id": req.session_id,
        "status": "APPROVED",
        "patch_applied": state["patch_applied"],
        "test_status": state["test_status"],
        "test_output": state["test_output"],
        "git_push": push_result
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
    uvicorn.run(
        "server:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        reload_excludes=["workspace_repo/*", "mock_repo/*", "*.db"]
    )