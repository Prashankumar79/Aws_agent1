"""
================================================================================
  backend/app/services/bedrock_service.py  —  AWS BEDROCK LEGACY CLIENT
================================================================================

PURPOSE:
  Low-level AWS Bedrock wrapper used in the earliest version of the app.
  Wraps `invoke_model` and `invoke_model_with_response_stream` for Claude.

STATUS: LEGACY — mostly superseded
  The active design-doc generation now uses `DesignDocGenerator` in
  design_doc_service.py (4 chained focused calls with streaming).
  The active terraform chat uses `TerraformChatService` in terraform_chat.py.
  This class is kept for backward compatibility and as a reference.

CONNECTIONS TO OTHER FILES:
  • core/config.py   → reads AWS_* credentials and AWS_BEDROCK_MODEL
  • api/v1/jobs.py   → BedrockService imported but TerraformChatService used

HOW AWS BEDROCK WORKS:
  1. boto3 client sends an HTTP request to Bedrock endpoint in AWS_DEFAULT_REGION
  2. Body is JSON with Anthropic's messages format
  3. Streaming: Bedrock returns an EventStream; each event has a `chunk.bytes`
     field containing a JSON blob with `delta.text`
  4. Non-streaming: Bedrock returns a single response body with `content[0].text`

SECURITY:
  Credentials are read from .env via config.py.
  NEVER hardcode credentials in this file.
================================================================================
"""

# 🟢 BEGINNER: boto3 is the official AWS SDK for Python. It lets us call AWS services like Bedrock.
import boto3
import json
import logging
import asyncio
from typing import Dict, List, Any, AsyncGenerator
from app.core.config import settings

logger = logging.getLogger(__name__)


