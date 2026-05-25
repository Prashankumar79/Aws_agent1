"""
================================================================================
  backend/app/agents/nodes/prompt_analyzer.py  —  USER PROMPT ANALYZER
================================================================================

PURPOSE:
  Parse the user's free-form text prompt into a structured requirements object
  using an LLM (AWS Bedrock Claude). This replaces the static client profile
  system with dynamic, user-provided requirements.

OUTPUT:
  Updates state with:
    - structured_requirements: dict with naming, tags, services, security, etc.
================================================================================
"""
import json
import logging
import re
from typing import Any

from app.agents.state import PipelineState
from app.services.bedrock_service import BedrockService

logger = logging.getLogger(__name__)

# Pydantic-style schema for the expected output (used in the LLM prompt)
REQUIREMENTS_SCHEMA = """
{
  "cloud_provider": "aws|azure|gcp (default: auto-detect)",
  "naming_convention": {
    "pattern": "e.g. {env}-{app}-{resource}",
    "lowercase": true|false,
    "separator": "-"
  },
  "mandatory_tags": {
    "Environment": "required",
    "Owner": "required"
  },
  "approved_services": ["EC2", "S3", "RDS"],
  "restricted_services": ["Lambda", "DynamoDB"],
  "security_rules": {
    "encryption_required": true|false,
    "public_ip_allowed": true|false,
    "ssh_from_internet_allowed": true|false,
    "multi_az_required": true|false
  },
  "network_rules": {
    "allowed_regions": ["us-east-1", "eu-west-1"],
    "required_vpc": true|false,
    "nat_gateway_required": true|false
  },
  "compliance_frameworks": ["SOC2", "PCI-DSS"],
  "deployment_preferences": {
    "style": "direct_resources|modules",
    "backend": "local|s3",
    "state_locking": true|false
  },
  "budget_constraints": {
    "max_monthly_estimate_usd": 0
  },
  "special_instructions": "Any free-form notes not covered above"
}
"""

PROMPT_TEMPLATE = """You are an expert cloud infrastructure requirement analyst.

A user has provided the following free-form request describing their cloud infrastructure needs, constraints, and preferences.

USER REQUEST:
{user_prompt}

USER'S SELECTED CLOUD PROVIDER: {target_cloud}

Your task: analyze the request and extract a structured requirements object.

Return ONLY a valid JSON object matching this schema (no markdown, no prose):

{schema}

Rules:
- If a field is not mentioned in the user request, set it to null or a sensible default.
- For "cloud_provider", use the USER'S SELECTED CLOUD PROVIDER above. Only return "auto-detect" if it says "not specified".
- For "special_instructions", capture any nuanced requirements that don't fit the structured fields.
- Be precise with service names (e.g., "AWS EC2", "Azure VM", "S3", "RDS").
"""


def analyze_prompt(state: PipelineState) -> PipelineState:
    """LangGraph node: parse user prompt into structured requirements."""
    job_id = state["job_id"]
    user_prompt = state.get("user_prompt", "")

    logger.info(f"🚀 [AGENT:PromptAnalyzer] STARTED  | job_id={job_id} | prompt_len={len(user_prompt)}")
    logger.info(f"[PIPELINE][analyze_prompt][{job_id}] ENTER | prompt_len={len(user_prompt)}")
    logger.info(f"[PromptAnalyzer:{job_id}] Analyzing user prompt ({len(user_prompt)} chars)")

    # If no prompt, return empty requirements with defaults
    if not user_prompt or not user_prompt.strip():
        logger.info(f"[PromptAnalyzer:{job_id}] Empty prompt, using defaults")
        result = {
            **state,
            "structured_requirements": _default_requirements(),
            "pipeline_stage": "PROMPT_ANALYZED",
        }
        logger.info(f"[PIPELINE][analyze_prompt][{job_id}] EXIT  | empty_prompt_defaults")
        logger.info(f"✅ [AGENT:PromptAnalyzer] COMPLETED | job_id={job_id} | mode=defaults (empty prompt)")
        return result

    try:
        bedrock = BedrockService()
        target_clouds = state.get("target_clouds", [])
        target_cloud = target_clouds[0] if target_clouds else "not specified"
        llm_prompt = PROMPT_TEMPLATE.format(
            user_prompt=user_prompt,
            target_cloud=target_cloud,
            schema=REQUIREMENTS_SCHEMA
        )

        messages = [{"role": "user", "content": llm_prompt}]
        response = bedrock.invoke(messages)

        # Parse JSON from response
        requirements = _extract_json(response)
        if not requirements:
            logger.warning(f"[PromptAnalyzer:{job_id}] Failed to parse JSON from LLM response, using defaults")
            requirements = _default_requirements()

        # Ensure all expected keys exist
        requirements = _merge_with_defaults(requirements)

        logger.info(f"[PromptAnalyzer:{job_id}] Extracted requirements: cloud={requirements.get('cloud_provider')}, services={len(requirements.get('approved_services', []))}")

        result = {
            **state,
            "structured_requirements": requirements,
            "pipeline_stage": "PROMPT_ANALYZED",
        }
        logger.info(f"[PIPELINE][analyze_prompt][{job_id}] EXIT  | cloud={requirements.get('cloud_provider')}, services={len(requirements.get('approved_services', []))}")
        logger.info(f"✅ [AGENT:PromptAnalyzer] COMPLETED | job_id={job_id} | cloud={requirements.get('cloud_provider')} | services={len(requirements.get('approved_services', []))}")
        return result

    except Exception as e:
        logger.error(f"[PromptAnalyzer:{job_id}] Error: {e}", exc_info=True)
        result = {
            **state,
            "structured_requirements": _default_requirements(),
            "pipeline_stage": "PROMPT_ANALYZED",
            "error": f"Prompt analysis failed: {e}",
        }
        logger.info(f"[PIPELINE][analyze_prompt][{job_id}] EXIT  | FAILED error={e}")
        logger.info(f"⚠️  [AGENT:PromptAnalyzer] COMPLETED (fallback) | job_id={job_id} | error={e}")
        return result


def _default_requirements() -> dict:
    """Default requirements when no prompt is provided or parsing fails."""
    return {
        "cloud_provider": "auto-detect",
        "naming_convention": {
            "pattern": "{env}-{app}-{resource}",
            "lowercase": True,
            "separator": "-"
        },
        "mandatory_tags": {},
        "approved_services": [],
        "restricted_services": [],
        "security_rules": {
            "encryption_required": False,
            "public_ip_allowed": True,
            "ssh_from_internet_allowed": True,
            "multi_az_required": False
        },
        "network_rules": {
            "allowed_regions": [],
            "required_vpc": True,
            "nat_gateway_required": False
        },
        "compliance_frameworks": [],
        "deployment_preferences": {
            "style": "direct_resources",
            "backend": "local",
            "state_locking": False
        },
        "budget_constraints": {
            "max_monthly_estimate_usd": 0
        },
        "special_instructions": ""
    }


def _merge_with_defaults(requirements: dict) -> dict:
    """Ensure all expected keys exist by merging with defaults."""
    defaults = _default_requirements()

    def deep_merge(base: dict, overlay: dict) -> dict:
        result = base.copy()
        for key, value in overlay.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    return deep_merge(defaults, requirements)


def _extract_json(text: str) -> dict | None:
    """Extract JSON object from LLM response text."""
    # Try to find JSON block
    json_match = re.search(r'\{[\s\S]*\}', text)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass
    return None
