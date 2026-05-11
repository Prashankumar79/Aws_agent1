"""
================================================================================
  backend/app/services/terraform_chat.py  —  CONVERSATIONAL TERRAFORM GENERATOR
================================================================================

PURPOSE:
  Stage 3 of the pipeline. Handles the AI chat that converts user intent
  into complete, production-ready Terraform HCL files. Supports two AI
  providers: AWS Bedrock Claude and Google Gemini.

CONNECTIONS TO OTHER FILES:
  • core/config.py   → AWS + GEMINI credentials, model names
  • api/v1/jobs.py   → calls .chat() for the /terraform-chat SSE endpoint
  • TerraformChatPage.tsx → sends messages, renders streamed HCL response

DEPENDENCY INJECTION (Provider Routing):
  The `model` parameter decides the provider:
    "claude-*"  →  _call_claude() via AWS Bedrock boto3
    "gemini-*"  →  _call_gemini() via google-generativeai SDK
  Switching providers requires zero code changes — just change the model name.

SYSTEM PROMPT STRATEGY:
  _build_system_prompt() injects the vision analysis context (detected resources,
  connections, region, project name) so Claude knows EXACTLY what infrastructure
  the diagram shows. The rules section enforces:
    • Split output by filename (main.tf, variables.tf, vpc.tf, ...)
    • CIS benchmark hardening by default (KMS, IMDSv2, no public S3)
    • Complete HCL only (no placeholders, no TODOs)
    • Usage Commands section with terraform init/plan/apply

STREAMING ARCHITECTURE:
  .chat() is a Python Generator (yield from) — it streams text chunks.
  api/v1/jobs.py wraps each chunk in SSE format:
    data: {"type": "delta", "text": "..."}\n\n
  TerraformChatPage.tsx reads the stream with fetch + ReadableStream.

DATA FLOW:
  User message → TerraformChatPage sends POST /terraform-chat
              → jobs.py builds messages list from chat history
              → TerraformChatService.chat(messages, model, context)
              → Streams HCL chunks back
              → Frontend parses files by **N. filename.tf** headers
================================================================================
"""

import json
import logging
from typing import Dict, List, Generator, AsyncGenerator

from app.core.config import settings

logger = logging.getLogger(__name__)


