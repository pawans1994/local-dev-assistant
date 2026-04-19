import json
import os

ASSISTANT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEMORY_FILE = os.path.join(ASSISTANT_DIR, "memory", "session_memory.json")


def load_session_memory() -> list:
    os.makedirs(os.path.dirname(MEMORY_FILE), exist_ok=True)
    if not os.path.exists(MEMORY_FILE):
        return []
    with open(MEMORY_FILE, "r") as f:
        try:
            return json.load(f)
        except (json.JSONDecodeError, IOError):
            return []


def save_session_memory(memory: list):
    os.makedirs(os.path.dirname(MEMORY_FILE), exist_ok=True)
    with open(MEMORY_FILE, "w") as f:
        json.dump(memory, f, indent=2)


def add_to_memory(query: str, answer: str):
    memory = load_session_memory()
    memory.append({"query": query, "answer": answer})
    save_session_memory(memory[-20:])
