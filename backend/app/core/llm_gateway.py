"""
================================================================================
  backend/app/core/llm_gateway.py — CENTRALIZED LLM GATEWAY
================================================================================

PURPOSE:
  Single entry point for ALL LLM calls in the application.
  Handles: caching → model routing → circuit breaking → budget → fallback.

USAGE:
  from app.core.llm_gateway import gateway
  response = gateway.call(
      messages=[{"role": "user", "content": "..."}],
      task_type="template_compression",
      max_tokens=3000,
  )

CONNECTIONS:
  • semantic_cache.py → checks/stores cached responses
  • circuit_breaker.py → checks model availability
  • config.py → budget limits, model IDs
  • bedrock_service.py / haiku_service.py → actual LLM calls
================================================================================
"""
import json
import logging
import time
from datetime import date
from typing import Dict, List, Optional, Any

from app.core.config import settings
from app.core.semantic_cache import get_cache
from app.core.circuit_breaker import get_breaker

logger = logging.getLogger(__name__)


# ── Task type → model routing ─────────────────────────────────────────────────
# Routing: Sonnet for quality-critical tasks, Haiku for simple/fast tasks.
# The fallback chain (sonnet→haiku→gemini) handles failures automatically.
TASK_ROUTING = {
    # Simple compression / extraction → Haiku (cheap, fast)
    "template_compression": "haiku",
    "image_compression": "haiku",
    "prompt_compression": "haiku",
    "prompt_suggestions": "haiku",
    "rag_synthesis": "haiku",

    # Quality-critical generation → Sonnet (better reasoning, richer output)
    "design_doc_section": "sonnet",
    "terraform_prompts": "sonnet",
    "architecture_diagram": "sonnet",
    "component_extraction": "sonnet",
    "prompt_analysis": "sonnet",

    # Chat / adaptive → Haiku first (fast iteration), Sonnet in fallback
    "terraform_chat": "haiku",
}

# ── Cache TTL per task type (seconds) ─────────────────────────────────────────
CACHE_TTL = {
    "template_compression": 7 * 86400,   # 7 days
    "image_compression": 24 * 3600,      # 24 hours
    "prompt_compression": 24 * 3600,     # 24 hours
    "prompt_suggestions": 3600,          # 1 hour
    "rag_synthesis": 4 * 3600,           # 4 hours
    "design_doc_section": 24 * 3600,     # 24 hours
    "terraform_prompts": 24 * 3600,      # 24 hours
    "architecture_diagram": 12 * 3600,   # 12 hours
    "terraform_chat": 3600,              # 1 hour
    "prompt_analysis": 24 * 3600,        # 24 hours
    "component_extraction": 24 * 3600,   # 24 hours
}

# ── Cost tracking ─────────────────────────────────────────────────────────────
COST_PER_1K_TOKENS = {
    "haiku_input": 0.001,
    "haiku_output": 0.005,
    "sonnet_input": 0.003,
    "sonnet_output": 0.015,
    "gemini_input": 0.0,     # Free tier
    "gemini_output": 0.0,    # Free tier
}

# Daily budget tracking (resets at midnight)
_daily_spend: Dict[str, float] = {"date": "", "total_usd": 0.0, "calls": 0}

def _get_daily_budget() -> float:
    """Read daily budget from settings (configurable via .env DAILY_BUDGET_USD)."""
    return settings.DAILY_BUDGET_USD


