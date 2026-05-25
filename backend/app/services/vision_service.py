"""
================================================================================
  backend/app/services/vision_service.py  —  DIAGRAM ANALYSIS via GEMINI VISION
================================================================================

PURPOSE:
  The first stage of the pipeline. Takes the uploaded diagram image and uses
  Google Gemini's multimodal vision API to extract a structured JSON description
  of every cloud component, network boundary, and connection it can see.

WHY GEMINI (not Bedrock) for Vision:
  AWS Bedrock Claude does not accept image inputs in the same SDK path.
  Google Gemini's `gemini-2.5-pro` is a top multimodal model and has a
  generous free tier. Vision = Gemini, Text = Claude (Bedrock).

CONNECTIONS TO OTHER FILES:
  • core/config.py         → GEMINI_API_KEY, GEMINI_VISION_MODEL
  • api/v1/jobs.py         → calls analyze_diagram() and stores result in job
  • design_doc_service.py  → receives the analysis dict as `vision_analysis`

DATA FLOW:
  1. jobs.py saves uploaded file to disk (UUID filename in uploads/)
  2. jobs.py calls VisionService.analyze_diagram(image_path)
  3. This service reads the image as bytes
  4. Sends bytes + prompt to Gemini via google.genai SDK
  5. Parses JSON from Gemini's text response
  6. Returns {success, analysis{components, connections, boundaries}, raw_response}
  7. jobs.py stores result in _jobs[job_id] as `vision_analysis`

OUTPUT SHAPE:
  {
    "components":  [{name, type, provider, configuration, confidence}, ...]
    "connections": [{source, target, protocol, port, type}, ...]
    "boundaries":  [{type, name, cidr, region}, ...]
    "metadata":    {regions, environments, cidrs}
  }
================================================================================
"""

# 🟢 BEGINNER: Standard library imports for JSON parsing, regex, and logging.
import json
import re
import logging
# 🟢 BEGINNER: Google Generative AI SDK. genai is the client; types defines message structures.
from google import genai
from google.genai import types
from typing import Dict, List, Any, Optional
from pathlib import Path
# 🟢 BEGINNER: Import our centralized config to get the Gemini API key and model names.
from app.core.config import settings

# 🟢 BEGINNER: Create a logger for this module. Log messages will show [VisionService] prefix.
logger = logging.getLogger(__name__)