class TerraformChatService:
    """Routes conversational Terraform generation to the correct AI provider."""

    def chat(
        self,
        messages: List[Dict],
        model: str,
        context: Dict,
        stream: bool = True,
    ) -> Generator[str, None, None]:
        """
        Route to the correct provider based on model string.
        Yields text chunks for SSE streaming.
        """
        system = self._build_system_prompt(context)

        if model.startswith("claude"):
            yield from self._call_claude(messages, model, system, stream)
        elif model.startswith("gemini"):
            yield from self._call_gemini(messages, model, system, stream)
        else:
            raise ValueError(f"Unknown model: {model}")

    def _build_system_prompt(self, context: Dict) -> str:
        """Build a rich system prompt from the terraform_context."""
        resources = context.get("detected_resources", [])
        res_list = "\n".join(
            f"  - {r.get('name', 'unknown')} ({r.get('service', 'unknown')}) ×{r.get('count', 1)}"
            for r in resources
        )
        connections = context.get("detected_connections", [])
        conn_list = "\n".join(
            f"  - {c.get('from', '?')} → {c.get('to', '?')} ({c.get('protocol', 'HTTPS')})"
            for c in connections
        )

        return f"""You are an expert Terraform engineer inside InfraSketch.

The user has uploaded an architecture diagram. Here is what was detected:

DETECTED RESOURCES:
{res_list or "  None — user is describing requirements from scratch"}

NETWORK CONNECTIONS:
{conn_list or "  None detected"}

CONTEXT:
  Cloud:       {context.get("cloud", "AWS")}
  Environment: {context.get("environment", "not specified")}
  Region:      {context.get("region", "not specified")}
  Project:     {context.get("project_name", "not specified")}
  CIS hardening: {context.get("security", {}).get("cis_hardening", True)}

RULES — follow these on every response:
1. Generate complete, valid HCL. No placeholders. No TODOs.
2. Split output into named files: main.tf, variables.tf, vpc.tf, etc.
3. Format each file as:
   **1. main.tf**
```hcl
   [complete HCL content]
```
4. After the last file, add a **Usage Commands** section with bash:
```bash
   # Initialize working directory
   terraform init

   # Preview changes
   terraform plan

   # Deploy infrastructure
   terraform apply
```
5. Apply CIS hardening by default:
   - KMS encryption on all storage
   - IMDSv2 required on EC2
   - No public S3 buckets
   - VPC flow logs enabled
   - Multi-AZ RDS
   - deletion_protection = true in prod
6. Use exact values from CONTEXT above. Do not invent regions or sizes.
7. When the user asks to modify existing code, show only the changed
   file(s), not the entire set again.
8. Keep explanations brief (2-3 sentences max before the code).
   The user is a developer — they want code, not lectures."""

    def _call_claude(
        self,
        messages: List[Dict],
        model: str,
        system: str,
        stream: bool,
    ) -> Generator[str, None, None]:
        """Call Claude via AWS Bedrock (boto3)."""
        try:
            import boto3
        except ImportError:
            yield "[Error] boto3 package not installed. Run: pip install boto3"
            return

        if not settings.AWS_ACCESS_KEY_ID or not settings.AWS_SECRET_ACCESS_KEY:
            yield "[Error] AWS credentials not configured. Add AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY to your .env file."
            return

        bedrock = boto3.client(
            'bedrock-runtime',
            region_name=settings.AWS_DEFAULT_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )

        # Convert messages to Anthropic Bedrock format
        anthropic_messages = []
        for msg in messages:
            anthropic_messages.append({
                "role": msg["role"],
                "content": msg["content"],
            })

        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 4096,
            "temperature": 0.2,
            "system": system,
            "messages": anthropic_messages,
        })

        try:
            if stream:
                resp = bedrock.invoke_model_with_response_stream(
                    modelId=settings.AWS_BEDROCK_MODEL,
                    contentType="application/json",
                    accept="application/json",
                    body=body,
                )
                for event in resp.get("body", []):
                    chunk_bytes = event.get("chunk", {}).get("bytes", b"")
                    if not chunk_bytes:
                        continue
                    chunk = json.loads(chunk_bytes)
                    if chunk.get("type") == "content_block_delta":
                        text = chunk.get("delta", {}).get("text", "")
                        if text:
                            yield text
            else:
                resp = bedrock.invoke_model(
                    modelId=settings.AWS_BEDROCK_MODEL,
                    contentType="application/json",
                    accept="application/json",
                    body=body,
                )
                response_body = json.loads(resp["body"].read())
                yield response_body["content"][0]["text"]
        except Exception as e:
            logger.error(f"[TerraformChat] Bedrock error: {e}", exc_info=True)
            yield f"[Error] Bedrock Claude error: {str(e)}"

    def _call_gemini(
        self,
        messages: List[Dict],
        model: str,
        system: str,
        stream: bool,
    ) -> Generator[str, None, None]:
        """Call Google Gemini API."""
        try:
            import google.generativeai as genai
        except ImportError:
            yield "[Error] google-generativeai package not installed. Run: pip install google-generativeai"
            return

        api_key = settings.GEMINI_API_KEY
        if not api_key:
            yield "[Error] GEMINI_API_KEY not configured. Add it to your .env file."
            return

        genai.configure(api_key=api_key)

        model_map = {
            "gemini-2.5-flash": "gemini-2.5-flash",
            "gemini-2.5-pro": "gemini-2.5-pro",
        }
        model_id = model_map.get(model, "gemini-2.5-flash")

        gemini_model = genai.GenerativeModel(
            model_name=model_id,
            system_instruction=system,
        )

        # Convert from Anthropic format to Gemini format
        history = []
        for msg in messages[:-1]:
            history.append({
                "role": "user" if msg["role"] == "user" else "model",
                "parts": [{"text": msg["content"]}]
            })

        try:
            chat = gemini_model.start_chat(history=history)
            last_msg = messages[-1]["content"] if messages else ""

            if stream:
                response = chat.send_message(last_msg, stream=True)
                for chunk in response:
                    yield chunk.text
            else:
                response = chat.send_message(last_msg)
                yield response.text
        except Exception as e:
            logger.error(f"[TerraformChat] Gemini error: {e}", exc_info=True)
            yield f"[Error] Gemini API error: {str(e)}"
