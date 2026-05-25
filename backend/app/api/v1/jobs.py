# 🟢 BEGINNER: Standard library imports for file handling, JSON, time, UUID generation, async, and logging.
import re
import json
import time
import uuid
import asyncio
import logging
from pathlib import Path

# 🟢 BEGINNER: FastAPI imports. APIRouter = groups of endpoints; HTTPException = sends error responses;
# BackgroundTasks = runs code after the HTTP response is sent; UploadFile = handles uploaded files.
from fastapi import APIRouter, HTTPException, BackgroundTasks, UploadFile, File, Form, Query, Body
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

# 🟢 BEGINNER: Import centralized config to get upload directories and credentials.
from app.core.config import settings

# 🟢 BEGINNER: Logger for this module. Messages appear with [jobs] prefix.
logger = logging.getLogger(__name__)

# 🟢 BEGINNER: Create a router. All endpoints in this file will be prefixed with /api/v1/jobs.
router = APIRouter()


@router.post("/suggest-prompt")
async def suggest_terraform_prompt(
    rough_prompt: str = Body(...),
    cloud_provider: str = Body("aws"),
    detected_resources: list[str] = Body([])
):
    try:
        from app.services.haiku_service import HaikuService

        if not rough_prompt or not rough_prompt.strip():
            raise HTTPException(status_code=400, detail="rough_prompt is required")
        if len(rough_prompt) > 10_000:
            raise HTTPException(status_code=400, detail="rough_prompt is too long (max 10000 chars)")
        if cloud_provider not in {"aws", "azure", "gcp"}:
            raise HTTPException(status_code=400, detail="cloud_provider must be one of aws|azure|gcp")

        haiku = HaikuService()
        suggestions = haiku.suggest_terraform_prompt(rough_prompt, cloud_provider, detected_resources)
        return {"suggestions": suggestions}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[suggest-prompt] Failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal error occurred. Please try again later.")

# ─────────────────────────────────────────────────
# Persistent job store — survives uvicorn --reload and server restarts.
# Backed by storage/job_store/pipeline.json on disk.
# ─────────────────────────────────────────────────
from app.core.job_store import JobStore
_jobs: dict[str, dict] = JobStore("pipeline")

# ─────────────────────────────────────────────────
# 🟢 BEGINNER: Service singletons — created once, reused across all requests.
# "Lazy init" means the first call creates the object (e.g., connects to AWS Bedrock);
# every later call reuses the same instance. This saves 100-500 ms per request.
# ─────────────────────────────────────────────────
_design_doc_generator = None
_terraform_chat_service = None


def _get_design_doc_generator():
    """Lazy singleton getter for the design document AI service."""
    global _design_doc_generator
    if _design_doc_generator is None:
        from app.services.design_doc_service import DesignDocGenerator
        _design_doc_generator = DesignDocGenerator()
    return _design_doc_generator


def _get_terraform_chat_service():
    """Lazy singleton getter for the Terraform chat AI service."""
    global _terraform_chat_service
    if _terraform_chat_service is None:
        from app.services.terraform_chat import TerraformChatService
        _terraform_chat_service = TerraformChatService()
    return _terraform_chat_service


# 🟢 BEGINNER: Pydantic model defining the shape of the POST /analyse request body.
class FullPipelineRequest(BaseModel):
    file_path: str
    target_clouds: list[str] = ["aws"]


# 🟢 BEGINNER: Pydantic model defining the shape of the POST /terraform/chat/stream request body.
class ChatRequest(BaseModel):
    messages: list[dict]          # 🟢 BEGINNER: Array of chat messages (role + content).
    model: str = "claude-sonnet-4-6"  # 🟢 BEGINNER: Which AI model to use.
    analysis_id: str | None = None     # 🟢 BEGINNER: Optional job ID to load diagram context from.
    context: dict | None = None       # 🟢 BEGINNER: Optional diagram context dict.


# ─────────────────────────────────────────────────
# POST /api/v1/jobs — Upload + start full pipeline
# ─────────────────────────────────────────────────
# 🟢 BEGINNER: POST /api/v1/jobs/ — The main entry point. Uploads a file and starts the AI pipeline.
@router.post("/")
async def create_job(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    target_clouds: str = Form(default="aws"),
    user_prompt: str = Form(default=""),
    template_id: str = Form(default=""),
    company_id: str = Form(default=""),
):
    """
    Upload any file (image, PDF, DOCX, TXT, CSV, XLSX, MD) and start the multi-agent analysis pipeline.
    target_clouds: comma-separated, e.g. "aws" or "aws,azure"
    user_prompt: free-form text describing requirements, constraints, or architecture intent
    template_id: instruction template ID to use for design doc and terraform generation
    company_id: company ID for multi-tenant template scoping
    """
    logger.info(f"[Job] Creating new job with file: {file.filename}, template_id: {template_id}, company_id: {company_id}")

    # 🟢 BEGINNER: Validate file extension — allow any document, image, or spreadsheet type.
    allowed = {
        ".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf", ".svg", ".drawio",
        ".docx", ".txt", ".md", ".csv", ".xlsx", ".xls"
    }
    ext = Path(file.filename or "").suffix.lower()
    if ext not in allowed:
        logger.error(f"[Job] Invalid file type: {ext}")
        raise HTTPException(
            status_code=400,
            detail=f"File type '{ext}' not allowed. Accepted types: {', '.join(sorted(allowed))}"
        )

    # Validate upload size — read once and reuse the bytes
    max_bytes = settings.MAX_IMAGE_SIZE_MB * 1024 * 1024
    content = await file.read()
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum allowed size is {settings.MAX_IMAGE_SIZE_MB} MB."
        )

    # 🟢 BEGINNER: Save the uploaded file to disk with a unique job ID as the filename.
    # The on-disk filename is derived solely from job_id + the validated extension —
    # the user-supplied filename never touches the filesystem path.
    job_id = str(uuid.uuid4())[:8]
    upload_dir = Path(settings.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = upload_dir / f"{job_id}{ext}"

    file_path.write_bytes(content)
    logger.info(f"[Job:{job_id}] File saved to: {file_path}")

    # 🟢 BEGINNER: Parse the comma-separated cloud string into a clean list.
    clouds = [c.strip() for c in target_clouds.split(",") if c.strip()]
    logger.info(f"[Job:{job_id}] Target clouds: {clouds}")

    # Load template content if template_id is provided
    template_content = None
    logger.info(f"[Job:{job_id}] Template parameters - template_id: {template_id}, company_id: {company_id}")
    
    if template_id:
        try:
            from app.services.template_service import TemplateService
            template_service = TemplateService()
            
            # Load template with or without company_id
            template = template_service.get_template(template_id, company_id)
            if template:
                template_content = template.get("content")
                logger.info(f"[Job:{job_id}] ✅ Loaded template: {template_id} (company: {company_id or 'global'}), content length: {len(template_content)}")
            else:
                logger.warning(f"[Job:{job_id}] ❌ Template not found: template_id={template_id}, company_id={company_id}, using default")
        except Exception as e:
            logger.error(f"[Job:{job_id}] ❌ Failed to load template: {e}", exc_info=True)
    else:
        logger.info(f"[Job:{job_id}] No template_id provided, using default template")

    # 🟢 BEGINNER: Create the in-memory job record. Display filename is sanitized.
    safe_display_name = Path(file.filename or f"upload{ext}").name
    _jobs[job_id] = {
        "id": job_id,
        "filename": safe_display_name,
        "file_path": str(file_path),
        "target_clouds": clouds,
        "status": "running",
        "pipeline_stage": "UPLOADED",
        "user_prompt": user_prompt,
        "template_id": template_id,
        "company_id": company_id,
        "template_content": template_content,
        "vision_result": None,
        "graph_json": None,
        "design_docs_json": None,
        "terraform_prompts_json": None,
        "error_message": None,
        "created_at": time.time(),
    }

    # 🟢 BEGINNER: Start the AI pipeline in the BACKGROUND so the HTTP response returns immediately.
    logger.info(f"[Job:{job_id}] Starting multi-agent background pipeline")
    background_tasks.add_task(_run_pipeline, job_id)

    return {
        "job_id": job_id,
        "status": "running",
        "pipeline_stage": "UPLOADED",
        "target_clouds": clouds,
    }


# ─────────────────────────────────────────────────
# POST /api/v1/jobs/architecture-diagram — Generate architecture diagram
# ─────────────────────────────────────────────────
@router.post("/architecture-diagram")
async def generate_architecture_diagram(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    target_clouds: str = Form("aws"),
    diagram_type: str = Form("hld"),
    custom_instruction: str = Form(""),
    to_be_cloud: str = Form(""),
):
    """
    Generate architecture diagram from uploaded file using Docling + Vision.
    diagram_type: one of hld, lld, network, security, dr, cicd, kubernetes,
                  migration_wave, data_flow, observability, landing_zone, as_is
    """
    job_id = str(uuid.uuid4())[:8]
    logger.info(f"[ArchitectureDiagram] STARTED | job_id={job_id} | file={file.filename} | type={diagram_type}")

    allowed = {".png", ".jpg", ".jpeg", ".webp", ".pdf", ".svg", ".drawio", ".docx", ".txt", ".md"}
    ext = Path(file.filename or "").suffix.lower()
    if ext not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{ext}' not allowed for architecture diagrams. Accepted types: {', '.join(sorted(allowed))}"
        )

    content = await file.read()
    max_bytes = settings.MAX_IMAGE_SIZE_MB * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum allowed size is {settings.MAX_IMAGE_SIZE_MB} MB."
        )

    # Save uploaded file under a safe, sanitized filename
    upload_dir = Path("storage/uploads") / job_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    # Path(...).name strips any directory components from the user-supplied filename.
    raw_name = Path(file.filename or f"architecture{ext}").name
    # Whitelist filename characters to avoid surprises with shell/path metachars.
    safe_name = re.sub(r"[^A-Za-z0-9._\-]+", "_", raw_name) or f"architecture{ext}"
    file_path = upload_dir / safe_name
    if upload_dir.resolve() not in file_path.resolve().parents:
        raise HTTPException(status_code=400, detail="Invalid filename")

    file_path.write_bytes(content)
    logger.info(f"[ArchitectureDiagram:{job_id}] File saved to: {file_path}")

    _jobs[job_id] = {
        "id": job_id,
        "filename": safe_name,
        "file_path": str(file_path),
        "target_clouds": target_clouds,
        "diagram_type": diagram_type,
        "custom_instruction": custom_instruction,
        "to_be_cloud": to_be_cloud,
        "status": "running",
        "pipeline_stage": "ARCHITECTURE_UPLOADED",
        "progress": 10,
        "progress_log": [
            {"stage": "ARCHITECTURE_UPLOADED", "message": "File uploaded for architecture diagram generation.", "progress": 10, "timestamp": time.time()}
        ],
        "infra_graph": None,
        "drawio_xml": None,
        "error_message": None,
        "created_at": time.time(),
        "updated_at": time.time(),
    }

    background_tasks.add_task(_run_architecture_diagram_job, job_id)

    return {
        "job_id": job_id,
        "status": "running",
        "pipeline_stage": "ARCHITECTURE_UPLOADED",
        "progress": 10,
    }


@router.get("/architecture-diagram/{job_id}")
async def get_architecture_diagram_status(job_id: str):
    """Poll architecture diagram generation status and final editable draw.io XML."""
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Architecture diagram job {job_id} not found")

    return {
        "job_id": job_id,
        "status": job.get("status", "unknown"),
        "pipeline_stage": job.get("pipeline_stage", "UNKNOWN"),
        "progress": job.get("progress", 0),
        "progress_log": job.get("progress_log", []),
        "error_message": job.get("error_message"),
        "graph": job.get("infra_graph"),
        "drawio_xml": job.get("drawio_xml"),
        "filename": job.get("filename"),
        "updated_at": job.get("updated_at"),
    }


# ─────────────────────────────────────────────────
# GET /api/v1/jobs/:id/graph — Get architecture graph for a job
# ─────────────────────────────────────────────────
@router.get("/{job_id}/graph")
async def get_job_graph(job_id: str):
    """Get the architecture graph for a job."""
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    return {
        "job_id": job_id,
        "graph": job.get("infra_graph"),
        "drawio_xml": job.get("drawio_xml"),
    }


# ─────────────────────────────────────────────────
# POST /api/v1/jobs/:id/graph — Save updated architecture graph
# ─────────────────────────────────────────────────
@router.post("/{job_id}/graph")
async def save_job_graph(job_id: str, xml: str = Form(...)):
    """
    Save updated architecture graph from draw.io editor.
    Converts XML back to canonical graph and stores it.
    """
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    try:
        from app.services.drawio_converter import DrawIOConverter
        from app.models.infra_graph import CloudProvider

        # Convert XML back to canonical graph
        converter = DrawIOConverter()
        graph = converter.xml_to_graph(xml)

        # Update job storage
        job["infra_graph"] = graph.to_dict()
        job["drawio_xml"] = xml

        logger.info(f"[ArchitectureDiagram:{job_id}] Graph updated | nodes={len(graph.nodes)} | edges={len(graph.edges)}")

        return {
            "job_id": job_id,
            "status": "updated",
            "graph": graph.to_dict(),
        }

    except Exception as e:
        logger.error(f"[ArchitectureDiagram:{job_id}] Graph save failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Graph save failed: {e}")


