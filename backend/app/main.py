"""
================================================================================
  backend/app/main.py  —  APPLICATION ENTRY POINT
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
  • core/config.py          → loads env vars (APP_NAME, CORS origins, etc.)
  • api/upload.py           → legacy single-file upload router (prefix=/api/upload)
  • api/v1/jobs.py          → ALL active business endpoints (prefix=/api/v1/jobs)
  • rag/knowledge_base.py   → ChromaDB startup health check only

REQUEST LIFECYCLE:
  1. uvicorn imports this file
  2. FastAPI app instance created with metadata
  3. CORS middleware attached (allows React dev server to talk to backend)
  4. Routers mounted at their URL prefixes
  5. @app.on_event("startup") fires — checks ChromaDB collections
  6. Server listens on port 8000

SECURITY NOTE:
  CORS is currently permissive (allow_methods=["*"]).
  In production, tighten ALLOWED_ORIGINS in .env.
================================================================================
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from app.core.config import settings

# ── 1. Create FastAPI app instance ───────────────────────────────────────────
# FastAPI auto-generates OpenAPI docs at /docs and /redoc
app = FastAPI(
    title=settings.APP_NAME,      # e.g. "AWS Architecture AI"
    version="2.0.0",              # semver tracked in frontend
    docs_url="/docs",             # Swagger UI
    redoc_url="/redoc",           # ReDoc UI
)

# ── 2. Compression Middleware ────────────────────────────────────────────────
# Compresses any response body ≥ 500 bytes with gzip.
# Large payloads (design doc JSON ~50-100 KB) shrink by 60-80%.
# SSE streams are excluded automatically (chunked transfer encoding).
app.add_middleware(GZipMiddleware, minimum_size=500)

# ── 3. CORS Middleware ───────────────────────────────────────────────────────
# The React dev server runs on localhost:5173 (Vite default).
# Without this, browser blocks all fetch() calls due to Same-Origin Policy.
# allow_origins comes from .env → ALLOWED_ORIGINS env var.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS.split(","),
    allow_credentials=True,
    allow_methods=["*"],          # GET, POST, OPTIONS, etc.
    allow_headers=["*"],          # Content-Type, Authorization, etc.
)

# ── 3. Router Registration ─────────────────────────────────────────────────
# upload.py  = legacy single-file upload endpoint (kept for compatibility)
# jobs_v1.py = the heart of the app: diagram analysis, design doc streaming,
#              terraform chat, job status polling.
from app.api import upload
from app.api.v1 import jobs as jobs_v1

app.include_router(upload.router, prefix="/api/upload", tags=["upload"])
app.include_router(jobs_v1.router, prefix="/api/v1/jobs", tags=["jobs-v1"])


# ── 4. Startup Event ─────────────────────────────────────────────────────
# Fires once when uvicorn starts the worker process.
# Checks whether ChromaDB vector database has enough ingested documents
# to support RAG (Retrieval-Augmented Generation). If collections are
# empty, the system falls back to template-based generation.
@app.on_event("startup")
async def startup_event():
    """Check ChromaDB knowledge base availability on startup."""
    try:
        from app.rag.knowledge_base import list_collection_stats
        stats = list_collection_stats()
        print(f"[Knowledge Base] {stats}")
        # Thresholds: if fewer than 50 AWS/Azure docs, warn developer
        if stats.get("aws_resources", 0) < 50:
            print("[Knowledge Base] WARNING: AWS docs not ingested. Run: python scripts/ingest_aws.py")
        if stats.get("azure_resources", 0) < 50:
            print("[Knowledge Base] WARNING: Azure docs not ingested. Run: python scripts/ingest_azure.py")
    except Exception as e:
        # ChromaDB might not be installed or DB file missing.
        # Non-fatal: the app works without RAG, just less smart.
        print(f"[Knowledge Base] ChromaDB not available: {e}. RAG disabled, using templates.")


# ── 5. Health & Root Endpoints ─────────────────────────────────────────────
@app.get("/")
async def root():
    """Root endpoint — used by frontend to verify API is alive."""
    return {"message": f"Welcome to {settings.APP_NAME} API", "version": "2.0.0"}


@app.get("/health")
async def health():
    """Health check — load balancers / Kubernetes probes hit this."""
    return {"status": "healthy"}
