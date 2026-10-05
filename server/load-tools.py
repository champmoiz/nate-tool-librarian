"""
load-tools.py -- Nate's tool library loader.

Reads D:\\Nate\\tools\\tools.txt (6 fields per line) and upserts into ChromaDB.

Format:
    name | category | type | pricing | verified/unverified | description

    type:    repo | website | app | saas | list | skill | model | unknown
    pricing: free | freemium | paid | open | unknown

Run:  python load-tools.py           # load/reload
      python load-tools.py --check   # print DB count only
"""

import argparse
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
if _missing:
    print("[ERROR] Missing Python dependencies: " + ", ".join(_missing))
    print("        pip install " + " ".join(_missing))
    sys.exit(1)

from retrieval import OllamaEmbeddingFunction

TOOLS_FILE       = Path(r"D:\Nate\tools\tools.txt")
CHROMA_DB_PATH   = r"D:\Nate\server\chroma_db"
COLLECTION_NAME  = "nate_tools"
OLLAMA_EMBED_URL = "http://localhost:11434/api/embeddings"
EMBED_MODEL      = "nomic-embed-text"


def parse_tools_file(path: Path) -> list[dict]:
    tools = []
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        print(f"[ERROR] Tools file not found: {path}")
        sys.exit(1)

    for lineno, line in enumerate(raw.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) not in (6, 7):
            print(f"[WARN] Line {lineno}: expected 6 or 7 fields, got {len(parts)} -- skipping")
            continue
        if len(parts) == 7:
            name, category, ttype, pricing, status, description, aliases = parts
        else:
            name, category, ttype, pricing, status, description = parts
            aliases = ""
        if not name or not description:
            print(f"[WARN] Line {lineno}: empty name or description -- skipping")
            continue
        verified = status.lower() in ("verified", "true", "yes", "1")
        tools.append({
            "name": name.lower(),
            "category": category or "Unknown",
            "type": (ttype or "unknown").lower(),
            "pricing": (pricing or "unknown").lower(),
            "verified": verified,
            "description": description,
            "aliases": aliases,
        })
    return tools


def make_client():
    return chromadb.PersistentClient(
        path=CHROMA_DB_PATH,
        settings=Settings(anonymized_telemetry=False),
    )


def check_db(embedding_fn):
    col = make_client().get_or_create_collection(name=COLLECTION_NAME, embedding_function=embedding_fn)
    count = col.count()
    print(f"ChromaDB at {CHROMA_DB_PATH}")
    print(f"Collection '{COLLECTION_NAME}' holds {count} tools.")
    if count == 0:
        return
    sample = col.get(limit=5, include=["metadatas"])
    for tid, meta in zip(sample["ids"], sample["metadatas"]):
        meta = meta or {}
        print(f"  - {tid} ({meta.get('category','')}, {meta.get('type','')}, {meta.get('pricing','')})")


def run_load(embedding_fn):
    tools = parse_tools_file(TOOLS_FILE)
    if not tools:
        print(f"[ERROR] No valid tools parsed from {TOOLS_FILE}")
        sys.exit(1)

    col = make_client().get_or_create_collection(name=COLLECTION_NAME, embedding_function=embedding_fn)

    ids       = [t["name"] for t in tools]
    def _doc(t):
        base = f"{t['name']} — {t['description']} (Category: {t['category']} · Type: {t['type']} · Pricing: {t['pricing']})"
        if t.get("aliases"):
            base += f" · Also known for: {t['aliases']}"
        return base
    documents = [_doc(t) for t in tools]
    metadatas = [{
        "category": t["category"],
        "type": t["type"],
        "pricing": t["pricing"],
        "verified": t["verified"],
        "description": t["description"],
        "aliases": t.get("aliases", ""),
    } for t in tools]

    print(f"Upserting {len(tools)} tools... this may take 5-15 minutes.")
    col.upsert(ids=ids, documents=documents, metadatas=metadatas)

    verified = sum(1 for t in tools if t["verified"])
    print(f"[OK] Upsert complete. DB now holds {col.count()} tools.")
    print(f"Loaded {len(tools)} tools ({verified} verified, {len(tools)-verified} unverified)")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--check", action="store_true")
    args = p.parse_args()
    ef = OllamaEmbeddingFunction()
    if args.check:
        check_db(ef)
    else:
        run_load(ef)


if __name__ == "__main__":
    main()