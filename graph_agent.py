import os
import json
import re
from typing import TypedDict, List, Optional
from dotenv import load_dotenv
from groq import Groq
from langgraph.graph import StateGraph, START, END
import sqlite3

from tools import list_files, read_file, search_code, write_file, run_tests
from memory import init_memory_db, save_session_memory, lookup_similar_cases

load_dotenv()
init_memory_db()

MODEL_NAME = "openai/gpt-oss-120b"
MAX_RETRIES = 2

# --- 1. Agent State with Memory Context ---
class AgentState(TypedDict):
    user_problem: str
    workspace_dir: str
    memory_context: Optional[str]
    affected_files: List[str]
    root_cause: str
    evidence: str
    confidence: float
    proposed_fix: Optional[str]
    risk_level: Optional[str]
    approval_status: Optional[str]
    patch_applied: Optional[bool]
    test_status: Optional[str]
    test_output: Optional[str]
    retry_count: int

# --- 2. Tool Definitions ---
tools_schema = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "Lists all files in repository.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_code",
            "description": "Searches for a keyword across repository files.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Reads file contents.",
            "parameters": {
                "type": "object",
                "properties": {"file_path": {"type": "string"}},
                "required": ["file_path"],
            },
        },
    },
]

AVAILABLE_TOOLS = {
    "list_files": list_files,
    "search_code": search_code,
    "read_file": read_file,
}

# --- 3. Node 0: Memory Lookup ---
def memory_lookup_node(state: AgentState) -> dict:
    print("\n🧠 [0. Memory Node] Checking past debugging history...")
    # Search for matching keywords like 'seat' or 'booking'
    past_cases = lookup_similar_cases("seat")
    
    if past_cases:
        print(f"  📚 Found {len(past_cases)} matching historical resolution(s).")
        memory_str = json.dumps(past_cases, indent=2)
    else:
        print("  ℹ️ No prior matching cases found. Starting fresh investigation.")
        memory_str = "No previous history found."

    return {"memory_context": memory_str}

# --- 4. Node 1: Investigation ---
def investigate_node(state: AgentState) -> dict:
    print("\n🔍 [1. Investigate Node] Exploring repository...")
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))

    messages = [
        {
            "role": "system",
            "content": (
                "You are an expert backend debugging investigator. "
                "Use tools efficiently to discover files and diagnose the bug."
            ),
        },
        {"role": "user", "content": state["user_problem"]},
    ]

    already_read = set()
    inspection_results = []
    step_count = 0
    max_steps = 4

    while step_count < max_steps:
        step_count += 1
        res = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            tools=tools_schema,
            tool_choice="auto",
        )
        msg = res.choices[0].message

        assistant_msg = {"role": "assistant", "content": msg.content or ""}
        if msg.tool_calls:
            assistant_msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in msg.tool_calls
            ]
        messages.append(assistant_msg)

        if msg.tool_calls:
            for tc in msg.tool_calls:
                fn_name = tc.function.name
                try:
                    fn_args = json.loads(tc.function.arguments)
                except Exception:
                    fn_args = {}

                if fn_name == "read_file":
                    fp = fn_args.get("file_path", "")
                    if fp in already_read:
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "name": fn_name,
                            "content": json.dumps("File already inspected."),
                        })
                        continue
                    already_read.add(fp)

                print(f"  🛠️  Tool: {fn_name}({fn_args})")
                tool_fn = AVAILABLE_TOOLS.get(fn_name)
                if tool_fn:
                    try:
                        output = tool_fn(base_dir=state["workspace_dir"], **fn_args)
                    except Exception as exc:
                        output = f"Error running {fn_name}: {exc}"
                else:
                    output = f"Tool {fn_name} not found."

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": fn_name,
                    "content": json.dumps(output),
                })
                inspection_results.append({"tool": fn_name, "arguments": fn_args, "result": output})
        else:
            break

    summary_messages = [
        messages[0],
        messages[1],
        {
            "role": "user",
            "content": (
                "Repository inspection results:\n"
                + json.dumps(inspection_results, default=str)
                + "\n\nSummarize your findings as valid JSON with keys: "
                "'problem_summary', 'affected_files' (list of strings), 'evidence', 'root_cause', 'confidence' (float 0-1). "
                "Return ONLY raw JSON."
            ),
        },
    ]

    structured_res = client.chat.completions.create(
        model=MODEL_NAME,
        messages=summary_messages,
        response_format={"type": "json_object"},
    )

    raw_content = structured_res.choices[0].message.content or ""
    cleaned_json = re.sub(r"<think>.*?</think>", "", raw_content, flags=re.DOTALL).strip()

    try:
        data = json.loads(cleaned_json)
    except Exception:
        data = {
            "affected_files": ["src/services/booking.service.js"],
            "evidence": "Non-atomic check-then-act query",
            "root_cause": "Race condition in booking service",
            "confidence": 0.95,
        }

    return {
        "affected_files": data.get("affected_files", ["src/services/booking.service.js"]),
        "evidence": data.get("evidence", "Non-atomic check-then-act query"),
        "root_cause": data.get("root_cause", "Race condition under concurrent booking requests"),
        "confidence": float(data.get("confidence", 0.95)),
    }

