import random
import random as _random
from prompts import HUMOR_JOKES

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


def maybe_append_joke(text: str, probability: float = 0.25) -> str:
    """Append a random joke from the humor pool with given probability."""
    if not HUMOR_JOKES:
        return text
    if _random.random() >= probability:
        return text
    joke = _random.choice(HUMOR_JOKES)
    return text.rstrip() + "\n\n" + joke


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


def render_recommend(data: dict, records: list[dict]) -> str:
    picks = data.get("picks") or []
    lines = []
    for p in picks:
        lines.append(f"- {p['tool']} -- {p['why'].strip()}")
    if not lines:
        lines.append("Nothing in my library is a strong match. Closest I have:")
        for r in records[:2]:
            lines.append(f"  - {r['name']} -- {r['description'][:120]}")
    opener = random.choice(OPENERS)
    closer = random.choice(CLOSERS)
    parts = [opener, ""] + lines
    if closer:
        parts += ["", closer]
    return maybe_append_joke("\n".join(parts))


def render_howto(data: dict, records: list[dict]) -> str:
    picks = data.get("picks") or []
    flow = data.get("flow") or []
    lines = []
    for p in picks:
        lines.append(f"- {p['tool']} -- {p['why'].strip()}")
    if not lines:
        lines.append("Nothing in my library is a strong match. Closest I have:")
        for r in records[:2]:
            lines.append(f"  - {r['name']} -- {r['description'][:120]}")
    if flow and picks:
        parts = []
        for s in flow:
            label = s["stage"]
            tool = s["tool"]
            parts.append(f"{label} ({tool})" if tool != "none" else label)
        lines.append("")
        lines.append("Flow: " + " -> ".join(parts))
    opener = random.choice(OPENERS)
    closer = random.choice(CLOSERS)
    parts = [opener, ""] + lines
    if closer:
        parts += ["", closer]
    return maybe_append_joke("\n".join(parts))


def render_define(data: dict) -> str:
    return f"{data['tool']} -- {data['definition'].strip()}"


def render_factcheck(data: dict) -> str:
    lead = {
        "yes": "Yes.",
        "no": "No.",
        "partly": "Partly.",
        "unknown": "Not sure from my notes.",
    }[data["verdict"]]
    return f"{lead} {data['explanation'].strip()}"


def render_chat(text: str) -> str:
    if not text or len(text.strip()) < 3:
        return "Hey bud. What are we building?"
    return text.strip()
