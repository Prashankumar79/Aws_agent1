"""
================================================================================
  backend/app/agents/nodes/haiku_compression.py  —  HAIKU COMPRESSION NODE
================================================================================

PURPOSE:
  LangGraph node that uses Haiku to compress high-token context (template, 
  image analysis, user prompt) into structured JSON before final generation.

WHY SEPARATE NODE:
  - Isolated responsibility
  - Easier debugging
  - Scalable
  - Reusable
  - Observable
  - Independently testable

CONNECTIONS TO OTHER FILES:
  • services/haiku_service.py → HaikuService for compression operations
  • state.py → PipelineState with master_context and raw_context
  • graph.py → Pipeline graph includes this node after context_fusion

IMPORTANT:
  This node COMPRESSES context for downstream generation.
  CRITICAL structured fields (cloud provider, subnet topology, IAM relationships, 
  database type, service names, dependency graph) are preserved uncompressed.
================================================================================
"""
import logging
from typing import Any

from app.agents.state import PipelineState

logger = logging.getLogger(__name__)


def compress_context(state: PipelineState) -> PipelineState:
    """
    LangGraph node: compress template, image analysis, and user prompt using Haiku.
    
    Compresses ONLY high-token noisy sections:
    - Template content (governance rules, terraform rules, naming standards, security, compliance)
    - Image analysis (components, relationships, networking, security topology, scaling)
    - User prompt (business requirements, infra expectations, compliance, HA/DR)
    
    Preserves CRITICAL structured fields uncompressed:
    - cloud provider
    - subnet topology
    - IAM relationships
    - database type
    - service names
    - dependency graph
    """
    import time
    start_time = time.time()
    
    job_id = state["job_id"]
    template_content = state.get("template_content") or ""
    image_analysis = state.get("image_analysis") or {}
    user_prompt = state.get("user_prompt") or ""
    fused_context = state.get("fused_context") or {}

    # Calculate input sizes
    template_size = len(template_content) if template_content else 0
    image_size = len(str(image_analysis)) if image_analysis else 0
    prompt_size = len(user_prompt) if user_prompt else 0
    fused_size = len(str(fused_context)) if fused_context else 0
    total_input_size = template_size + image_size + prompt_size + fused_size

    logger.info(f"🚀 [AGENT:HaikuCompression] STARTED  | job_id={job_id} | template_len={template_size} | img_size={image_size} | prompt_len={prompt_size} | fused_size={fused_size} | total={total_input_size}")

    # Import HaikuService
    from app.services.haiku_service import HaikuService
    haiku_service = HaikuService()

    # Import context storage (for debugging/audit)
    from app.services.context_storage import get_context_storage
    context_storage = get_context_storage()

    # Import tracer for detailed logging
    try:
        from app.utils.pipeline_tracer import get_tracer
        tracer = get_tracer(job_id)
        tracer.start_stage("haiku_compression", {"template_size": template_size, "image_size": image_size, "prompt_size": prompt_size, "fused_size": fused_size})
    except Exception:
        tracer = None

    # Step 1: Compress template content
    compressed_template = {}
    if template_content and template_content.strip():
        try:
            compressed_template = haiku_service.compress_template(template_content)
            compressed_size = len(str(compressed_template))
            logger.info(f"[HaikuCompression:{job_id}] Compressed template: {template_size} → {compressed_size} chars, ratio={template_size/compressed_size:.2f}x")
        except Exception as e:
            logger.error(f"[HaikuCompression:{job_id}] Template compression failed: {e}, using rule-based fallback")
            # Use rule-based extraction as last resort
            from app.services.haiku_service import HaikuService as _HS
            compressed_template = _HS._rule_based_template_extraction(template_content)
    elif not template_content and user_prompt and len(user_prompt) > 500:
        # If no template_content but user_prompt looks like a template (long, structured),
        # try to extract template rules from the user_prompt as well
        try:
            compressed_template = haiku_service.compress_template(user_prompt)
            logger.info(f"[HaikuCompression:{job_id}] Extracted template rules from user_prompt (no template_content provided)")
        except Exception as e:
            logger.warning(f"[HaikuCompression:{job_id}] Could not extract template from user_prompt: {e}")

    # Step 2: Compress image analysis
    compressed_image = {}
    if image_analysis and image_analysis.get("components"):
        try:
            compressed_image = haiku_service.compress_image_analysis(image_analysis)
            compressed_size = len(str(compressed_image))
            logger.info(f"[HaikuCompression:{job_id}] Compressed image: {image_size} → {compressed_size} chars, ratio={image_size/compressed_size:.2f}x")
        except Exception as e:
            logger.error(f"[HaikuCompression:{job_id}] Image compression failed: {e}")
            compressed_image = {}

    # Step 3: Compress user prompt
    compressed_prompt = {}
    if user_prompt and user_prompt.strip():
        try:
            compressed_prompt = haiku_service.compress_user_prompt(user_prompt)
            compressed_size = len(str(compressed_prompt))
            logger.info(f"[HaikuCompression:{job_id}] Compressed prompt: {prompt_size} → {compressed_size} chars, ratio={prompt_size/compressed_size:.2f}x")
        except Exception as e:
            logger.error(f"[HaikuCompression:{job_id}] User prompt compression failed: {e}")
            compressed_prompt = {}

    # Step 4: Preserve critical structured fields (DO NOT COMPRESS)
    critical_fields = {
        "cloud_provider": fused_context.get("cloud_provider"),
        "components": fused_context.get("components", []),
        "connections": fused_context.get("connections", []),
        "naming_convention": fused_context.get("naming_convention", {}),
        "component_count": fused_context.get("component_count", 0),
        "connection_count": fused_context.get("connection_count", 0),
    }

    # Step 5: Build master_context (compressed context for generation)
    master_context = {
        # From template compression (rich descriptive rules)
        "governance": compressed_template.get("governance", {}),
        "terraform_rules": compressed_template.get("terraform_rules", {}),
        "naming_standards": compressed_template.get("naming_standards", {}),
        "security": compressed_template.get("security", {}),
        "compliance": compressed_template.get("compliance", {}),
        # From image analysis compression (rich architecture intelligence)
        "architecture": compressed_image.get("architecture", {}),
        "data_flows": compressed_image.get("data_flows", []),
        "topology": compressed_image.get("topology", {}),
        "scaling": compressed_image.get("scaling", {}),
        "inferred_config": compressed_image.get("inferred_config", {}),
        # Legacy field — kept for backward compat with existing code
        "relationships": compressed_image.get("relationships", compressed_image.get("data_flows", [])),
        # From user prompt compression (rich requirements + raw intent)
        "raw_intent": compressed_prompt.get("raw_intent"),
        "requirements": compressed_prompt.get("requirements", {}),
        # Raw user prompt preserved for downstream LLMs to understand exact user words
        "user_prompt_raw": user_prompt,
        # Critical structured fields (preserved uncompressed)
        "critical_fields": critical_fields,
    }

    # Step 6: Store raw_context for debugging/audit
    raw_context = {
        "template_content": template_content,
        "image_analysis": image_analysis,
        "user_prompt": user_prompt,
        "fused_context": fused_context,
    }

    # Save raw_context to disk for debugging/audit (async, non-blocking)
    try:
        context_storage.save_raw_context(job_id, raw_context)
    except Exception as e:
        logger.warning(f"[HaikuCompression:{job_id}] Failed to save raw_context: {e}")

    # Calculate compression metrics
    master_size = len(str(master_context))
    raw_size = len(str(raw_context))
    compression_ratio = raw_size / master_size if master_size > 0 else 0
    reduction = (1 - master_size / raw_size) * 100 if raw_size > 0 else 0
    
    duration = time.time() - start_time
    logger.info(f"[HaikuCompression:{job_id}] Master context built: {len(master_context)} keys, raw_size={raw_size} → master_size={master_size}, ratio={compression_ratio:.2f}x, reduction={reduction:.1f}%, duration={duration:.2f}s")

    # Log to tracer if available
    if tracer:
        tracer.log_compression(raw_size, master_size, "haiku_compression")
        tracer.log_context_size("master_context", master_context)
        tracer.log_context_size("raw_context", raw_context)
        tracer.end_stage({"master_context": master_context, "raw_context": raw_context})

    result = {
        **state,
        "master_context": master_context,
        "raw_context": raw_context,
        "pipeline_stage": "CONTEXT_COMPRESSED",
    }

    logger.info(f"✅ [AGENT:HaikuCompression] COMPLETED | job_id={job_id} | duration={duration:.2f}s | compression_ratio={compression_ratio:.2f}x")
    return result
