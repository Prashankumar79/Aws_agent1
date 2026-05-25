"""Tests for the LLM semantic cache safety guarantees."""

from app.core.config import settings
from app.core.semantic_cache import SemanticCache, _L1_CACHE


def test_exact_cache_key_uses_full_prompt(monkeypatch):
    monkeypatch.setattr(settings, "SEMANTIC_CACHE_ENABLED", True)
    monkeypatch.setattr(settings, "SEMANTIC_CACHE_L2_ENABLED", False)
    _L1_CACHE.clear()

    cache = SemanticCache()
    shared_prefix = "x" * 2500
    cache.put(shared_prefix + "first", "ctx", "design_doc_section", "first-response", ttl_seconds=60)

    assert cache.get(shared_prefix + "first", "ctx", "design_doc_section") == "first-response"
    assert cache.get(shared_prefix + "second", "ctx", "design_doc_section") is None


def test_l1_ttl_and_task_invalidation(monkeypatch):
    monkeypatch.setattr(settings, "SEMANTIC_CACHE_ENABLED", True)
    monkeypatch.setattr(settings, "SEMANTIC_CACHE_L2_ENABLED", False)
    _L1_CACHE.clear()

    cache = SemanticCache()
    cache.put("prompt-a", "ctx", "task_a", "a", ttl_seconds=60)
    cache.put("prompt-b", "ctx", "task_b", "b", ttl_seconds=60)
    cache.invalidate("task_a")

    assert cache.get("prompt-a", "ctx", "task_a") is None
    assert cache.get("prompt-b", "ctx", "task_b") == "b"

    cache.put("short-lived", "ctx", "task_b", "expired", ttl_seconds=-1)
    assert cache.get("short-lived", "ctx", "task_b") is None


def test_l2_semantic_cache_is_task_allowlisted(monkeypatch):
    monkeypatch.setattr(settings, "SEMANTIC_CACHE_ENABLED", True)
    monkeypatch.setattr(settings, "SEMANTIC_CACHE_L2_ENABLED", True)
    monkeypatch.setattr(settings, "SEMANTIC_CACHE_L2_TASK_TYPES", "template_compression,terraform_chat")

    cache = SemanticCache()

    assert cache._l2_enabled_for_task("template_compression") is True
    assert cache._l2_enabled_for_task("terraform_chat") is True
    assert cache._l2_enabled_for_task("design_doc_section") is False
    assert cache._l2_enabled_for_task("terraform_prompts") is False


def test_stats_do_not_expose_response_bodies(monkeypatch):
    monkeypatch.setattr(settings, "SEMANTIC_CACHE_ENABLED", True)
    monkeypatch.setattr(settings, "SEMANTIC_CACHE_L2_ENABLED", False)
    _L1_CACHE.clear()

    cache = SemanticCache()
    cache.put("prompt", "ctx", "task", "sensitive response body", ttl_seconds=60)
    stats = cache.stats()

    assert stats["total_entries"] == 1
    assert stats["by_task_type"] == {"task": 1}
    assert "sensitive response body" not in str(stats)