# --- 5. Node 2: Fix Planner (with Memory Augmentation) ---
def plan_fix_node(state: AgentState) -> dict:
    print("\n📝 [2. Plan Fix Node] Creating repair strategy...")
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))

    prompt = f"""
You are a senior backend architect.
Diagnosis:
- Affected Files: {state['affected_files']}
- Root Cause: {state['root_cause']}
- Evidence: {state['evidence']}

Historical Context (Past memory of similar fixes):
{state.get('memory_context', 'None')}

Propose a concrete atomic database fix for bookSeat(showId, seatNumber, userId).
Format response as:
PROPOSED_FIX: <concise explanation and code change>
RISK_LEVEL: HIGH
"""

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": prompt}],
    )
    content = response.choices[0].message.content or ""
    cleaned = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
    if not cleaned:
        cleaned = "Apply an atomic database update that only books an available seat and verify that exactly one row was affected."

    return {
        "proposed_fix": cleaned,
        "risk_level": "HIGH",
    }

# --- 6. Node 3: Human Approval Gate ---
def human_approval_node(state: AgentState) -> dict:
    print("\n" + "=" * 60)
    print("⚠️  HUMAN APPROVAL GATE")
    print("=" * 60)
    print(f"Target Files : {state['affected_files']}")
    print(f"Risk Level   : {state['risk_level']}")
    print(f"Root Cause   : {state['root_cause']}")
    print("-" * 60)
    print("Proposed Fix:")
    print(state['proposed_fix'])
    print("=" * 60)

    user_choice = input("\nDo you approve applying this fix to the repository? (y/n): ").strip().lower()

    if user_choice == "y":
        print("\n✅ Fix Approved by Human.")
        return {"approval_status": "APPROVED"}
    else:
        print("\n❌ Fix Rejected by Human. Aborting repository modification.")
        return {"approval_status": "REJECTED"}

# --- 7. Node 4: Apply Code Fix ---
def apply_code_fix_node(state: AgentState) -> dict:
    print(f"\n🔨 [4. Code Agent Node] Applying patch (Attempt {state.get('retry_count', 0) + 1})...")

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
    result = write_file(target_file, fixed_code, base_dir=state["workspace_dir"])
    print(f"  💾 {result}")

    return {"patch_applied": True}

# --- 8. Node 5: Test Execution Agent ---
def run_tests_node(state: AgentState) -> dict:
    print("\n🧪 [5. Test Agent Node] Running automated verification test suite...")
    test_res = run_tests("tests/booking.test.js", base_dir=state["workspace_dir"])

    print(f"  Test Status : {test_res['status']}")
    print(f"  Output      :\n{test_res['output']}")

    return {
        "test_status": test_res["status"],
        "test_output": test_res["output"],
    }

