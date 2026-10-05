import random
from pathlib import Path

PERSONALITY_FILE     = Path(r"D:\Nate\personality\nate-system-prompt.txt")
HUMOR_FILE           = Path(r"D:\Nate\personality\humor-pool.txt")

HINTS_PER_RESPONSE   = 3
JOKE_PROBABILITY     = 0.5

FALLBACK_PROMPT = (
    "You are Nate, a local AI tool librarian. Be honest and in character."
)


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


def load_humor_pool():
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


SYSTEM_PROMPT = load_personality()
HUMOR_HINTS, HUMOR_JOKES = load_humor_pool()


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


def build_recommend_prompt(query: str, tools: list[dict]) -> str:
    tool_block = "\n".join(
        f"- {t['name']} ({t['category']}, {t['type']}, {t['pricing']}, "
        f"{'verified' if t['verified'] else 'unverified'}): {t['description']}"
        for t in tools
    )
    return (
        f"User request: {query}\n\n"
        f"Tools in the library:\n{tool_block}\n\n"
        "Pick up to 4 tools from this list that best fit the request. "
        "For each pick, write one sentence (under 25 words) on why it fits. "
        "Use only tool names from the list. If none fit, return an empty picks array."
    )


def build_howto_prompt(query: str, tools: list[dict]) -> str:
    tool_block = "\n".join(
        f"- {t['name']} ({t['category']}, {t['type']}, {t['pricing']}, "
        f"{'verified' if t['verified'] else 'unverified'}): {t['description']}"
        for t in tools
    )
    return (
        f"User request: {query}\n\n"
        f"Tools in the library:\n{tool_block}\n\n"
        "The user wants to know how to build or connect something. "
        "First pick up to 4 tools from the list that fit. "
        "Then fill in 'flow': 3 to 6 stages in order, specific to exactly "
        "what the user asked about. Each stage gets a short label (1-3 words) "
        "and the library tool that handles it, or 'none' if no listed tool covers it. "
        "Use only tool names from the list. "
        "Do not use a generic voice pipeline -- the flow must match the specific request."
    )


def build_define_prompt(query: str, tool: dict) -> str:
    record = (
        f"- {tool['name']} ({tool['category']}, {tool['type']}, {tool['pricing']}, "
        f"{'verified' if tool['verified'] else 'unverified'}): {tool['description']}"
    )
    return (
        f"User question: {query}\n\n"
        f"Library entry:\n{record}\n\n"
        "Define this tool in 1-2 sentences using only the entry above. "
        "Say what it does and who it is for. Do not add facts not in the entry."
    )


def build_factcheck_prompt(query: str, tool: dict) -> str:
    record = (
        f"- {tool['name']} ({tool['category']}, {tool['type']}, {tool['pricing']}, "
        f"{'verified' if tool['verified'] else 'unverified'}): {tool['description']}"
    )
    return (
        f"User question: {query}\n\n"
        f"Library entry:\n{record}\n\n"
        "Answer the question using only the entry above. "
        "Set 'verdict' to yes, no, partly, or unknown "
        "(use unknown only if the entry does not address the question at all). "
        "Then write one short sentence explaining your verdict in plain English."
    )


CHAT_SYSTEM_PROMPT = (
    "You are Nate, a tool librarian. Keep replies to 1-2 sentences.\n\n"
    "CRITICAL: You do NOT have access to the user's tool library in this "
    "mode. You must NEVER claim to have tools for anything. Never say "
    "'we have tools' or 'I have tools'. If the user is asking about tools "
    "and you don't have a specific answer, respond:\n"
    "  'Nothing in the library fits that well, bud. Can you be more "
    "specific about what you're trying to build?'\n\n"
    "Only for greetings, thanks, or chit-chat, respond normally."
)
