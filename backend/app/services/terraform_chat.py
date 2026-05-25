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

# 🟢 BEGINNER: Standard library imports for JSON parsing and logging.
import json
import logging
from typing import Dict, List, Generator, AsyncGenerator
# 🟢 BEGINNER: Import centralized config to get AWS and Gemini credentials.
from app.core.config import settings

# 🟢 BEGINNER: Logger for this module. Messages will be prefixed with [TerraformChat].
logger = logging.getLogger(__name__)


# 🟢 BEGINNER: This class routes chat requests to either Claude (AWS Bedrock) or Gemini (Google AI).
# It builds a detailed "system prompt" that tells the AI about the detected diagram resources.
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
        # 🟢 BEGINNER: Build the system prompt that includes detected resources and rules.
        system = self._build_system_prompt(context)

        # 🟢 BEGINNER: If the model name starts with "claude", use AWS Bedrock; if "gemini", use Google.
        if model.startswith("claude"):
            yield from self._call_claude(messages, model, system, stream)
        elif model.startswith("gemini"):
            yield from self._call_gemini(messages, model, system, stream)
        else:
            raise ValueError(f"Unknown model: {model}")

    def generate_from_prompt(
        self,
        messages: List[Dict],
        model: str,
        system_prompt: str,
        stream: bool = True,
    ) -> Generator[str, None, None]:
        """Generate terraform from an externally built system prompt."""
        if model.startswith("claude"):
            yield from self._call_claude(messages, model, system_prompt, stream)
        elif model.startswith("gemini"):
            yield from self._call_gemini(messages, model, system_prompt, stream)
        else:
            raise ValueError(f"Unknown model: {model}")

    def _build_system_prompt(self, context: Dict) -> str:
        """Build a rich system prompt from the terraform_context.
        
        Injects governance rules, naming conventions, security constraints,
        and template instructions when available from the pipeline's master_context.
        """
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

        # Build dynamic governance/template section if master_context is available
        governance_block = ""
        master = context.get("master_context", {})
        if master:
            parts = []

            # User intent
            raw_intent = master.get("raw_intent")
            if raw_intent:
                parts.append(f"CLIENT'S GOAL: {raw_intent}")

            # Terraform rules (rich descriptive strings)
            terraform_rules = master.get("terraform_rules", {})
            if terraform_rules and any(v for v in terraform_rules.values() if v):
                parts.append("TERRAFORM/IaC RULES (from enterprise template):")
                for key, value in terraform_rules.items():
                    if value:
                        parts.append(f"  - {key}: {value}")

            # Governance rules (may have 'rules' list or flat key-value)
            governance = master.get("governance", {})
            if governance:
                rules = governance.get("rules", [])
                if isinstance(rules, list) and rules:
                    parts.append("GOVERNANCE RULES:")
                    for rule in rules:
                        parts.append(f"  - {rule}")
                else:
                    non_empty = {k: v for k, v in governance.items() if v and k != "rules"}
                    if non_empty:
                        parts.append("GOVERNANCE RULES:")
                        for key, value in non_empty.items():
                            parts.append(f"  - {key}: {value}")

            # Naming standards
            naming = master.get("naming_standards", {})
            if naming and any(v for v in naming.values() if v):
                parts.append("NAMING STANDARDS (use in ALL resource names):")
                if naming.get("pattern"):
                    parts.append(f"  Pattern: {naming['pattern']}")
                if naming.get("examples"):
                    examples = naming["examples"]
                    parts.append(f"  Examples: {', '.join(examples[:5]) if isinstance(examples, list) else examples}")
                for key in ["case_rule", "separator", "prefix_suffix_rules", "max_length"]:
                    if naming.get(key):
                        parts.append(f"  {key}: {naming[key]}")

            # Security constraints (may have 'rules' list or flat key-value)
            security = master.get("security", {})
            if security:
                sec_rules = security.get("rules", [])
                if isinstance(sec_rules, list) and sec_rules:
                    parts.append("SECURITY CONSTRAINTS:")
                    for rule in sec_rules:
                        parts.append(f"  - {rule}")
                else:
                    non_empty = {k: v for k, v in security.items() if v and k != "rules"}
                    if non_empty:
                        parts.append("SECURITY CONSTRAINTS:")
                        for key, value in non_empty.items():
                            parts.append(f"  - {key}: {value}")

            # Compliance (dict with frameworks list, or bare list)
            compliance = master.get("compliance", {})
            if compliance:
                if isinstance(compliance, dict):
                    frameworks = compliance.get("frameworks", [])
                    controls = compliance.get("specific_controls", [])
                    if frameworks:
                        parts.append(f"COMPLIANCE FRAMEWORKS: {', '.join(frameworks) if isinstance(frameworks, list) else frameworks}")
                    if controls:
                        parts.append(f"COMPLIANCE CONTROLS: {'; '.join(controls[:8])}")
                elif isinstance(compliance, list) and compliance:
                    parts.append(f"COMPLIANCE FRAMEWORKS: {', '.join(compliance)}")

            if parts:
                governance_block = "\n".join(parts) + "\n\n⚠️ CRITICAL: All generated Terraform code MUST follow the rules, naming convention, and security constraints above.\n"

        return f"""You are an expert Terraform engineer inside InfraSketch.

The user has uploaded an architecture diagram. Here is what was detected:

DETECTED RESOURCES:
{res_list or "  None — user is describing requirements from scratch"}

NETWORK CONNECTIONS:
{conn_list or "  None detected"}

{governance_block}
CONTEXT:
  Default Cloud: {context.get("cloud", "AWS")} (override if user specifies a different cloud provider)
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
5. Apply security hardening by default:
   - Encryption on all storage (KMS for AWS, CMEK for GCP, CMK for Azure)
   - No public access to databases or storage
   - VPC/network flow logs enabled
   - Multi-AZ/multi-zone for databases
   - deletion_protection = true in prod
6. If the user asks for a DIFFERENT cloud provider than the default context (e.g., asks for GCP when context says AWS), generate code for the cloud they requested. Always use the correct provider and resource types:
   - AWS: provider "aws", resources like aws_instance, aws_vpc, aws_s3_bucket
   - GCP: provider "google", resources like google_compute_instance, google_compute_network, google_storage_bucket
   - Azure: provider "azurerm", resources like azurerm_virtual_machine, azurerm_virtual_network, azurerm_storage_account
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
        # 🟢 BEGINNER: boto3 is imported inside the function so the app can start even if AWS isn't configured.
        try:
            import boto3
        except ImportError:
            yield "[Error] boto3 package not installed. Run: pip install boto3"
            return

        # 🟢 BEGINNER: Validate that AWS credentials exist before trying to call Bedrock.
        if not settings.AWS_ACCESS_KEY_ID or not settings.AWS_SECRET_ACCESS_KEY:
            yield "[Error] AWS credentials not configured. Add AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY to your .env file."
            return

        # 🟢 BEGINNER: Use the shared Bedrock client factory so timeouts and
        # retry behavior are consistent with every other Bedrock caller in the
        # app. The factory enforces 180s read_timeout and 0 boto3-level retries
        # (the gateway/fallback chain owns retry policy).
        from app.core.bedrock_client import get_bedrock_client
        bedrock = get_bedrock_client()

        # 🟢 BEGINNER: Route to the correct Bedrock model ID based on the user's selection.
        # Haiku is faster/cheaper for simple tasks; Sonnet is more powerful for complex generation.
        model_map = {
            "claude-haiku-4-5": settings.AWS_BEDROCK_HAIKU_MODEL,
            "claude-sonnet-4-6": settings.AWS_BEDROCK_MODEL,
        }
        bedrock_model_id = model_map.get(model, settings.AWS_BEDROCK_MODEL)
        logger.info(f"[TerraformChat] Using model: {model} → {bedrock_model_id}")

        # 🟢 BEGINNER: Convert our simple message dicts into Anthropic's expected format.
        anthropic_messages = []
        for msg in messages:
            anthropic_messages.append({
                "role": msg["role"],
                "content": msg["content"],
            })

        # 🟢 BEGINNER: Build the JSON body that Bedrock expects.
        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 8192,       # 🟢 BEGINNER: Maximum number of tokens (words/pieces) in the response.
            "temperature": 0.2,       # 🟢 BEGINNER: Lower = more deterministic, less creative randomness.
            "system": system,         # 🟢 BEGINNER: The system prompt we built earlier (rules + context).
            "messages": anthropic_messages,
        })

        try:
            if stream:
                # 🟢 BEGINNER: Streaming path — must use raw boto3 (streaming can't be cached).
                resp = bedrock.invoke_model_with_response_stream(
                    modelId=bedrock_model_id,
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
                # 🟢 BEGINNER: Non-streaming path — route through LLM Gateway for caching,
                # circuit breaking, budget tracking, and Gemini fallback.
                try:
                    from app.core.llm_gateway import get_gateway
                    # Build messages list (system prompt as first user message prefix)
                    gw_messages = [{"role": "user", "content": f"{system}\n\n{messages[-1]['content']}"}]
                    if len(messages) > 1:
                        # Include full conversation history
                        gw_messages = [{"role": m["role"], "content": m["content"]} for m in messages]
                        gw_messages[0]["content"] = f"{system}\n\n{gw_messages[0]['content']}"
                    response = get_gateway().call(
                        messages=gw_messages,
                        task_type="terraform_chat",
                        max_tokens=8192,
                        context=system[:200],
                    )
                    yield response
                    return
                except Exception as gw_err:
                    logger.warning(f"[TerraformChat] Gateway failed, falling back to direct boto3: {gw_err}")
                    resp = bedrock.invoke_model(
                        modelId=bedrock_model_id,
                        contentType="application/json",
                        accept="application/json",
                        body=body,
                    )
                    response_body = json.loads(resp["body"].read())
                    yield response_body["content"][0]["text"]
        except Exception as e:
            logger.error(f"[TerraformChat] Bedrock error with {bedrock_model_id}: {e}", exc_info=True)
            # Fallback: try the other model if the selected one fails
            fallback_model_id = settings.AWS_BEDROCK_MODEL if bedrock_model_id != settings.AWS_BEDROCK_MODEL else settings.AWS_BEDROCK_HAIKU_MODEL
            logger.info(f"[TerraformChat] Retrying with fallback model: {fallback_model_id}")
            try:
                if stream:
                    resp = bedrock.invoke_model_with_response_stream(
                        modelId=fallback_model_id,
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
                        modelId=fallback_model_id,
                        contentType="application/json",
                        accept="application/json",
                        body=body,
                    )
                    response_body = json.loads(resp["body"].read())
                    yield response_body["content"][0]["text"]
            except Exception as e2:
                logger.error(f"[TerraformChat] Fallback also failed: {e2}", exc_info=True)
                yield f"[Error] Bedrock Claude error: {str(e)}. Fallback also failed: {str(e2)}"

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
        # 🟢 BEGINNER: Validate that the Gemini API key exists.
        if not api_key:
            yield "[Error] GEMINI_API_KEY not configured. Add it to your .env file."
            return

        # 🟢 BEGINNER: Configure the Gemini SDK with our API key.
        genai.configure(api_key=api_key)

        # 🟢 BEGINNER: Map our friendly model names to Gemini's internal model IDs.
        model_map = {
            "gemini-2.5-flash": "gemini-2.5-flash",
            "gemini-2.5-pro": "gemini-2.5-pro",
        }
        model_id = model_map.get(model, "gemini-2.5-flash")

        # 🟢 BEGINNER: Create the Gemini model object with our system instruction.
        gemini_model = genai.GenerativeModel(
            model_name=model_id,
            system_instruction=system,
        )

        # 🟢 BEGINNER: Convert messages from Anthropic format to Gemini format.
        # Gemini uses "model" instead of "assistant" for AI responses.
        history = []
        for msg in messages[:-1]:
            history.append({
                "role": "user" if msg["role"] == "user" else "model",
                "parts": [{"text": msg["content"]}]
            })

        try:
            # 🟢 BEGINNER: Start a Gemini chat session with the previous messages as "history".
            chat = gemini_model.start_chat(history=history)
            last_msg = messages[-1]["content"] if messages else ""

            if stream:
                # 🟢 BEGINNER: Send the latest user message and stream the response chunks.
                response = chat.send_message(last_msg, stream=True)
                for chunk in response:
                    yield chunk.text
            else:
                response = chat.send_message(last_msg)
                yield response.text
        except Exception as e:
            logger.error(f"[TerraformChat] Gemini error: {e}", exc_info=True)
            yield f"[Error] Gemini API error: {str(e)}"