# 🟢 BEGINNER: LEGACY class — this was the original way to call Claude on Bedrock.
# The newer code in design_doc_service.py and terraform_chat.py has replaced most of its usage,
# but it's kept here for backward compatibility.
class BedrockService:
    """AWS Bedrock service for Claude/Sonnet integration"""

    def __init__(self):
        # 🟢 BEGINNER: Read AWS credentials and region from our centralized config (.env file).
        self.region = settings.AWS_DEFAULT_REGION
        # 🟢 BEGINNER: Use the shared Bedrock client factory so timeouts and retry
        # behavior are consistent across the whole app (no more 9-minute hangs
        # from boto3's silent retries).
        from app.core.bedrock_client import get_bedrock_client
        self.client = get_bedrock_client()
        # 🟢 BEGINNER: The specific Claude model ID to use (e.g., us.anthropic.claude-sonnet-4-5-20250929-v1:0).
        self.model_id = settings.AWS_BEDROCK_MODEL

    async def generate_design_document_stream(
        self,
        context_pack: Dict,
        enriched_context: Dict
    ) -> AsyncGenerator[str, None]:
        """Generate design document using Claude via AWS Bedrock with streaming"""

        # 🟢 BEGINNER: Build the giant text prompt that tells Claude what to write.
        prompt = self._build_design_document_prompt(context_pack, enriched_context)

        try:
            # 🟢 BEGINNER: Call Bedrock in streaming mode. The response comes back as a series of "chunks" (text pieces).
            response = self.client.invoke_model_with_response_stream(
                modelId=self.model_id,
                contentType="application/json",
                accept="application/json",
                body=json.dumps({
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 8000,         # 🟢 BEGINNER: Maximum response length (8000 tokens ≈ 6000 words).
                    "messages": [
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ]
                })
            )

            # 🟢 BEGINNER: Loop over each chunk in the stream, parse the JSON inside it, and yield the text.
            stream = response['body']
            for event in stream:
                chunk = event.get('chunk')
                if chunk:
                    chunk_data = json.loads(chunk.get('bytes').decode())
                    if 'delta' in chunk_data and 'text' in chunk_data['delta']:
                        yield chunk_data['delta']['text']

        except Exception as e:
            yield f"\n\n[Error]: {str(e)}"

    async def generate_design_document(
        self,
        context_pack: Dict,
        enriched_context: Dict
    ) -> Dict:
        """Generate design document using Claude via AWS Bedrock (non-streaming)"""

        # 🟢 BEGINNER: Build the prompt text that describes the architecture to Claude.
        prompt = self._build_design_document_prompt(context_pack, enriched_context)

        try:
            # 🟢 BEGINNER: Call Bedrock in non-streaming mode — waits for the entire response before returning.
            response = self.client.invoke_model(
                modelId=self.model_id,
                contentType="application/json",
                accept="application/json",
                body=json.dumps({
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 8000,
                    "messages": [
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ]
                })
            )

            # 🟢 BEGINNER: Parse the JSON response body and extract the generated text.
            response_body = json.loads(response['body'].read())
            design_text = response_body['content'][0]['text']

            # 🟢 BEGINNER: Try to extract structured JSON from the text (Claude sometimes wraps JSON in markdown).
            design_doc = self._parse_design_document(design_text)

            return {
                "success": True,
                "design_document": design_doc,
                "raw_response": design_text
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "design_document": None
            }

    def _build_design_document_prompt(
        self,
        context_pack: Dict,
        enriched_context: Dict
    ) -> str:
        """Build prompt for design document generation"""
        
        prompt = """You are a senior cloud infrastructure architect. Generate a comprehensive design document based on the provided architecture analysis.

## Architecture Context
"""
        
        # Add context pack information
        prompt += f"""
Primary Provider: {context_pack.get('primary_provider', 'aws')}
Overall Confidence: {context_pack.get('overall_confidence', 0.8)}

### Components
"""
        for component in context_pack.get('components', []):
            prompt += f"""
- **{component.get('name')}** ({component.get('service_type')})
  - Provider: {component.get('provider')}
  - Configuration: {component.get('configuration')}
  - Boundaries: {', '.join(component.get('boundaries', []))}
  - Ports: {component.get('ports')}
  - Confidence: {component.get('confidence')}
"""
        
        # Add connections
        prompt += f"""
### Connections
"""
        for connection in context_pack.get('connections', []):
            prompt += f"- {connection.get('source')} → {connection.get('target')} ({connection.get('protocol')}:{connection.get('port')})\n"
        
        # Add boundaries
        prompt += f"""
### Boundaries
"""
        for boundary in context_pack.get('boundaries', []):
            prompt += f"- {boundary.get('boundary_type')}: {boundary.get('name')} ({boundary.get('cidr')})\n"
        
        # Add enriched context
        prompt += f"""
## Enriched Context (RAG)

### Best Practices
"""
        for practice in enriched_context.get('best_practices', [])[:3]:
            if isinstance(practice, dict):
                prompt += f"- {practice.get('content', str(practice))[:200]}...\n"
        
        prompt += f"""
### Security Controls (CIS)
"""
        for control in enriched_context.get('security_controls', [])[:3]:
            if isinstance(control, dict):
                prompt += f"- {control.get('content', str(control))[:200]}...\n"
        
        prompt += f"""
### Architecture Patterns
"""
        for pattern in enriched_context.get('architecture_patterns', [])[:2]:
            if isinstance(pattern, dict):
                prompt += f"- {pattern.get('content', str(pattern))[:200]}...\n"
        
        # Add instructions
        prompt += """
## Instructions

Generate a comprehensive design document in JSON format with the following structure:

```json
{
  "title": "Infrastructure Design Document",
  "summary": "Brief overview of the architecture",
  "architecture_overview": {
    "description": "Detailed architecture description",
    "components": [
      {
        "name": "component_name",
        "type": "service_type",
        "purpose": "Purpose of this component",
        "configuration": {},
        "dependencies": ["component1", "component2"]
      }
    ],
    "data_flow": "Description of data flows",
    "scalability_considerations": "Scalability approach"
  },
  "network_design": {
    "vpc_design": "VPC architecture",
    "subnet_strategy": "Subnet configuration",
    "security_groups": "Security group strategy"
  },
  "security_design": {
    "iam_strategy": "IAM approach",
    "encryption": "Encryption strategy",
    "compliance": "Compliance considerations"
  },
  "cost_estimation": {
    "estimated_monthly_cost": "Cost estimate",
    "cost_optimization": "Cost optimization recommendations"
  },
  "best_practices": [
    "Best practice 1",
    "Best practice 2"
  ],
  "assumptions": [
    "Assumption 1",
    "Assumption 2"
  ],
  "unresolved_questions": [
    "Question 1",
    "Question 2"
  ]
}
```

Ensure the design document:
- Is production-ready
- Incorporates the retrieved best practices and security controls
- Addresses scalability, security, and cost optimization
- Lists any assumptions and unresolved questions
"""
        
        return prompt
    
    def _parse_design_document(self, design_text: str) -> Dict:
        """Parse design document from Claude response"""
        try:
            # Extract JSON from response
            import re
            json_match = re.search(r'\{[\s\S]*\}', design_text)

            if json_match:
                json_str = json_match.group()
                design_doc = json.loads(json_str)
                return design_doc
            else:
                # Fallback: return raw text
                return {
                    "raw_text": design_text,
                    "error": "Could not extract JSON from response"
                }

        except Exception as e:
            return {
                "error": f"Failed to parse design document: {str(e)}",
                "raw_text": design_text
            }

    def invoke(self, messages: List[Dict[str, str]], max_tokens: int = 4000) -> str:
        """Simple non-streaming invoke for agent nodes. Returns raw text response.
        Routes through LLM Gateway for caching, circuit breaking, and cost tracking."""
        from app.core.llm_gateway import get_gateway
        return get_gateway().call(
            messages=messages,
            task_type="prompt_analysis",
            max_tokens=max_tokens,
        )

    def check_credentials(self) -> dict:
        """Verify AWS credentials and Bedrock model access by sending a minimal test invoke."""
        import boto3
        from botocore.exceptions import ClientError, NoCredentialsError

        result = {
            "aws_access_key_present": bool(settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY),
            "region": self.region,
            "model_id": self.model_id,
            "bedrock_accessible": False,
            "model_accessible": False,
            "error": None,
        }

        try:
            # Test 1: List foundation models (requires bedrock:ListFoundationModels)
            # Short timeout — this is a health check, not a user-facing call.
            from botocore.config import Config as _BotoConfig
            bedrock_client = boto3.client(
                'bedrock',
                region_name=self.region,
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                config=_BotoConfig(connect_timeout=5, read_timeout=15, retries={'max_attempts': 0, 'mode': 'standard'}),
            )
            models = bedrock_client.list_foundation_models()
            result["bedrock_accessible"] = True
            available_models = [m['modelId'] for m in models.get('modelSummaries', [])]
            result["models_found"] = len(available_models)
            result["model_accessible"] = self.model_id in available_models or any(self.model_id in m for m in available_models)

            # Test 2: Minimal invoke to verify runtime access
            test_response = self.invoke(
                messages=[{"role": "user", "content": "Say 'AWS credentials OK' and nothing else."}],
                max_tokens=20
            )
            result["invoke_test_response"] = test_response.strip()
            result["invoke_test_passed"] = "OK" in test_response or "ok" in test_response.lower()

            logger.info(f"[BedrockService] Credential check: bedrock_accessible={result['bedrock_accessible']}, model_accessible={result['model_accessible']}, invoke_passed={result.get('invoke_test_passed', False)}")

        except NoCredentialsError as e:
            result["error"] = f"AWS credentials not found: {e}"
            logger.error(f"[BedrockService] Credential check FAILED: No AWS credentials")
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            result["error"] = f"AWS ClientError ({error_code}): {e}"
            logger.error(f"[BedrockService] Credential check FAILED: {error_code} - {e}")
        except Exception as e:
            result["error"] = f"Unexpected error: {e}"
            logger.error(f"[BedrockService] Credential check FAILED: {e}")

        return result

