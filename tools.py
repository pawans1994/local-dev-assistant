import os

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