import re
from pathlib import Path

TOOLS_FILE = Path(r"D:\Nate\tools\tools.txt")

norm = lambda s: re.sub(r"[^a-z0-9]", "", s.lower())

_ALL_TOOL_NAMES: set[str] = set()
NAME_INDEX: dict[str, str] = {}


def load_tool_whitelist():
    global _ALL_TOOL_NAMES, NAME_INDEX
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
    NAME_INDEX = {norm(n): n for n in _ALL_TOOL_NAMES}
    print(f"[OK] Tool whitelist loaded: {len(names)} names")


def register_tool_name(name: str) -> None:
    """Register a newly-added tool name at runtime so find_tool can see it."""
    _ALL_TOOL_NAMES.add(name.lower())
    NAME_INDEX[norm(name)] = name.lower()


def find_tool(query: str):
    words = re.findall(r"[a-z0-9]+", query.lower())
    for n in (3, 2, 1):
        for i in range(len(words) - n + 1):
            key = "".join(words[i:i+n])
            if key in NAME_INDEX:
                return NAME_INDEX[key]
    return None


def sync_whitelist_from_db(db_path: str, collection_name: str) -> int:
    """Pull all tool IDs from ChromaDB and register them in the whitelist.
    Returns number of names registered. Safe if DB is empty or unreachable."""
    try:
        import chromadb
        from chromadb.config import Settings
        client = chromadb.PersistentClient(
            path=db_path,
            settings=Settings(anonymized_telemetry=False),
        )
        col = client.get_or_create_collection(name=collection_name)
        ids = col.get().get("ids") or []
        for tool_id in ids:
            register_tool_name(tool_id)
        return len(ids)
    except Exception as e:
        print(f"[WARN] Could not sync whitelist from DB: {e}")
        return 0
