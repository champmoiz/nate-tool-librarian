"""
nate-server.py -- Nate's Flask API server (fully local).

Uses Ollama's structured output (JSON schema with enum) so the model
CANNOT name a tool that isn't in the retrieved library.
"""

import json
import random
import re
import sys
from pathlib import Path

_missing = []
try:
    import chromadb
    from chromadb.config import Settings
except ImportError:
    _missing.append("chromadb")
try:
    import requests
except ImportError:
    _missing.append("requests")
try:
    from flask import Flask, Response, jsonify, request, stream_with_context
except ImportError:
    _missing.append("flask")
try:
    from flask_cors import CORS
except ImportError:
    _missing.append("flask-cors")

if _missing:
    print("[ERROR] Missing Python dependencies: " + ", ".join(_missing))
    print("        pip install " + " ".join(_missing))
    sys.exit(1)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CHROMA_DB_PATH       = r"D:\Nate\server\chroma_db"
COLLECTION_NAME      = "nate_tools"
OLLAMA_CHAT_URL      = "http://localhost:11434/api/chat"
OLLAMA_CHAT_MODEL    = "llama3.1:8b"
OLLAMA_EMBED_URL     = "http://localhost:11434/api/embeddings"
EMBED_MODEL          = "nomic-embed-text"
MAX_TOOLS_IN_CONTEXT = 8
TOOLS_BLOCK_HEADER   = "RELEVANT TOOLS FROM YOUR LIBRARY:"

PERSONALITY_FILE     = Path(r"D:\Nate\personality\nate-system-prompt.txt")
HUMOR_FILE           = Path(r"D:\Nate\personality\humor-pool.txt")
TOOLS_FILE           = Path(r"D:\Nate\tools\tools.txt")

HINTS_PER_RESPONSE   = 3
JOKE_PROBABILITY     = 0.5
CHAT_TEMPERATURE     = 0.4
STREAM_CHUNK_SIZE    = 25

FALLBACK_PROMPT = (
    "You are Nate, a local AI tool librarian. Be honest and in character."
)

OPENERS = [
    "Alright bud, here's the deal.",
    "Okay, so -- quick scan of the library.",
    "Right. Let me pull from the shelf.",
    "Got it. Here's what fits.",
    "Alright, so -- this is what I've got.",
    "Okay, look -- here's what's in the library.",
    "Yeah, I've got a few that work here.",
    "Straight answer first.",
]

CLOSERS = [
    "That's what I've got. Want me to dig deeper on any of them?",
    "Any of those catch your eye?",
    "Let me know if you want more detail on one.",
    "That's the shortlist. Say the word and I'll go deeper.",
    "Your call, bud. Any of those fit?",
    "Want me to walk through any of them?",
    "",
    "",
]

NOTHING_FITS = [
    "Hmm. Nothing in my library really fits that, bud. Want me to help you find something to add?",
    "Looked through the library -- nothing matches what you're describing. Want me to search for something new?",
    "Yeah, I've got nothing in the library for that one. Want me to help you add something?",
    "Nothing on the shelf for that, bud. Tell me more and I'll see if we can find something to add.",
]


# ---------------------------------------------------------------------------
# Load personality, humor, whitelist
# ---------------------------------------------------------------------------
def load_personality() -> str:
    try:
        text = PERSONALITY_FILE.read_text(encoding="utf-8").strip()
        if len(text) < 100:
            return FALLBACK_PROMPT
        print(f"[OK] Personality loaded: {len(text)} chars from {PERSONALITY_FILE.name}")
        return text
    except FileNotFoundError:
        print(f"[WARN] Personality file not found: {PERSONALITY_FILE}")
        return FALLBACK_PROMPT
    except Exception as exc:
        print(f"[WARN] Could not read personality file: {exc}")
        return FALLBACK_PROMPT


def load_humor_pool() -> tuple[list[str], list[str]]:
    hints, jokes = [], []
    mode = None
    try:
        raw = HUMOR_FILE.read_text(encoding="utf-8")
    except FileNotFoundError:
        print(f"[WARN] Humor file not found: {HUMOR_FILE}")
        return [], []
    except Exception as exc:
        print(f"[WARN] Could not read humor file: {exc}")
        return [], []

    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("==="):
            upper = stripped.upper()
            if "STYLE HINTS" in upper:
                mode = "hints"
            elif "JOKES" in upper:
                mode = "jokes"
            continue
        if stripped.startswith("#"):
            continue
        if stripped.startswith("- ") and mode:
            item = stripped[2:].strip()
            if not item:
                continue
            (hints if mode == "hints" else jokes).append(item)

    print(f"[OK] Humor pool loaded: {len(hints)} hints, {len(jokes)} jokes")
    return hints, jokes


