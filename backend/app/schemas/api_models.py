"""
================================================================================
  backend/app/schemas/api_models.py  —  PYDANTIC DATA MODELS
================================================================================

PURPOSE:
  Defines the shape of every HTTP request and response.
  FastAPI uses these classes for:
    • Automatic JSON parsing / serialization
    • Request validation (wrong type → 422 Unprocessable Entity)
    • OpenAPI schema generation (visible at /docs)

WHY IT EXISTS:
  Type safety at the API boundary. If a client sends `{success: "yes"}`
  instead of `{success: true}`, Pydantic rejects it BEFORE it hits business logic.

CONNECTIONS TO OTHER FILES:
  • api/upload.py   → response_model=UploadResponse
  • api/v1/jobs.py  → request/response models for ChatRequest, FullPipelineRequest
  • services/*.py   → return dicts that match these shapes

PATTERN: Data Transfer Object (DTO)
  Lightweight classes whose only job is to carry data between layers.
================================================================================
"""

from pydantic import BaseModel
from typing import Optional


class UploadResponse(BaseModel):
    """Response shape returned by POST /api/upload/

    Fields:
        success:   Whether the upload succeeded.
        message:   Human-readable status message.
        file_path: Server-side path where the file was saved.
        file_name: Original filename from the client.
        file_size: Size in bytes.
    """
    success: bool
    message: str
    file_path: Optional[str] = None
    file_name: Optional[str] = None
    file_size: Optional[int] = None


class AnalyseResponse(BaseModel):
    """Response shape for diagram analysis endpoints.

    Used by legacy /api/analyse routes. The current pipeline uses
    the _jobs dict directly (defined in api/v1/jobs.py).
    """
    success: bool
    message: str
    job_id: Optional[str] = None
    data: Optional[dict] = None


class DesignResponse(BaseModel):
    """Response shape for design document generation.

    Contains the fully generated document. In practice, the streaming
    endpoint (/stream-design-doc-sections) returns raw SSE instead of JSON.
    This model is used by the non-streaming fallback path.
    """
    success: bool
    message: str
    design_doc: Optional[dict] = None


class TerraformResponse(BaseModel):
    """Response shape for Terraform code generation.

    Similar to DesignResponse: the streaming chat returns SSE,
    while this model covers the non-streaming POST endpoint.
    """
    success: bool
    message: str
    terraform_code: Optional[str] = None
