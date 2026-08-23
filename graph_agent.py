import os
import json
import re
from typing import TypedDict, List, Optional
from dotenv import load_dotenv
from groq import Groq
from pydantic import BaseModel
from langgraph.graph import StateGraph, START, END

from tools import list_files, read_file, search_code

load_dotenv()

MODEL_NAME = "qwen/qwen3.6-27b"

# --- 1. Agent State with Approval Tracking ---
class AgentState(TypedDict):
    user_problem: str
    affected_files: List[str]
    root_cause: str
    evidence: str
    confidence: float
    proposed_fix: Optional[str]
    risk_level: Optional[str]
    approval_status: Optional[str]  # "APPROVED" or "REJECTED"

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

class DiagnosticReport(BaseModel):
    problem_summary: str
    affected_files: list[str]
    evidence: str
    root_cause: str
    confidence: float

# --- 3. Node 1: Investigation ---
def investigate_node(state: AgentState) -> dict:
    print("\n🔍 [1. Investigate Node] Exploring repository...")
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))

    messages = [
        {"role": "system", "content": "You are a backend debugging investigator. Explore using tools to locate the bug."},
        {"role": "user", "content": state["user_problem"]},
    ]

    while True:
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
                fn_args = json.loads(tc.function.arguments)
                print(f"  🛠️  Tool: {fn_name}({fn_args})")
                tool_fn = AVAILABLE_TOOLS.get(fn_name)
                output = tool_fn(**fn_args) if tool_fn else f"Tool {fn_name} not found."
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": fn_name,
                    "content": json.dumps(output),
                })
        else:
            break

    schema_json = json.dumps(DiagnosticReport.model_json_schema())
    messages.append({
        "role": "user",
        "content": f"Output diagnosis as JSON matching this schema:\n{schema_json}\nReturn ONLY JSON.",
    })

    structured_res = client.chat.completions.create(
        model=MODEL_NAME,
        messages=messages,
        response_format={"type": "json_object"},
    )
    report = DiagnosticReport.model_validate_json(structured_res.choices[0].message.content)

    return {
        "affected_files": report.affected_files,
        "evidence": report.evidence,
        "root_cause": report.root_cause,
        "confidence": report.confidence,
    }

# --- 4. Node 2: Fix Planner ---
def plan_fix_node(state: AgentState) -> dict:
    print("\n📝 [2. Plan Fix Node] Creating repair strategy...")
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))

    prompt = f"""
You are a senior backend architect.
Diagnosis:
- Affected Files: {state['affected_files']}
- Root Cause: {state['root_cause']}
- Evidence: {state['evidence']}

Propose a concrete fix. Do not include thinking tags.
Format your response exactly as:
PROPOSED_FIX: <concise explanation and code change>
RISK_LEVEL: <LOW/MEDIUM/HIGH/CRITICAL>
"""

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": prompt}],
    )
    content = response.choices[0].message.content

    # Strip thinking tags if present
    cleaned_content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()

    risk = "HIGH"
    if "RISK_LEVEL: LOW" in cleaned_content:
        risk = "LOW"
    elif "RISK_LEVEL: MEDIUM" in cleaned_content:
        risk = "MEDIUM"
    elif "RISK_LEVEL: CRITICAL" in cleaned_content:
        risk = "CRITICAL"

    return {
        "proposed_fix": cleaned_content,
        "risk_level": risk,
    }

# --- 5. Node 3: Human-in-the-Loop Approval Gate ---
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

    # Interactive Human Prompt
    user_choice = input("\nDo you approve applying this fix to the repository? (y/n): ").strip().lower()

    if user_choice == "y":
        print("\n✅ Fix Approved by Human. Proceeding to code modification...")
        return {"approval_status": "APPROVED"}
    else:
        print("\n❌ Fix Rejected by Human. Aborting repository modification.")
        return {"approval_status": "REJECTED"}

# --- 6. Assemble Graph with Approval Gate ---
def build_guardian_graph():
    workflow = StateGraph(AgentState)

    workflow.add_node("investigate", investigate_node)
    workflow.add_node("plan_fix", plan_fix_node)
    workflow.add_node("human_approval", human_approval_node)

    workflow.add_edge(START, "investigate")
    workflow.add_edge("investigate", "plan_fix")
    workflow.add_edge("plan_fix", "human_approval")
    workflow.add_edge("human_approval", END)

    return workflow.compile()

if __name__ == "__main__":
    app = build_guardian_graph()

    initial_state = {
        "user_problem": "Two users can book the same seat simultaneously. Investigate and plan a fix.",
        "affected_files": [],
        "root_cause": "",
        "evidence": "",
        "confidence": 0.0,
        "proposed_fix": None,
        "risk_level": None,
        "approval_status": None,
    }

    final_state = app.invoke(initial_state)
    print(f"\nFinal Execution Status: {final_state['approval_status']}")