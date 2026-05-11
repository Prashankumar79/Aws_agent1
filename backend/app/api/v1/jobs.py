import os
import json
import time
import uuid
import asyncio
import traceback
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, BackgroundTasks, UploadFile, File, Form, Query
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

# ─────────────────────────────────────────────────
# In-memory job store (production would use aiosqlite)
# ─────────────────────────────────────────────────
_jobs: dict[str, dict] = {}

# ─────────────────────────────────────────────────
# Service singletons — created once, reused across all requests.
# Lazy init: first call pays the setup cost (boto3/Gemini client
# handshake, model loading); every subsequent call reuses the same
# instance.  This shaves 100–500 ms off every analysis/chat/stream
# request that previously re-created these objects per call.
# ─────────────────────────────────────────────────
_design_doc_generator = None
_vision_service = None
_terraform_chat_service = None


def _get_design_doc_generator():
    global _design_doc_generator
    if _design_doc_generator is None:
        from app.services.design_doc_service import DesignDocGenerator
        _design_doc_generator = DesignDocGenerator()
    return _design_doc_generator


def _get_vision_service():
    global _vision_service
    if _vision_service is None:
        from app.services.vision_service import VisionService
        _vision_service = VisionService()
    return _vision_service


def _get_terraform_chat_service():
    global _terraform_chat_service
    if _terraform_chat_service is None:
        from app.services.terraform_chat import TerraformChatService
        _terraform_chat_service = TerraformChatService()
    return _terraform_chat_service


class FullPipelineRequest(BaseModel):
    file_path: str
    target_clouds: list[str] = ["aws"]


class ChatRequest(BaseModel):
    messages: list[dict]
    model: str = "claude-sonnet-4-6"
    analysis_id: str | None = None
    context: dict | None = None


