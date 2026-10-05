import json
import re
import sys

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

from schemas import (
    build_schema,
    build_recommend_schema,
    build_howto_schema,
    build_define_schema,
    build_factcheck_schema,
)
from whitelist import load_tool_whitelist, _ALL_TOOL_NAMES, TOOLS_FILE, norm, register_tool_name, sync_whitelist_from_db
from retrieval import (
    CHROMA_DB_PATH,
    COLLECTION_NAME,
    get_collection,
    retrieve_tools,
    _upsert_tool,
)
from router import handle_add_tool_command, handle_describe_command, route
from prompts import (
    SYSTEM_PROMPT, HUMOR_HINTS, HUMOR_JOKES,
    build_humor_block,
    build_recommend_prompt,
    build_howto_prompt,
    build_define_prompt,
    build_factcheck_prompt,
    CHAT_SYSTEM_PROMPT,
)
from renderer import (
    render_recommend,
    render_howto,
    render_define,
    render_factcheck,
    render_chat,
)

load_tool_whitelist()
synced = sync_whitelist_from_db(CHROMA_DB_PATH, COLLECTION_NAME)
print(f"[OK] Whitelist synced from DB: {synced} tools")

OLLAMA_CHAT_URL      = "http://localhost:11434/api/chat"
OLLAMA_CHAT_MODEL    = "llama3.1:8b"
TOOLS_BLOCK_HEADER   = "RELEVANT TOOLS FROM YOUR LIBRARY:"
STREAM_CHUNK_SIZE    = 25


app = Flask(__name__)
CORS(app)


def error_response(message: str, status: int) -> Response:
    return Response(json.dumps({"error": message}) + "\n", status=status,
                    mimetype="application/json")


def fake_stream(final_text: str):
    for i in range(0, len(final_text), STREAM_CHUNK_SIZE):
        piece = final_text[i:i + STREAM_CHUNK_SIZE]
        yield json.dumps({"message": {"content": piece}}) + "\n"


def build_system_message(include_personality: bool = True) -> str:
    if not include_personality:
        return CHAT_SYSTEM_PROMPT
    parts = [SYSTEM_PROMPT]
    humor = build_humor_block()
    if humor:
        parts.append(humor)
    return "\n\n".join(parts)


def run_structured_ollama(messages: list, schema: dict, temperature: float):
    ollama_payload = {
        "model": OLLAMA_CHAT_MODEL,
        "messages": messages,
        "stream": False,
        "format": schema,
        "options": {"temperature": temperature},
    }
    try:
        ollama_resp = requests.post(OLLAMA_CHAT_URL, json=ollama_payload, timeout=120)
    except requests.exceptions.ConnectionError:
        return None, ("Cannot reach Ollama at http://localhost:11434. Start Ollama and try again.", 502)
    except requests.exceptions.Timeout:
        return None, ("Timed out connecting to Ollama.", 504)
    if ollama_resp.status_code != 200:
        detail = ollama_resp.text[:300].replace("\n", " ").strip()
        return None, (f"Ollama returned HTTP {ollama_resp.status_code}: {detail}", ollama_resp.status_code)
    try:
        body = ollama_resp.json()
        raw_content = (body.get("message") or {}).get("content", "") or "{}"
        print(f"[DEBUG] Ollama raw: {raw_content[:400]}")
        parsed = json.loads(raw_content)
    except Exception as exc:
        print(f"[WARN] Failed to parse Ollama JSON: {exc}")
        parsed = {}
    return parsed, None


def run_streaming_chat_ollama(messages: list, temperature: float):
    ollama_payload = {
        "model": OLLAMA_CHAT_MODEL,
        "messages": messages,
        "stream": True,
        "options": {"temperature": temperature},
    }
    try:
        resp = requests.post(OLLAMA_CHAT_URL, json=ollama_payload, stream=True, timeout=180)
    except requests.exceptions.ConnectionError:
        return None, ("Cannot reach Ollama at http://localhost:11434. Start Ollama and try again.", 502)
    except requests.exceptions.Timeout:
        return None, ("Timed out connecting to Ollama.", 504)
    if resp.status_code != 200:
        detail = resp.text[:300].replace("\n", " ").strip()
        return None, (f"Ollama returned HTTP {resp.status_code}: {detail}", resp.status_code)
    full = ""
    for line in resp.iter_lines(decode_unicode=True):
        if not line:
            continue
        try:
            chunk = json.loads(line)
        except Exception:
            continue
        delta = (chunk.get("message") or {}).get("content") or ""
        full += delta
    return full, None


