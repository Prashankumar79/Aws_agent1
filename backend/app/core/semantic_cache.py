"""
Semantic LLM response cache.

Layers:
- L1: in-process exact-match cache keyed by the full prompt/context/task.
- L2: optional Qdrant semantic cache, restricted to configured task types.

The exact cache is safe for long generation prompts because keys never truncate
inputs. The semantic cache is intentionally opt-in per task type so similar
architecture documents cannot accidentally reuse another customer's output.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from typing import Any, Dict, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

_L1_CACHE: Dict[str, Dict[str, Any]] = {}
_L1_LOCK = threading.RLock()


class SemanticCache:
    """Two-layer cache for LLM responses."""

    CACHE_COLLECTION = "llm_semantic_cache"

    def __init__(self):
        self._qdrant = None
        self._embedding_model = None

    def get(self, prompt: str, context: str = "", task_type: str = "general") -> Optional[str]:
        """Return a cached response, or None on miss."""
        if not settings.SEMANTIC_CACHE_ENABLED:
            return None

        cache_key = self._make_key(prompt, context, task_type)
        l1_result = self._l1_get(cache_key)
        if l1_result is not None:
            logger.info("[SemanticCache] L1 HIT | task=%s | key=%s", task_type, cache_key[:16])
            return l1_result

        l2_result = self._l2_get(prompt, context, task_type)
        if l2_result is not None:
            logger.info("[SemanticCache] L2 HIT | task=%s", task_type)
            self._l1_put(cache_key, l2_result, task_type)
            return l2_result

        logger.debug("[SemanticCache] MISS | task=%s | key=%s", task_type, cache_key[:16])
        return None

    def put(self, prompt: str, context: str, task_type: str, response: str, ttl_seconds: int = 86400):
        """Store a response in enabled cache layers."""
        if not settings.SEMANTIC_CACHE_ENABLED or not response:
            return

        cache_key = self._make_key(prompt, context, task_type)
        self._l1_put(cache_key, response, task_type, ttl_seconds)
        self._l2_put(prompt, context, task_type, response, ttl_seconds)

    def invalidate(self, pattern: str = ""):
        """Invalidate all cache entries or entries for one task_type."""
        if not pattern:
            with _L1_LOCK:
                _L1_CACHE.clear()
            logger.info("[SemanticCache] L1 cleared (all)")
            self._l2_clear_all()
            return

        with _L1_LOCK:
            keys_to_remove = [
                key for key, value in _L1_CACHE.items()
                if value.get("task_type") == pattern
            ]
            for key in keys_to_remove:
                del _L1_CACHE[key]

        logger.info("[SemanticCache] L1 invalidated %s entries for task_type=%s", len(keys_to_remove), pattern)
        self._l2_clear_task_type(pattern)

    def stats(self) -> Dict[str, Any]:
        """Return cache stats without exposing response bodies."""
        now = time.time()
        with _L1_LOCK:
            total = len(_L1_CACHE)
            expired = sum(1 for value in _L1_CACHE.values() if now > value.get("expires_at", 0))
            by_task_type: Dict[str, int] = {}
            for value in _L1_CACHE.values():
                task_type = value.get("task_type", "unknown")
                by_task_type[task_type] = by_task_type.get(task_type, 0) + 1

        return {
            "total_entries": total,
            "active_entries": total - expired,
            "expired_entries": expired,
            "by_task_type": by_task_type,
            "max_entries": settings.SEMANTIC_CACHE_L1_MAX_SIZE,
            "enabled": settings.SEMANTIC_CACHE_ENABLED,
            "l2_enabled": settings.SEMANTIC_CACHE_L2_ENABLED,
            "l2_task_types": sorted(self._l2_task_types()),
            "version": settings.SEMANTIC_CACHE_VERSION,
        }

    @staticmethod
    def _make_key(prompt: str, context: str, task_type: str) -> str:
        """Create an exact-match key from full inputs.

        Never truncate here. Design-doc prompts often share long prefixes; a
        truncated key can return another architecture's cached answer.
        """
        raw = json.dumps(
            {
                "version": settings.SEMANTIC_CACHE_VERSION,
                "task_type": task_type,
                "prompt": prompt,
                "context": context,
            },
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def _l1_get(key: str) -> Optional[str]:
        with _L1_LOCK:
            entry = _L1_CACHE.get(key)
            if entry is None:
                return None
            if time.time() > entry.get("expires_at", 0):
                del _L1_CACHE[key]
                return None
            entry["last_accessed_at"] = time.time()
            return entry["response"]

    @staticmethod
    def _l1_put(key: str, response: str, task_type: str, ttl_seconds: int = 86400):
        with _L1_LOCK:
            max_size = max(1, settings.SEMANTIC_CACHE_L1_MAX_SIZE)
            now = time.time()

            for expired_key in [
                existing_key for existing_key, value in _L1_CACHE.items()
                if now > value.get("expires_at", 0)
            ]:
                del _L1_CACHE[expired_key]

            while len(_L1_CACHE) >= max_size:
                lru_key = min(
                    _L1_CACHE,
                    key=lambda existing_key: _L1_CACHE[existing_key].get(
                        "last_accessed_at",
                        _L1_CACHE[existing_key].get("created_at", 0),
                    ),
                )
                del _L1_CACHE[lru_key]

            _L1_CACHE[key] = {
                "response": response,
                "task_type": task_type,
                "created_at": now,
                "last_accessed_at": now,
                "expires_at": now + ttl_seconds,
            }

    @staticmethod
    def _l2_task_types() -> set[str]:
        return {
            task.strip()
            for task in settings.SEMANTIC_CACHE_L2_TASK_TYPES.split(",")
            if task.strip()
        }

    def _l2_enabled_for_task(self, task_type: str) -> bool:
        if not settings.SEMANTIC_CACHE_ENABLED or not settings.SEMANTIC_CACHE_L2_ENABLED:
            return False
        allowed = self._l2_task_types()
        return "*" in allowed or task_type in allowed

    def _get_qdrant(self):
        if not settings.SEMANTIC_CACHE_ENABLED or not settings.SEMANTIC_CACHE_L2_ENABLED:
            return None
        if self._qdrant is None:
            try:
                from qdrant_client import QdrantClient
                self._qdrant = QdrantClient(url=settings.QDRANT_URL, timeout=10)
            except Exception as exc:
                logger.warning("[SemanticCache] Qdrant unavailable: %s", exc)
                self._qdrant = False
        return self._qdrant if self._qdrant is not False else None

    def _get_embedding_model(self):
        if not settings.SEMANTIC_CACHE_ENABLED or not settings.SEMANTIC_CACHE_L2_ENABLED:
            return None
        if self._embedding_model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._embedding_model = SentenceTransformer(settings.EMBEDDING_MODEL, device="cpu")
            except Exception as exc:
                logger.warning("[SemanticCache] Embedding model unavailable: %s", exc)
                self._embedding_model = False
        return self._embedding_model if self._embedding_model is not False else None

    def _ensure_collection(self) -> bool:
        client = self._get_qdrant()
        if not client:
            return False
        try:
            existing = {collection.name for collection in client.get_collections().collections}
            if self.CACHE_COLLECTION in existing:
                return True

            from qdrant_client.models import Distance, VectorParams
            model = self._get_embedding_model()
            if not model:
                return False
            dim = model.get_sentence_embedding_dimension()
            client.create_collection(
                collection_name=self.CACHE_COLLECTION,
                vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
            )
            logger.info("[SemanticCache] Created Qdrant collection '%s' (dim=%s)", self.CACHE_COLLECTION, dim)
            return True
        except Exception as exc:
            logger.warning("[SemanticCache] Collection setup failed: %s", exc)
            return False

    def _l2_get(self, prompt: str, context: str, task_type: str) -> Optional[str]:
        if not self._l2_enabled_for_task(task_type):
            return None

        client = self._get_qdrant()
        model = self._get_embedding_model()
        if not client or not model:
            return None

        try:
            if not self._ensure_collection():
                return None

            from qdrant_client.models import FieldCondition, Filter, MatchValue, PointIdsList

            query_text = f"{task_type}: {prompt[:500]} {context[:300]}"
            embedding = model.encode([query_text])[0].tolist()
            results = client.search(
                collection_name=self.CACHE_COLLECTION,
                query_vector=embedding,
                limit=1,
                query_filter=Filter(
                    must=[FieldCondition(key="task_type", match=MatchValue(value=task_type))]
                ),
                score_threshold=settings.SEMANTIC_CACHE_L2_SCORE_THRESHOLD,
            )

            if not results:
                return None

            hit = results[0]
            payload = hit.payload or {}
            expires_at = payload.get("expires_at", 0)
            if time.time() > expires_at:
                try:
                    client.delete(
                        collection_name=self.CACHE_COLLECTION,
                        points_selector=PointIdsList(points=[hit.id]),
                    )
                except Exception:
                    pass
                return None

            if payload.get("task_type") != task_type:
                return None
            if payload.get("cache_version") not in (None, settings.SEMANTIC_CACHE_VERSION):
                return None
            return payload.get("response")
        except Exception as exc:
            logger.debug("[SemanticCache] L2 search failed: %s", exc)
            return None

    def _l2_put(self, prompt: str, context: str, task_type: str, response: str, ttl_seconds: int):
        if not self._l2_enabled_for_task(task_type):
            return

        client = self._get_qdrant()
        model = self._get_embedding_model()
        if not client or not model:
            return

        try:
            if not self._ensure_collection():
                return

            import uuid
            from qdrant_client.models import PointStruct

            query_text = f"{task_type}: {prompt[:500]} {context[:300]}"
            embedding = model.encode([query_text])[0].tolist()
            cache_key = self._make_key(prompt, context, task_type)
            point_id = str(uuid.UUID(cache_key[:32]))
            now = time.time()

            point = PointStruct(
                id=point_id,
                vector=embedding,
                payload={
                    "cache_version": settings.SEMANTIC_CACHE_VERSION,
                    "task_type": task_type,
                    "response": response,
                    "prompt_preview": prompt[:200],
                    "created_at": now,
                    "expires_at": now + ttl_seconds,
                },
            )
            client.upsert(collection_name=self.CACHE_COLLECTION, points=[point])
            logger.debug("[SemanticCache] L2 stored | task=%s | ttl=%ss", task_type, ttl_seconds)
        except Exception as exc:
            logger.debug("[SemanticCache] L2 store failed: %s", exc)

    def _l2_clear_all(self):
        client = self._get_qdrant()
        if not client:
            return
        try:
            client.delete_collection(self.CACHE_COLLECTION)
            logger.info("[SemanticCache] L2 collection deleted")
        except Exception:
            pass

    def _l2_clear_task_type(self, task_type: str):
        client = self._get_qdrant()
        if not client:
            return
        try:
            from qdrant_client.models import FieldCondition, Filter, MatchValue
            client.delete(
                collection_name=self.CACHE_COLLECTION,
                points_selector=Filter(
                    must=[FieldCondition(key="task_type", match=MatchValue(value=task_type))]
                ),
            )
            logger.info("[SemanticCache] L2 invalidated task_type=%s", task_type)
        except Exception as exc:
            logger.debug("[SemanticCache] L2 task invalidation failed: %s", exc)


_cache_instance: Optional[SemanticCache] = None


def get_cache() -> SemanticCache:
    """Get the global semantic cache singleton."""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = SemanticCache()
    return _cache_instance
