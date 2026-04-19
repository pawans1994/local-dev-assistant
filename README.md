# Local Dev Assistant

A fully offline coding copilot that runs against any local repository using a self-hosted Ollama model. Wraps an interactive REPL around a retrieval-augmented generation (RAG) pipeline so the model can read files, search code semantically, run commands, edit files, and check git state — all without touching the cloud.

> **Stack**
> - LLM: `qwen2.5:7b` via Ollama (`http://localhost:11434/api/chat`)
> - Embeddings: `sentence-transformers/all-MiniLM-L6-v2` → `code_index.json`
> - Tools: file read/write, keyword + semantic search, shell commands, git
> - Observability: per-session JSON traces + persistent Q&A memory

## Getting started

### Quick run
```bash
./run.sh                          # index + chat in current directory
./run.sh ~/workspace/my-project   # index + chat in any repo
```

### Manual setup
1. **Prerequisites**
   - Python 3.10+
   - [Ollama](https://ollama.ai/) with a model pulled: `ollama pull qwen2.5:7b`

2. **Install dependencies**
   ```bash
   cd local-dev-assistant
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Build the semantic index**
   ```bash
   python build_index.py --path /path/to/your/repo
   ```
   Auto-discovers all `.py` files (skips `.venv`, `__pycache__`, `.git`, `node_modules`, etc.) and writes embeddings to `code_index.json` inside the repo.

4. **Run the assistant**
   ```bash
   python chat.py --repo /path/to/your/repo --model qwen2.5:7b
   ```

## CLI flags

| Flag | Default | Description |
|---|---|---|
| `--repo` | `.` | Path to the repository to analyze |
| `--model` | `qwen2.5:7b` | Ollama model to use |

## Slash commands

Type these at the `You:` prompt:

| Command | Description |
|---|---|
| `/help` | Show all commands |
| `/clear` | Clear conversation history (keeps system prompt) |
| `/memory` | Show saved Q&A memory from past sessions |
| `/reindex` | Rebuild the semantic code index in-place |
| `/history` | Show the current conversation history |
| `/files` | List all files currently indexed |
| `/model <name>` | Switch Ollama model mid-session |

## Available tools

The LLM has access to these tools:

### Read
- `list_files(path)` — list directory contents
- `list_entries(path)` — list with metadata (name, is_dir, size_bytes)
- `read_file(path)` — read entire file
- `read_file_chunk(path, start_line, end_line)` — read exact line range

### Search
- `search_codebase(query)` — keyword search over Python files
- `semantic_search_codebase(query, top_k=3)` — semantic search over indexed chunks

### Write & Execute
- `edit_file(path, new_content)` — write or create a file (shows a unified diff, requires `y` confirmation before writing)
- `run_command(command, cwd=".", timeout=30)` — run a shell command and capture stdout/stderr

### Git
- `git_status(path=".")` — show git status
- `git_diff(path=".", file=null)` — show git diff

## Memory & observability

- **Session memory** — every Q&A pair is saved to `memory/session_memory.json`. The last 5 are injected into the system prompt on startup so the assistant remembers prior context across restarts.
- **Traces** — each REPL session writes a timestamped JSON file to `traces/` logging every `user_input`, `tool_call`, `tool_result`, `final_answer`, and repair attempt.

## Repository layout

```
local-dev-assistant/
├── chat.py               # REPL loop: colors, streaming, memory, slash commands
├── build_index.py        # Auto-discovers .py files, embeds chunks, writes code_index.json
├── semantic_search.py    # Standalone semantic search query tool
├── tools.py              # All tool implementations (read, search, edit, run, git)
├── run.sh                # Convenience script: rebuild index + launch assistant
├── requirements.txt      # Python dependencies
├── prompts/
│   └── system.md         # System prompt + tool-calling protocol
├── helpers/
│   ├── dirs.py           # Ensures memory/ and traces/ directories exist
│   ├── memory.py         # Load/save/append session memory (JSON)
│   └── tracing.py        # Per-session event tracing to JSON files
├── memory/               # Persisted Q&A memory (gitignored)
├── traces/               # Run-by-run trace dumps (gitignored)
└── code_index.json       # Generated embeddings (gitignored once large)
```

## Tool-calling protocol

Every tool call from the LLM must be a single JSON object:
```json
{"action": "tool_name", "args": {"param": "value"}}
```
- Codebase questions always start with `semantic_search_codebase`, then optionally `read_file_chunk`
- The assistant may not fabricate code outside retrieved snippets
- Malformed tool calls are repaired up to 2 times before giving up
- Duplicate tool calls (same action + args) are blocked and the model is nudged to answer
