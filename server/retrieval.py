# NOTE: Changing the embedding function requires re-embedding.
# Delete D:\Nate\server\chroma_db and re-run load-tools.py.
import chromadb
import math
import requests
from chromadb.config import Settings

CHROMA_DB_PATH       = r"D:\Nate\server\chroma_db"
COLLECTION_NAME      = "nate_tools"
OLLAMA_EMBED_URL     = "http://localhost:11434/api/embeddings"
EMBED_MODEL          = "nomic-embed-text"
MAX_TOOLS_IN_CONTEXT = 8


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
            vec = list(emb)
            norm = math.sqrt(sum(x * x for x in vec))
            if norm > 0:
                vec = [x / norm for x in vec]
            vectors.append(vec)
        return vectors


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


def _upsert_tool(name, category, ttype, pricing, verified, description):
    get_collection().upsert(
        ids=[name.lower()],
        documents=[f"{name.lower()} — {description} (Category: {category} · Type: {ttype} · Pricing: {pricing})"],
        metadatas=[{
            "category": category, "type": ttype, "pricing": pricing,
            "verified": verified, "description": description,
        }],
    )
    append_or_update_tools_file(name, category, ttype, pricing, verified, description)


def retrieve_tools(query: str):
    collection = get_collection()
    count = collection.count()
    if count == 0:
        return [], []
    n = min(MAX_TOOLS_IN_CONTEXT, count)
    result = collection.query(query_texts=[query], n_results=n)

    ids = (result.get("ids") or [[]])[0]
    metas = (result.get("metadatas") or [[]])[0]
    dists = (result.get("distances") or [[]])[0]

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
    return tools, list(dists)


def append_or_update_tools_file(name: str, category: str, ttype: str,
                                  pricing: str, verified: bool, description: str) -> None:
    """Write or update a tool line in tools.txt. Idempotent."""
    from pathlib import Path
    import re
    tools_path = Path(r"D:\Nate\tools\tools.txt")
    if not tools_path.exists():
        return
    status = "verified" if verified else "unverified"
    new_line = f"{name.lower()} | {category} | {ttype} | {pricing} | {status} | {description}"
    try:
        lines = tools_path.read_text(encoding="utf-8").splitlines()
    except Exception as e:
        print(f"[WARN] Could not read tools.txt for update: {e}")
        return
    norm = re.sub(r"[^a-z0-9]", "", name.lower())
    found_idx = None
    for i, line in enumerate(lines):
        if line.strip().startswith("#") or "|" not in line:
            continue
        first = line.split("|")[0].strip()
        if re.sub(r"[^a-z0-9]", "", first.lower()) == norm:
            found_idx = i
            break
    if found_idx is not None:
        lines[found_idx] = new_line
    else:
        lines.append(new_line)
    try:
        tools_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except Exception as e:
        print(f"[WARN] Could not write tools.txt: {e}")
