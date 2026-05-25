"""
================================================================================
  backend/app/api/v1/admin.py  —  ADMIN / MONITORING ENDPOINTS
================================================================================

PURPOSE:
  Internal monitoring endpoints for the LLM Gateway, circuit breakers,
  and semantic cache. Useful for dashboards, alerting, and debugging.

ENDPOINTS:
  GET /api/v1/admin/gateway-status  → daily spend, budget, circuit breaker states
  POST /api/v1/admin/cache/clear    → clear all or a specific task-type from cache
================================================================================
"""
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


# ── GET /api/v1/admin/gateway-status ─────────────────────────────────────────

@router.get("/gateway-status")
def gateway_status():
    """
    Returns current LLM Gateway health:
      - Daily spend vs budget
      - Circuit breaker state per model (sonnet / haiku / gemini)
      - Cache hit/miss stats (L1 in-memory size)
    """
    try:
        from app.core.llm_gateway import get_gateway
        from app.core.circuit_breaker import get_all_status
        from app.core.semantic_cache import get_cache

        usage = get_gateway().get_daily_usage()
        breakers = get_all_status()

        return {
            "budget": usage,
            "circuit_breakers": breakers,
            "cache": get_cache().stats(),
        }
    except Exception as e:
        logger.error(f"[Admin] gateway-status failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get gateway status: {e}")


# ── POST /api/v1/admin/cache/clear ───────────────────────────────────────────

class CacheClearRequest(BaseModel):
    task_type: Optional[str] = None  # If None, clears ALL cache


@router.post("/cache/clear")
def clear_cache(request: CacheClearRequest):
    """
    Invalidate semantic cache entries.
    - task_type=None → clears ALL cache (L1 + L2 Qdrant collection)
    - task_type="template_compression" → clears only that task type from L1
    """
    try:
        from app.core.semantic_cache import get_cache
        cache = get_cache()
        pattern = request.task_type or ""
        cache.invalidate(pattern)
        msg = f"Cache cleared for task_type='{pattern}'" if pattern else "All cache cleared"
        logger.info(f"[Admin] {msg}")
        return {"message": msg, "task_type": pattern or "all"}
    except Exception as e:
        logger.error(f"[Admin] cache/clear failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Cache clear failed: {e}")


# ── GET /api/v1/admin/circuit-breakers ───────────────────────────────────────

@router.get("/circuit-breakers")
def circuit_breakers():
    """Returns detailed circuit breaker state for all models."""
    try:
        from app.core.circuit_breaker import get_all_status
        return {"circuit_breakers": get_all_status()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
