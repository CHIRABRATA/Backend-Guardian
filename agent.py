import os
import json
from dotenv import load_dotenv
from groq import Groq
from pydantic import BaseModel, Field
from tools import list_files, read_file, search_code

load_dotenv()

# --- 1. Define Structured Output Schema ---
class DiagnosticReport(BaseModel):
    problem_summary: str = Field(
        description="A concise summary of the reported backend issue."
    )
    affected_files: list[str] = Field(
        description="List of file paths that contain the bug or need modification."
    )
    evidence: str = Field(
        description="Specific code snippets, function names, or lines proving why the bug occurs."
    )
    root_cause: str = Field(
        description="Detailed explanation of the underlying flaw (e.g., race condition, missing auth)."
    )
    confidence: float = Field(
        description="Confidence score from 0.0 to 1.0 in this diagnosis.",
        ge=0.0,
        le=1.0,
    )

# --- 2. Tool Definitions ---
tools_schema = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "Lists all files in the repository to understand project layout.",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_code",
            "description": "Searches for a keyword or string across all files in the repository.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The exact keyword to search for (e.g. 'seats', 'booking', 'SELECT')."
                    }
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
                    "file_path": {
                        "type": "string",
                        "description": "The relative file path (e.g. 'src/services/booking.service.js')."
                    }
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

def run_agent(user_problem: str):
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY missing in .env")

    client = Groq(api_key=api_key)

    messages = [
        {
            "role": "system",
            "content": (
                "You are Backend Guardian, an expert backend debugging agent. "
                "Investigate the codebase using the provided tools. "
                "Use 'list_files' to discover files, 'search_code' to find keywords, and 'read_file' to inspect source code. "
                "Do not assume code structure without inspecting it first."
            ),
        },
        {
            "role": "user",
            "content": user_problem,
        },
    ]

    print(f"\n[Problem Received]: {user_problem}\n")

    # Step A: Autonomous Investigation Loop
    while True:
        response = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=messages,
            tools=tools_schema,
            tool_choice="auto",
        )

        response_message = response.choices[0].message

        # Safely append assistant message to conversation history
        assistant_msg = {
            "role": "assistant",
            "content": response_message.content or "",
        }
        if response_message.tool_calls:
            assistant_msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in response_message.tool_calls
            ]
        
        messages.append(assistant_msg)

        if response_message.tool_calls:
            for tool_call in response_message.tool_calls:
                function_name = tool_call.function.name
                function_args = json.loads(tool_call.function.arguments)

                print(f"🛠️  [Agent Action] Calling tool '{function_name}' with args: {function_args}")

                tool_function = AVAILABLE_TOOLS.get(function_name)
                if tool_function:
                    if function_name == "list_files":
                        tool_output = tool_function()
                    elif function_name == "search_code":
                        tool_output = tool_function(query=function_args.get("query"))
                    elif function_name == "read_file":
                        tool_output = tool_function(file_path=function_args.get("file_path"))
                else:
                    tool_output = f"Error: Tool '{function_name}' not found."

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": function_name,
                    "content": json.dumps(tool_output),
                })
        else:
            # Done exploring
            break

    # Step B: Format the diagnosis into our strict Pydantic model
    print("\n🔍 Formatting diagnosis into structured report...")

    schema_json = json.dumps(DiagnosticReport.model_json_schema())
    
    messages.append({
        "role": "user",
        "content": (
            f"Based on your investigation, output the final diagnosis as a valid JSON object matching this schema:\n"
            f"{schema_json}\n"
            "Return ONLY the raw JSON object, with no markdown code fences or conversational text."
        ),
    })

    structured_response = client.chat.completions.create(
        model="qwen/qwen3.6-27b",
        messages=messages,
        response_format={"type": "json_object"},
    )

    raw_json = structured_response.choices[0].message.content
    report = DiagnosticReport.model_validate_json(raw_json)

    print("\n" + "=" * 50)
    print("📋 STRUCTURED DIAGNOSTIC REPORT (PYDANTIC OBJECT)")
    print("=" * 50)
    print(f"• Problem Summary : {report.problem_summary}")
    print(f"• Affected Files  : {report.affected_files}")
    print(f"• Evidence        : {report.evidence}")
    print(f"• Root Cause      : {report.root_cause}")
    print(f"• Confidence      : {report.confidence * 100:.1f}%")
    print("=" * 50 + "\n")

    return report

if __name__ == "__main__":
    problem = "Two users are able to book the exact same seat concurrently in my ticket booking system. Investigate the codebase and find the root cause."
    run_agent(problem)
