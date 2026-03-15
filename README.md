# Local Dev Assistant

A small, fully offline coding copilot that runs against your local repository and a self-hosted Ollama model. It wraps an interactive REPL around a retrieval pipeline so the model can:

- read files, list directories, and pull targeted snippets
- run keyword + semantic search over the codebase
- issue follow-up tool calls until it has enough context to answer
- log every step for later debugging and capture short-term memory between runs

> **Stack highlights**
> - LLM: `qwen2.5:7b` served by Ollama (`http://localhost:11434/api/chat`)
> - Retrieval: `sentence-transformers/all-MiniLM-L6-v2` for embeddings, stored in `code_index.json`
> - Tool layer: Python helpers in `tools.py` (list/read files, keyword search, semantic search, line-range reads)
> - Observability: JSON traces per session under `traces/`, lightweight memory under `memory/`

## Getting started

### Prerequisites
- Python 3.10+ (project currently runs on 3.14 via venv)
- [Ollama](https://ollama.ai/) with the `qwen2.5:7b` model pulled locally (`ollama pull qwen2.5:7b`)
- Build tools for `sentence-transformers` (Mac/Linux: `clang`/`gcc` + `rust` already covered by pip wheels)

### Install dependencies
```bash
cd local-dev-assistant
python3 -m venv .venv
source .venv/bin/activate
pip install requests sentence-transformers numpy
```

### Build the semantic index
`build_index.py` slices the selected Python files (currently `chat.py`) into overlapping chunks, embeds them, and writes the vectors to `code_index.json`.

```bash
python build_index.py
```

If you add more files, update `INDEX_FILES` inside `build_index.py` before rebuilding.

### Run the assistant
```bash
python chat.py
```
You will see a REPL prompt. Type your question, and the agent will:
1. append your message + the system prompt to its conversation buffer
2. call `semantic_search_codebase` (mandatory for any code question)
3. optionally expand the retrieved snippets with `read_file_chunk`
4. decide whether it already has enough context or needs another tool call
5. stream the final answer once it is confident or hit the step limit (default 8)

Type `exit` or `quit` to leave the loop.

## Repository layout
```
local-dev-assistant/
├── chat.py                  # REPL + tool-execution loop
├── build_index.py           # creates semantic embeddings for selected files
├── semantic_search.py       # standalone script to query the index
├── tools.py                 # concrete tool implementations called by the LLM
├── prompts/system.md        # system prompt + tool-calling protocol
├── helpers/
│   ├── tracing.py           # appends structured events per run
│   └── dirs.py              # ensures memory/trace directories exist
├── memory/                  # persisted short-term memory (JSON list)
├── traces/                  # run-by-run trace dumps
└── code_index.json          # generated embedding store (gitignored once large)
```

## Tool-calling protocol (from `prompts/system.md`)
- Every tool call must be a single JSON object: `{"action":"tool_name","args":{...}}`
- Only the listed tools are available: `list_files`, `read_file`, `list_entries`, `search_codebase`, `semantic_search_codebase`, `read_file_chunk`
- Codebase questions must start with `semantic_search_codebase`, then optionally `read_file_chunk`
- The assistant may not fabricate code outside retrieved snippets; if retrieval is insufficient it should say so.

## Observability & memory
- `helpers/tracing.py` records events like `user_input`, `assistant_response`, `tool_call`, `tool_result`, etc. Each REPL session produces a new JSON file under `traces/`.
- `memory/session_memory.json` is a simple list you can use to persist Q&A pairs or other conversational context between runs.

## Future ideas
- Expand `INDEX_FILES` + add auto-discovery to cover entire repositories.
- Ship a `requirements.txt` / Poetry lock for repeatable installs.
- Add more tools (run tests, parse logs, edit files) with corresponding safety rails.
- Introduce evaluation scripts for tool-response validity.

PRs welcome!