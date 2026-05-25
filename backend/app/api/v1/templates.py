"""
================================================================================
  backend/app/api/v1/templates.py  —  INSTRUCTION TEMPLATE API ENDPOINTS
================================================================================

PURPOSE:
  REST API endpoints for managing instruction templates in the multi-tenant system.
  All endpoints require company_id for scoping (via the X-Company-Id header).

CONNECTIONS TO OTHER FILES:
  • services/template_service.py → TemplateService for business logic
  • main.py → Router registration
================================================================================
"""
# 🟢 BEGINNER: FastAPI bits. Header reads HTTP headers; Depends injects shared logic
# (we use it to enforce X-Company-Id once instead of repeating the check in every handler).
from fastapi import APIRouter, HTTPException, Header, Depends
from pydantic import BaseModel, Field
from typing import Optional
import logging

from app.services.template_service import TemplateService

# 🟢 BEGINNER: Logger for this module. Messages appear with [API] prefix in the console.
logger = logging.getLogger(__name__)

# 🟢 BEGINNER: Routes registered under /api/v1/templates.
router = APIRouter(prefix="/templates", tags=["templates"])
# 🟢 BEGINNER: One TemplateService shared across requests.
template_service = TemplateService()

# 🟢 BEGINNER: Generic error message — never echo raw exception strings to the client.
INTERNAL_ERROR_DETAIL = "An internal error occurred. Please try again later."


# 🟢 BEGINNER: Pydantic models with explicit length limits to prevent payload-flood attacks.
class TemplateCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field("", max_length=2000)
    content: str = Field(..., min_length=1, max_length=200_000)
    is_company_default: bool = False


class TemplateUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    content: Optional[str] = Field(None, min_length=1, max_length=200_000)
    is_company_default: Optional[bool] = None


class TemplateResponse(BaseModel):
    id: str
    company_id: Optional[str]
    name: str
    description: str
    content: str
    created_at: str
    updated_at: str
    is_default: bool
    is_company_default: bool


def get_company_id(x_company_id: Optional[str] = Header(None, alias="X-Company-Id")) -> str:
    """🟢 BEGINNER: FastAPI dependency — pulls X-Company-Id from headers.

    Using a dependency means every endpoint shares the SAME validation logic.
    No more copy-pasting `if not company_id: raise ...` in five places.
    """
    if not x_company_id:
        raise HTTPException(status_code=400, detail="X-Company-Id header is required")
    return x_company_id


# 🟢 BEGINNER: GET /api/v1/templates/ — list every template visible to this company.
@router.get("/", response_model=list[TemplateResponse])
def list_templates(company_id: str = Depends(get_company_id)):
    """List all templates for a company (including global defaults)."""
    try:
        templates = template_service.list_templates(company_id)
        logger.info(f"[API] Listed {len(templates)} templates for company {company_id}")
        return templates
    except HTTPException:
        raise
    except Exception as e:
        # 🟢 BEGINNER: Log the full stack trace server-side; return a generic message client-side.
        logger.error(f"[API] Failed to list templates: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=INTERNAL_ERROR_DETAIL)


# 🟢 BEGINNER: GET /api/v1/templates/{id} — fetch one template.
@router.get("/{template_id}", response_model=TemplateResponse)
def get_template(template_id: str, company_id: str = Depends(get_company_id)):
    """Get a specific template by ID."""
    try:
        template = template_service.get_template(template_id, company_id)
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")
        return template
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[API] Failed to get template {template_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=INTERNAL_ERROR_DETAIL)


# 🟢 BEGINNER: POST /api/v1/templates/ — create a new template under this company.
@router.post("/", response_model=TemplateResponse, status_code=201)
def create_template(request: TemplateCreateRequest, company_id: str = Depends(get_company_id)):
    """Create a new template for a company."""
    try:
        template = template_service.create_template(
            company_id=company_id,
            name=request.name,
            description=request.description,
            content=request.content,
            is_company_default=request.is_company_default,
        )
        logger.info(f"[API] Created template: {template['id']} for company {company_id}")
        return template
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[API] Failed to create template: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=INTERNAL_ERROR_DETAIL)


# 🟢 BEGINNER: PUT /api/v1/templates/{id} — partial update (any field can be omitted).
@router.put("/{template_id}", response_model=TemplateResponse)
def update_template(template_id: str, request: TemplateUpdateRequest, company_id: str = Depends(get_company_id)):
    """Update a template. Invalidates semantic cache for template_compression task type."""
    try:
        template = template_service.update_template(
            template_id=template_id,
            company_id=company_id,
            name=request.name,
            description=request.description,
            content=request.content,
            is_company_default=request.is_company_default,
        )
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")
        logger.info(f"[API] Updated template: {template_id}")

        # Invalidate semantic cache for template_compression so the updated template
        # content is used on the next pipeline run (not served from stale cache).
        try:
            from app.core.semantic_cache import get_cache
            get_cache().invalidate("template_compression")
            logger.info(f"[API] Invalidated semantic cache for template_compression after template update")
        except Exception as cache_err:
            logger.warning(f"[API] Cache invalidation failed (non-fatal): {cache_err}")

        return template
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[API] Failed to update template {template_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=INTERNAL_ERROR_DETAIL)


# 🟢 BEGINNER: DELETE /api/v1/templates/{id} — global defaults can't be deleted.
@router.delete("/{template_id}")
def delete_template(template_id: str, company_id: str = Depends(get_company_id)):
    """Delete a template (cannot delete global defaults)."""
    try:
        deleted = template_service.delete_template(template_id, company_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Template not found or cannot be deleted")
        logger.info(f"[API] Deleted template: {template_id}")
        return {"message": "Template deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[API] Failed to delete template {template_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=INTERNAL_ERROR_DETAIL)
