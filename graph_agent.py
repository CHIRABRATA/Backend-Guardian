import os
import json
from typing import TypedDict, List, Optional
from dotenv import load_dotenv
from groq import Groq
from pydantic import BaseModel, Field
from langgraph.graph import StateGraph, START, END

from tools import list_files, read_file, search_code

load_dotenv()

# --- 1. Define the Shared Agent State (The Clipboard) ---
class AgentState(TypedDict):
    user_problem: str
    affected_files: List[str]
    root_cause: str
    evidence: str
    confidence: float
    proposed_fix: Optional[str]
    risk_level: Optional[str]

# --- 2. Tool Definition & Mapping ---
tools_schema = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "Lists all files in the repository to understand project layout.",
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
                "properties": {
                    "query": {"type": "string", "description": "The keyword to search for."}
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Reads the entire contents of a file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Relative file path."}
                },
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

# --- 3. Node 1: Investigation Worker ---
def investigate_node(state: AgentState) -> dict:
    print("\n🔍 [Node: Investigate] Starting repository exploration...")
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))

    messages = [
        {
            "role": "system",
            "content": (
                "You are an expert backend debugging investigator. "
                "Explore the repository using tools to find the bug."
            ),
        },
        {"role": "user", "content": state["user_problem"]},
    ]

    # Tool execution loop
    while True:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            tools=tools_schema,
            tool_choice="auto",
        )
        msg = response.choices[0].message
        
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
                print(f"  🛠️  Tool called: {fn_name} with args {fn_args}")

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

    # Structure the diagnosis into Pydantic
    schema_json = json.dumps(DiagnosticReport.model_json_schema())
    messages.append({
        "role": "user",
        "content": f"Output diagnosis as JSON matching this schema:\n{schema_json}\nReturn ONLY JSON.",
    })

    structured_res = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=messages,
        response_format={"type": "json_object"},
    )
    report = DiagnosticReport.model_validate_json(structured_res.choices[0].message.content)

    # Return only the fields we want to update in the shared State
    return {
        "affected_files": report.affected_files,
        "evidence": report.evidence,
        "root_cause": report.root_cause,
        "confidence": report.confidence,
    }

# --- 4. Node 2: Fix Planner Worker ---
def plan_fix_node(state: AgentState) -> dict:
    print("\n📝 [Node: Plan Fix] Designing a repair plan based on investigation...")
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))

    prompt = f"""
You are a senior backend architect.
Based on the following bug diagnosis:
- Affected Files: {state['affected_files']}
- Root Cause: {state['root_cause']}
- Evidence: {state['evidence']}

Propose a concrete fix. Also assign a risk level (LOW, MEDIUM, HIGH, CRITICAL).
Return your response in this exact format:
PROPOSED_FIX: <clear description of the fix>
RISK_LEVEL: <LOW/MEDIUM/HIGH/CRITICAL>
"""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
    )
    content = response.choices[0].message.content

    # Extract proposed fix and risk level
    risk = "HIGH"
    if "RISK_LEVEL: LOW" in content:
        risk = "LOW"
    elif "RISK_LEVEL: MEDIUM" in content:
        risk = "MEDIUM"
    elif "RISK_LEVEL: CRITICAL" in content:
        risk = "CRITICAL"

    return {
        "proposed_fix": content,
        "risk_level": risk,
    }

# --- 5. Assemble the LangGraph ---
def build_guardian_graph():
    # 1. Initialize the graph with our state blueprint
    workflow = StateGraph(AgentState)

    # 2. Add nodes (our worker functions)
    workflow.add_node("investigate", investigate_node)
    workflow.add_node("plan_fix", plan_fix_node)

    # 3. Add edges (the workflow pipeline)
    workflow.add_edge(START, "investigate")
    workflow.add_edge("investigate", "plan_fix")
    workflow.add_edge("plan_fix", END)

    # 4. Compile into an executable graph
    return workflow.compile()

# --- 6. Execution ---
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
    }

    final_state = app.invoke(initial_state)

    print("\n" + "=" * 60)
    print("🏁 FINAL LANGGRAPH STATE SUMMARY")
    print("=" * 60)
    print(f"• Problem        : {final_state['user_problem']}")
    print(f"• Affected Files : {final_state['affected_files']}")
    print(f"• Root Cause     : {final_state['root_cause']}")
    print(f"• Risk Level     : {final_state['risk_level']}")
    print(f"• Proposed Fix   :\n{final_state['proposed_fix']}")
    print("=" * 60)