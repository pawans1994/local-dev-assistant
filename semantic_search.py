import json
import numpy as np
from sentence_transformers import SentenceTransformer

MODEL_NAME = "all-MiniLM-L6-v2"
INDEX_FILE = "code_index.json"

model = SentenceTransformer(MODEL_NAME)

def keyword_bonus(query: str, text: str) -> float:
    q = query.lower()
    t = text.lower()
    bonus = 0.0

    if "execute" in q or "tool" in q:
        if "try_execute_tool" in t:
            bonus += 0.10
        if "tool_result" in t:
            bonus += 0.08
        if '"role": "tool"' in t or "'role': 'tool'" in t:
            bonus += 0.08
        if "for _ in range(max_steps)" in t:
            bonus += 0.08
        if "action, tool_result" in t:
            bonus += 0.08

    if "conversation state" in q or "messages" in q:
        if "messages =" in t:
            bonus += 0.08
        if "messages.append" in t:
            bonus += 0.08

    if "model call" in q or "ollama" in q:
        if "def chat(messages)" in t:
            bonus += 0.08
        if "requests.post" in t:
            bonus += 0.10
        if "payload =" in t:
            bonus += 0.05

    return bonus


def cosine_similarity(a, b):
    a = np.array(a)
    b = np.array(b)
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))


def semantic_search(query, top_k=5):
    with open(INDEX_FILE, "r") as f:
        index = json.load(f)

    query_embedding = model.encode(query).tolist()

    scored = []
    for item in index:
        score = cosine_similarity(query_embedding, item["embedding"])
        score += keyword_bonus(query, item["text"])
        scored.append((score, item))

    scored.sort(key=lambda x: x[0], reverse=True)

    results = []
    for score, item in scored[:top_k]:
        results.append({
            "file": item["file"],
            "start_line": item["start_line"],
            "end_line": item["end_line"],
            "score": round(float(score), 4),
            "text": item["text"]
        })

    return results


if __name__ == "__main__":
    query = input("Query: ").strip()
    results = semantic_search(query)

    for r in results:
        print("\n---")
        print(f"{r['file']}:{r['start_line']}-{r['end_line']} score={r['score']}")
        print(r["text"])