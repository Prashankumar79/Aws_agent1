"""
================================================================================
  backend/app/agents/state.py  —  PIPELINE STATE DEFINITION
================================================================================

PURPOSE:
  TypedDict that defines the shared state passed between LangGraph nodes.
  Every node reads from and writes to this state.

WHY TYPEDDICT:
  LangGraph requires a state schema. TypedDict gives us type hints + runtime
  validation without the overhead of a full Pydantic model.
================================================================================
"""
from typing import TypedDict, Any


class PipelineState(TypedDict, total=False):
    """Shared state for the multi-agent pipeline."""

    job_id: str
    file_path: str
    file_type: str                # "image", "pdf", "docx", "text", "spreadsheet", "unsupported"
    user_prompt: str
    target_clouds: list[str]      # e.g. ["aws"], ["azure"], ["gcp"] — from frontend UI selection
    template_content: str         # Instruction template content for design doc and terraform generation
    template_id: str              # Instruction template ID for tracking
    company_id: str               # Company ID for multi-tenant template scoping

    # Parsed document outputs
    raw_text: str                 # Extracted text/tables from document
    embedded_images: list[str]    # Paths to extracted embedded images
    image_analysis: dict          # Vision output for images

    # Prompt analysis
    structured_requirements: dict  # Parsed from user_prompt

    # Fused context
    fused_context: dict           # Merged raw_text + image_analysis + requirements

    # Master context (compressed by Haiku) - used for generation
    master_context: dict          # Compressed context for design doc and terraform generation

    # Raw context (original) - used for debugging/audit only
    raw_context: dict            # Original uncompressed context for debugging

    # Generated outputs
    design_doc: dict              # {title, content, cloud, architecture_summary, ...}
    terraform_prompts: list[dict] # [{category, prompt}, ...]
    graph_json: str               # JSON string of {nodes, edges} for downstream services

    # Pipeline control
    status: str                   # "running", "complete", "failed"
    pipeline_stage: str
    error: str | None
