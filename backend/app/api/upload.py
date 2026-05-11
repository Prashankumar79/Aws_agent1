"""
================================================================================
  backend/app/api/upload.py  —  LEGACY STANDALONE UPLOAD ENDPOINT
================================================================================

PURPOSE:
  Simple file upload router. Kept for backward compatibility.
  The newer workflow (UploadPage → AnalyseButton) uses POST /api/v1/jobs/
  in jobs.py instead, which uploads AND starts the pipeline in one call.

WHY IT EXISTS:
  Early versions of the app had a two-step upload:
      1. POST /api/upload/       → save file, return path
      2. POST /api/analyse       → start analysis from path
  Current app does both in one call to /api/v1/jobs/.
  This router is kept in case external tools want a simple upload-only endpoint.

CONNECTIONS TO OTHER FILES:
  • services/upload_service.py  → file validation & disk I/O
  • schemas/api_models.py       → UploadResponse Pydantic model

ENDPOINTS:
  POST /api/upload/  → UploadResponse {success, file_path, file_name, file_size}
================================================================================
"""

from fastapi import APIRouter, UploadFile, File, HTTPException
from app.services.upload_service import UploadService
from app.schemas.api_models import UploadResponse

# FastAPI router instance — mounted in main.py at prefix=/api/upload
router = APIRouter()

# Service instance handles validation and disk writes.
# Uploaded files land in ./uploads/ (relative to backend/ working dir).
upload_service = UploadService()


@router.post("/", response_model=UploadResponse)
async def upload_diagram(file: UploadFile = File(...)):
    """Upload a diagram file (PNG, JPG, PDF, SVG, Draw.io export).

    Args:
        file: The uploaded image file from multipart/form-data.

    Returns:
        UploadResponse with file path, name, and size in bytes.

    Raises:
        HTTPException 400: Invalid file type or file too large.
        HTTPException 500: Unexpected server error during save.
    """
    try:
        # ── Step 1: Validate file extension ───────────────────────────────
        # upload_service checks against ALLOWED_EXTENSIONS (.png, .jpg, etc.)
        if not upload_service.validate_file_type(file.filename):
            raise HTTPException(status_code=400, detail="Invalid file type")

        # ── Step 2: Validate file size ────────────────────────────────────
        # Read entire file into memory (diagrams are small, usually < 5 MB).
        file_content = await file.read()
        if not upload_service.validate_file_size(file_content):
            raise HTTPException(status_code=400, detail="File too large (max 50MB)")

        # ── Step 3: Persist to disk ─────────────────────────────────────
        # File is saved with a UUID filename: {uuid}.{ext}
        # This prevents filename collisions and path-traversal attacks.
        file_path = await upload_service.save_file(file_content, file.filename)

        return UploadResponse(
            success=True,
            message="File uploaded successfully",
            file_path=file_path,
            file_name=file.filename,
            file_size=len(file_content)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