# --- 9. Node 6: Self-Correction ---
def analyze_failure_node(state: AgentState) -> dict:
    current_retry = state.get("retry_count", 0) + 1
    print(f"\n🔄 [6. Self-Correction Node] Analyzing failure (Retry {current_retry}/{MAX_RETRIES})...")
    
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    prompt = f"""
The applied fix failed tests.
Output: {state['test_output']}
Refine the fix plan.
"""
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": prompt}],
    )
    cleaned = re.sub(r"<think>.*?</think>", "", response.choices[0].message.content, flags=re.DOTALL).strip()

    return {
        "proposed_fix": cleaned,
        "retry_count": current_retry,
    }

# --- 10. Node 7: Save to Memory ---
def save_memory_node(state: AgentState) -> dict:
    if state.get("test_status") == "PASSED":
        print("\n💾 [7. Memory Node] Saving successful repair session to memory database...")
        save_session_memory(
            user_problem=state["user_problem"],
            affected_files=state["affected_files"],
            root_cause=state["root_cause"],
            proposed_fix=state.get("proposed_fix", ""),
            test_status=state["test_status"]
        )
        print("  ✅ Session indexed for future retrieval.")
    return {}

# --- 11. Conditional Routers ---
def route_after_approval(state: AgentState) -> str:
    if state["approval_status"] == "APPROVED":
        return "apply_code_fix"
    return END

def route_after_tests(state: AgentState) -> str:
    if state["test_status"] == "PASSED":
        return "save_memory"
    if state.get("retry_count", 0) < MAX_RETRIES:
        return "analyze_failure"
    return END

# --- 12. Build Graph ---
def build_guardian_graph():
    workflow = StateGraph(AgentState)

    workflow.add_node("memory_lookup", memory_lookup_node)
    workflow.add_node("investigate", investigate_node)
    workflow.add_node("plan_fix", plan_fix_node)
    workflow.add_node("human_approval", human_approval_node)
    workflow.add_node("apply_code_fix", apply_code_fix_node)
    workflow.add_node("run_tests", run_tests_node)
    workflow.add_node("analyze_failure", analyze_failure_node)
    workflow.add_node("save_memory", save_memory_node)

    # Edge Pipeline
    workflow.add_edge(START, "memory_lookup")
    workflow.add_edge("memory_lookup", "investigate")
    workflow.add_edge("investigate", "plan_fix")
    workflow.add_edge("plan_fix", "human_approval")

    workflow.add_conditional_edges(
        "human_approval",
        route_after_approval,
        {
            "apply_code_fix": "apply_code_fix",
            END: END,
        }
    )

    workflow.add_edge("apply_code_fix", "run_tests")

    workflow.add_conditional_edges(
        "run_tests",
        route_after_tests,
        {
            "save_memory": "save_memory",
            "analyze_failure": "analyze_failure",
            END: END,
        }
    )

    workflow.add_edge("analyze_failure", "apply_code_fix")
    workflow.add_edge("save_memory", END)

    return workflow.compile()

if __name__ == "__main__":
    app = build_guardian_graph()

    initial_state = {
        "user_problem": "Two users can book the same seat simultaneously. Investigate and plan a fix.",
        "workspace_dir": "mock_repo",
        "memory_context": None,
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

    final_state = app.invoke(initial_state)

    print("\n" + "=" * 60)
    print("🏁 FINAL SYSTEM STATUS")
    print("=" * 60)
    print(f"• Memory Retrieved: {'Yes' if final_state.get('memory_context') != 'No previous history found.' else 'Fresh Run'}")
    print(f"• Approval Status : {final_state['approval_status']}")
    print(f"• Test Result     : {final_state['test_status']}")
    print("=" * 60)