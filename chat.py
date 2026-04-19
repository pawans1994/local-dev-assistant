import json
import re
import requests
import argparse
import os
import sys

from tools import (
    list_files, read_file, read_file_chunk, list_entries,
    search_codebase, semantic_search_codebase,
    edit_file, run_command, git_status, git_diff,
)
from helpers.tracing import trace_event, save_trace
from helpers.dirs import ensure_dirs
from helpers.memory import load_session_memory, add_to_memory

ASSISTANT_DIR = os.path.dirname(os.path.abspath(__file__))
OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "qwen2.5:7b"

# ── ANSI colors ────────────────────────────────────────────────────────────
try:
    _color = sys.stdout.isatty()
except Exception:
    _color = False

def _c(code): return code if _color else ""

RESET   = _c("\033[0m")
BOLD    = _c("\033[1m")
DIM     = _c("\033[2m")
CYAN    = _c("\033[36m")
GREEN   = _c("\033[32m")
YELLOW  = _c("\033[33m")
RED     = _c("\033[31m")
MAGENTA = _c("\033[35m")
BLUE    = _c("\033[34m")


# ── System prompt & memory ─────────────────────────────────────────────────

def load_system_prompt() -> str:
    path = os.path.join(ASSISTANT_DIR, "prompts", "system.md")
    with open(path, "r") as f:
        return f.read()


def build_system_message(memory: list) -> str:
    base = load_system_prompt()
    if not memory:
        return base
    ctx = "\n\n---\n## Recent session memory\n"
    for item in memory[-5:]:
        answer = item.get("answer") or item.get("final_answer", "")
        ctx += f"\nQ: {item['query']}\nA: {answer[:400]}\n"
    return base + ctx


# ── JSON helpers ───────────────────────────────────────────────────────────

def tool_content(result) -> str:
    if isinstance(result, (dict, list)):
        return json.dumps(result, indent=2)
    return str(result)


def extract_json(text: str):
    text = text.strip()
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    m = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        try:
            data = json.loads(m.group(1))
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            data = json.loads(m.group(0))
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass
    return None


def looks_like_invalid_protocol(text: str) -> bool:
    return text.strip().lower() in {"false", "true", "null", "[]", "{}"}


# ── Tool validation & dispatch ─────────────────────────────────────────────

ALLOWED_TOOLS = {
    "list_files", "read_file", "read_file_chunk", "list_entries",
    "search_codebase", "semantic_search_codebase",
    "edit_file", "run_command", "git_status", "git_diff",
}

REQUIRED_ARGS = {
    "semantic_search_codebase": ["query"],
    "search_codebase": ["query"],
    "read_file": ["path"],
    "read_file_chunk": ["path", "start_line", "end_line"],
    "edit_file": ["path", "new_content"],
    "run_command": ["command"],
}


def validate_tool_call(data) -> tuple[bool, str | None]:
    if not isinstance(data, dict):
        return False, "Tool call must be a JSON object."
    action = data.get("action")
    args = data.get("args")
    if not isinstance(action, str) or not action.strip():
        return False, "Field 'action' must be a non-empty string."
    if not isinstance(args, dict):
        return False, "Field 'args' must be an object."
    if action not in ALLOWED_TOOLS:
        return False, f"Unknown tool '{action}'."
    for arg in REQUIRED_ARGS.get(action, []):
        if arg not in args:
            return False, f"Missing required argument '{arg}' for '{action}'."
    return True, None


def try_execute_tool(response_text: str):
    data = extract_json(response_text)
    if data is None:
        return None, None, "No valid JSON object found."
    is_valid, error = validate_tool_call(data)
    if not is_valid:
        return None, None, error
    action, args = data["action"], data["args"]
    dispatch = {
        "list_files":               lambda: list_files(**args),
        "read_file":                lambda: read_file(**args),
        "read_file_chunk":          lambda: read_file_chunk(**args),
        "list_entries":             lambda: list_entries(**args),
        "search_codebase":          lambda: search_codebase(**args),
        "semantic_search_codebase": lambda: semantic_search_codebase(**args),
        "edit_file":                lambda: edit_file(**args),
        "run_command":              lambda: run_command(**args),
        "git_status":               lambda: git_status(**args),
        "git_diff":                 lambda: git_diff(**args),
    }
    try:
        return action, dispatch[action](), None
    except Exception as e:
        return action, f"Error: {e}", None


