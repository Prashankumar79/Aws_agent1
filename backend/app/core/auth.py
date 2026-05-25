"""
================================================================================
  backend/app/core/auth.py  —  OPTIONAL API-KEY AUTHENTICATION
================================================================================

PURPOSE:
  Provide a lightweight ``require_api_key`` FastAPI dependency that:
    • Allows ALL requests through when ``settings.API_KEY`` is empty (dev mode).
    • Requires the header ``X-API-Key: <value>`` to match when API_KEY is set.

  This protects the entire API surface (jobs, companies, templates, RAG)
  without forcing a full IdP integration.

USAGE (in main.py or routers):
    from app.core.auth import require_api_key
    app.include_router(jobs_v1.router, prefix="/api/v1/jobs", tags=["jobs-v1"],
                       dependencies=[Depends(require_api_key)])

PRODUCTION:
  Set API_KEY in your .env to a random 32+ character string. Rotate periodically.
================================================================================
"""

# 🟢 BEGINNER: hmac.compare_digest does a constant-time string comparison
# (prevents timing-attack leaks of the real key, byte by byte).
import hmac
import logging
from typing import Optional

from fastapi import Header, HTTPException, status

from app.core.config import settings

# 🟢 BEGINNER: Logger for this module. Messages appear with [Auth] prefix.
logger = logging.getLogger(__name__)

# 🟢 BEGINNER: Paths exempt from the API-key check. /health is needed by
# Kubernetes / load-balancer probes; / and /docs are convenience endpoints.
_PUBLIC_PATHS = {"/", "/health", "/health/agents", "/docs", "/redoc", "/openapi.json"}


async def require_api_key(
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
) -> None:
    """🟢 BEGINNER: FastAPI dependency that enforces the API key (when configured).

    No-op when ``settings.API_KEY`` is empty (typical in local development).
    """
    expected = settings.API_KEY
    if not expected:
        # 🟢 BEGINNER: API_KEY not configured → auth disabled. Useful for local dev.
        return

    if not x_api_key or not hmac.compare_digest(x_api_key, expected):
        # 🟢 BEGINNER: Log without echoing the supplied value to avoid leaking partial keys.
        logger.warning("[Auth] Rejected request: invalid or missing X-API-Key")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )
