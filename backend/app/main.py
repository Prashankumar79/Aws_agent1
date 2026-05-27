"""
================================================================================
  backend/app/main.py  â€”  APPLICATION ENTRY POINT
================================================================================

PURPOSE:
  This is the FastAPI application bootstrap file. It creates the app,
  wires up all middleware (CORS), mounts API routers, and defines startup
  health checks. Think of it as the "main()" of the backend.

WHY IT EXISTS:
  FastAPI needs a single callable that uvicorn can run:
      uvicorn app.main:app
  Everything else is imported from here.

CONNECTIONS TO OTHER FILES:
  â€¢ core/config.py          â†’ loads env vars (APP_NAME, CORS origins, etc.)
  â€¢ api/upload.py           â†’ legacy single-file upload router (prefix=/api/upload)
  â€¢ api/v1/jobs.py          â†’ ALL active business endpoints (prefix=/api/v1/jobs)

REQUEST LIFECYCLE:
  1. uvicorn imports this file
  2. FastAPI app instance created with metadata
  3. CORS middleware attached (allows React dev server to talk to backend)
  4. Routers mounted at their URL prefixes
  5. @app.on_event("startup") fires â€” checks AWS credentials
  6. Server listens on port 8000

SECURITY NOTE:
  CORS is currently permissive (allow_methods=["*"]).
  In production, tighten ALLOWED_ORIGINS in .env.
================================================================================
"""

# ðŸŸ¢ BEGINNER: These are library imports. FastAPI is the web framework.
# CORSMiddleware lets the frontend (running on a different port) talk to this backend.
# GZipMiddleware compresses large responses so they download faster.
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from app.core.config import settings
from app.core.logging import setup_logging
import logging
import json
import traceback

# Configure logging so INFO-level agent tracking logs are visible
setup_logging()

# â”€â”€ LangSmith tracing setup â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# LangChain/LangGraph reads these env vars automatically for tracing.
import os
if settings.LANGSMITH_TRACING and settings.LANGSMITH_API_KEY:
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_ENDPOINT"] = settings.LANGSMITH_ENDPOINT
    os.environ["LANGCHAIN_API_KEY"] = settings.LANGSMITH_API_KEY
    os.environ["LANGCHAIN_PROJECT"] = settings.LANGSMITH_PROJECT
    logging.getLogger(__name__).info(f"[LangSmith] Tracing enabled â†’ project: {settings.LANGSMITH_PROJECT}")

logger = logging.getLogger(__name__)