# ─────────────────────────────────────────────────
# POST /api/v1/jobs/analyse — Start pipeline from file_path (frontend compat)
# ─────────────────────────────────────────────────
@router.post("/analyse")
async def analyse_from_path(
    request: FullPipelineRequest,
    background_tasks: BackgroundTasks,
):
    """Start pipeline from an already-uploaded file path.

    SECURITY: ``request.file_path`` is locked down to the configured upload
    directory. Any attempt to escape (path traversal, absolute path elsewhere)
    is rejected with HTTP 400. This prevents arbitrary local file read by
    untrusted callers.
    """
    upload_root = Path(settings.UPLOAD_DIR).resolve()
    try:
        candidate = Path(request.file_path).resolve()
    except (OSError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid file_path")

    # Reject if not inside the upload directory or if file is missing.
    if upload_root not in candidate.parents and candidate != upload_root:
        raise HTTPException(status_code=400, detail="file_path must reference an uploaded file")
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail="Uploaded file not found")

    job_id = str(uuid.uuid4())[:8]
    clouds = request.target_clouds

    _jobs[job_id] = {
        "id": job_id,
        "filename": candidate.name,
        "file_path": str(candidate),
        "target_clouds": clouds,
        "status": "running",
        "pipeline_stage": "UPLOADED",
        "vision_result": None,
        "graph_json": None,
        "error_message": None,
        "created_at": time.time(),
        "client_id": "default",
        "environment": "dev",
        "application_name": "",
        "region": "",
        "owner": "",
        "cost_center": "",
        "data_classification": "internal",
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
# 🟢 BEGINNER: The frontend calls this endpoint every 5 seconds to check if the pipeline is done.
@router.get("/{job_id}")
async def get_job(job_id: str):
    """Poll job status and results."""
    # 🟢 BEGINNER: Look up the job in our in-memory dictionary. If not found, return 404.
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
        "user_prompt": job.get("user_prompt", ""),
    }

    # 🟢 BEGINNER: Add vision analysis context pack if available (for ExtractedServices UI on the frontend).
    if job.get("graph_json"):
        response["context_pack"] = json.loads(job["graph_json"])

    # 🟢 BEGINNER: Add design docs if they're ready. Strip out large PDF bytes to keep the JSON small.
    if job.get("design_docs_json"):
        design_docs = json.loads(job["design_docs_json"])
        if isinstance(design_docs, dict):
            for cloud in design_docs:
                if isinstance(design_docs[cloud], dict) and "pdf_bytes" in design_docs[cloud]:
                    del design_docs[cloud]["pdf_bytes"]
            response["design_docs"] = design_docs
        else:
            # New single-doc format from LangGraph pipeline
            if isinstance(design_docs, dict) and "pdf_bytes" in design_docs:
                del design_docs["pdf_bytes"]
            response["design_docs"] = {"aws": design_docs} if design_docs else {}

    # Add terraform prompts if ready
    if job.get("terraform_prompts_json"):
        try:
            prompts = json.loads(job["terraform_prompts_json"])
            response["terraform_prompts"] = prompts
        except Exception:
            response["terraform_prompts"] = []
    elif job.get("design_docs_json"):
        # Fallback: extract inline terraform prompts from design_docs_json
        try:
            design_docs = json.loads(job["design_docs_json"])
            if isinstance(design_docs, dict):
                for cloud_key, doc in design_docs.items():
                    if isinstance(doc, dict) and doc.get("terraform_prompts"):
                        response["terraform_prompts"] = doc["terraform_prompts"]
                        break
        except Exception:
            pass

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
            design_docs = json.loads(job.get("design_docs_json") or "{}")
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
# 🟢 BEGINNER: SSE (Server-Sent Events) endpoint. The frontend connects and stays open while the AI writes the design doc.
# Instead of waiting for the entire document, text arrives piece by piece in real time.
@router.get("/{job_id}/stream-design-doc-sections")
async def stream_design_doc_sections(job_id: str, cloud: str = Query(default="aws")):
    """
    SSE endpoint. Client connects and receives section events:
      section_start → delta → delta → ... → section_end → [DONE]
    The client renders each section immediately without waiting for the whole document.
    
    CACHING: If the design doc was already generated for this job+cloud,
    replays the cached content as fast SSE events (no LLM call).
    """
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if not job.get("graph_json"):
        raise HTTPException(status_code=400, detail="Graph not available. Run vision analysis first.")

    # ── Cache check: if design doc already exists for this job, replay it instantly ──
    cached_docs = None
    if job.get("design_docs_json"):
        try:
            cached_docs = json.loads(job["design_docs_json"])
        except Exception:
            pass

    if cached_docs and cached_docs.get(cloud) and cached_docs[cloud].get("content"):
        # Replay cached design doc as fast SSE events (no LLM call needed)
        logger.info(f"[StreamDesignDocSections:{job_id}] Serving from CACHE (already generated)")
        cached_content = cached_docs[cloud]["content"]
        sections = cached_content.split("\n\n---\n\n")
        section_names = ["snapshot", "flows", "audit", "guidance", "terraform_prompts"]

        async def replay_cached():
            for i, section_text in enumerate(sections):
                name = section_names[i] if i < len(section_names) else f"section_{i}"
                title = name.replace("_", " ").title()
                yield f"data: {json.dumps({'type': 'section_start', 'section': name, 'title': title})}\n\n"
                # Send in chunks for smooth rendering
                chunk_size = 200
                for j in range(0, len(section_text), chunk_size):
                    yield f"data: {json.dumps({'type': 'delta', 'text': section_text[j:j+chunk_size]})}\n\n"
                yield f"data: {json.dumps({'type': 'section_end', 'section': name})}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            replay_cached(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "Content-Encoding": "identity"},
        )

    async def event_stream():
        try:
            import threading

            # Reconstruct the vision analysis format from the stored graph JSON.
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
            master_context = job.get("master_context")
            current_section = None
            section_texts = {}  # section_name → accumulated text

            # ── Thread + asyncio.Queue bridge ─────────────────────────────
            loop = asyncio.get_event_loop()
            queue: asyncio.Queue = asyncio.Queue()

            def _produce():
                """Run the sync boto3 generator in a background thread.
                Uses dynamic streaming when master_context is available (injects
                user prompt, template, governance, security rules into every prompt).
                Falls back to static streaming for legacy/architecture-diagram jobs."""
                try:
                    if master_context:
                        logger.info(f"[StreamDesignDocSections:{job_id}] Using DYNAMIC streaming with master_context")
                        gen = doc_gen.generate_design_document_streamed_dynamic(master_context, cloud)
                    else:
                        logger.info(f"[StreamDesignDocSections:{job_id}] Using static streaming (no master_context)")
                        gen = doc_gen.generate_design_document_streamed(vision_result, cloud)
                    for ch in gen:
                        loop.call_soon_threadsafe(queue.put_nowait, ch)
                except Exception as exc:
                    err_chunk = f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
                    loop.call_soon_threadsafe(queue.put_nowait, err_chunk)
                finally:
                    loop.call_soon_threadsafe(queue.put_nowait, None)

            thread = threading.Thread(target=_produce, daemon=True)
            thread.start()

            # 🟢 BEGINNER: Drain the queue asynchronously, forwarding each chunk to the SSE client immediately.
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
            content_parts = [section_texts.get(sec, "") for sec in ["snapshot", "flows", "audit", "guidance", "terraform_prompts"]]
            combined_content = "\n\n---\n\n".join(p for p in content_parts if p.strip())

            # Parse Terraform prompts — supports JSON array (new) or numbered list (legacy)
            tf_raw = section_texts.get("terraform_prompts", "")
            terraform_prompts_list = []

            # Try JSON array first (new format with priority, complexity, etc.)
            try:
                json_match = re.search(r'\[[\s\S]*\]', tf_raw)
                if json_match:
                    parsed = json.loads(json_match.group())
                    if isinstance(parsed, list) and parsed:
                        for item in parsed:
                            if isinstance(item, dict) and "prompt" in item:
                                terraform_prompts_list.append({
                                    "category": item.get("category", "general"),
                                    "prompt": item.get("prompt", ""),
                                    "priority": item.get("priority", "P1"),
                                    "complexity": item.get("complexity", "moderate"),
                                    "depends_on": item.get("depends_on", []),
                                    "estimated_resources": item.get("estimated_resources", 1),
                                })
            except (json.JSONDecodeError, Exception):
                pass

            # Fallback: legacy numbered list format (1. [Category] prompt text)
            if not terraform_prompts_list:
                merged_lines: list[str] = []
                for line in tf_raw.splitlines():
                    stripped = line.strip()
                    if not stripped:
                        continue
                    if re.match(r'^\d+\.\s*\[', stripped):
                        merged_lines.append(stripped)
                    elif merged_lines:
                        merged_lines[-1] += " " + stripped
                for line in merged_lines:
                    m = re.match(r'^\d+\.\s*\[([^\]]+)\]\s*(.+)', line)
                    if m:
                        terraform_prompts_list.append({
                            "category": m.group(1).strip(),
                            "prompt": m.group(2).strip(),
                            "priority": "P1",
                            "complexity": "moderate",
                            "depends_on": [],
                            "estimated_resources": 1,
                        })

            design_doc = {
                "title": f"{cloud.upper()} Architecture Design Document",
                "content": combined_content,
                "cloud": cloud.upper(),
                "architecture_summary": "Design document generated via streaming.",
                "component_count": len(components),
                "connection_count": len(connections),
                "sections": list(section_texts.keys()),
                "word_count": len(combined_content.split()),
                "terraform_prompts": terraform_prompts_list,
            }

            design_docs = json.loads(job.get("design_docs_json") or "{}")
            design_docs[cloud] = design_doc
            job["design_docs_json"] = json.dumps(design_docs)

            # Store terraform prompts at the top-level job field so get_job returns them
            if terraform_prompts_list and not job.get("terraform_prompts_json"):
                job["terraform_prompts_json"] = json.dumps(terraform_prompts_list)
                logger.info(f"[StreamDesignDocSections:{job_id}] Stored {len(terraform_prompts_list)} terraform prompts from streaming")

            # Only update status/stage if the background pipeline hasn't already progressed further
            advanced_stages = {"TERRAFORM_PROMPTS_GENERATING", "TERRAFORM_PROMPTS_GENERATED"}
            if job["status"] != "complete" and job.get("pipeline_stage") not in advanced_stages:
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
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Content-Encoding": "identity",   # ← bypass GZipMiddleware buffering
        }
    )
