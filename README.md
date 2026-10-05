# Nate — Local AI Tool Librarian

A fully offline, private AI assistant that reads a personal library of
~240 curated tools, recommends them, and answers questions in the voice
of a cocky, witty Nathan-Drake-flavored assistant. Runs entirely on your
own hardware — no cloud APIs, no telemetry, no accounts.

## What it does

Ask Nate natural-language questions and it routes them through a
5-mode intent system (chat / recommend / howto / define / factcheck),
retrieves the most relevant tools from a local ChromaDB vector store,
and answers in character.

Example queries:
- "What tools do you have for making videos with AI?"
- "Recommend something for OSINT"
- "Is Shodan free?"
- "How do I build a voice agent?"
- "I wanna build Jarvis"

## Stack

- **LLM:** Ollama + llama3.1:8b (local)
- **Embeddings:** nomic-embed-text via Ollama
- **Vector DB:** ChromaDB (local, persistent)
- **API:** Flask on :5000
- **UI:** Single-file HTML, red/black DedSec theme

## Requirements

- Windows 10/11 (tested), Linux/macOS should work
- Python 3.10+
- Ollama installed with `llama3.1:8b` and `nomic-embed-text` pulled
- ~8 GB RAM minimum (16 GB recommended)
- GPU optional — works on CPU, faster with one

## Install

1. Clone the repo to `D:\Nate\`
2. `cd server && pip install -r requirements.txt`
3. `ollama pull llama3.1:8b && ollama pull nomic-embed-text`
4. `python load-tools.py` (embeds the tool library — 5–15 min first run)
5. `python server.py`
6. Open `nate.html` in your browser

Or: double-click `start-nate.bat`.

## Adding your own tools

Two ways:

**1. In the chat** — type:

```
add tool: my-tool | Category | repo | open | verified | Description here.
```

**2. Direct edit** — append to `tools/tools.txt` (pipe-separated,
6 or 7 fields) and re-run `python load-tools.py`.

Format:

```
name | category | type | pricing | verified/unverified | description | optional aliases
```

## Architecture

```
nate.html → /chat → router.py → retrieval.py → ChromaDB
                          ↓
                      prompts.py → Ollama (llama3.1:8b)
                          ↓
                      renderer.py → NDJSON stream → browser
```

## License

MIT — see `LICENSE` file. Fill in `[YOUR NAME]` before shipping.