# ── Ollama chat ────────────────────────────────────────────────────────────

def chat(messages: list, stream_print: bool = False) -> str:
    payload = {
        "model": MODEL,
        "messages": messages,
        "stream": stream_print,
        "options": {"temperature": 0},
    }
    if stream_print:
        full = ""
        sys.stdout.write(f"\n{GREEN}{BOLD}Assistant:{RESET} ")
        sys.stdout.flush()
        with requests.post(OLLAMA_URL, json=payload, stream=True, timeout=120) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue
                token = chunk.get("message", {}).get("content", "")
                sys.stdout.write(token)
                sys.stdout.flush()
                full += token
                if chunk.get("done"):
                    break
        sys.stdout.write("\n\n")
        sys.stdout.flush()
        return full
    else:
        r = requests.post(OLLAMA_URL, json=payload, timeout=120)
        r.raise_for_status()
        return r.json()["message"]["content"]


# ── Retrieval followups & repair ───────────────────────────────────────────

def add_retrieval_followup(action: str, messages: list):
    if action == "semantic_search_codebase":
        messages.append({"role": "user", "content": (
            "You now have relevant code snippets. "
            "Answer the original question using these snippets. "
            "Explain the full runtime flow step by step. "
            "Only call read_file_chunk if more exact context is truly needed."
        )})
    elif action == "read_file_chunk":
        messages.append({"role": "user", "content": (
            "You now have exact code context. "
            "Answer the original question completely using only this code. "
            "Explain step by step. Do not call any more tools. Do not return JSON."
        )})
    elif action == "search_codebase":
        messages.append({"role": "user", "content": (
            "Using only the retrieved snippets, answer the original question. "
            "If snippets are insufficient, say so. Do not invent code."
        )})
    elif action in {"run_command", "git_status", "git_diff"}:
        messages.append({"role": "user", "content": (
            "Here is the command output. "
            "Summarize the key findings and answer the original question."
        )})
    elif action == "edit_file":
        messages.append({"role": "user", "content": (
            "The file operation is complete. "
            "Summarize what was changed and confirm the task is done."
        )})


def add_repair_prompt(messages: list, error: str):
    messages.append({"role": "user", "content": (
        f"Your previous response was invalid.\nError: {error}\n\n"
        'Return EXACTLY ONE valid JSON object:\n{"action": "tool_name", "args": {}}\n'
        "No explanation, no markdown, no extra text."
    )})


# ── Query rewriting ────────────────────────────────────────────────────────

def rewrite_query(text: str) -> str:
    t = text.lower().strip()
    if "chat loop" in t:
        return "while True max_steps main input"
    if "execute tools" in t:
        return "try_execute_tool action tool_result max_steps"
    return text


# ── UI helpers ─────────────────────────────────────────────────────────────

def print_banner(repo_path: str, n_chunks: int, n_memory: int):
    width = 56
    border = "─" * width
    model_disp = MODEL[:width - 2]
    repo_disp = (repo_path if len(repo_path) <= width - 2 else "…" + repo_path[-(width - 3):])
    idx_str = f"{n_chunks} chunks indexed" if n_chunks else "No index — run /reindex"
    mem_str = f"{n_memory} Q&As loaded" if n_memory else "empty"

    print(f"\n{CYAN}╭{border}╮{RESET}")
    print(f"{CYAN}│{RESET}  {BOLD}🤖  Local Dev Assistant{RESET}{'':<34}{CYAN}│{RESET}")
    print(f"{CYAN}│{RESET}  {DIM}Model  :{RESET}  {model_disp:<{width-10}}{CYAN}│{RESET}")
    print(f"{CYAN}│{RESET}  {DIM}Repo   :{RESET}  {repo_disp:<{width-10}}{CYAN}│{RESET}")
    print(f"{CYAN}│{RESET}  {DIM}Index  :{RESET}  {idx_str:<{width-10}}{CYAN}│{RESET}")
    print(f"{CYAN}│{RESET}  {DIM}Memory :{RESET}  {mem_str:<{width-10}}{CYAN}│{RESET}")
    print(f"{CYAN}╰{border}╯{RESET}")
    print(f"  {DIM}Type {CYAN}/help{RESET}{DIM} for commands · {CYAN}exit{RESET}{DIM} to quit{RESET}\n")


