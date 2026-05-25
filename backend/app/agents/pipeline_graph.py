"""
================================================================================
  backend/app/agents/pipeline_graph.py  —  COMPILED LANGGRAPH PIPELINE
================================================================================

PURPOSE:
  Defines and compiles the multi-agent pipeline as a LangGraph StateGraph.
  This is the central orchestrator that wires all agent nodes together.

USAGE:
  from app.agents.pipeline_graph import compiled_pipeline
  final_state = await compiled_pipeline.ainvoke(initial_state)

GRAPH:
  START → detect_file_type
          ├─ image  → analyze_image ─┐
          ├─ document → parse_document─┤
          └─ unsupported → error_node─┘
                              │
                        analyze_prompt (always runs in parallel with above)
                              │
                        fuse_context
                              │
                        haiku_compression (NEW)
                              │
                        generate_design_doc
                              │
                        generate_terraform_prompts
                              │
                        END
================================================================================
"""
import logging
from typing import Literal

from langgraph.graph import StateGraph, END

from app.agents.state import PipelineState
from app.agents.nodes.document_parser import detect_file_type, parse_document
from app.agents.nodes.image_analyzer import analyze_image
from app.agents.nodes.prompt_analyzer import analyze_prompt
from app.agents.nodes.context_fusion import fuse_context
from app.agents.nodes.haiku_compression import compress_context
from app.agents.nodes.design_doc_agent import generate_design_doc
from app.agents.nodes.terraform_prompt_agent import generate_terraform_prompts

logger = logging.getLogger(__name__)

# ── Conditional routing ─────────────────────────────────────────────────────


def _route_by_file_type(state: PipelineState) -> Literal["image", "document", "unsupported"]:
    """Route to the appropriate parser based on detected file type."""
    file_type = state.get("file_type", "unsupported")
    if file_type in ("image",):
        return "image"
    elif file_type in ("pdf", "docx", "text", "spreadsheet"):
        return "document"
    else:
        return "unsupported"


def _error_node(state: PipelineState) -> PipelineState:
    """Terminal error node for unsupported files."""
    job_id = state["job_id"]
    file_type = state.get("file_type", "unknown")
    logger.error(f"[PIPELINE][error_node][{job_id}] ENTER | file_type={file_type}")
    logger.error(f"[Pipeline:{job_id}] Unsupported file type: {file_type}")
    return {
        **state,
        "status": "failed",
        "pipeline_stage": "FAILED",
        "error": f"Unsupported file type: {file_type}. Supported: images (PNG, JPG, SVG, PDF), documents (PDF, DOCX, TXT, MD), spreadsheets (CSV, XLSX).",
    }


def _detect_file_type_node(state: PipelineState) -> PipelineState:
    """Wrapper node that logs and detects file type."""
    job_id = state["job_id"]
    file_path = state["file_path"]
    file_type = detect_file_type(file_path)
    logger.info(f"[PIPELINE][detect_file_type][{job_id}] ENTER | path={file_path}")
    logger.info(f"[PIPELINE][detect_file_type][{job_id}] EXIT  | detected={file_type}")
    return {**state, "file_type": file_type}


# ── Build the graph ─────────────────────────────────────────────────────────

workflow = StateGraph(PipelineState)

# Register nodes
workflow.add_node("detect_file_type", _detect_file_type_node)
workflow.add_node("parse_document", parse_document)
workflow.add_node("analyze_image", analyze_image)
workflow.add_node("analyze_prompt", analyze_prompt)
workflow.add_node("fuse_context", fuse_context)
workflow.add_node("haiku_compression", compress_context)
workflow.add_node("generate_design_doc", generate_design_doc)
workflow.add_node("generate_terraform_prompts", generate_terraform_prompts)
workflow.add_node("error_node", _error_node)

# Entry point
workflow.set_entry_point("detect_file_type")

# Conditional edges from detect_file_type
workflow.add_conditional_edges(
    "detect_file_type",
    _route_by_file_type,
    {
        "image": "analyze_image",
        "document": "parse_document",
        "unsupported": "error_node",
    }
)

# After document parse → analyze_image (to process any embedded images)
workflow.add_edge("parse_document", "analyze_image")

# After image analysis → analyze_prompt
workflow.add_edge("analyze_image", "analyze_prompt")

# After prompt analysis → fuse_context
workflow.add_edge("analyze_prompt", "fuse_context")

# After context fusion → haiku compression (NEW)
workflow.add_edge("fuse_context", "haiku_compression")

# After haiku compression → design doc
workflow.add_edge("haiku_compression", "generate_design_doc")

# After design doc → terraform prompts
workflow.add_edge("generate_design_doc", "generate_terraform_prompts")

# End states
workflow.add_edge("generate_terraform_prompts", END)
workflow.add_edge("error_node", END)

# Compile
_compiled = workflow.compile()

logger.info("[PipelineGraph] Multi-agent LangGraph pipeline compiled successfully")


class _LoggedPipeline:
    """Wrapper that adds top-level pipeline execution logging around compiled graph."""
    def __init__(self, graph):
        self._graph = graph

    def invoke(self, state: PipelineState, **kwargs):
        job_id = state.get("job_id", "unknown")
        logger.info(f"[PIPELINE][START][{job_id}] ================================")
        logger.info(f"[PIPELINE][START][{job_id}] file_path={state.get('file_path')}")
        logger.info(f"[PIPELINE][START][{job_id}] user_prompt_len={len(state.get('user_prompt', ''))}")
        logger.info(f"[PIPELINE][START][{job_id}] ================================")
        start_time = __import__('time').time()
        try:
            result = self._graph.invoke(state, **kwargs)
            elapsed = __import__('time').time() - start_time
            logger.info(f"[PIPELINE][DONE][{job_id}] ================================")
            logger.info(f"[PIPELINE][DONE][{job_id}] elapsed_seconds={elapsed:.2f}")
            logger.info(f"[PIPELINE][DONE][{job_id}] final_stage={result.get('pipeline_stage')}")
            logger.info(f"[PIPELINE][DONE][{job_id}] error={result.get('error') is not None}")
            logger.info(f"[PIPELINE][DONE][{job_id}] design_doc_words={result.get('design_doc', {}).get('word_count', 0)}")
            logger.info(f"[PIPELINE][DONE][{job_id}] terraform_prompts={len(result.get('terraform_prompts', []))}")
            logger.info(f"[PIPELINE][DONE][{job_id}] ================================")
            return result
        except Exception as e:
            elapsed = __import__('time').time() - start_time
            logger.error(f"[PIPELINE][FAIL][{job_id}] ================================")
            logger.error(f"[PIPELINE][FAIL][{job_id}] elapsed_seconds={elapsed:.2f}")
            logger.error(f"[PIPELINE][FAIL][{job_id}] error={e}", exc_info=True)
            logger.error(f"[PIPELINE][FAIL][{job_id}] ================================")
            raise


compiled_pipeline = _LoggedPipeline(_compiled)