_ALL_TOOL_NAMES: set[str] = set()


def load_tool_whitelist():
    global _ALL_TOOL_NAMES
    try:
        raw = TOOLS_FILE.read_text(encoding="utf-8")
    except FileNotFoundError:
        print(f"[WARN] tools.txt not found at {TOOLS_FILE}")
        return
    names = set()
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) >= 1:
            names.add(parts[0].lower())
    _ALL_TOOL_NAMES = names
    print(f"[OK] Tool whitelist loaded: {len(names)} names")


SYSTEM_PROMPT = load_personality()
HUMOR_HINTS, HUMOR_JOKES = load_humor_pool()
load_tool_whitelist()


def build_humor_block() -> str:
    if not HUMOR_HINTS and not HUMOR_JOKES:
        return ""
    picked = random.sample(HUMOR_HINTS, min(HINTS_PER_RESPONSE, len(HUMOR_HINTS))) if HUMOR_HINTS else []
    lines = ["HUMOR AMMUNITION (optional -- use only if it lands naturally):"]
    for h in picked:
        lines.append(f"- {h}")
    if HUMOR_JOKES and random.random() < JOKE_PROBABILITY:
        lines.append(f"- Optional joke, only if it truly fits: {random.choice(HUMOR_JOKES)}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Embedding function
# ---------------------------------------------------------------------------
class OllamaEmbeddingFunction:
    def __init__(self, model: str = EMBED_MODEL, url: str = OLLAMA_EMBED_URL):
        self.model = model
        self.url = url

    def name(self) -> str:
        return "ollama_nomic_embed"

    def embed_documents(self, input):
        return self.__call__(input)

    def embed_query(self, input):
        return self.__call__(input)

    def __call__(self, input: list[str]) -> list[list[float]]:
        vectors = []
        for text in input:
            try:
                r = requests.post(self.url, json={"model": self.model, "prompt": text}, timeout=60)
            except requests.exceptions.ConnectionError:
                raise RuntimeError(f"\n[ERROR] Could not reach Ollama at {self.url}\n"
                                   f"        Start Ollama and run: ollama pull {self.model}\n")
            except requests.exceptions.Timeout:
                raise RuntimeError(f"\n[ERROR] Timed out talking to Ollama at {self.url}\n")
            if r.status_code != 200:
                raise RuntimeError(f"\n[ERROR] Ollama HTTP {r.status_code}: {r.text[:200]}\n")
            emb = r.json().get("embedding")
            if not emb:
                raise RuntimeError(f"\n[ERROR] No embedding from Ollama. Raw: {r.text[:200]}\n")
            vectors.append(list(emb))
        return vectors


# ---------------------------------------------------------------------------
# Flask app + ChromaDB
# ---------------------------------------------------------------------------
app = Flask(__name__)
CORS(app)

_chroma_client = chromadb.PersistentClient(
    path=CHROMA_DB_PATH,
    settings=Settings(anonymized_telemetry=False),
)
_embedding_fn = OllamaEmbeddingFunction()


def get_collection():
    return _chroma_client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=_embedding_fn,
    )


def error_response(message: str, status: int) -> Response:
    return Response(json.dumps({"error": message}) + "\n", status=status,
                    mimetype="application/json")


# ---------------------------------------------------------------------------
# Add-tool / describe commands
# ---------------------------------------------------------------------------
ADD_HELP = (
    "Format that, bud:\n"
    "  add tool name\n"
    "  add tool: name | category | type | pricing | verified | description\n"
    "Types: repo, website, app, saas, list, skill, model, unknown\n"
    "Pricing: free, freemium, paid, open, unknown"
)


def _upsert_tool(name, category, ttype, pricing, verified, description):
    get_collection().upsert(
        ids=[name.lower()],
        documents=[f"{name.lower()} ({category}, {ttype}, {pricing}): {description}"],
        metadatas=[{
            "category": category, "type": ttype, "pricing": pricing,
            "verified": verified, "description": description,
        }],
    )


