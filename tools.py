import os
import json
import subprocess
import difflib
import numpy as np
from sentence_transformers import SentenceTransformer

INDEX_FILE = "code_index.json"
EMBED_MODEL_NAME = "all-MiniLM-L6-v2"

_embedding_model = None


def get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        _embedding_model = SentenceTransformer(EMBED_MODEL_NAME)
    return _embedding_model


def cosine_similarity(a, b):
    a = np.array(a)
    b = np.array(b)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def _keyword_bonus(query: str, text: str) -> float:
    q = query.lower()
    t = text.lower()
    bonus = 0.0
    if "execute" in q or "tool" in q:
        if "try_execute_tool" in t: bonus += 0.10
        if "tool_result" in t: bonus += 0.08
        if '"role": "tool"' in t: bonus += 0.08
        if "for _ in range(max_steps)" in t: bonus += 0.08
    if "conversation" in q or "messages" in q:
        if "messages.append" in t: bonus += 0.08
        if "messages =" in t: bonus += 0.05
    if "model call" in q or "ollama" in q:
        if "requests.post" in t: bonus += 0.10
        if "def chat(messages)" in t: bonus += 0.08
        if "payload =" in t: bonus += 0.05
    return bonus


# ── Search ─────────────────────────────────────────────────────────────────

def semantic_search_codebase(query: str, top_k: int = 3):
    if not os.path.exists(INDEX_FILE):
        return [{"error": "No index found. Run build_index.py or use /reindex."}]
    with open(INDEX_FILE, "r") as f:
        index = json.load(f)

    model = get_embedding_model()
    query_emb = model.encode(query).tolist()

    scored = []
    for item in index:
        score = cosine_similarity(query_emb, item["embedding"])
        score += _keyword_bonus(query, item["text"])
        scored.append((score, item))

    scored.sort(key=lambda x: x[0], reverse=True)

    return [
        {
            "file": item["file"],
            "start_line": item["start_line"],
            "end_line": item["end_line"],
            "score": round(score, 4),
            "text": item["text"],
        }
        for score, item in scored[:top_k]
    ]


def search_codebase(query: str, root: str = "."):
    results = []
    query_words = [w.lower() for w in query.split() if len(w) > 2]
    skip_dirs = {".venv", "venv", "__pycache__", ".git", "node_modules"}

    try:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in skip_dirs]
            for fname in filenames:
                if not fname.endswith(".py"):
                    continue
                full = os.path.join(dirpath, fname)
                rel = os.path.relpath(full, root)
                try:
                    with open(full, "r", errors="ignore") as f:
                        lines = f.readlines()
                except Exception:
                    continue
                for i, line in enumerate(lines):
                    ll = line.lower()
                    if "http://localhost" in ll or '{"action":' in ll:
                        continue
                    if any(w in ll for w in query_words):
                        start, end = max(0, i - 2), min(len(lines), i + 3)
                        results.append({
                            "file": rel,
                            "line_number": i + 1,
                            "snippet": "".join(lines[start:end]),
                        })
        return results if results else [{"message": "No matches found"}]
    except Exception as e:
        return {"error": str(e)}


# ── Read ───────────────────────────────────────────────────────────────────

def list_files(path: str = "."):
    try:
        return "\n".join(sorted(os.listdir(path)))
    except Exception as e:
        return f"Error: {e}"


def list_entries(path: str = "."):
    try:
        out = []
        for name in sorted(os.listdir(path)):
            full = os.path.join(path, name)
            out.append({
                "name": name,
                "is_dir": os.path.isdir(full),
                "size_bytes": os.path.getsize(full) if os.path.isfile(full) else None,
            })
        return out
    except Exception as e:
        return {"error": str(e)}


def read_file(path: str):
    try:
        with open(path, "r", errors="ignore") as f:
            return f.read()
    except Exception as e:
        return f"Error: {e}"


def read_file_chunk(path: str, start_line: int, end_line: int):
    try:
        start_line, end_line = int(start_line), int(end_line)
        if start_line < 1:
            start_line = 1
        if end_line < start_line:
            return {"error": "end_line must be >= start_line"}
        with open(path, "r", errors="ignore") as f:
            lines = f.readlines()
        total = len(lines)
        if start_line > total:
            return {"error": f"start_line {start_line} beyond file length {total}"}
        end_line = min(end_line, total)
        return {
            "file": path,
            "start_line": start_line,
            "end_line": end_line,
            "text": "".join(lines[start_line - 1:end_line]),
        }
    except Exception as e:
        return {"error": str(e)}


# ── Write ──────────────────────────────────────────────────────────────────

def edit_file(path: str, new_content: str):
    """Write new_content to path. Shows a unified diff and asks for confirmation."""
    old_content = ""
    if os.path.exists(path):
        try:
            with open(path, "r", errors="ignore") as f:
                old_content = f.read()
        except Exception as e:
            return {"error": f"Could not read existing file: {e}"}

    if old_content == new_content:
        return {"status": "no_changes", "path": path}

    if old_content:
        diff_lines = list(difflib.unified_diff(
            old_content.splitlines(keepends=True),
            new_content.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            n=3,
        ))
        if diff_lines:
            print("\n" + "".join(diff_lines))

    action_label = "Create" if not old_content else "Update"
    try:
        confirm = input(f"\n{action_label} {path}? [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return {"status": "cancelled", "path": path}

    if confirm != "y":
        return {"status": "cancelled", "path": path}

    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    with open(path, "w") as f:
        f.write(new_content)
    return {"status": "success", "path": path, "bytes_written": len(new_content)}


# ── Shell ──────────────────────────────────────────────────────────────────

def run_command(command: str, cwd: str = ".", timeout: int = 30):
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=int(timeout),
        )
        return {
            "command": command,
            "returncode": result.returncode,
            "stdout": result.stdout[-4000:],
            "stderr": result.stderr[-1000:],
        }
    except subprocess.TimeoutExpired:
        return {"error": f"Timed out after {timeout}s"}
    except Exception as e:
        return {"error": str(e)}


# ── Git ────────────────────────────────────────────────────────────────────

def git_status(path: str = "."):
    return run_command("git status --short --branch", cwd=path)


def git_diff(path: str = ".", file: str = None):
    cmd = f"git diff -- {file}" if file else "git diff"
    return run_command(cmd, cwd=path)