# ─────────────────────────────────────────────────
# POST /api/v1/jobs — Upload + start full pipeline
# ─────────────────────────────────────────────────
@router.post("/")
async def create_job(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    target_clouds: str = Form(default="aws"),
):
    """
    Upload an architecture diagram and start the full analysis pipeline.
    target_clouds: comma-separated, e.g. "aws" or "aws,azure"
    """
    logger.info(f"[Job] Creating new job with file: {file.filename}")
    
    # Validate file
    allowed = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf"}
    ext = Path(file.filename).suffix.lower()
    if ext not in allowed:
        logger.error(f"[Job] Invalid file type: {ext}")
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}")

    # Save file
    job_id = str(uuid.uuid4())[:8]
    upload_dir = Path(settings.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = upload_dir / f"{job_id}{ext}"

    content = await file.read()
    file_path.write_bytes(content)
    logger.info(f"[Job:{job_id}] File saved to: {file_path}")

    clouds = [c.strip() for c in target_clouds.split(",") if c.strip()]
    logger.info(f"[Job:{job_id}] Target clouds: {clouds}")

    # Create job record
    _jobs[job_id] = {
        "id": job_id,
        "filename": file.filename,
        "file_path": str(file_path),
        "target_clouds": clouds,
        "status": "running",
        "pipeline_stage": "UPLOADED",
        "vision_result": None,
        "graph_json": None,
        "error_message": None,
        "created_at": time.time(),
    }

    # Run pipeline in background (design doc only)
    logger.info(f"[Job:{job_id}] Starting background pipeline")
    background_tasks.add_task(_run_pipeline, job_id)

    return {
        "job_id": job_id,
        "status": "running",
        "pipeline_stage": "UPLOADED",
        "target_clouds": clouds,
    }


# ─────────────────────────────────────────────────
# POST /api/v1/jobs/analyse — Start pipeline from file_path (frontend compat)
# ─────────────────────────────────────────────────
@router.post("/analyse")
async def analyse_from_path(
    request: FullPipelineRequest,
    background_tasks: BackgroundTasks,
):
    """Start pipeline from an already-uploaded file path."""
    job_id = str(uuid.uuid4())[:8]
    clouds = request.target_clouds

    _jobs[job_id] = {
        "id": job_id,
        "filename": Path(request.file_path).name,
        "file_path": request.file_path,
        "target_clouds": clouds,
        "status": "running",
        "pipeline_stage": "UPLOADED",
        "vision_result": None,
        "graph_json": None,
        "error_message": None,
        "created_at": time.time(),
    }

    background_tasks.add_task(_run_pipeline, job_id)

    return {
        "job_id": job_id,
        "status": "running",
        "pipeline_stage": "UPLOADED",
        "target_clouds": clouds,
    }


# ─────────────────────────────────────────────────
# GET /api/v1/jobs/{id}/design-doc/{cloud} — Download design doc markdown
# ─────────────────────────────────────────────────
@router.get("/{job_id}/design-doc/{cloud}")
async def download_design_doc_markdown(job_id: str, cloud: str):
    """
    Download the design document markdown for a specific cloud.
    """
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if not job.get("design_docs_json"):
        raise HTTPException(status_code=404, detail="Design document not available")

    design_docs = json.loads(job["design_docs_json"])
    if cloud not in design_docs:
        raise HTTPException(status_code=404, detail=f"Design document for {cloud} not available")

    design_doc = design_docs[cloud]
    content = design_doc.get("content", "")
    title = design_doc.get("title", "design-doc")

    # Sanitize filename to remove non-ASCII characters
    safe_title = title.replace(' ', '-').encode('ascii', 'ignore').decode('ascii')
    if not safe_title:
        safe_title = "design-doc"

    return Response(
        content=content,
        media_type="text/markdown",
        headers={
            "Content-Disposition": f"attachment; filename={cloud}-{safe_title}.md"
        }
    )


# ─────────────────────────────────────────────────
# GET /api/v1/jobs/{id} — Poll job status
# ─────────────────────────────────────────────────
@router.get("/{job_id}")
async def get_job(job_id: str):
    """Poll job status and results."""
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    response = {
        "job_id": job["id"],
        "status": job["status"],
        "pipeline_stage": job["pipeline_stage"],
        "filename": job.get("filename"),
        "target_clouds": job.get("target_clouds"),
        "error_message": job.get("error_message"),
    }

    # Add design docs if available (without PDF bytes to avoid large responses)
    if job.get("design_docs_json"):
        design_docs = json.loads(job["design_docs_json"])
        # Remove PDF bytes from response to avoid large JSON
        for cloud in design_docs:
            if "pdf_bytes" in design_docs[cloud]:
                del design_docs[cloud]["pdf_bytes"]
        response["design_docs"] = design_docs

    return response


# ─────────────────────────────────────────────────
# GET /api/v1/jobs/{id}/stream-design-doc — Stream design document generation
# ─────────────────────────────────────────────────
@router.get("/{job_id}/stream-design-doc")
async def stream_design_doc(job_id: str, cloud: str = Query(default="aws")):
    """Stream design document generation in real-time."""
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if not job.get("graph_json"):
        raise HTTPException(status_code=400, detail="Graph not available. Run vision analysis first.")

    async def event_generator():
        try:
            from app.services.design_doc_service import DesignDocGenerator
            from app.services.bedrock_service import BedrockService
            
            bedrock_service = BedrockService()
            doc_gen = DesignDocGenerator()
            
            # Get vision result
            graph = json.loads(job["graph_json"])
            vision_result = {"graph": graph, "raw": graph}
            
            # Stream design doc generation
            async for chunk in bedrock_service.generate_design_document_stream(
                context_pack={"graph": graph},
                enriched_context={}
            ):
                yield {
                    "event": "chunk",
                    "data": chunk
                }
            
            # After streaming, parse and store the complete design doc
            design_doc = await asyncio.to_thread(
                doc_gen.generate_design_document,
                vision_result["raw"],
                cloud
            )
            
            # Update job with design doc
            design_docs = json.loads(job.get("design_docs_json", "{}"))
            design_docs[cloud] = design_doc
            job["design_docs_json"] = json.dumps(design_docs)
            job["pipeline_stage"] = "DESIGN_DOC_GENERATED"
            
            yield {
                "event": "complete",
                "data": json.dumps({"success": True})
            }
            
        except Exception as e:
            logger.error(f"[StreamDesignDoc:{job_id}] Error: {e}", exc_info=True)
            yield {
                "event": "error",
                "data": json.dumps({"error": str(e)})
            }
    
    return EventSourceResponse(event_generator())


# ─────────────────────────────────────────────────
# GET /api/v1/jobs/{id}/stream-design-doc-sections — Stream design doc section by section
# ─────────────────────────────────────────────────
@router.get("/{job_id}/stream-design-doc-sections")
async def stream_design_doc_sections(job_id: str, cloud: str = Query(default="aws")):
    """
    SSE endpoint. Client connects and receives 4 events:
      section=snapshot → section=flows → section=audit → section=guidance → [DONE]
    Each event's data field is the parsed JSON for that section group.
    The client renders each section immediately without waiting for all 4.
    """
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if not job.get("graph_json"):
        raise HTTPException(status_code=400, detail="Graph not available. Run vision analysis first.")

    async def event_stream():
        try:
            import threading

            # Reconstruct vision-compatible format from stored graph
            graph = json.loads(job["graph_json"])
            components = []
            for node in graph.get("nodes", []):
                components.append({
                    "name": node.get("label") or node.get("id", "unnamed"),
                    "type": node.get("type") or node.get("service_type", "Other"),
                    "provider": node.get("cloud_provider", "aws"),
                    "confidence": node.get("confidence", 0.7),
                })
            connections = []
            for edge in graph.get("edges", []):
                connections.append({
                    "source": edge.get("source", ""),
                    "target": edge.get("target", ""),
                    "type": edge.get("connection_type") or edge.get("type", "CONNECTS_TO"),
                })
            vision_result = {"analysis": {"components": components, "connections": connections}}

            doc_gen = _get_design_doc_generator()
            current_section = None
            section_texts = {}  # section_name → accumulated text

            # ── Thread + asyncio.Queue bridge ─────────────────────────────
            # generate_design_document_streamed() calls synchronous boto3
            # APIs which would block uvicorn's event loop if called directly
            # from an async function. We push chunks into a queue from a
            # background thread so the event loop stays free for other requests.
            loop = asyncio.get_event_loop()
            queue: asyncio.Queue = asyncio.Queue(maxsize=128)

            def _produce():
                """Run the sync boto3 generator in a background thread."""
                try:
                    for ch in doc_gen.generate_design_document_streamed(vision_result, cloud):
                        loop.call_soon_threadsafe(queue.put_nowait, ch)
                except Exception as exc:
                    err_chunk = f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
                    loop.call_soon_threadsafe(queue.put_nowait, err_chunk)
                finally:
                    loop.call_soon_threadsafe(queue.put_nowait, None)  # sentinel

            thread = threading.Thread(target=_produce, daemon=True)
            thread.start()

            # Drain the queue asynchronously, forwarding each chunk to the client
            while True:
                chunk = await queue.get()
                if chunk is None:
                    break

                # Track section text for persistent storage after streaming
                if chunk.strip().startswith("data:") and "[DONE]" not in chunk:
                    try:
                        payload = json.loads(chunk.strip()[5:].strip())
                        evt_type = payload.get("type")
                        if evt_type == "section_start":
                            current_section = payload.get("section")
                            if current_section:
                                section_texts[current_section] = ""
                        elif evt_type == "delta" and current_section:
                            section_texts[current_section] += payload.get("text", "")
                    except Exception:
                        pass

                yield chunk  # forward to SSE client immediately

            # Store the complete design doc in the job for downstream use
            content_parts = [section_texts.get(sec, "") for sec in ["snapshot", "flows", "audit", "guidance"]]
            combined_content = "\n\n---\n\n".join(content_parts)
            design_doc = {
                "title": f"{cloud.upper()} Architecture Design Document",
                "content": combined_content,
                "cloud": cloud.upper(),
                "architecture_summary": "Design document generated via streaming.",
                "component_count": len(components),
                "connection_count": len(connections),
                "sections": list(section_texts.keys()),
                "word_count": len(combined_content.split()),
            }

            design_docs = json.loads(job.get("design_docs_json", "{}"))
            design_docs[cloud] = design_doc
            job["design_docs_json"] = json.dumps(design_docs)
            if job["status"] != "complete":
                job["status"] = "design_doc_ready"
            job["pipeline_stage"] = "DESIGN_DOC_GENERATED"
            logger.info(f"[StreamDesignDocSections:{job_id}] Stored design doc for {cloud}")

        except Exception as e:
            logger.error(f"[StreamDesignDocSections:{job_id}] Error: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )


# ─────────────────────────────────────────────────
# POST /api/v1/jobs/terraform/chat/stream — SSE streaming chat
# ─────────────────────────────────────────────────
@router.post("/terraform/chat/stream")
async def terraform_chat_stream(body: ChatRequest):
    """Stream conversational Terraform generation via SSE."""
    service = _get_terraform_chat_service()

    # Build context from diagram if analysis_id provided
    context = body.context or {}
    if body.analysis_id and not context:
        job = _jobs.get(body.analysis_id)
        if job and job.get("graph_json"):
            graph = json.loads(job["graph_json"])
            context = {
                "detected_resources": [
                    {"name": n.get("label", n.get("id", "unknown")), "service": n.get("service_type", "unknown")}
                    for n in graph.get("nodes", [])
                ],
                "detected_connections": [
                    {"from": e.get("source", ""), "to": e.get("target", "")}
                    for e in graph.get("edges", [])
                ],
                "cloud": job.get("target_clouds", ["aws"])[0],
            }

    def generate():
        for chunk in service.chat(
            messages=body.messages,
            model=body.model,
            context=context,
            stream=True,
        ):
            yield f"data: {json.dumps({'text': chunk})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


# ─────────────────────────────────────────────────
# POST /api/v1/jobs/terraform/chat — Non-streaming chat
# ─────────────────────────────────────────────────
@router.post("/terraform/chat")
async def terraform_chat(body: ChatRequest):
    """Non-streaming conversational Terraform generation."""
    service = _get_terraform_chat_service()
    context = body.context or {}

    full_text = ""
    for chunk in service.chat(body.messages, body.model, context, stream=False):
        full_text += chunk
    return {"response": full_text, "model": body.model}


# ─────────────────────────────────────────────────
# Background pipeline execution
# ─────────────────────────────────────────────────
async def _run_pipeline(job_id: str):
    """
    Execute the pipeline:
    Phase 1: Vision analysis (always runs)
    Phase 2: Design document streams on-demand via SSE
    """
    job = _jobs[job_id]
    logger.info(f"[Pipeline:{job_id}] Starting pipeline execution")

    try:
        file_path = job["file_path"]
        clouds = job["target_clouds"]
        logger.info(f"[Pipeline:{job_id}] File: {file_path}, Clouds: {clouds}")

        # ── Stage 1: Vision Analysis ──
        job["pipeline_stage"] = "VISION_RUNNING"
        logger.info(f"[Pipeline:{job_id}] Stage 1: Vision analysis starting")

        vision_result = await asyncio.to_thread(_run_vision_analysis_with_raw, file_path)
        graph = vision_result["graph"]
        job["graph_json"] = json.dumps(graph)
        job["pipeline_stage"] = "GRAPH_BUILT"
        job["status"] = "graph_ready"
        logger.info(f"[Pipeline:{job_id}] Vision complete - {len(graph.get('nodes', []))} nodes, {len(graph.get('edges', []))} edges")
        logger.info(f"[Pipeline:{job_id}] Graph ready — design doc will stream on-demand")

    except Exception as e:
        job["status"] = "failed"
        job["pipeline_stage"] = "FAILED"
        job["error_message"] = str(e)
        logger.error(f"[Pipeline:{job_id}] FAILED: {e}", exc_info=True)


def _run_vision_analysis_with_raw(file_path: str) -> dict:
    """
    Run Gemini Vision to extract architecture components from the diagram.
    Returns both graph and raw vision result for design doc generation.
    """
    vision = _get_vision_service()
    result = vision.analyze_diagram(file_path)

    if not result.get("success"):
        raise RuntimeError(f"Vision analysis failed: {result.get('error', 'unknown')}")

    analysis = result.get("analysis", {})

    # Convert vision output to graph format expected by IaCAgent
    nodes = []
    edges = []

    for component in analysis.get("components", []):
        nodes.append({
            "id": component.get("name", "unnamed"),
            "label": component.get("name", "unnamed"),
            "service_type": component.get("type", "Other"),
            "type": component.get("type", "Other"),
            "cloud_provider": component.get("provider", "aws"),
            "confidence": component.get("confidence", 0.7),
        })

    for conn in analysis.get("connections", []):
        edges.append({
            "source": conn.get("source", ""),
            "target": conn.get("target", ""),
            "connection_type": conn.get("type", "CONNECTS_TO"),
        })

    return {
        "graph": {"nodes": nodes, "edges": edges},
        "raw": result,
    }