# 🟢 BEGINNER: This class wraps the Google Gemini Vision API.
# It sends architecture diagram images to Gemini and asks it to return structured JSON data.
class VisionService:
    """Gemini Vision service for analyzing architecture diagrams.

    Uses the google.genai SDK (not deprecated google.generativeai).
    Initialized once per app worker process (singleton pattern in jobs.py).
    """

    def __init__(self):
        # 🟢 BEGINNER: Create the Gemini API client using the API key from our .env file.
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)
        # 🟢 BEGINNER: Use the vision-specific model (gemini-2.5-pro) for diagram analysis.
        self.model_name = settings.GEMINI_VISION_MODEL
        logger.info(f"[VisionService] Initialized with model: {self.model_name}")

    def analyze_diagram(self, image_path: str, ocr_text: str = None, context_pack: dict = None) -> Dict:
        """Analyze architecture diagram using Gemini Vision with retry logic."""
        logger.info(f"[VisionService] Analyzing diagram: {image_path}")

        for attempt in range(2):
            try:
                image_bytes = Path(image_path).read_bytes()
                logger.info(f"[VisionService] Loaded image: {len(image_bytes)} bytes (attempt {attempt + 1})")

                prompt = self._build_analysis_prompt(ocr_text, context_pack)

                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=[
                        types.Content(parts=[
                            types.Part.from_text(text=prompt),
                            types.Part.from_bytes(data=image_bytes, mime_type=self._get_mime_type(image_path)),
                        ])
                    ]
                )

                response_text = response.text
                logger.info(f"[VisionService] Gemini response: {len(response_text)} chars")

                analysis = self._parse_vision_response(response_text)

                # Quality gate: must have at least 1 component
                if not analysis.get("components"):
                    logger.warning(f"[VisionService] No components detected, attempt {attempt + 1}")
                    if attempt == 0:
                        continue
                    return {
                        "success": False,
                        "error": "No components detected in diagram after retry",
                        "analysis": analysis,
                        "raw_response": response_text
                    }

                logger.info(f"[VisionService] Success: {len(analysis.get('components', []))} components, {len(analysis.get('connections', []))} connections, {len(analysis.get('data_flows', []))} data flows")

                return {
                    "success": True,
                    "analysis": analysis,
                    "raw_response": response_text
                }

            except Exception as e:
                logger.error(f"[VisionService] Attempt {attempt + 1} failed: {e}")
                if attempt == 0:
                    import time as _time
                    _time.sleep(2 ** attempt)  # 1s backoff
                    continue
                return {
                    "success": False,
                    "error": str(e),
                    "analysis": {}
                }

    @staticmethod
    def _get_mime_type(image_path: str) -> str:
        """Determine MIME type from file extension."""
        # 🟢 BEGINNER: Get the file extension (e.g., ".png") and look it up in a dictionary.
        # The MIME type tells Gemini what kind of image we're sending.
        ext = Path(image_path).suffix.lower()
        mime_map = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
            ".svg": "image/svg+xml",
            ".pdf": "application/pdf",
        }
        return mime_map.get(ext, "image/png")

    def _build_analysis_prompt(self, ocr_text: str = None, context_pack: dict = None) -> str:
        """Build a world-class prompt for architecture diagram analysis.

        This prompt is designed to extract maximum fidelity from Gemini Vision,
        with a $500/hr cloud architect quality bar. Every component must include
        specific configuration details that would appear in production Terraform.
        """
        context_block = ""
        if context_pack:
            comps = context_pack.get("components", [])
            conns = context_pack.get("connections", [])
            cloud = context_pack.get("cloud_provider", "aws")
            context_block = f"""
## PREVIOUS CONTEXT (from document text analysis)
Detected Cloud Provider: {cloud.upper()}
Known Components ({len(comps)}):
"""
            for c in comps[:10]:
                context_block += f"- {c.get('name', 'unknown')} ({c.get('type', 'unknown')})\n"
            if conns:
                context_block += f"\nKnown Connections ({len(conns)}):\n"
                for cn in conns[:5]:
                    context_block += f"- {cn.get('source', '?')} -> {cn.get('target', '?')}\n"
            context_block += "\nUse this context to cross-validate your visual detections. Resolve conflicts in favor of the visual diagram.\n"

        prompt = f"""You are a senior cloud infrastructure architect billing $500/hour. Your task is to analyze an architecture diagram and produce a machine-precise extraction.

## QUALITY BAR
For EVERY component you detect, you MUST include:
- Exact service name (e.g., "aws_db_instance" not just "RDS")
- Concrete configuration: instance class, engine version, storage type, CIDR ranges, port numbers
- IAM role / security group references if implied by the diagram
- Cost tier (t3.micro, db.t3.medium, etc.) — pick the most appropriate for the drawn size/importance
- Confidence score (0.0–1.0) with a 1-sentence rationale

## EXTRACTION SCHEMA
Return ONLY valid JSON. No markdown fences, no commentary outside the JSON.

```json
{{
  "cloud_providers": [
    {{
      "provider": "aws|gcp|azure",
      "confidence": 0.95,
      "evidence": ["VPC shape with AWS logo", "IAM role icon present"]
    }}
  ],
  "components": [
    {{
      "name": "prod-web-vpc",
      "type": "vpc",
      "provider": "aws",
      "display_name": "Production Web VPC",
      "configuration": {{
        "cidr": "10.0.0.0/16",
        "tenancy": "default",
        "dns_hostnames": true
      }},
      "labels": ["prod", "web-tier"],
      "ports": [],
      "confidence": 0.98,
      "confidence_rationale": "Clearly labeled VPC with CIDR block visible",
      "security_group_refs": ["sg-web", "sg-db"],
      "iam_role_refs": ["ec2-instance-role"],
      "tier": "production"
    }},
    {{
      "name": "web-alb",
      "type": "application_load_balancer",
      "provider": "aws",
      "display_name": "Web Application Load Balancer",
      "configuration": {{
        "scheme": "internet-facing",
        "idle_timeout": 60,
        "deletion_protection": false
      }},
      "labels": ["public"],
      "ports": [80, 443],
      "confidence": 0.95,
      "confidence_rationale": "Classic ALB icon with listener arrows to EC2",
      "security_group_refs": ["sg-alb"],
      "tier": "production"
    }},
    {{
      "name": "web-asg",
      "type": "auto_scaling_group",
      "provider": "aws",
      "display_name": "Web Auto Scaling Group",
      "configuration": {{
        "min_size": 2,
        "max_size": 6,
        "desired_capacity": 2,
        "instance_type": "t3.medium",
        "ami": "ami-0c02fb55956c7d316",
        "key_name": "prod-key"
      }},
      "labels": ["web-tier", "auto-scaled"],
      "ports": [80],
      "confidence": 0.92,
      "confidence_rationale": "EC2 instances in an ASG pattern with CloudWatch alarm",
      "security_group_refs": ["sg-web"],
      "iam_role_refs": ["ec2-instance-role"],
      "tier": "production"
    }},
    {{
      "name": "app-db",
      "type": "rds",
      "provider": "aws",
      "display_name": "Application PostgreSQL Database",
      "configuration": {{
        "engine": "postgres",
        "engine_version": "15.4",
        "instance_class": "db.t3.medium",
        "allocated_storage": 100,
        "storage_type": "gp3",
        "multi_az": true,
        "publicly_accessible": false,
        "backup_retention": 7,
        "encryption": true
      }},
      "labels": ["database", "encrypted"],
      "ports": [5432],
      "confidence": 0.97,
      "confidence_rationale": "RDS icon with PostgreSQL label and Multi-AZ indicator",
      "security_group_refs": ["sg-db"],
      "tier": "production"
    }},
    {{
      "name": "app-s3-bucket",
      "type": "s3",
      "provider": "aws",
      "display_name": "Application Assets Bucket",
      "configuration": {{
        "versioning": true,
        "encryption": "AES256",
        "public_access_block": true,
        "lifecycle_days": 90
      }},
      "labels": ["assets", "versioned"],
      "ports": [443],
      "confidence": 0.94,
      "confidence_rationale": "S3 bucket icon with CloudFront arrow",
      "tier": "production"
    }}
  ],
  "boundaries": [
    {{
      "type": "vpc",
      "name": "prod-web-vpc",
      "provider": "aws",
      "cidr": "10.0.0.0/16",
      "region": "us-east-1",
      "azs": ["us-east-1a", "us-east-1b", "us-east-1c"],
      "confidence": 0.98
    }},
    {{
      "type": "subnet",
      "name": "public-subnet-1a",
      "provider": "aws",
      "cidr": "10.0.1.0/24",
      "region": "us-east-1",
      "az": "us-east-1a",
      "is_public": true,
      "confidence": 0.90
    }},
    {{
      "type": "subnet",
      "name": "private-subnet-1a",
      "provider": "aws",
      "cidr": "10.0.2.0/24",
      "region": "us-east-1",
      "az": "us-east-1a",
      "is_public": false,
      "confidence": 0.90
    }}
  ],
  "connections": [
    {{
      "source": "web-alb",
      "target": "web-asg",
      "protocol": "HTTP",
      "port": 80,
      "type": "synchronous",
      "direction": "forward",
      "confidence": 0.95,
      "rationale": "ALB listener arrow pointing to target group"
    }},
    {{
      "source": "web-asg",
      "target": "app-db",
      "protocol": "TCP",
      "port": 5432,
      "type": "synchronous",
      "direction": "bidirectional-read",
      "confidence": 0.92,
      "rationale": "Dashed line from EC2 tier to RDS with port annotation"
    }},
    {{
      "source": "web-asg",
      "target": "app-s3-bucket",
      "protocol": "HTTPS",
      "port": 443,
      "type": "synchronous",
      "direction": "write",
      "confidence": 0.88,
      "rationale": "IAM policy arrow from EC2 to S3"
    }}
  ],
  "data_flows": [
    {{
      "path": "Client → ALB → EC2 → RDS",
      "classification": "customer_pii",
      "criticality": "high",
      "encryption_in_transit": true,
      "encryption_at_rest": true
    }},
    {{
      "path": "EC2 → S3",
      "classification": "internal_assets",
      "criticality": "medium",
      "encryption_in_transit": true,
      "encryption_at_rest": true
    }}
  ],
  "metadata": {{
    "regions": ["us-east-1"],
    "environments": ["production"],
    "cidrs": ["10.0.0.0/16", "10.0.1.0/24", "10.0.2.0/24"],
    "compliance_frameworks": ["SOC2", "GDPR"],
    "estimated_monthly_cost_usd": 450
  }},
  "security_groups": [
    {{
      "name": "sg-alb",
      "ingress": [{{"from_port": 80, "to_port": 80, "protocol": "tcp", "cidr": "0.0.0.0/0"}}, {{"from_port": 443, "to_port": 443, "protocol": "tcp", "cidr": "0.0.0.0/0"}}],
      "egress": [{{"from_port": 0, "to_port": 0, "protocol": "-1", "cidr": "0.0.0.0/0"}}]
    }},
    {{
      "name": "sg-web",
      "ingress": [{{"from_port": 80, "to_port": 80, "protocol": "tcp", "source_sg": "sg-alb"}}],
      "egress": [{{"from_port": 0, "to_port": 0, "protocol": "-1", "cidr": "0.0.0.0/0"}}]
    }},
    {{
      "name": "sg-db",
      "ingress": [{{"from_port": 5432, "to_port": 5432, "protocol": "tcp", "source_sg": "sg-web"}}],
      "egress": []
    }}
  ],
  "unresolved": [
    {{
      "item": "mystery-box-top-right",
      "ambiguity": "Unlabeled rectangle with no connecting lines",
      "possible_interpretations": ["bastion host", "management console", "monitoring dashboard"],
      "confidence": 0.3
    }}
  ]
}}
```

## RULES
1. Output ONLY the JSON object. No markdown code fences, no preamble, no postscript.
2. If a CIDR is not visible in the diagram, infer a reasonable RFC1918 range and mark confidence < 0.9.
3. If an instance type is not labeled, choose the smallest production-appropriate type (t3.medium for compute, db.t3.medium for RDS) and flag it.
4. Every connection MUST have a rationale explaining WHY that connection exists based on the diagram.
5. Include security groups as first-class objects if the diagram shows any network segmentation.
6. Include compliance frameworks ONLY if explicitly shown (e.g., "PCI", "HIPAA" labels).
7. The "data_flows" array captures end-to-end paths, not just individual connections.
{context_block}"""

        if ocr_text:
            prompt += f"\n\n## OCR SUPPLEMENTARY TEXT\n{ocr_text[:3000]}\n\nUse this OCR text to resolve ambiguous labels, but the visual diagram structure takes precedence."

        return prompt

    def _parse_vision_response(self, response_text: str) -> Dict:
        """Parse Gemini Vision response into structured format with validation."""
        response_text = response_text.strip()

        # Try multiple JSON extraction strategies
        candidates = []

        # Strategy 1: Look for JSON inside markdown fences
        fence_match = re.search(r'```(?:json)?\s*\n(\{[\s\S]*?\})\n```', response_text)
        if fence_match:
            candidates.append(fence_match.group(1))

        # Strategy 2: Find the outermost balanced braces
        brace_depth = 0
        start_idx = None
        for i, ch in enumerate(response_text):
            if ch == '{':
                if brace_depth == 0:
                    start_idx = i
                brace_depth += 1
            elif ch == '}':
                brace_depth -= 1
                if brace_depth == 0 and start_idx is not None:
                    candidates.append(response_text[start_idx:i+1])
                    start_idx = None

        # Strategy 3: First { ... } match (legacy fallback)
        if not candidates:
            json_match = re.search(r'\{[\s\S]*\}', response_text)
            if json_match:
                candidates.append(json_match.group())

        # Try each candidate
        for candidate in candidates:
            try:
                analysis = json.loads(candidate)
                # Validate required keys
                validated = self._validate_analysis(analysis)
                if validated:
                    logger.info(f"[VisionService] Parsed analysis: {len(validated.get('components', []))} components")
                    return validated
            except json.JSONDecodeError:
                continue

        # All parsing failed — fallback
        logger.warning("[VisionService] JSON extraction failed, falling back to text parser")
        return self._parse_text_response(response_text)

    def _validate_analysis(self, analysis: Dict) -> Optional[Dict]:
        """Validate and normalize the analysis dict. Returns None if unusable."""
        if not isinstance(analysis, dict):
            return None

        # Ensure all required keys exist
        required_keys = ["components", "connections", "boundaries", "metadata"]
        for key in required_keys:
            if key not in analysis:
                analysis[key] = []

        if "metadata" not in analysis or not isinstance(analysis["metadata"], dict):
            analysis["metadata"] = {"regions": [], "environments": [], "cidrs": []}

        # Normalize components
        for comp in analysis.get("components", []):
            if not isinstance(comp, dict):
                continue
            comp.setdefault("name", "unnamed")
            comp.setdefault("type", "unknown")
            comp.setdefault("provider", "aws")
            comp.setdefault("display_name", comp.get("name", ""))
            comp.setdefault("confidence", 0.5)
            comp.setdefault("confidence_rationale", "")
            comp.setdefault("configuration", {})
            comp.setdefault("labels", [])
            comp.setdefault("ports", [])
            comp.setdefault("security_group_refs", [])
            comp.setdefault("iam_role_refs", [])
            comp.setdefault("tier", "production")

        # Normalize connections
        for conn in analysis.get("connections", []):
            if not isinstance(conn, dict):
                continue
            conn.setdefault("source", "")
            conn.setdefault("target", "")
            conn.setdefault("protocol", "TCP")
            conn.setdefault("port", 0)
            conn.setdefault("type", "synchronous")
            conn.setdefault("direction", "forward")
            conn.setdefault("confidence", 0.5)
            conn.setdefault("rationale", "")

        # Ensure data_flows exists
        if "data_flows" not in analysis:
            analysis["data_flows"] = []

        # Ensure security_groups exists
        if "security_groups" not in analysis:
            analysis["security_groups"] = []

        return analysis

    def _parse_text_response(self, text: str) -> Dict:
        """Fallback text parser when JSON extraction fails"""
        # 🟢 BEGINNER: If Gemini didn't return valid JSON, we do a very simple keyword search.
        # This creates a minimal analysis object so the app doesn't crash.
        analysis = {
            "cloud_providers": [],
            "components": [],
            "boundaries": [],
            "connections": [],
            "metadata": {"regions": [], "environments": [], "cidrs": []},
            "unresolved": []
        }

        text_lower = text.lower()

        # 🟢 BEGINNER: Simple keyword matching to guess which cloud provider is mentioned.
        if "aws" in text_lower or "amazon" in text_lower:
            analysis["cloud_providers"].append({"provider": "aws", "confidence": 0.8})
        if "gcp" in text_lower or "google" in text_lower:
            analysis["cloud_providers"].append({"provider": "gcp", "confidence": 0.8})
        if "azure" in text_lower or "microsoft" in text_lower:
            analysis["cloud_providers"].append({"provider": "azure", "confidence": 0.8})

        return analysis

    def extract_components_with_bounding_boxes(self, image_path: str) -> List[Dict]:
        """Extract components with their visual bounding boxes"""
        try:
            image_bytes = Path(image_path).read_bytes()
            # 🟢 BEGINNER: This is an alternative prompt that asks Gemini to also provide bounding boxes.
            # Not currently used by the main pipeline, but available for future features.
            prompt = """Identify all components in this architecture diagram. For each component, provide:
            - Component name/type
            - Approximate bounding box (x, y, width, height as percentages)
            - Cloud provider

            Return as JSON list."""

            response = self.client.models.generate_content(
                model=self.model_name,
                contents=[
                    types.Content(parts=[
                        types.Part.from_text(text=prompt),
                        types.Part.from_bytes(data=image_bytes, mime_type=self._get_mime_type(image_path)),
                    ])
                ]
            )

            json_match = re.search(r'\[[\s\S]*\]', response.text)
            if json_match:
                return json.loads(json_match.group())
            return []
        except Exception as e:
            logger.warning(f"Bounding box extraction failed: {e}")
            return []

    def detect_connections(self, image_path: str, components: List[Dict]) -> List[Dict]:
        """Detect connections between components"""
        # 🟢 BEGINNER: Another specialized prompt that focuses ONLY on connections/arrows between components.
        # Passes the already-detected component names so Gemini knows what to look for.
        prompt = f"""Analyze the connections and data flows in this architecture diagram.

Known components:
{', '.join([c.get('name', c.get('type', 'unknown')) for c in components])}

For each connection, identify:
- Source component
- Target component
- Type of connection (synchronous, asynchronous, pub/sub, etc.)
- Protocol if visible (HTTP, TCP, etc.)
- Port if visible

Return as JSON list."""

        try:
            image_bytes = Path(image_path).read_bytes()
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=[
                    types.Content(parts=[
                        types.Part.from_text(text=prompt),
                        types.Part.from_bytes(data=image_bytes, mime_type=self._get_mime_type(image_path)),
                    ])
                ]
            )

            json_match = re.search(r'\[[\s\S]*\]', response.text)
            if json_match:
                return json.loads(json_match.group())
            return []
        except Exception as e:
            logger.warning(f"Connection detection failed: {e}")
            return []