class LLMGateway:
    """Centralized LLM call router with caching, circuit breaking, and budget control."""

    # Bedrock connection tuning. Long enough for 16K-token responses, short
    # enough that a stuck connection fails before the user gives up.
    # Tuned from real diagram-generation P95 latency (~90s) plus 60s headroom.
    _BEDROCK_READ_TIMEOUT_SECONDS = 180
    _BEDROCK_CONNECT_TIMEOUT_SECONDS = 10
    # Bedrock retries on 5xx automatically. We disable boto3-level retries here
    # because the LLMGateway owns retry policy via the fallback chain. Without
    # this, a stuck stream would silently retry up to 3 times = 9 minutes.
    _BEDROCK_MAX_RETRIES = 0

    def __init__(self):
        self._bedrock_client = None
        self._haiku_client = None
        self._gemini_configured = False

    def _get_bedrock_client(self):
        """Return the process-wide reusable boto3 client.

        Delegates to core.bedrock_client.get_bedrock_client so every Bedrock
        caller in the app shares the SAME client and the SAME timeout/retry
        config. Single source of truth for connection tuning.
        """
        if self._bedrock_client is None:
            from app.core.bedrock_client import get_bedrock_client
            self._bedrock_client = get_bedrock_client()
            logger.info("[LLMGateway] Bedrock client wired via shared factory")
        return self._bedrock_client

    def call(
        self,
        messages: List[Dict[str, str]],
        task_type: str = "general",
        max_tokens: int = 4000,
        context: str = "",
        skip_cache: bool = False,
        stream: bool = False,
    ) -> str:
        """
        Single entry point for all LLM calls.

        Args:
            messages: Chat messages for the LLM
            task_type: Determines model routing and cache TTL
            max_tokens: Maximum response tokens
            context: Additional context for cache key generation
            skip_cache: Force bypass cache (for regeneration)
            stream: If True, returns a generator (not cached)

        Returns:
            LLM response text
        """
        prompt_text = messages[-1]["content"] if messages else ""

        # ── Step 1: Check cache (skip for streaming) ──────────────────────
        if not skip_cache and not stream:
            cache = get_cache()
            cached = cache.get(prompt_text, context, task_type)
            if cached is not None:
                self._track_cost(0, 0, "cache_hit")
                logger.info(f"[LLMGateway] {task_type} → cache HIT | source=cache")
                return cached

        # ── Step 2: Select model ──────────────────────────────────────────
        preferred_model = TASK_ROUTING.get(task_type, "sonnet")

        # ── Step 3: Check budget ──────────────────────────────────────────
        if self._is_over_budget():
            # Downgrade to cheapest model
            preferred_model = "haiku"
            logger.warning(f"[LLMGateway] Daily budget ${_get_daily_budget():.2f} exceeded — downgrading to haiku")

        # ── Step 4: Try models with circuit breaker ───────────────────────
        fallback_chain = self._get_fallback_chain(preferred_model)

        last_error = None
        for model in fallback_chain:
            breaker = get_breaker(model)
            if not breaker.is_available:
                logger.debug(f"[LLMGateway] {model} circuit OPEN — skipping")
                continue

            try:
                response = self._invoke_model(model, messages, max_tokens)
                breaker.record_success()

                # ── Step 5: Cache the response ────────────────────────────
                if not stream:
                    ttl = CACHE_TTL.get(task_type, 3600)
                    cache = get_cache()
                    cache.put(prompt_text, context, task_type, response, ttl)

                # ── Step 6: Track cost ────────────────────────────────────
                input_tokens = sum(len(m.get("content", "")) // 4 for m in messages)
                output_tokens = len(response) // 4
                self._track_cost(input_tokens, output_tokens, model)

                # NB: this is a FRESH call (not a cache hit). Cache hits
                # return earlier from the cache.get() branch above.
                logger.info(f"[LLMGateway] {task_type} → {model} | tokens_out≈{output_tokens} | source=fresh")
                return response

            except Exception as e:
                breaker.record_failure(str(e)[:100])
                last_error = e
                # Log timeouts at INFO not WARNING — they're expected on slow
                # bedrock paths and the fallback chain handles them.
                level_log = logger.info if "timeout" in str(e).lower() else logger.warning
                level_log(f"[LLMGateway] {model} failed: {str(e)[:200]} — trying next")
                continue

        # All models failed
        error_msg = f"All LLM models failed for task '{task_type}': {last_error}"
        logger.error(f"[LLMGateway] {error_msg}")
        raise RuntimeError(error_msg)

    # ── Model invocation ──────────────────────────────────────────────────

    def _invoke_model(self, model: str, messages: List[Dict], max_tokens: int) -> str:
        """Call the actual LLM API with LangSmith tracing.

        Uses traced_invoke() so every call appears in your LangSmith dashboard
        with full input/output, model ID, and latency.
        """
        if model in ("sonnet", "haiku"):
            from app.core.bedrock_client import traced_invoke
            model_id = settings.AWS_BEDROCK_MODEL if model == "sonnet" else settings.AWS_BEDROCK_HAIKU_MODEL
            return traced_invoke(
                model_id=model_id,
                messages=messages,
                max_tokens=max_tokens,
                task_name=f"llm_gateway_{model}",
            )

        elif model == "gemini":
            return self._invoke_gemini(messages, max_tokens)

        else:
            raise ValueError(f"Unknown model: {model}")

    def _invoke_gemini(self, messages: List[Dict], max_tokens: int) -> str:
        """Fallback to Gemini when Bedrock is down."""
        try:
            import google.generativeai as genai
            genai.configure(api_key=settings.GEMINI_API_KEY)
            model = genai.GenerativeModel(settings.GEMINI_TEXT_MODEL)
            # Combine messages into a single prompt for Gemini
            prompt = "\n".join(m.get("content", "") for m in messages)
            response = model.generate_content(prompt)
            return response.text
        except Exception as e:
            raise RuntimeError(f"Gemini fallback failed: {e}")

    # ── Fallback chain ────────────────────────────────────────────────────

    @staticmethod
    def _get_fallback_chain(preferred: str) -> List[str]:
        """Get ordered list of models to try."""
        if preferred == "sonnet":
            return ["sonnet", "haiku", "gemini"]
        elif preferred == "haiku":
            return ["haiku", "sonnet", "gemini"]
        else:
            return ["sonnet", "haiku", "gemini"]

    # ── Budget tracking ───────────────────────────────────────────────────

    @staticmethod
    def _is_over_budget() -> bool:
        """Check if daily budget is exceeded."""
        today = date.today().isoformat()
        if _daily_spend["date"] != today:
            _daily_spend["date"] = today
            _daily_spend["total_usd"] = 0.0
            _daily_spend["calls"] = 0
        return _daily_spend["total_usd"] >= _get_daily_budget()

    @staticmethod
    def _track_cost(input_tokens: int, output_tokens: int, model: str):
        """Track cost for budget enforcement."""
        today = date.today().isoformat()
        if _daily_spend["date"] != today:
            _daily_spend["date"] = today
            _daily_spend["total_usd"] = 0.0
            _daily_spend["calls"] = 0

        if model == "cache_hit":
            _daily_spend["calls"] += 1
            return

        input_cost = (input_tokens / 1000) * COST_PER_1K_TOKENS.get(f"{model}_input", 0.003)
        output_cost = (output_tokens / 1000) * COST_PER_1K_TOKENS.get(f"{model}_output", 0.015)
        total = input_cost + output_cost

        _daily_spend["total_usd"] += total
        _daily_spend["calls"] += 1

    @staticmethod
    def get_daily_usage() -> dict:
        """Get current daily usage stats (for monitoring)."""
        budget = _get_daily_budget()
        return {
            "date": _daily_spend["date"],
            "total_usd": round(_daily_spend["total_usd"], 4),
            "calls": _daily_spend["calls"],
            "budget_usd": budget,
            "remaining_usd": round(max(0, budget - _daily_spend["total_usd"]), 4),
            "budget_pct_used": round((_daily_spend["total_usd"] / budget) * 100, 1) if budget > 0 else 0.0,
        }


# ── Singleton ─────────────────────────────────────────────────────────────────
_gateway_instance: Optional[LLMGateway] = None


def get_gateway() -> LLMGateway:
    """Get the global LLM gateway singleton."""
    global _gateway_instance
    if _gateway_instance is None:
        _gateway_instance = LLMGateway()
    return _gateway_instance


# Convenience alias
gateway = get_gateway
