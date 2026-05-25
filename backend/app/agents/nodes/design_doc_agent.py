"""
================================================================================
  backend/app/agents/nodes/design_doc_agent.py  —  DESIGN DOCUMENT AGENT
================================================================================

PURPOSE:
  Generates the comprehensive 15-section architecture design document
  using the existing DesignDocGenerator, but fed with the fused_context
  from all upstream agents.

INPUT:
  state.fused_context — contains components, connections, requirements, etc.

OUTPUT:
  state.design_doc — {title, content, cloud, architecture_summary, ...}
================================================================================
"""
import logging
from typing import Any

from app.agents.state import PipelineState

logger = logging.getLogger(__name__)


def generate_design_doc(state: PipelineState) -> PipelineState:
    """LangGraph node: generate design document from master context (compressed by Haiku)."""
    job_id = state["job_id"]
    master = state.get("master_context", {})
    critical = master.get("critical_fields", {})
    cloud = critical.get("cloud_provider", "aws")

    logger.info(f"🚀 [AGENT:DesignDoc] STARTED  | job_id={job_id} | cloud={cloud} | comps={critical.get('component_count', 0)} | conns={critical.get('connection_count', 0)}")
    logger.info(f"[PIPELINE][generate_design_doc][{job_id}] ENTER | cloud={cloud}, comps={critical.get('component_count', 0)}, conns={critical.get('connection_count', 0)}")
    logger.info(f"[DesignDocAgent:{job_id}] Generating DYNAMIC design doc for cloud={cloud}")

    try:
        from app.services.design_doc_service import DesignDocGenerator
        doc_gen = DesignDocGenerator()

        # Use the new master-context-aware entry point (compressed by Haiku)
        design_doc = doc_gen.generate_from_fused_context(master_context=master, cloud=cloud)

        logger.info(f"[DesignDocAgent:{job_id}] Dynamic design doc generated: {design_doc.get('word_count', 0)} words")

        result = {
            **state,
            "design_doc": design_doc,
            "pipeline_stage": "DESIGN_DOC_GENERATED",
        }
        logger.info(f"[PIPELINE][generate_design_doc][{job_id}] EXIT  | words={design_doc.get('word_count', 0)}")
        logger.info(f"✅ [AGENT:DesignDoc] COMPLETED | job_id={job_id} | words={design_doc.get('word_count', 0)} | sections={len(design_doc.get('sections', []))}")
        return result

    except Exception as e:
        logger.error(f"[DesignDocAgent:{job_id}] Error: {e}", exc_info=True)
        result = {
            **state,
            "design_doc": {},
            "pipeline_stage": "DESIGN_DOC_FAILED",
            "error": f"Design doc generation failed: {e}",
        }
        logger.info(f"[PIPELINE][generate_design_doc][{job_id}] EXIT  | FAILED error={e}")
        logger.info(f"❌ [AGENT:DesignDoc] FAILED | job_id={job_id} | error={e}")
        return result