def handle_add_tool_command(text: str):
    if not text:
        return None
    lowered = text.lower().strip()
    if lowered.startswith("nate "):
        lowered = lowered[5:].strip()
        original = text.strip()[5:].strip()
    else:
        original = text.strip()
    if not lowered.startswith("add tool"):
        return None

    payload = original[len("add tool"):].strip()
    if payload.startswith(":"):
        payload = payload[1:].strip()
    if not payload:
        return ADD_HELP

    if "|" not in payload:
        name = payload.strip().lower()
        if not name or " " in name:
            return ("Hmm, that doesn't look like a single tool name, bud. "
                    "Try: add tool wireflow  OR  add tool: name | category | type | pricing | verified | description")
        try:
            _upsert_tool(name, "Unknown", "unknown", "unknown", False,
                         "Added via chat -- needs research")
            _ALL_TOOL_NAMES.add(name)
        except Exception as exc:
            return f"Couldn't add that one, bud: {exc}"
        return (f"Added {name} to your library, bud. Marked unverified with "
                f"no details yet -- want to give me more info? Say something like:\n"
                f"  describe {name}: <what it does>")

    parts = [p.strip() for p in payload.split("|")]
    if len(parts) != 6:
        return ADD_HELP
    name, category, ttype, pricing, status, description = parts
    if not name or not description:
        return ADD_HELP
    verified = status.lower() in ("verified", "true", "yes", "1")
    try:
        _upsert_tool(name, category or "Unknown",
                     (ttype or "unknown").lower(),
                     (pricing or "unknown").lower(),
                     verified, description)
        _ALL_TOOL_NAMES.add(name.lower())
    except Exception as exc:
        return f"Couldn't add that one, bud: {exc}"
    return f"Added {name.lower()} to your library, bud. {category}, {ttype}, {pricing}. Got it."


def handle_describe_command(text: str):
    if not text:
        return None
    m = re.match(r"^(?:nate\s+)?describe\s+([^\s:]+)\s*:\s*(.+)$",
                 text.strip(), re.IGNORECASE | re.DOTALL)
    if not m:
        return None
    name = m.group(1).strip().lower()
    new_desc = m.group(2).strip()
    if not new_desc:
        return "Give me something to describe it with, bud. Format: describe <name>: <text>"

    col = get_collection()
    existing = col.get(ids=[name], include=["metadatas"])
    if not existing["ids"]:
        return f"Don't have '{name}' in the library yet. Add it first: add tool {name}"
    meta = (existing["metadatas"] or [{}])[0] or {}
    try:
        _upsert_tool(name, meta.get("category", "Unknown"),
                     meta.get("type", "unknown"),
                     meta.get("pricing", "unknown"),
                     bool(meta.get("verified", False)), new_desc)
    except Exception as exc:
        return f"Couldn't update that one, bud: {exc}"
    return f"Got it -- updated the description for {name}."


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------
def retrieve_tools(query: str) -> list[dict]:
    collection = get_collection()
    count = collection.count()
    if count == 0:
        return []
    n = min(MAX_TOOLS_IN_CONTEXT, count)
    result = collection.query(query_texts=[query], n_results=n)

    ids = (result.get("ids") or [[]])[0]
    metas = (result.get("metadatas") or [[]])[0]

    tools = []
    for tool_id, meta in zip(ids, metas):
        meta = meta or {}
        tools.append({
            "name": tool_id,
            "category": meta.get("category", ""),
            "type": meta.get("type", "unknown"),
            "pricing": meta.get("pricing", "unknown"),
            "verified": bool(meta.get("verified", False)),
            "description": meta.get("description", ""),
        })
    return tools


def build_schema(tool_names: list[str]) -> dict:
    return {
        "type": "object",
        "properties": {
            "picks": {
                "type": "array",
                "maxItems": 4,
                "items": {
                    "type": "object",
                    "properties": {
                        "tool": {"type": "string", "enum": tool_names},
                        "why": {"type": "string", "maxLength": 180},
                    },
                    "required": ["tool", "why"],
                },
            },
            "diagram": {"type": "string", "maxLength": 250},
        },
        "required": ["picks"],
    }