# POST /api/v1/jobs/terraform/chat/stream — SSE streaming chat
# ─────────────────────────────────────────────────
# 🟢 BEGINNER: The Terraform chat endpoint. Frontend sends chat messages; backend streams AI responses back.
@router.post("/terraform/chat/stream")
async def terraform_chat_stream(body: ChatRequest):
    """Stream conversational Terraform generation via SSE."""
    service = _get_terraform_chat_service()

    # 🟢 BEGINNER: Build the diagram context so the AI knows what resources were detected.
    # If the frontend sent a context dict, use it. Otherwise, look up the job and extract from graph_json.
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
                "master_context": job.get("master_context", {}),
            }

    # 🟢 BEGINNER: Inner generator function. Yields SSE-formatted strings (data: {...}\n\n) for each text chunk.
    def generate():
        try:
            chunk_count = 0
            for chunk in service.chat(
                messages=body.messages,
                model=body.model,
                context=context,
                stream=True,
            ):
                chunk_count += 1
                yield f"data: {json.dumps({'text': chunk})}\n\n"
            logger.info(f"[TerraformChat] Stream completed | chunks={chunk_count} | model={body.model}")
        except Exception as e:
            logger.error(f"[TerraformChat] Stream error: {e}", exc_info=True)
            yield f"data: {json.dumps({'text': f'[Error] {str(e)}'})}\n\n"
        yield "data: [DONE]\n\n"  # 🟢 BEGINNER: Special sentinel tells the frontend to stop reading the stream.

    # 🟢 BEGINNER: Return a StreamingResponse with SSE headers. The connection stays open until the AI finishes.
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Content-Encoding": "identity",  # 🟢 BEGINNER: Disables gzip buffering so chunks arrive immediately.
        }
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
    Execute the multi-agent pipeline with parallelization.

    Phases:
      1. Detect file type
      2. Parse document (if doc — must run before image analysis)
      3. Run image analysis + prompt analysis IN PARALLEL (both hit LLM APIs)
      4. Fuse context
      5. Mark graph_ready → frontend starts streaming design doc NOW
      6. Generate design doc + terraform prompts in background
    """
    job = _jobs[job_id]
    logger.info(f"🚀🚀🚀 [PIPELINE] STARTED | job_id={job_id} | file={Path(job['file_path']).name}")
    logger.info(f"[Pipeline:{job_id}] Starting optimized multi-agent pipeline")

    try:
        file_path = job["file_path"]
        user_prompt = job.get("user_prompt", "")
        clouds = job["target_clouds"]

        # ── Phase 1: Detect file type ───────────────────────────────
        from app.agents.nodes.document_parser import detect_file_type
        file_type = detect_file_type(file_path)
        logger.info(f"📋 [PIPELINE] Phase 1 | job_id={job_id} | file_type={file_type}")
        logger.info(f"[Pipeline:{job_id}] File type: {file_type}")

        if file_type == "unsupported":
            job["status"] = "failed"
            job["pipeline_stage"] = "FAILED"
            job["error_message"] = (
                f"Unsupported file type: {file_type}. "
                f"Supported: images (PNG, JPG, SVG), documents (PDF, DOCX, TXT), spreadsheets (CSV, XLSX)."
            )
            return

        # ── Phase 2: Build initial state ────────────────────────────
        from app.agents.state import PipelineState
        state: PipelineState = {
            "job_id": job_id,
            "file_path": file_path,
            "file_type": file_type,
            "user_prompt": user_prompt,
            "target_clouds": clouds,
            "template_content": job.get("template_content", ""),
            "company_id": job.get("company_id", ""),
            "template_id": job.get("template_id", ""),
            "raw_text": "",
            "embedded_images": [],
            "image_analysis": {},
            "structured_requirements": {},
            "fused_context": {},
            "design_doc": {},
            "terraform_prompts": [],
            "status": "running",
            "pipeline_stage": "UPLOADED",
            "error": None,
        }

        # ── Phase 3: Parse document (for docs, must run before image analysis) ──
        if file_type in ("pdf", "docx", "text", "spreadsheet"):
            logger.info(f"📋 [PIPELINE] Phase 3 | job_id={job_id} | parsing_document")
            from app.agents.nodes.document_parser import parse_document
            state = parse_document(state)

        # ── Phase 4: Run image analysis + prompt analysis IN PARALLEL ──
        logger.info(f"📋 [PIPELINE] Phase 4 | job_id={job_id} | parallel_agents=ImageAnalyzer+PromptAnalyzer")
        from app.agents.nodes.image_analyzer import analyze_image
        from app.agents.nodes.prompt_analyzer import analyze_prompt

        job["pipeline_stage"] = "AGENTS_RUNNING"

        # Both nodes call LLM APIs (Gemini / Bedrock) — run concurrently in thread pool
        # Timeout after 180s to prevent infinite hangs on API failures
        image_task = asyncio.to_thread(analyze_image, state)
        prompt_task = asyncio.to_thread(analyze_prompt, state)

        try:
            image_result, prompt_result = await asyncio.wait_for(
                asyncio.gather(image_task, prompt_task),
                timeout=180  # 3 minutes max for both agents combined
            )
        except asyncio.TimeoutError:
            logger.error(f"[Pipeline:{job_id}] Agents timed out after 180s — using defaults")
            image_result = state  # fallback: no image analysis
            prompt_result = state  # fallback: no prompt analysis

        # Merge results (nodes write to non-overlapping keys)
        merged = {**state}
        for key, value in image_result.items():
            if key != "pipeline_stage":
                merged[key] = value
        for key, value in prompt_result.items():
            if key != "pipeline_stage":
                merged[key] = value
        merged["pipeline_stage"] = "IMAGE_AND_PROMPT_ANALYZED"
        job["pipeline_stage"] = "IMAGE_AND_PROMPT_ANALYZED"
        await asyncio.sleep(0.5)  # visibility pause for frontend polling

        # ── Phase 5: Fuse context ───────────────────────────────────
        logger.info(f"📋 [PIPELINE] Phase 5 | job_id={job_id} | fusing_context")
        from app.agents.nodes.context_fusion import fuse_context
        fused_state = fuse_context(merged)
        job["pipeline_stage"] = "CONTEXT_FUSED"
        await asyncio.sleep(0.5)  # visibility pause

        # ── Phase 5b: Haiku compression ─────────────────────────────
        logger.info(f"📋 [PIPELINE] Phase 5b | job_id={job_id} | compressing_context")
        from app.agents.nodes.haiku_compression import compress_context
        compressed_state = await asyncio.to_thread(compress_context, fused_state)
        job["pipeline_stage"] = "CONTEXT_COMPRESSED"
        await asyncio.sleep(0.3)

        # ── Phase 6: Mark graph ready — frontend can stream NOW! ────
        logger.info(f"📋 [PIPELINE] Phase 6 | job_id={job_id} | graph_ready → frontend streaming")
        job["graph_json"] = compressed_state.get("graph_json") or fused_state.get("graph_json")
        job["master_context"] = compressed_state.get("master_context", {})
        job["status"] = "graph_ready"
        job["pipeline_stage"] = "GRAPH_READY"
        logger.info(
            f"[Pipeline:{job_id}] Graph ready. "
            f"Frontend can start streaming design doc. "
            f"Continuing with terraform prompts in background."
        )
        await asyncio.sleep(0.5)  # visibility pause

        # ── DONE: Phase 7 (background design doc + terraform prompts) was REMOVED.
        # The frontend's SSE stream at /stream-design-doc-sections is now the
        # SOLE path for generating the design doc + terraform prompts. This
        # avoids the architectural bug where the pipeline ran a parallel
        # generation while the frontend ALSO opened an SSE stream — causing
        # 2x the LLM cost, 2x the latency, and race conditions on storage.
        #
        # Flow now:
        #   Phase 6: graph_ready → frontend polls and sees it → opens SSE
        #   SSE endpoint: generates design doc sections + terraform prompts
        #   SSE endpoint: stores result in job["design_docs_json"] on completion
        job["status"] = "graph_ready"  # frontend already saw this — no-op
        logger.info(f"✅✅✅ [PIPELINE] COMPLETED | job_id={job_id} | stage={job['pipeline_stage']} (design doc handled via SSE)")

    except Exception as e:
        job["status"] = "failed"
        job["pipeline_stage"] = "FAILED"
        job["error_message"] = str(e)
        logger.error(f"❌❌❌ [PIPELINE] FAILED | job_id={job_id} | error={e}", exc_info=True)


def _set_architecture_progress(job_id: str, stage: str, message: str, progress: int):
    """Update architecture diagram job progress for frontend polling and console tracing."""
    job = _jobs[job_id]
    job["pipeline_stage"] = stage
    job["progress"] = progress
    job["updated_at"] = time.time()
    job.setdefault("progress_log", []).append({
        "stage": stage,
        "message": message,
        "progress": progress,
        "timestamp": job["updated_at"],
    })
    logger.info(f"[ArchitectureDiagram:{job_id}] {stage} | {progress}% | {message}")


async def _run_architecture_diagram_job(job_id: str):
    """Background architecture diagram pipeline with pollable progress and master_context."""
    job = _jobs[job_id]

    try:
        from app.services.diagram_generator import DiagramGenerator

        # Resolve cloud provider from job
        provider_str = str(job.get("target_clouds", "aws")).split(",")[0].strip().lower()
        provider = "azure" if "azure" in provider_str else "gcp" if "gcp" in provider_str else "aws"

        # Resolve diagram type from job (default to hld)
        diagram_type = job.get("diagram_type", "hld")
        custom_instruction = job.get("custom_instruction", "")
        to_be_cloud = job.get("to_be_cloud", "")

        # For To-Be diagrams, use the to_be_cloud as the target provider
        if diagram_type == "to_be" and to_be_cloud:
            provider = to_be_cloud.strip().lower()
            provider = "azure" if "azure" in provider else "gcp" if "gcp" in provider else "aws"

        _set_architecture_progress(job_id, "ARCHITECTURE_PROVIDER_SELECTED",
                                   f"Generating {provider.upper()} {diagram_type.upper()} diagram…", 15)
        await asyncio.sleep(0)

        _set_architecture_progress(job_id, "ARCHITECTURE_EXTRACTING",
                                   "Extracting document text with Docling…", 25)

        generator = DiagramGenerator()

        _set_architecture_progress(job_id, "ARCHITECTURE_PARSING",
                                   "Parsing document structure and identifying components…", 35)
        await asyncio.sleep(0.2)

        _set_architecture_progress(job_id, "ARCHITECTURE_GENERATING",
                                   f"Claude is analysing the document and building the {diagram_type.replace('_', ' ').title()} diagram…", 45)

        # Start a background progress ticker so the user sees movement during the LLM call
        import asyncio as _asyncio

        progress_messages = [
            (55, "Mapping cloud services and relationships…"),
            (62, "Applying tier bands and layout rules…"),
            (70, "Adding security zones and network boundaries…"),
            (77, "Generating draw.io XML with provider icons…"),
            (83, "Validating diagram structure…"),
        ]

        async def _tick_progress():
            for pct, msg in progress_messages:
                await _asyncio.sleep(8)  # every 8s show next step
                if job.get("status") == "running":
                    _set_architecture_progress(job_id, "ARCHITECTURE_GENERATING", msg, pct)

        ticker = _asyncio.create_task(_tick_progress())

        try:
            result = await asyncio.to_thread(generator.generate, job["file_path"], provider, diagram_type, custom_instruction)
        finally:
            ticker.cancel()
            try:
                await ticker
            except _asyncio.CancelledError:
                pass

        if result.get("error") or not result.get("drawio_xml"):
            err = result.get("error", "No XML returned")
            logger.error(f"[ArchitectureDiagram:{job_id}] Generation failed: {err}")
            job["status"] = "failed"
            job["error_message"] = f"Diagram generation failed: {err}"
            _set_architecture_progress(job_id, "ARCHITECTURE_FAILED",
                                       f"Failed: {err}", 100)
            return

        xml_string  = result["drawio_xml"]
        components  = result.get("components") or []

        _set_architecture_progress(job_id, "ARCHITECTURE_GRAPH_EXTRACTED",
                                   f"Diagram ready — {len(components)} components identified.", 80)

        # Build master_context for downstream Terraform / design-doc pipeline
        master_context = {
            "cloud_provider": provider,
            "components": [
                {
                    "name":          c.get("id", ""),
                    "display_name":  c.get("label", ""),
                    "type":          c.get("service", c.get("type", "Other")),
                    "configuration": c.get("configuration", {}),
                    "confidence":    c.get("confidence", 0.8),
                }
                for c in components
            ],
            "connections": [],
            "metadata": {
                "cidrs": list(dict.fromkeys(
                    str(c.get("configuration", {}).get("cidr", ""))
                    for c in components if c.get("configuration", {}).get("cidr")
                )),
            },
            "pipeline": {
                "extraction_method": "langgraph:docling+claude",
                "component_count":   len(components),
            },
        }

        job["infra_graph"]    = {"nodes": components, "edges": [], "provider": provider}
        job["graph_json"]     = json.dumps({"nodes": components, "edges": [], "provider": provider})
        job["drawio_xml"]     = xml_string
        job["master_context"] = master_context
        job["status"]         = "completed"

        _set_architecture_progress(job_id, "DRAWIO_READY",
                                   "Editable architecture diagram is ready.", 100)

        logger.info(f"[ArchitectureDiagram:{job_id}] COMPLETED | provider={provider} "
                    f"| components={len(components)} | xml_chars={len(xml_string)}")

    except Exception as e:
        job["status"] = "failed"
        job["error_message"] = str(e)
        _set_architecture_progress(job_id, "ARCHITECTURE_FAILED",
                                   f"Architecture diagram generation failed: {e}", 100)
        logger.error(f"[ArchitectureDiagram:{job_id}] FAILED: {e}", exc_info=True)


