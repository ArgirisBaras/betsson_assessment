"""Knowledge store — hybrid memory store for long-term memory.

Uses an in-memory JSON store with keyword-based search as the primary backend
(always works, no external dependencies). Optionally upgrades to ChromaDB
vector search when an OpenAI API key is configured, using OpenAI embeddings
to avoid downloading models at runtime.

Provides search over user preferences, contact info, and organizational facts.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

import structlog

from app.config import settings

logger = structlog.get_logger(__name__)

# ── Collection names ─────────────────────────────────────────────────────────

CONTACTS = "contacts"
PREFERENCES = "preferences"
ORG_FACTS = "org_facts"
EMAIL_HISTORY = "email_history"

# ── In-memory JSON store (always works) ──────────────────────────────────────

_store: dict[str, dict[str, dict]] = {
    CONTACTS: {},
    PREFERENCES: {},
    ORG_FACTS: {},
    EMAIL_HISTORY: {},
}

_store_path = Path(settings.chroma_path) / "memory_store.json"


def _load_json_store() -> None:
    """Load persisted JSON memory from disk if present."""
    global _store
    try:
        if _store_path.exists():
            with open(_store_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            for collection in [CONTACTS, PREFERENCES, ORG_FACTS, EMAIL_HISTORY]:
                loaded.setdefault(collection, {})
            _store = loaded
            logger.info("json_memory_store_loaded", path=str(_store_path))
    except Exception as exc:
        logger.warning("json_memory_store_load_failed", error=str(exc))


def _persist_json_store() -> None:
    """Persist JSON memory to disk."""
    try:
        _store_path.parent.mkdir(parents=True, exist_ok=True)
        with open(_store_path, "w", encoding="utf-8") as f:
            json.dump(_store, f, ensure_ascii=False, indent=2)
    except Exception as exc:
        logger.warning("json_memory_store_persist_failed", error=str(exc))

# ── ChromaDB (optional, for true vector search) ─────────────────────────────

_chromadb_available = False
_client = None
_embedding_fn: Any = None


def _build_embedding_function() -> Any:
    """Build an OpenAI embedding function for ChromaDB.

    Uses the already-configured OpenAI API key so no local model download
    is needed.  Returns ``None`` when the key is absent.
    """
    if not settings.openai_api_key:
        return None
    try:
        from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction
        return OpenAIEmbeddingFunction(
            api_key=settings.openai_api_key,
            model_name="text-embedding-3-small",
        )
    except Exception as exc:
        logger.debug("openai_embedding_fn_failed", error=str(exc))
        return None


def _try_init_chromadb():
    """Try to initialize ChromaDB with OpenAI embeddings.

    Falls back to JSON store if ChromaDB init fails or no API key is set.
    """
    global _chromadb_available, _client, _embedding_fn
    try:
        import chromadb

        ef = _build_embedding_function()
        if ef is None:
            logger.info(
                "chromadb_skipped_no_api_key",
                reason="OPENAI_API_KEY not set; using JSON/keyword store",
            )
            return

        _client = chromadb.PersistentClient(path=settings.chroma_path)
        # Smoke-test: create a throw-away collection with OpenAI embeddings
        test_col = _client.get_or_create_collection("init_test", embedding_function=ef)
        test_col.upsert(documents=["test"], ids=["test-init"])
        _client.delete_collection("init_test")

        _embedding_fn = ef
        _chromadb_available = True
        logger.info(
            "chromadb_initialized",
            path=settings.chroma_path,
            embedding="openai/text-embedding-3-small",
        )
    except Exception as exc:
        _chromadb_available = False
        logger.info("chromadb_unavailable_using_json_store", reason=str(exc)[:200])


_load_json_store()
_try_init_chromadb()


# ── Public API ───────────────────────────────────────────────────────────────

def add_documents(
    collection_name: str,
    documents: list[str],
    ids: list[str],
    metadatas: list[dict] | None = None,
) -> None:
    """Add documents to a collection (upsert)."""
    metas = metadatas or [{} for _ in ids]

    # Always store in JSON store
    if collection_name not in _store:
        _store[collection_name] = {}
    for i, doc_id in enumerate(ids):
        _store[collection_name][doc_id] = {
            "id": doc_id,
            "document": documents[i],
            "metadata": metas[i],
        }
    _persist_json_store()

    # Also try ChromaDB if available
    if _chromadb_available and _client:
        try:
            col = _client.get_or_create_collection(
                name=collection_name,
                embedding_function=_embedding_fn,
                metadata={"hnsw:space": "cosine"},
            )
            col.upsert(documents=documents, ids=ids, metadatas=metas)
        except Exception:
            pass

    logger.info("documents_added", collection=collection_name, count=len(documents))


def query(
    collection_name: str,
    query_text: str,
    n_results: int = 5,
    where: dict | None = None,
) -> list[dict]:
    """Search a collection. Uses ChromaDB vector search if available, else keyword matching."""

    # Try ChromaDB first
    if _chromadb_available and _client:
        try:
            col = _client.get_or_create_collection(
                name=collection_name,
                embedding_function=_embedding_fn,
            )
            if col.count() > 0:
                kwargs = {"query_texts": [query_text], "n_results": min(n_results, col.count())}
                if where:
                    kwargs["where"] = where
                results = col.query(**kwargs)
                items = []
                for i in range(len(results["ids"][0])):
                    items.append({
                        "id": results["ids"][0][i],
                        "document": results["documents"][0][i],
                        "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                        "distance": results["distances"][0][i] if results["distances"] else None,
                    })
                logger.info("knowledge_queried", collection=collection_name, backend="chromadb", results_count=len(items))
                return items
        except Exception:
            pass

    # Fallback: keyword-based search over JSON store
    return _keyword_search(collection_name, query_text, n_results)


def _keyword_search(collection_name: str, query_text: str, n_results: int) -> list[dict]:
    """Simple keyword-matching search over the in-memory JSON store."""
    docs = _store.get(collection_name, {})
    if not docs:
        return []

    query_words = set(query_text.lower().split())
    scored = []
    for doc_id, entry in docs.items():
        doc_text = entry["document"].lower()
        # Score = number of query words found in document
        score = sum(1 for w in query_words if w in doc_text)
        if score > 0:
            scored.append((score, entry))

    # Sort by score descending
    scored.sort(key=lambda x: x[0], reverse=True)

    items = []
    for score, entry in scored[:n_results]:
        items.append({
            "id": entry["id"],
            "document": entry["document"],
            "metadata": entry["metadata"],
            "distance": 1.0 - (score / max(len(query_words), 1)),  # pseudo-distance
        })

    logger.info("knowledge_queried", collection=collection_name, backend="json_keyword", results_count=len(items))
    return items


def get_all_documents(collection_name: str) -> list[dict]:
    """Get all documents in a collection."""
    docs = _store.get(collection_name, {})
    return list(docs.values())


def delete_document(collection_name: str, doc_id: str) -> bool:
    """Delete a document by ID."""
    docs = _store.get(collection_name, {})
    if doc_id in docs:
        del docs[doc_id]
        _persist_json_store()
        logger.info("document_deleted", collection=collection_name, doc_id=doc_id)
        return True
    return False


def reset_store() -> None:
    """Reset all collections."""
    global _store
    _store = {
        CONTACTS: {},
        PREFERENCES: {},
        ORG_FACTS: {},
        EMAIL_HISTORY: {},
    }
    _persist_json_store()
    logger.info("knowledge_store_reset")

