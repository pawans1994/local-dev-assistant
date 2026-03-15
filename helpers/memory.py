import json
import os

MEMORY_FILE = "memory/session_memory.json"

def ensure_dirs():
    os.makedirs("memory", exist_ok=True)
    os.makedirs("traces", exist_ok=True)

def save_session(trace, user):
    memory = load_session_memory()
    memory.append({
        "query": user,
        "rewritten_query": trace["rewritten_query"],
        "final_answer": trace["final_answer"]
    })
    memory = memory[-20:]
    save_session_memory(memory)

def ensure_memory_dir():
    os.makedirs("memory", exist_ok=True)


def load_session_memory():
    ensure_memory_dir()

    if not os.path.exists(MEMORY_FILE):
        return []

    with open(MEMORY_FILE, "r") as f:
        return json.load(f)


def save_session_memory(memory):
    ensure_memory_dir()

    with open(MEMORY_FILE, "w") as f:
        json.dump(memory, f, indent=2)