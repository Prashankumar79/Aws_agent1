"""
================================================================================
  backend/app/api/v1/rag.py  —  RAG API ENDPOINTS
================================================================================

PURPOSE:
  API endpoints for the RAG chat feature.

ENDPOINTS:
  POST /api/v1/rag/index  - Index uploaded document
  GET  /api/v1/rag/index/{job_id} - Check indexing status
  POST /api/v1/rag/chat - Chat with indexed document (SSE streaming)
================================================================================
"""

import logging
import uuid
import time
from pathlib import Path
from typing import Dict

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.services.rag_service import RAGService
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

# 🟢 BEGINNER: One RAGService per process. The first chat call pays the model
# load cost (~5-10 s for BGE-M3 + a few seconds for the BM25 model); every
# subsequent call reuses the same warm singleton and stays sub-second.
_rag_service: RAGService | None = None


def _get_rag_service() -> RAGService:
    global _rag_service
    if _rag_service is None:
        _rag_service = RAGService()
    return _rag_service


# Persistent job store for RAG indexing jobs — survives uvicorn --reload
from app.core.job_store import JobStore
_rag_jobs: Dict[str, dict] = JobStore("rag")


class ChatRequest(BaseModel):
    query: str
    rag_job_id: str | None = None


@router.post("/index")
async def index_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
):
    """
    Index uploaded document for RAG chat.

    Returns job_id for tracking indexing progress.
    """
    job_id = str(uuid.uuid4())[:8]
    logger.info(f"[RAG] Indexing started | job_id={job_id} | file={file.filename}")

    # Validate file type
    allowed = {".pdf", ".docx", ".txt", ".md"}
    raw_name = Path(file.filename or "").name  # strip any directory components
    ext = Path(raw_name).suffix.lower()
    if ext not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{ext}' not allowed for RAG. Accepted: {', '.join(sorted(allowed))}"
        )

    # Validate size before reading the entire body into memory
    max_bytes = settings.MAX_IMAGE_SIZE_MB * 1024 * 1024
    content = await file.read()
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum allowed size is {settings.MAX_IMAGE_SIZE_MB} MB."
        )

    # Save uploaded file under a safe, derived filename (no path traversal possible)
    upload_dir = Path("storage/uploads") / job_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    safe_filename = f"document{ext}"
    file_path = upload_dir / safe_filename
    # Final guard: ensure the resolved path stays inside upload_dir
    if upload_dir.resolve() not in file_path.resolve().parents:
        raise HTTPException(status_code=400, detail="Invalid filename")
    file_path.write_bytes(content)

    # Store job state
    _rag_jobs[job_id] = {
        "job_id": job_id,
        "file_path": str(file_path),
        "filename": raw_name,
        "status": "indexing",
        "stage": "starting",
        "progress": 0,
        "error": None,
        "created_at": time.time(),
    }

    # Run indexing in background
    background_tasks.add_task(_run_indexing, job_id)

    return {
        "job_id": job_id,
        "status": "indexing",
        "message": "Document indexing started",
    }


@router.get("/index/{job_id}")
async def get_index_status(job_id: str):
    """
    Check RAG indexing job status.
    """
    job = _rag_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"RAG job {job_id} not found")

    return {
        "job_id": job["job_id"],
        "status": job["status"],
        "stage": job["stage"],
        "progress": job["progress"],
        "error": job.get("error"),
        "filename": job.get("filename"),
        "chunks_count": job.get("chunks_count", 0),
        "collection_name": job.get("collection_name"),
    }


@router.post("/chat")
async def chat(request: ChatRequest):
    """
    Chat with indexed document using pure retrieval RAG.
    Returns structured JSON with summary + ranked sources (no LLM, no streaming).
    """
    if not request.query or not request.query.strip():
        raise HTTPException(status_code=400, detail="Query is required")
    if len(request.query) > 4000:
        raise HTTPException(status_code=400, detail="Query is too long (max 4000 chars)")

    logger.info(f"[RAG] Chat request | query={request.query[:80]!r}")

    service = _get_rag_service()
    try:
        result = service.query(request.query)
        return result
    except Exception as e:
        logger.error(f"[RAG] Chat failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Retrieval failed: {e}")


def _run_indexing(job_id: str):
    """
    Run RAG indexing pipeline in background with granular progress updates.
    """
    job = _rag_jobs[job_id]
    file_path = job["file_path"]

    try:
        service = _get_rag_service()

        # Build initial state — pre-populate metadata with the original filename
        state = {
            "file_path": file_path,
            "query": None,
            "raw_text": "",
            "chunks": [],
            "metadata": {"original_filename": job.get("filename", "")},
            "embeddings": [],
            "indexed": False,
            "collection_name": settings.RAG_COLLECTION_NAME,
            "retrieved_nodes": [],
            "reranked_nodes": [],
            "context_str": "",
            "response": "",
            "sources": [],
            "error": None,
            "stage": "starting",
        }

        # Step 1: Parse document
        job["stage"] = "parsing document..."
        job["progress"] = 10
        logger.info(f"[RAG] job_id={job_id} | stage=parsing")
        state = service._parse_document(state)
        if state.get("error"):
            raise Exception(f"Parse failed: {state['error']}")

        # Step 2: Extract metadata
        job["stage"] = "extracting metadata..."
        job["progress"] = 25
        logger.info(f"[RAG] job_id={job_id} | stage=metadata")
        state = service._extract_metadata(state)
        if state.get("error"):
            raise Exception(f"Metadata failed: {state['error']}")

        # Step 3: Chunk & generate embeddings (model load may take minutes on first run)
        job["stage"] = "loading embedding model (first run may take 1-2 min)..."
        job["progress"] = 35
        logger.info(f"[RAG] job_id={job_id} | stage=embeddings")
        state = service._generate_embeddings(state)
        if state.get("error"):
            raise Exception(f"Embeddings failed: {state['error']}")

        # Step 4: Index in Qdrant
        job["stage"] = "indexing in vector database..."
        job["progress"] = 80
        logger.info(f"[RAG] job_id={job_id} | stage=qdrant")
        state = service._index_qdrant(state)
        if state.get("error"):
            raise Exception(f"Qdrant index failed: {state['error']}")

        # Done
        job["status"] = "indexed"
        job["stage"] = "completed"
        job["progress"] = 100
        job["collection_name"] = state.get("collection_name")
        job["chunks_count"] = len(state.get("chunks", []))
        logger.info(f"[RAG] Indexing completed | job_id={job_id} | chunks={job['chunks_count']}")

    except Exception as e:
        job["status"] = "failed"
        job["error"] = str(e)
        job["stage"] = "failed"
        logger.error(f"[RAG] Indexing crashed | job_id={job_id} | error={e}", exc_info=True)
