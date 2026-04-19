import os
import json
import argparse
from sentence_transformers import SentenceTransformer

MODEL_NAME = "all-MiniLM-L6-v2"
OUTPUT_FILE = "code_index.json"

SKIP_DIRS = {
    ".venv", "venv", "__pycache__", ".git", "node_modules",
    ".mypy_cache", ".pytest_cache", "dist", "build", ".eggs",
    "htmlcov", ".tox", ".cache", ".ruff_cache",
}

SKIP_MARKERS = [
    "Using only the retrieved snippets above",
    "Do not invent code",
    "If the snippets are insufficient",
    'return "try_execute_tool action tool_result max_steps"',
    'return "while True max_steps main input"',
]

_model = None


def get_model():
    global _model
    if _model is None:
        print("Loading embedding model...")
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def discover_files(root: str = ".", extensions=(".py",)) -> list[str]:
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(
            d for d in dirnames
            if d not in SKIP_DIRS and not d.startswith(".")
        )
        for fname in sorted(filenames):
            if any(fname.endswith(ext) for ext in extensions):
                rel = os.path.relpath(os.path.join(dirpath, fname), root)
                found.append(rel)
    return found


def is_mostly_imports(text: str) -> bool:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if not lines:
        return True
    import_lines = sum(
        1 for l in lines if l.startswith("import ") or l.startswith("from ")
    )
    return import_lines / len(lines) > 0.4


def should_skip_chunk(text: str) -> bool:
    return any(marker in text for marker in SKIP_MARKERS)


def chunk_lines(lines: list, chunk_size: int = 30, overlap: int = 5) -> list:
    chunks = []
    start = 0
    while start < len(lines):
        end = min(len(lines), start + chunk_size)
        chunks.append({
            "start_line": start + 1,
            "end_line": end,
            "text": "".join(lines[start:end]),
        })
        if end == len(lines):
            break
        start += chunk_size - overlap
    return chunks


def build_index(root: str = ".", output_file: str = None) -> int:
    if output_file is None:
        output_file = os.path.join(root, OUTPUT_FILE)

    files = discover_files(root)
    print(f"Discovered {len(files)} Python file(s) in {root}")

    model = get_model()
    index = []

    for rel_path in files:
        full_path = os.path.join(root, rel_path)
        try:
            with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
        except Exception as e:
            print(f"  skip {rel_path}: {e}")
            continue

        file_chunks = 0
        for chunk in chunk_lines(lines):
            if should_skip_chunk(chunk["text"]) or is_mostly_imports(chunk["text"]):
                continue
            embedding = model.encode(chunk["text"]).tolist()
            index.append({
                "file": rel_path,
                "start_line": chunk["start_line"],
                "end_line": chunk["end_line"],
                "text": chunk["text"],
                "embedding": embedding,
            })
            file_chunks += 1

        if file_chunks:
            print(f"  {rel_path}: {file_chunks} chunk(s)")

    with open(output_file, "w") as f:
        json.dump(index, f)

    print(f"\nIndexed {len(index)} chunks from {len(files)} file(s) → {output_file}")
    return len(index)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build semantic code index")
    parser.add_argument("--path", default=".", help="Root directory to index (default: .)")
    args = parser.parse_args()
    build_index(root=args.path)