def print_help():
    cmds = [
        ("/help",          "Show this help"),
        ("/clear",         "Clear conversation history (keeps system prompt)"),
        ("/memory",        "Show saved Q&A memory"),
        ("/reindex",       "Rebuild the semantic code index"),
        ("/history",       "Show conversation history"),
        ("/files",         "List all files currently indexed"),
        ("/model <name>",  "Switch Ollama model  e.g. /model llama3"),
        ("exit / quit",    "Exit the assistant"),
    ]
    print(f"\n{BOLD}Commands:{RESET}")
    for cmd, desc in cmds:
        print(f"  {CYAN}{cmd:<22}{RESET}{DIM}{desc}{RESET}")
    print()


def print_tool_call(action: str, args: dict):
    details = {
        "semantic_search_codebase": lambda: f'→ "{args.get("query","")[:60]}"',
        "search_codebase":          lambda: f'→ "{args.get("query","")[:60]}"',
        "read_file":                lambda: f'→ {args.get("path","")}',
        "read_file_chunk":          lambda: f'→ {args.get("path","")} :{args.get("start_line","")}-{args.get("end_line","")}',
        "edit_file":                lambda: f'→ {args.get("path","")}',
        "run_command":              lambda: f'→ {args.get("command","")[:60]}',
        "git_diff":                 lambda: f'→ {args.get("file","") or "."}',
    }
    suffix = details[action]() if action in details else ""
    print(f"\n{MAGENTA}⚙  {action}{RESET}  {DIM}{suffix}{RESET}")


def count_index_chunks(repo_path: str) -> int:
    idx = os.path.join(repo_path, "code_index.json")
    if not os.path.exists(idx):
        return 0
    try:
        with open(idx) as f:
            return len(json.load(f))
    except Exception:
        return 0


# ── Slash command handler ──────────────────────────────────────────────────

def handle_slash(raw: str, messages: list, memory: list, repo_path: str) -> bool:
    global MODEL
    parts = raw.strip().split(maxsplit=1)
    cmd = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""

    if cmd == "/help":
        print_help()
        return True

    if cmd == "/clear":
        del messages[1:]
        print(f"{YELLOW}Conversation cleared.{RESET}\n")
        return True

    if cmd == "/memory":
        if not memory:
            print(f"{DIM}No memory yet.{RESET}\n")
        else:
            print(f"\n{BOLD}Session memory ({len(memory)} entries):{RESET}")
            for i, item in enumerate(memory[-10:], 1):
                print(f"  {CYAN}{i}.{RESET} {item['query'][:100]}")
                preview = item.get("answer", "")[:200].replace("\n", " ")
                print(f"     {DIM}{preview}{RESET}")
            print()
        return True

    if cmd == "/reindex":
        print(f"{YELLOW}Rebuilding index for {repo_path}…{RESET}")
        try:
            from build_index import build_index
            build_index(root=repo_path)
            print(f"{GREEN}Done.{RESET}\n")
        except Exception as e:
            print(f"{RED}Reindex failed: {e}{RESET}\n")
        return True

    if cmd == "/history":
        if len(messages) <= 1:
            print(f"{DIM}No history yet.{RESET}\n")
        else:
            print()
            for msg in messages[1:]:
                role = msg["role"]
                content = msg["content"][:300].replace("\n", " ")
                col = CYAN if role == "user" else GREEN
                print(f"{col}[{role}]{RESET} {content}")
            print()
        return True

    if cmd == "/files":
        idx_path = os.path.join(repo_path, "code_index.json")
        if not os.path.exists(idx_path):
            print(f"{YELLOW}No index found. Run /reindex first.{RESET}\n")
            return True
        try:
            with open(idx_path) as f:
                index = json.load(f)
            files = sorted({item["file"] for item in index})
            print(f"\n{BOLD}Indexed files ({len(files)}):{RESET}")
            for fp in files:
                print(f"  {DIM}{fp}{RESET}")
            print()
        except Exception as e:
            print(f"{RED}Error: {e}{RESET}\n")
        return True

    if cmd == "/model":
        if arg:
            MODEL = arg
            print(f"{GREEN}Model → {MODEL}{RESET}\n")
        else:
            print(f"Current model: {CYAN}{MODEL}{RESET}\n")
        return True

    return False


