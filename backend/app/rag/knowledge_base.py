"""
================================================================================
  backend/app/rag/knowledge_base.py  —  VECTOR DATABASE CLIENT (RAG)
================================================================================

PURPOSE:
  Thin wrapper around ChromaDB, a local vector database.
  Stores embeddings of AWS and Azure documentation for semantic search.
  The app can retrieve relevant docs and inject them into AI prompts.

WHY IT EXISTS:
  RAG (Retrieval-Augmented Generation) lets the AI cite up-to-date docs
  instead of relying on training data cutoffs. ChromaDB is chosen because
  it requires zero external infrastructure — just a local SQLite file.

CONNECTIONS TO OTHER FILES:
  • main.py              → startup_event() calls list_collection_stats()
  • (dead code removed)  → ingestion scripts were in rag/ingestion/ (deleted)

HOW IT WORKS:
  1. Documents are split into chunks.
  2. Each chunk is converted to a dense vector via sentence-transformers.
  3. Vectors are stored in ChromaDB collections (aws_resources, azure_resources, ...).
  4. At query time, the user's question is also embedded, and the top-K
     nearest vectors (most relevant chunks) are returned.

PATTERN: Singleton with Lazy Initialization
  _client and _embedding_fn are created only when first accessed.
  This keeps import time fast and avoids building the embedding model
  unless a RAG query actually happens.

NOTE:
  Currently the RAG pipeline is NOT wired into the live code path.
  The ingestion scripts were removed during cleanup. The collections
  exist but may be empty. The app works fine without them (fallback to templates).
================================================================================
"""

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

# ── Singleton instances ──────────────────────────────────────────────────
# Lazy-initialized on first access. Never recreate once built.
_client = None          # ChromaDB persistent client (talks to SQLite)
_embedding_fn = None    # sentence-transformers embedding model

# Cache of opened collections. Key = collection name, Value = Collection object.
_collections = {}


def _get_client():
    """Return the singleton ChromaDB client, creating it if needed.

    The client connects to ./chroma_db/chroma.sqlite3 on disk.
    If the DB file doesn't exist, ChromaDB creates it automatically.
    """
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(path="./chroma_db")
    return _client


def _get_embedding_fn():
    """Return the singleton embedding function, creating it if needed.

    Uses "all-mpnet-base-v2", a 768-dimensional sentence embedding model.
    It runs locally (no API calls) but loads ~400 MB on first use.
    """
    global _embedding_fn
    if _embedding_fn is None:
        _embedding_fn = SentenceTransformerEmbeddingFunction(
            model_name="all-mpnet-base-v2"
        )
    return _embedding_fn


def get_collection(name: str):
    """Get or create a named ChromaDB collection.

    A "collection" is like a table in SQL — it holds a set of documents
    with the same embedding space. We have separate collections for
    AWS resources, Azure resources, security rules, etc.

    Args:
        name: Collection name, e.g. "aws_resources".

    Returns:
        chromadb.Collection object ready for add/query/delete.
    """
    if name not in _collections:
        client = _get_client()
        embedding_fn = _get_embedding_fn()
        # get_or_create_collection: safe to call even if collection exists.
        # metadata sets the distance metric to cosine similarity.
        _collections[name] = client.get_or_create_collection(
            name=name,
            embedding_function=embedding_fn,
            metadata={"hnsw:space": "cosine"},   # cosine similarity for nearest-neighbor
        )
    return _collections[name]


def list_collection_stats() -> dict:
    """Count documents in each known collection.

    Called once at startup (main.py → startup_event) to warn developers
    if the knowledge base is under-populated.

    Returns:
        Dict mapping collection name → document count (0 if missing).
    """
    client = _get_client()
    stats = {}
    # These collection names are hardcoded conventions across the project.
    for collection_name in [
        "aws_resources",
        "azure_resources",
        "aws_modules",
        "azure_modules",
        "security_rules",
    ]:
        try:
            coll = client.get_collection(collection_name)
            stats[collection_name] = coll.count()
        except Exception:
            # Collection doesn't exist yet — not an error, just empty.
            stats[collection_name] = 0
    return stats
