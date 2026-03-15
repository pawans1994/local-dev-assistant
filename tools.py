import os
import json
import numpy as np
from sentence_transformers import SentenceTransformer

INDEX_FILE = "code_index.json"
EMBED_MODEL_NAME = "all-MiniLM-L6-v2"

_embedding_model = None

def read_file_chunk(path, start_line, end_line):
    try:
        start_line = int(start_line)
        end_line = int(end_line)

        if start_line < 1:
            start_line = 1
        if end_line < start_line:
            return {"error": "end_line must be >= start_line"}

        with open(path, "r") as f:
            lines = f.readlines()

        total_lines = len(lines)
        if start_line > total_lines:
            return {"error": f"start_line {start_line} is beyond file length {total_lines}"}

        end_line = min(end_line, total_lines)

        chunk_lines = lines[start_line - 1:end_line]
        text = "".join(chunk_lines)

        return {
            "file": path,
            "start_line": start_line,
            "end_line": end_line,
            "text": text
        }

    except Exception as e:
        return {"error": str(e)}

def get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        _embedding_model = SentenceTransformer(EMBED_MODEL_NAME)
    return _embedding_model


def cosine_similarity(a, b):
    a = np.array(a)
    b = np.array(b)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def semantic_search_codebase(query, top_k=3):
    with open(INDEX_FILE, "r") as f:
        index = json.load(f)

    model = get_embedding_model()
    query_embedding = model.encode(query).tolist()

    scored = []
    for item in index:
        score = cosine_similarity(query_embedding, item["embedding"])
        scored.append((score, item))

    scored.sort(key=lambda x: x[0], reverse=True)

    results = []
    for score, item in scored[:top_k]:
        results.append({
            "file": item["file"],
            "start_line": item["start_line"],
            "end_line": item["end_line"],
            "score": round(score, 4),
            "text": item["text"]
        })

    return results

def list_files(path="."):
    try:
        return "\n".join(os.listdir(path))
    except Exception as e:
        return f"Error: {str(e)}"

def read_file(path):
    try:
        with open(path, "r") as f:
            return f.read()
    except Exception as e:
        return f"Error: {str(e)}"

def search_codebase(query, root="."):
    results = []
    query_words = [word.lower() for word in query.split() if len(word) > 2]

    try:
        for filename in os.listdir(root):
            full_path = os.path.join(root, filename)

            if not os.path.isfile(full_path):
                continue
            if not filename.endswith(".py"):
                continue

            with open(full_path, "r") as f:
                lines = f.readlines()

            for i, line in enumerate(lines):
                line_lower = line.lower()
                if "http://localhost" in line_lower:
                    continue
                if "Example valid tool calls" in line_lower:
                    continue
                if '{"action":' in line_lower:
                    continue
                if any(word in line_lower for word in query_words):
                    start = max(0, i - 2)
                    end = min(len(lines), i + 3)
                    snippet = "".join(lines[start:end])

                    results.append({
                        "file": filename,
                        "line_number": i + 1,
                        "snippet": snippet
                    })

        return results if results else [{"message": "No matches found"}]

    except Exception as e:
        return {"error": str(e)}



def list_entries(path="."):
    try:
        out = []
        for name in os.listdir(path):
            full = os.path.join(path, name)
            out.append({
                "name": name,
                "is_dir": os.path.isdir(full),
                "size_bytes": os.path.getsize(full) if os.path.isfile(full) else None
            })
        return out
    except Exception as e:
        return {"error": str(e)}