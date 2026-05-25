"""
================================================================================
  backend/app/core/bedrock_client.py — SHARED BEDROCK CLIENT FACTORY
================================================================================

PURPOSE:
  ONE place that builds boto3 Bedrock clients with the correct timeout and
  retry configuration. Every service that calls Bedrock should import this
  factory instead of calling boto3.client('bedrock-runtime', ...) directly.

  Also provides `traced_invoke()` — a LangSmith-traced wrapper around
  invoke_model that logs every LLM call to your LangSmith dashboard.

WHY THIS FILE EXISTS:
  Without timeouts, boto3 inherits a 60s read_timeout but retries 3 times
  silently — so a single stuck Bedrock connection could hang for 9 minutes
  while consuming 100% CPU on a worker thread. We saw a 2GB stuck process
  in production caused by exactly this.

CONNECTIONS:
  • llm_gateway.py        → primary user (via traced_invoke)
  • haiku_service.py      → bypasses gateway for direct Haiku calls
  • design_doc_service.py → uses streaming Bedrock API + traced_invoke
  • bedrock_service.py    → legacy compatibility
  • architecture_extractor.py → vision-enrichment LLM calls

CONFIGURATION:
  Read/connect timeouts can be overridden via environment variables:
    BEDROCK_READ_TIMEOUT_SECONDS    (default: 180)
    BEDROCK_CONNECT_TIMEOUT_SECONDS (default: 10)
    BEDROCK_MAX_RETRIES             (default: 0 — gateway owns retry policy)
================================================================================
"""
import json
import logging
import os
import time
from typing import Optional, List, Dict

import boto3
from botocore.config import Config

from app.core.config import settings

logger = logging.getLogger(__name__)

# ── Tuning constants ─────────────────────────────────────────────────────────
_DEFAULT_READ_TIMEOUT = int(os.environ.get("BEDROCK_READ_TIMEOUT_SECONDS", "180"))
_DEFAULT_CONNECT_TIMEOUT = int(os.environ.get("BEDROCK_CONNECT_TIMEOUT_SECONDS", "10"))
_DEFAULT_MAX_RETRIES = int(os.environ.get("BEDROCK_MAX_RETRIES", "0"))

# ── Process-wide singleton ───────────────────────────────────────────────────
_shared_client = None


def get_bedrock_client():
    """Return the process-wide shared Bedrock runtime client."""
    global _shared_client
    if _shared_client is None:
        _shared_client = _build_client()
    return _shared_client


def traced_invoke(
    model_id: str,
    messages: List[Dict],
    max_tokens: int = 4000,
    system: str = "",
    temperature: float = 0.2,
    task_name: str = "bedrock_invoke",
) -> str:
    """Invoke Bedrock with full LangSmith tracing.

    This is the recommended way to call Bedrock for non-streaming use cases.
    Every call appears in your LangSmith dashboard with:
      - Input: messages + system prompt
      - Output: response text
      - Metadata: model_id, tokens, latency
      - Run type: llm

    Falls back to untraced call if langsmith is not installed.
    """
    client = get_bedrock_client()

    body_dict = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": messages,
    }
    if system:
        body_dict["system"] = system

    def _do_invoke() -> str:
        response = client.invoke_model(
            modelId=model_id,
            contentType="application/json",
            accept="application/json",
            body=json.dumps(body_dict),
        )
        result = json.loads(response['body'].read())
        return result['content'][0]['text']

    # Try to wrap with LangSmith tracing
    try:
        from langsmith import traceable

        @traceable(name=task_name, run_type="llm", metadata={"model_id": model_id})
        def _traced_invoke(input_messages, **kwargs):
            return _do_invoke()

        return _traced_invoke(messages, system=system, max_tokens=max_tokens)
    except ImportError:
        return _do_invoke()
    except Exception as e:
        # Tracing failed — don't break the app, just invoke without tracing
        logger.debug(f"[BedrockClient] Tracing failed ({e}), invoking without trace")
        return _do_invoke()


def _build_client():
    """Build a fresh Bedrock client with the standard timeout/retry config."""
    if not settings.AWS_ACCESS_KEY_ID or not settings.AWS_SECRET_ACCESS_KEY:
        raise RuntimeError(
            "AWS credentials missing. Set AWS_ACCESS_KEY_ID and "
            "AWS_SECRET_ACCESS_KEY in your .env file."
        )

    cfg = Config(
        region_name=settings.AWS_DEFAULT_REGION,
        connect_timeout=_DEFAULT_CONNECT_TIMEOUT,
        read_timeout=_DEFAULT_READ_TIMEOUT,
        retries={"max_attempts": _DEFAULT_MAX_RETRIES, "mode": "standard"},
    )
    client = boto3.client(
        "bedrock-runtime",
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        config=cfg,
    )
    logger.info(
        f"[BedrockClient] Initialized | region={settings.AWS_DEFAULT_REGION} "
        f"| read_timeout={_DEFAULT_READ_TIMEOUT}s "
        f"| connect_timeout={_DEFAULT_CONNECT_TIMEOUT}s "
        f"| retries={_DEFAULT_MAX_RETRIES}"
    )
    return client


def reset_bedrock_client():
    """Drop the cached client (used in tests or after credential rotation)."""
    global _shared_client
    _shared_client = None
