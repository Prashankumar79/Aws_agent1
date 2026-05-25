"""
================================================================================
  backend/app/api/v1/companies.py  —  COMPANY MANAGEMENT API ENDPOINTS
================================================================================

PURPOSE:
  REST API endpoints for managing companies in the multi-tenant system.

CONNECTIONS TO OTHER FILES:
  • services/company_service.py → CompanyService for business logic
  • main.py → Router registration
================================================================================
"""
# 🟢 BEGINNER: FastAPI bits. APIRouter groups endpoints; HTTPException sends error responses.
# Pydantic's Field lets us declare validation rules (min_length, max_length, etc.) inline.
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import logging

from app.services.company_service import CompanyService

# 🟢 BEGINNER: Logger for this module. Messages appear with [API] prefix in the console.
logger = logging.getLogger(__name__)

# 🟢 BEGINNER: Create the router. All routes below are registered under /api/v1/companies.
router = APIRouter(prefix="/companies", tags=["companies"])
# 🟢 BEGINNER: One service instance shared by every request (cheaper than re-instantiating).
company_service = CompanyService()

# 🟢 BEGINNER: Generic error message — never echo raw exception strings to the client.
# Stack traces and DB error text often leak file paths, AWS error codes, etc.
INTERNAL_ERROR_DETAIL = "An internal error occurred. Please try again later."


# 🟢 BEGINNER: Pydantic models define the expected JSON body shape and auto-validate inputs.
class CompanyCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)


class CompanyUpdateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)


class CompanyResponse(BaseModel):
    id: str
    name: str
    created_at: str
    updated_at: str


# 🟢 BEGINNER: POST /api/v1/companies/ — create a new company.
@router.post("/", response_model=CompanyResponse, status_code=201)
def create_company(request: CompanyCreateRequest):
    """Create a new company."""
    try:
        company = company_service.create_company(request.name)
        logger.info(f"[API] Created company: {company['id']}")
        return company
    except Exception as e:
        # 🟢 BEGINNER: Log the full traceback server-side, return a generic message to the client.
        logger.error(f"[API] Failed to create company: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=INTERNAL_ERROR_DETAIL)


# 🟢 BEGINNER: GET /api/v1/companies/{id} — fetch a single company.
@router.get("/{company_id}", response_model=CompanyResponse)
def get_company(company_id: str):
    """Get a company by ID."""
    try:
        company = company_service.get_company(company_id)
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")
        return company
    except HTTPException:
        # 🟢 BEGINNER: Re-raise HTTP exceptions so FastAPI returns the right status code.
        raise
    except Exception as e:
        logger.error(f"[API] Failed to get company {company_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=INTERNAL_ERROR_DETAIL)


# 🟢 BEGINNER: GET /api/v1/companies/ — list every company.
@router.get("/", response_model=list[CompanyResponse])
def list_companies():
    """List all companies."""
    try:
        companies = company_service.list_companies()
        logger.info(f"[API] Listed {len(companies)} companies")
        return companies
    except Exception as e:
        logger.error(f"[API] Failed to list companies: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=INTERNAL_ERROR_DETAIL)


# 🟢 BEGINNER: PUT /api/v1/companies/{id} — rename an existing company.
@router.put("/{company_id}", response_model=CompanyResponse)
def update_company(company_id: str, request: CompanyUpdateRequest):
    """Update a company name."""
    try:
        company = company_service.update_company(company_id, request.name)
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")
        logger.info(f"[API] Updated company: {company_id}")
        return company
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[API] Failed to update company {company_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=INTERNAL_ERROR_DETAIL)


# 🟢 BEGINNER: DELETE /api/v1/companies/{id} — remove a company.
@router.delete("/{company_id}")
def delete_company(company_id: str):
    """Delete a company."""
    try:
        deleted = company_service.delete_company(company_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Company not found")
        logger.info(f"[API] Deleted company: {company_id}")
        return {"message": "Company deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[API] Failed to delete company {company_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=INTERNAL_ERROR_DETAIL)