# ── Main REPL ──────────────────────────────────────────────────────────────

def main():
    global MODEL

    parser = argparse.ArgumentParser(description="Local Dev Assistant — offline coding copilot")
    parser.add_argument("--repo",  default=".", help="Path to the repository to analyze (default: .)")
    parser.add_argument("--model", default=MODEL, help=f"Ollama model to use (default: {MODEL})")
    args = parser.parse_args()

    MODEL = args.model
    repo_path = os.path.abspath(args.repo)

    if not os.path.isdir(repo_path):
        print(f"{RED}Error: --repo path not found: {repo_path}{RESET}")
        sys.exit(1)

    os.chdir(repo_path)
    ensure_dirs()

    memory = load_session_memory()
    n_chunks = count_index_chunks(repo_path)

    print_banner(repo_path, n_chunks, len(memory))

    messages = [{"role": "system", "content": build_system_message(memory)}]

    while True:
        try:
            user = input(f"{CYAN}{BOLD}You:{RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n{DIM}Goodbye!{RESET}")
            break

        if not user:
            continue
        if user.lower() in {"exit", "quit"}:
            print(f"{DIM}Goodbye!{RESET}")
            break
        if user.startswith("/"):
            handle_slash(user, messages, memory, repo_path)
            continue

        trace_event("user_input", user)
        rewritten = rewrite_query(user)
        trace_event("rewritten_query", rewritten)

        messages.append({"role": "user", "content": rewritten})
        assistant = chat(messages)
        messages.append({"role": "assistant", "content": assistant})

        max_steps     = 8
        max_repairs   = 2
        repairs       = 0
        seen_calls    = set()
        expect_final  = False
        stream_printed = False
        final_answer  = None

        for _ in range(max_steps):
            trace_event("assistant_response", assistant)

            action, tool_result, validation_error = try_execute_tool(assistant)

            # ── No tool call detected ──────────────────────────────────
            if action is None:
                if looks_like_invalid_protocol(assistant):
                    repairs += 1
                    if repairs > max_repairs:
                        print(f"\n{RED}Failed to produce a valid response.{RESET}\n")
                        break
                    add_repair_prompt(messages, validation_error or "Invalid response.")
                    assistant = chat(messages)
                    messages.append({"role": "assistant", "content": assistant})
                    stream_printed = False
                    continue

                # Valid final answer
                trace_event("final_answer", assistant)
                final_answer = assistant
                if not stream_printed:
                    print(f"\n{GREEN}{BOLD}Assistant:{RESET} {assistant}\n")
                break

            # ── Duplicate call guard ───────────────────────────────────
            sig = (action, json.dumps(extract_json(assistant), sort_keys=True))
            if sig in seen_calls:
                trace_event("repeated_tool_call", {"tool": action})
                messages.append({"role": "user", "content": (
                    "You already made this tool call. "
                    "Use what you retrieved and answer the question now."
                )})
                expect_final = True
                assistant = chat(messages, stream_print=True)
                messages.append({"role": "assistant", "content": assistant})
                stream_printed = True
                continue

            seen_calls.add(sig)
            repairs = 0

            # ── Execute tool ───────────────────────────────────────────
            result_str = tool_content(tool_result)
            trace_event("tool_call", {"tool": action})
            trace_event("tool_result", result_str)

            print_tool_call(action, extract_json(assistant).get("args", {}))
            preview = result_str[:800]
            if len(result_str) > 800:
                preview += f"\n{DIM}… ({len(result_str)} chars total){RESET}"
            print(f"{DIM}{preview}{RESET}")

            messages.append({"role": "tool", "content": result_str})

            expect_final = action in {
                "read_file_chunk", "edit_file", "run_command", "git_status", "git_diff",
            }
            add_retrieval_followup(action, messages)

            if expect_final:
                assistant = chat(messages, stream_print=True)
                stream_printed = True
            else:
                assistant = chat(messages)
                stream_printed = False
            messages.append({"role": "assistant", "content": assistant})

        else:
            trace_event("step_limit_reached", {"max_steps": max_steps})
            print(f"\n{YELLOW}Hit the tool-call step limit ({max_steps}).{RESET}\n")

        save_trace()

        if final_answer:
            add_to_memory(user, final_answer)
            memory = load_session_memory()


if __name__ == "__main__":
    main()
