import os
import json
from dotenv import load_dotenv
from groq import Groq
from tools import list_files, read_file, search_code

load_dotenv()

# 1. Define the tool schemas for Groq
tools_schema = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "Lists all files in the repository to understand the project structure.",
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
            "description": "Searches for a specific keyword or phrase across all files in the repository.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The keyword or phrase to search for (e.g. 'seat', 'booking', 'SELECT')."
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
            "description": "Reads the entire contents of a specific file in the repository.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "The relative path to the file (e.g. 'src/services/booking.service.js')."
                    }
                },
                "required": ["file_path"],
            },
        },
    },
]

# 2. Map tool names to actual Python functions
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

    # Conversation history
    messages = [
        {
            "role": "system",
            "content": (
                "You are Backend Guardian, an expert backend debugging agent. "
                "Your job is to investigate repository files using the provided tools, "
                "locate bugs, identify the root cause, and explain your findings clearly."
            ),
        },
        {
            "role": "user",
            "content": user_problem,
        },
    ]

    print(f"\n[Problem Received]: {user_problem}\n")

    # Agent Execution Loop
    while True:
        # Ask Groq what to do next
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            tools=tools_schema,
            tool_choice="auto",
        )

        response_message = response.choices[0].message
        messages.append(response_message)

        # If the model requested tool calls, execute them
        if response_message.tool_calls:
            for tool_call in response_message.tool_calls:
                function_name = tool_call.function.name
                function_args = json.loads(tool_call.function.arguments)

                print(f"🛠️  [Agent Action] Calling tool '{function_name}' with arguments: {function_args}")

                # Call the corresponding Python function
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

                # Send tool execution result back to the model
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": function_name,
                    "content": json.dumps(tool_output),
                })
        else:
            # The model has finished its investigation and provided the final response
            print("\n📋 [Final Diagnosis]:")
            print(response_message.content)
            break

if __name__ == "__main__":
    problem = "Two users are able to book the exact same seat concurrently in my ticket booking system. Investigate the codebase and find the root cause."
    run_agent(problem)