def build_enriched_user_message(user_msg: str, tools: list[dict]) -> str:
    lines = [
        "The user asked:",
        user_msg,
        "",
        "Available tools in the library:",
    ]
    for t in tools:
        lines.append(f"- {t['name']} ({t['category']}, {t['type']}, {t['pricing']}, "
                     f"{'verified' if t['verified'] else 'unverified'}): {t['description']}")
    lines.append("")
    lines.append(
        "Pick up to 4 tools from the list above that best help with the user's request. "
        "For each pick, write ONE short sentence (under 25 words) explaining why it fits. "
        "You MUST only use tool names from the list above -- never any other name. "
        "If none of the tools fit the request, return an empty picks array. "
                "If the user's request is about HOW to build or connect things (starts with 'how do I', "
        "'how do I build', 'what's the flow', 'how do I connect', or similar), you MUST fill the "
        "diagram field with a simple linear flow like 'Mic → STT → LLM → TTS → Speaker'. "
        "Use arrows only. No boxes. If the request is NOT about how to build something, leave diagram empty."
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------
def render_picks_response(picks: list[dict], tool_lookup: dict, diagram: str) -> str:
    parts = []
    parts.append(random.choice(OPENERS))
    parts.append("")
    for p in picks:
        tname = p["tool"]
        why = p["why"].strip()
        meta = tool_lookup.get(tname, {})
        cat = meta.get("category", "")
        ttype = meta.get("type", "unknown")
        pricing = meta.get("pricing", "unknown")
        flag = "verified" if meta.get("verified") else "unverified"
        parts.append(f"- {tname} ({cat}, {ttype}, {pricing}, {flag}): {why}")
    if diagram:
        parts.append("")
        parts.append("Flow:")
        parts.append(f"  {diagram.strip()}")
    closer = random.choice(CLOSERS)
    if closer:
        parts.append("")
        parts.append(closer)
    return "\n".join(parts)


def render_nothing_fits() -> str:
    return random.choice(NOTHING_FITS)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route("/health", methods=["GET"])
def health():
    try:
        count = get_collection().count()
    except Exception as exc:
        return jsonify({"status": "error", "error": str(exc)}), 500
    return jsonify({
        "status": "ok",
        "tools_stored": count,
        "whitelist_size": len(_ALL_TOOL_NAMES),
        "humor_hints": len(HUMOR_HINTS),
        "humor_jokes": len(HUMOR_JOKES),
        "personality_chars": len(SYSTEM_PROMPT),
    })


@app.route("/tools/list", methods=["GET"])
def tools_list():
    try:
        result = get_collection().get(include=["metadatas"])
    except Exception as exc:
        return error_response(f"Failed to read ChromaDB: {exc}", 500)
    tools = []
    for tool_id, meta in zip(result["ids"], result["metadatas"]):
        meta = meta or {}
        tools.append({
            "name": tool_id,
            "category": meta.get("category", ""),
            "type": meta.get("type", "unknown"),
            "pricing": meta.get("pricing", "unknown"),
            "verified": bool(meta.get("verified", False)),
            "description": meta.get("description", ""),
        })
    return jsonify(tools)


@app.route("/tools/add", methods=["POST"])
def tools_add():
    data = request.get_json(force=True, silent=True)
    if not isinstance(data, dict):
        return error_response("Request body must be a JSON object.", 400)
    name        = (data.get("name") or "").strip()
    category    = (data.get("category") or "Unknown").strip()
    ttype       = (data.get("type") or "unknown").strip().lower()
    pricing     = (data.get("pricing") or "unknown").strip().lower()
    description = (data.get("description") or "").strip()
    verified    = bool(data.get("verified", False))
    if not name or not description:
        return error_response("Both 'name' and 'description' are required.", 400)
    try:
        _upsert_tool(name, category, ttype, pricing, verified, description)
        _ALL_TOOL_NAMES.add(name.lower())
    except RuntimeError as exc:
        return error_response(str(exc).strip(), 502)
    except Exception as exc:
        return error_response(f"Failed to upsert into ChromaDB: {exc}", 500)
    return jsonify({"status": "ok", "name": name.lower()})


@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json(force=True, silent=True)
    if not isinstance(data, dict):
        return error_response("Request body must be a JSON object.", 400)

    messages = data.get("messages") or []
    stream = bool(data.get("stream", True))

    last_user = None
    for msg in reversed(messages):
        if isinstance(msg, dict) and msg.get("role") == "user":
            last_user = (msg.get("content") or "").strip()
            break
    if not last_user:
        return error_response("No user message found in 'messages'.", 400)

    # --- Chat commands ---
    try:
        cmd_reply = handle_add_tool_command(last_user) or handle_describe_command(last_user)
    except Exception as exc:
        cmd_reply = f"Something went wrong with that command, bud: {exc}"

    if cmd_reply is not None:
        def generate_cmd():
            yield json.dumps({"message": {"content": cmd_reply}}) + "\n"
        return Response(stream_with_context(generate_cmd()),
                        mimetype="application/x-ndjson")

    # --- Retrieve tools ---
    try:
        tools = retrieve_tools(last_user)
    except RuntimeError as exc:
        return error_response(str(exc).strip(), 502)
    except Exception as exc:
        import traceback; traceback.print_exc()
        return error_response(f"Tool retrieval failed: {exc}", 500)

    if not tools:
        def generate_empty():
            msg = "My library's empty right now, bud. Add a tool first: add tool <name>"
            yield json.dumps({"message": {"content": msg}}) + "\n"
        return Response(stream_with_context(generate_empty()),
                        mimetype="application/x-ndjson")

    tool_names = [t["name"] for t in tools]
    tool_lookup = {t["name"]: t for t in tools}
    schema = build_schema(tool_names)
    enriched = build_enriched_user_message(last_user, tools)

    parts = [SYSTEM_PROMPT]
    humor = build_humor_block()
    if humor:
        parts.append(humor)
    full_system = "\n\n".join(parts)

    history = [m for m in messages[:-1] if isinstance(m, dict)]
    ollama_messages = [{"role": "system", "content": full_system}]
    ollama_messages.extend(history)
    ollama_messages.append({"role": "user", "content": enriched})

    ollama_payload = {
        "model": OLLAMA_CHAT_MODEL,
        "messages": ollama_messages,
        "stream": False,
        "format": schema,
        "options": {"temperature": CHAT_TEMPERATURE},
    }

    try:
        ollama_resp = requests.post(OLLAMA_CHAT_URL, json=ollama_payload, timeout=120)
    except requests.exceptions.ConnectionError:
        return error_response(
            "Cannot reach Ollama at http://localhost:11434. Start Ollama and try again.", 502
        )
    except requests.exceptions.Timeout:
        return error_response("Timed out connecting to Ollama.", 504)

    if ollama_resp.status_code != 200:
        detail = ollama_resp.text[:300].replace("\n", " ").strip()
        return error_response(f"Ollama returned HTTP {ollama_resp.status_code}: {detail}",
                              ollama_resp.status_code)

    # --- Parse ---
    try:
        body = ollama_resp.json()
        raw_content = (body.get("message") or {}).get("content", "") or "{}"
        print(f"[DEBUG] Ollama raw: {raw_content[:400]}")
        parsed = json.loads(raw_content)
    except Exception as exc:
        print(f"[WARN] Failed to parse Ollama JSON: {exc}")
        parsed = {"picks": []}

    picks = parsed.get("picks") or []
    diagram = parsed.get("diagram", "") or ""

    picks = [p for p in picks if isinstance(p, dict)
             and p.get("tool") in tool_lookup
             and isinstance(p.get("why"), str)]

    if picks:
        final_text = render_picks_response(picks, tool_lookup, diagram)
    else:
        final_text = render_nothing_fits()

    def generate():
        for i in range(0, len(final_text), STREAM_CHUNK_SIZE):
            piece = final_text[i:i + STREAM_CHUNK_SIZE]
            yield json.dumps({"message": {"content": piece}}) + "\n"

    if not stream:
        return jsonify({"message": {"content": final_text}})

    return Response(
        stream_with_context(generate()),
        mimetype="application/x-ndjson",
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=" * 62)
    print(" Nate -- local AI tool librarian")
    print(" API    : http://localhost:5000  (listening on 0.0.0.0:5000)")
    print(" Model  : llama3.1:8b via Ollama (structured output mode)")
    print(" Temp   : " + str(CHAT_TEMPERATURE))
    print(" DB     : ChromaDB at " + CHROMA_DB_PATH)
    print("=" * 62)
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)