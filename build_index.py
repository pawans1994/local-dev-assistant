import os
import json
from sentence_transformers import SentenceTransformer

MODEL_NAME = "all-MiniLM-L6-v2"
ROOT_DIR = "."
OUTPUT_FILE = "code_index.json"

INDEX_FILES = {"chat.py", "tools.py"}

model = SentenceTransformer(MODEL_NAME)

SKIP_MARKERS = [
    "Using only the retrieved snippets above",
    "Prefer actual loop/control-flow code over examples",
]

def is_mostly_imports(text: str) -> bool:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return True

    import_lines = sum(
        1 for line in lines
        if line.startswith("import ") or line.startswith("from ")
    )
    return import_lines / len(lines) > 0.4

def should_skip_chunk(text: str) -> bool:
    for marker in SKIP_MARKERS:
        if marker in text:
            return True
    return False

def chunk_lines(lines, chunk_size=30, overlap=5):
    chunks = []
    start = 0

    while start < len(lines):
        end = min(len(lines), start + chunk_size)
        chunk = "".join(lines[start:end])

        chunks.append({
            "start_line": start + 1,
            "end_line": end,
            "text": chunk
        })

        if end == len(lines):
            break

        start += chunk_size - overlap

    return chunks


def build_index():
    index = []

    for filename in os.listdir(ROOT_DIR):
        if not filename.endswith(".py") or filename not in INDEX_FILES:
            continue

        path = os.path.join(ROOT_DIR, filename)
        if not os.path.isfile(path):
            continue

        with open(path, "r") as f:
            lines = f.readlines()

        chunks = chunk_lines(lines)
        
        for chunk in chunks:
            if should_skip_chunk(chunk["text"]) or is_mostly_imports(chunk["text"]):
                continue
            
            embedding = model.encode(chunk["text"]).tolist()

            index.append({
                "file": filename,
                "start_line": chunk["start_line"],
                "end_line": chunk["end_line"],
                "text": chunk["text"],
                "embedding": embedding
            })

    with open(OUTPUT_FILE, "w") as f:
        json.dump(index, f)

    print(f"Indexed {len(index)} chunks into {OUTPUT_FILE}")


if __name__ == "__main__":
    build_index()