def clean_chat_whitelist(text: str) -> str:
    cleaned = text
    for name in sorted(_ALL_TOOL_NAMES, key=len, reverse=True):
        pattern = re.compile(r"\b" + re.escape(name) + r"\b", re.IGNORECASE)
        cleaned = pattern.sub("a suitable tool", cleaned)
    return cleaned


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
        register_tool_name(name)
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

    # --- Chat commands (add-tool / describe) ---
    try:
        cmd_reply = handle_add_tool_command(last_user) or handle_describe_command(last_user)
    except Exception as exc:
        cmd_reply = f"Something went wrong with that command, bud: {exc}"

    if cmd_reply is not None:
        if not stream:
            return jsonify({"message": {"content": cmd_reply}})
        return Response(stream_with_context(fake_stream(cmd_reply)),
                        mimetype="application/x-ndjson")

    # --- Retrieve tools ---
    try:
        tools, distances = retrieve_tools(last_user)
    except RuntimeError as exc:
        return error_response(str(exc).strip(), 502)
    except Exception as exc:
        import traceback; traceback.print_exc()
        return error_response(f"Tool retrieval failed: {exc}", 500)

    top_distance = distances[0] if distances else None
    print(f"[DEBUG] query='{last_user[:50]}' top_distance={top_distance} num_tools={len(tools)}")

    # --- Server-side routing ---
    mode, resolved_tool = route(last_user, top_distance)

    history = [m for m in messages[:-1] if isinstance(m, dict)]
    tool_names = [t["name"] for t in tools]
    tool_lookup = {t["name"]: t for t in tools}

    # === MODE: chat ===
    if mode == "chat":
        system_text = build_system_message(include_personality=False)
        ollama_messages = [{"role": "system", "content": system_text}]
        ollama_messages.extend(history)
        ollama_messages.append({"role": "user", "content": last_user})

        raw_chat_text, err = run_streaming_chat_ollama(ollama_messages, temperature=0.7)
        if err:
            return error_response(err[0], err[1])

        cleaned_chat = clean_chat_whitelist(raw_chat_text)
        final_text = render_chat(cleaned_chat)

        if not stream:
            return jsonify({"message": {"content": final_text}})
        return Response(stream_with_context(fake_stream(final_text)),
                        mimetype="application/x-ndjson")

    # === For the following modes, we need tools in the library ===
    if not tools:
        empty_msg = "My library's empty right now, bud. Add a tool first: add tool <name>"
        if not stream:
            return jsonify({"message": {"content": empty_msg}})
        return Response(stream_with_context(fake_stream(empty_msg)),
                        mimetype="application/x-ndjson")

    system_with_personality = build_system_message(include_personality=True)

    # === MODE: recommend ===
    if mode == "recommend":
        schema = build_recommend_schema(tool_names)
        prompt = build_recommend_prompt(last_user, tools)
        ollama_messages = [{"role": "system", "content": system_with_personality}]
        ollama_messages.extend(history)
        ollama_messages.append({"role": "user", "content": prompt})

        parsed, err = run_structured_ollama(ollama_messages, schema, temperature=0.3)
        if err:
            return error_response(err[0], err[1])

        picks = parsed.get("picks") or []
        picks = [p for p in picks if isinstance(p, dict)
                 and p.get("tool") in tool_lookup
                 and isinstance(p.get("why"), str)]
        if not picks and tools:
            picks = [
                {"tool": t["name"], "why": t["description"][:150]}
                for t in tools[:2]
            ]
        if not picks:
            parsed_fallback = {"picks": []}
        else:
            parsed_fallback = {"picks": picks}

        final_text = render_recommend(parsed_fallback, tools)

        if not stream:
            return jsonify({"message": {"content": final_text}})
        return Response(stream_with_context(fake_stream(final_text)),
                        mimetype="application/x-ndjson")

    # === MODE: howto ===
    if mode == "howto":
        schema = build_howto_schema(tool_names)
        prompt = build_howto_prompt(last_user, tools)
        ollama_messages = [{"role": "system", "content": system_with_personality}]
        ollama_messages.extend(history)
        ollama_messages.append({"role": "user", "content": prompt})

        parsed, err = run_structured_ollama(ollama_messages, schema, temperature=0.3)
        if err:
            return error_response(err[0], err[1])

        picks = parsed.get("picks") or []
        picks = [p for p in picks if isinstance(p, dict)
                 and p.get("tool") in tool_lookup
                 and isinstance(p.get("why"), str)]
        if not picks and tools:
            picks = [
                {"tool": t["name"], "why": t["description"][:150]}
                for t in tools[:2]
            ]
        flow = parsed.get("flow") or []
        validated_flow = []
        allowed = set(tool_names + ["none"])
        for s in flow:
            if (isinstance(s, dict)
                    and isinstance(s.get("stage"), str)
                    and s.get("tool") in allowed):
                validated_flow.append(s)

        validated = {"picks": picks, "flow": validated_flow}

        final_text = render_howto(validated, tools)

        if not stream:
            return jsonify({"message": {"content": final_text}})
        return Response(stream_with_context(fake_stream(final_text)),
                        mimetype="application/x-ndjson")

    # === MODE: define ===
    if mode == "define":
        if not resolved_tool:
            canned = "Hmm, I don't have that in my library."
            if not stream:
                return jsonify({"message": {"content": canned}})
            return Response(stream_with_context(fake_stream(canned)),
                            mimetype="application/x-ndjson")

        tool_record = tool_lookup.get(resolved_tool) or tool_lookup.get(resolved_tool.lower())
        if not tool_record:
            tool_record = {
                "name": resolved_tool,
                "category": "",
                "type": "unknown",
                "pricing": "unknown",
                "verified": False,
                "description": "",
            }

        schema = build_define_schema(resolved_tool)
        prompt = build_define_prompt(last_user, tool_record)
        ollama_messages = [{"role": "system", "content": system_with_personality}]
        ollama_messages.extend(history)
        ollama_messages.append({"role": "user", "content": prompt})

        parsed, err = run_structured_ollama(ollama_messages, schema, temperature=0.0)
        if err:
            return error_response(err[0], err[1])

        if not isinstance(parsed, dict) or "definition" not in parsed:
            parsed = {"tool": resolved_tool, "definition": tool_record.get("description", "") or "No details available."}
        parsed["tool"] = resolved_tool

        final_text = render_define(parsed)

        if not stream:
            return jsonify({"message": {"content": final_text}})
        return Response(stream_with_context(fake_stream(final_text)),
                        mimetype="application/x-ndjson")

    # === MODE: factcheck ===
    if mode == "factcheck":
        tool_record = tool_lookup.get(resolved_tool) or tool_lookup.get(resolved_tool.lower())
        if not tool_record:
            tool_record = {
                "name": resolved_tool,
                "category": "",
                "type": "unknown",
                "pricing": "unknown",
                "verified": False,
                "description": "",
            }

        schema = build_factcheck_schema(resolved_tool)
        prompt = build_factcheck_prompt(last_user, tool_record)
        ollama_messages = [{"role": "system", "content": system_with_personality}]
        ollama_messages.extend(history)
        ollama_messages.append({"role": "user", "content": prompt})

        parsed, err = run_structured_ollama(ollama_messages, schema, temperature=0.0)
        if err:
            return error_response(err[0], err[1])

        if not isinstance(parsed, dict) or parsed.get("verdict") not in ("yes", "no", "partly", "unknown"):
            parsed = {"tool": resolved_tool, "verdict": "unknown", "explanation": "My notes don't cover that."}
        parsed["tool"] = resolved_tool

        final_text = render_factcheck(parsed)

        if not stream:
            return jsonify({"message": {"content": final_text}})
        return Response(stream_with_context(fake_stream(final_text)),
                        mimetype="application/x-ndjson")

    # --- Fallback (shouldn't reach) ---
    fallback = render_recommend({"picks": []}, tools)
    if not stream:
        return jsonify({"message": {"content": fallback}})
    return Response(stream_with_context(fake_stream(fallback)),
                    mimetype="application/x-ndjson")


if __name__ == "__main__":
    print("=" * 62)
    print(" Nate -- local AI tool librarian (5-mode router)")
    print(" API    : http://localhost:5000  (listening on 0.0.0.0:5000)")
    print(" Model  : llama3.1:8b via Ollama")
    print(" DB     : ChromaDB at " + CHROMA_DB_PATH)
    print(" Modes  : chat | recommend | howto | define | factcheck")
    print("=" * 62)
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
