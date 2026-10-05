import re

from retrieval import _upsert_tool, get_collection
from whitelist import find_tool, _ALL_TOOL_NAMES, register_tool_name

ADD_HELP = (
    "Format that, bud:\n"
    "  add tool name\n"
    "  add tool: name | category | type | pricing | verified | description\n"
    "Types: repo, website, app, saas, list, skill, model, unknown\n"
    "Pricing: free, freemium, paid, open, unknown"
)

GREETING = re.compile(
    r"^\s*(hi|hey|hello|yo|sup|thanks|thank you|good (morning|evening)|what'?s up|how are you)"
    r"\b[\w\s'?!.,]{0,30}$", re.I)

HOWTO = re.compile(
    r"\b(how (do|can|would|should) (i|we)|how to|what'?s the (flow|setup|stack|architecture)"
    r"|set ?up|connect|build|pipeline)\b", re.I)

DEFINE = re.compile(
    r"^\s*(what is|what'?s|what are|who is|tell me about|explain)\b", re.I)

FACT = re.compile(
    r"^\s*(is|are|does|do|can|will|has|have)\b"
    r"|\b(free|open[- ]?source|paid|price|cost|licen[sc]e|verified|self[- ]?host|offline|windows)\b.*\?",
    re.I)


def route(query: str, top_distance):
    if GREETING.match(query):
        return "chat", None

    if HOWTO.search(query):
        return "howto", None

    tool = find_tool(query)

    if tool and FACT.search(query):
        return "factcheck", tool

    if tool and DEFINE.match(query):
        return "define", tool

    if DEFINE.match(query) and not tool:
        return "define", None

    if top_distance is not None and top_distance > 1.4:
        return "chat", None
    return "recommend", None


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
            register_tool_name(name)
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
        register_tool_name(name)
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