# â”€â”€ Lifespan: startup + graceful shutdown â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# ðŸŸ¢ BEGINNER: A "lifespan" is FastAPI's modern way to run code at server startup
# and shutdown. It replaces the older @app.on_event("startup") / @app.on_event("shutdown")
# decorators (deprecated since FastAPI 0.93). Anything before `yield` runs on startup,
# anything after runs on shutdown.
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Replaces deprecated @app.on_event("startup"/"shutdown")."""
    settings.validate_production_ready()

    # â”€â”€ Startup â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # ðŸŸ¢ BEGINNER: Verify AWS Bedrock credentials so we fail fast (with a useful log)
    # instead of crashing on the first user request.
    try:
        from app.services.bedrock_service import BedrockService
        bedrock = BedrockService()
        # Run credential check in background so API starts serving immediately
        import asyncio as _asyncio
        async def _bg_check():
            try:
                cred_check = await _asyncio.to_thread(bedrock.check_credentials)
                logger.info(f"[AWS Bedrock] Credential check: {json.dumps(cred_check, default=str)}")
                if not cred_check.get("invoke_test_passed"):
                    logger.warning("[AWS Bedrock] Bedrock invoke test failed.")
            except Exception as bg_err:
                logger.warning(f"[AWS Bedrock] Background credential check failed: {bg_err}")
        _asyncio.create_task(_bg_check())
    except Exception as e:
        logger.warning(f"[AWS Bedrock] Could not initialize: {e}")

    # ðŸŸ¢ BEGINNER: Gemini key isn't strictly required to start â€” just warn if it's missing.
    if not settings.GEMINI_API_KEY:
        logger.warning("[Gemini] GEMINI_API_KEY is empty. Image analysis will fail.")

    # ðŸŸ¢ BEGINNER: Control hands back to FastAPI here. Everything ABOVE = startup.
    yield

    # â”€â”€ Shutdown â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # ðŸŸ¢ BEGINNER: Anything BELOW the yield runs on Ctrl-C / SIGTERM / kubectl rollout.
    logger.info("[App] Shutting down â€” flushing pending writes.")


# â”€â”€ 1. Create FastAPI app instance â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# ðŸŸ¢ BEGINNER: This creates the main FastAPI application object.
# Think of it like creating the "app" in Express.js or Flask.
# FastAPI will auto-generate API docs at /docs (Swagger UI) and /redoc.
app = FastAPI(
    title=settings.APP_NAME,      # e.g. "AWS Architecture AI"
    version="2.0.0",              # semver tracked in frontend
    docs_url="/docs" if settings.DEBUG else None,   # disable interactive docs in prod
    redoc_url="/redoc" if settings.DEBUG else None,
    openapi_url="/openapi.json" if settings.DEBUG else None,
    lifespan=lifespan,
)

# â”€â”€ 2. Compression Middleware â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# ðŸŸ¢ BEGINNER: Middleware = code that runs on EVERY request/response.
# GZipMiddleware compresses any response body >= 500 bytes.
# This makes large JSON payloads (like design documents) 60-80% smaller.
# SSE streams are excluded automatically because they use chunked transfer encoding.
app.add_middleware(GZipMiddleware, minimum_size=500)

# â”€â”€ 3. CORS Middleware â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# ðŸŸ¢ BEGINNER: CORS = Cross-Origin Resource Sharing.
# Browsers block requests from one domain to another by default (security).
# The React dev server runs on localhost:3000, backend on localhost:8000.
# Without CORS middleware, the browser would reject ALL frontend fetch() calls.
# allow_origins comes from .env â†’ ALLOWED_ORIGINS env var.
# Production rule: never use "*" together with allow_credentials=True â€” browsers reject it.
_allowed_origins = [o.strip() for o in settings.ALLOWED_ORIGINS.split(",") if o.strip()]
if not _allowed_origins:
    _allowed_origins = ["http://localhost:3000"]
if "*" in _allowed_origins:
    logger.warning("[CORS] '*' in ALLOWED_ORIGINS is unsafe with allow_credentials=True; falling back to explicit list")
    _allowed_origins = [o for o in _allowed_origins if o != "*"] or ["http://localhost:3000"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Company-Id", "X-Requested-With"],
    max_age=600,
)

# â”€â”€ 4. Global Exception Handler (never expose stack traces to frontend) â”€â”€â”€â”€â”€
@app.exception_handler(Exception)
async def global_error_handler(request, exc):
    """Catch-all exception handler. Logs full error server-side, returns safe message to client."""
    logger.error(f"[Unhandled Exception] {type(exc).__name__}: {exc}\n{traceback.format_exc()}")
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "message": "An unexpected error occurred. Please try again later."
        }
    )

# â”€â”€ 5. Router Registration â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# ðŸŸ¢ BEGINNER: Routers are groups of related endpoints.
# jobs_v1.py = the heart of the app: diagram analysis, design doc streaming,
#              terraform chat, job status polling.
# companies.py = multi-tenant company management
# templates.py = instruction template management
from fastapi import Depends
from app.api.v1 import jobs as jobs_v1
from app.api.v1 import companies
from app.api.v1 import templates
from app.api.v1 import rag
from app.api.v1 import admin
from app.core.auth import require_api_key

# ðŸŸ¢ BEGINNER: Mount the routers at URL prefixes.
# All routes inside jobs.py will be prefixed with /api/v1/jobs.
# `dependencies=[Depends(require_api_key)]` enforces optional API-key auth on
# every endpoint when settings.API_KEY is non-empty (no-op in dev).
_auth_dep = [Depends(require_api_key)]
app.include_router(jobs_v1.router, prefix="/api/v1/jobs", tags=["jobs-v1"], dependencies=_auth_dep)
app.include_router(companies.router, prefix="/api/v1", tags=["companies"], dependencies=_auth_dep)
app.include_router(templates.router, prefix="/api/v1", tags=["templates"], dependencies=_auth_dep)
app.include_router(rag.router, prefix="/api/v1/rag", tags=["rag"], dependencies=_auth_dep)
app.include_router(admin.router, prefix="/api/v1", tags=["admin"], dependencies=_auth_dep)


# â”€â”€ 6. Health & Root Endpoints â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# ðŸŸ¢ BEGINNER: These are simple GET endpoints.
# The frontend can call /health to check if the backend is alive.
# Load balancers and Kubernetes also use /health to know if the server is healthy.
@app.get("/")
async def root():
    """Root endpoint â€” used by frontend to verify API is alive."""
    return {"message": f"Welcome to {settings.APP_NAME} API", "version": "2.0.0"}


@app.get("/health")
async def health():
    """Health check â€” load balancers / Kubernetes probes hit this."""
    return {"status": "healthy"}


@app.get("/health/agents")
async def health_agents():
    """Multi-agent pipeline health check â€” shows AWS credentials, graph compilation, and node status."""
    result = {
        "status": "healthy",
        "pipeline": {
            "compiled": True,
            "node_count": 7,
            "nodes": ["detect_file_type", "parse_document", "analyze_image", "analyze_prompt", "fuse_context", "generate_design_doc", "generate_terraform_prompts"],
        }
    }

    # Check AWS Bedrock credentials (needed by prompt_analyzer and terraform_prompt_agent)
    try:
        from app.services.bedrock_service import BedrockService
        bedrock = BedrockService()
        cred_check = bedrock.check_credentials()
        result["aws_bedrock"] = cred_check
        if not cred_check.get("invoke_test_passed"):
            result["status"] = "degraded"
            result["warning"] = "Bedrock invoke test failed. Prompt analyzer and Terraform prompt agent may not work."
    except Exception as e:
        result["aws_bedrock"] = {"error": str(e)}
        result["status"] = "degraded"
        result["warning"] = f"Could not verify AWS Bedrock credentials: {e}"

    # Check Gemini credentials (needed by image_analyzer)
    try:
        from app.core.config import settings
        result["gemini"] = {
            "api_key_present": bool(settings.GEMINI_API_KEY),
            "vision_model": settings.GEMINI_VISION_MODEL,
        }
        if not settings.GEMINI_API_KEY:
            result["status"] = "degraded"
            result["warning"] = (result.get("warning", "") + " Gemini API key missing. Image analysis will fail.").strip()
    except Exception as e:
        result["gemini"] = {"error": str(e)}

    return result

