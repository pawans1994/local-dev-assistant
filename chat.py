import requests
import json
from tools import list_files, read_file, list_entries, search_codebase
import re

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "qwen2.5:7b"   # change if you used another model

def load_system_prompt():
    with open("prompts/system.md") as f:
        return f.read()

def tool_content(result) -> str:
    if isinstance(result, (dict, list)):
        return json.dumps(result, indent=2)
    return str(result)

def rewrite_codebase_query(user_text: str) -> str:
    text = user_text.lower().strip()

    if "chat loop" in text:
        return "while True max_steps main input"
    if "execute tools" in text:
        return "try_execute_tool action tool_result max_steps"
    return user_text

def looks_like_invalid_protocol_response(text: str) -> bool:
    stripped = text.strip().lower()
    return stripped in {"false", "true", "null", "[]", "{}"}

def try_execute_tool(response_text):
    try:
        data = json.loads(response_text)
    except json.JSONDecodeError:
        return None, None

    if not isinstance(data, dict):
        return None, None

    action = data.get("action")
    args = data.get("args")

    if not isinstance(action, str) or not isinstance(args, dict):
        return None, None

    try:
        if action == "list_files":
            return action, list_files(**args)
        elif action == "read_file":
            return action, read_file(**args)
        elif action == "list_entries":
            return action, list_entries(**args)
        elif action == "search_codebase":
            return action, search_codebase(**args)
    except Exception as e:
        return action, f"Error executing tool: {str(e)}"

    return None, None

def chat(messages):
    payload = {
        "model": MODEL,
        "messages": messages,
        "stream": False,
    }
    r = requests.post(OLLAMA_URL, json=payload, timeout=120)
    r.raise_for_status()
    data = r.json()
    return data["message"]["content"]

def main():
    messages = [
        {
            "role": "system",
            "content": load_system_prompt()
        }
    ]

    print("Local Dev Assistant (type 'exit' to quit)\n")

    while True:
        user = input("You: ").strip()
        if user.lower() in {"exit", "quit"}:
            break

        rewritten_user = rewrite_codebase_query(user)
        messages.append({"role": "user", "content": rewritten_user})

        assistant = chat(messages)
        messages.append({"role": "assistant", "content": assistant})

        max_steps = 8
        for _ in range(max_steps):
            action, tool_result = try_execute_tool(assistant)

            if action is None:
                if looks_like_invalid_protocol_response(assistant):
                    messages.append({
                        "role": "user",
                        "content": (
                            "Your previous response was invalid. "
                            "For this codebase question, either:\n"
                            "1. return EXACTLY ONE tool-call JSON object, or\n"
                            "2. return a normal natural-language answer.\n"
                            "Do not return booleans, null, empty arrays, or empty objects."
                        )
                    })
                    assistant = chat(messages)
                    messages.append({"role": "assistant", "content": assistant})
                    continue

                print(f"\nAssistant: {assistant}\n")
                break

            print(f"\n[Tool: {action}]\n{tool_content(tool_result)}\n")
            messages.append({"role": "tool", "content": tool_content(tool_result)})

            if action == "search_codebase":
                messages.append({
                    "role": "user",
                    "content": (
                        "Using only the retrieved snippets above, answer the original question. "
                        "Prefer actual loop/control-flow code over examples, URLs, or prompt text."
                    )
                })

            assistant = chat(messages)
            messages.append({"role": "assistant", "content": assistant})
        else:
            print("\nAssistant: I hit the tool-call step limit.\n")

if __name__ == "__main__":
    main()