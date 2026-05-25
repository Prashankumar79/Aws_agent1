"""
================================================================================
  backend/app/services/architecture_extractor.py  —  ARCHITECTURE EXTRACTION
================================================================================

PURPOSE:
  Extract canonical infrastructure graph from uploaded documents using Docling + LLM.
  
  Flow:
  1. Docling parses PDF/DOCX/images into structured markdown
  2. Bedrock Claude LLM extracts infrastructure components from the parsed text
  3. Vision service (Gemini) analyzes images/diagrams
  4. Results merged into canonical InfraGraph

CONNECTIONS TO OTHER FILES:
  • models/infra_graph.py → Outputs canonical graph format
  • services/vision_service.py → Uses for image analysis
  • core/config.py → AWS Bedrock credentials

IMPORTANT:
  Always outputs canonical InfraGraph format (not raw OCR, not raw vision data).
================================================================================
"""
import logging
import json
import re
import boto3
from pathlib import Path
from typing import Dict, List, Optional, Any
from app.models.infra_graph import InfraGraph, GraphNode, GraphEdge, CloudProvider
from app.core.config import settings

logger = logging.getLogger(__name__)


class ArchitectureExtractor:
    """Extracts canonical infrastructure graph from documents using Docling + LLM."""
    
    def __init__(self):
        """Initialize the extractor with Bedrock client.

        Uses the shared core.bedrock_client factory so timeouts/retries match
        the rest of the system. Without this, vision-enrichment LLM calls
        could hang for 9 minutes on a stuck stream.
        """
        from app.core.bedrock_client import get_bedrock_client
        self.bedrock_client = get_bedrock_client()
        self.model_id = settings.AWS_BEDROCK_MODEL
    
    def extract_from_file(
        self,
        file_path: str,
        provider: CloudProvider = CloudProvider.AWS,
        use_vision: bool = True,
        context_pack: dict = None
    ) -> InfraGraph:
        """
        Extract infrastructure graph from uploaded file with dynamic context.
        Pipeline: Docling structured extraction → LLM refinement → Vision enrichment → edge inference.

        Args:
            file_path: Path to uploaded file (PDF, DOCX, image)
            provider: Cloud provider to detect
            use_vision: Whether to use Vision service for image analysis
            context_pack: Optional pre-existing context (from vision analysis) for cross-validation

        Returns:
            InfraGraph: Canonical infrastructure graph with rich properties
        """
        logger.info(f"[ArchitectureExtractor] Extracting from: {file_path}")

        file_path = Path(file_path)
        file_type = self._detect_file_type(file_path)

        # Step 1: Rich structured document extraction (Docling)
        structured_doc = {"text": "", "headings": [], "tables": [], "images": [], "page_count": 0}
        if file_type in ["pdf", "docx", "text"]:
            structured_doc = self._extract_structured_document(file_path, file_type)
        
        # Step 1b: Extract embedded images from PDF for vision analysis
        embedded_image_paths = []
        if use_vision and file_type == "pdf":
            embedded_image_paths = self._extract_images_from_pdf(file_path)
            structured_doc["images"] = [str(p) for p in embedded_image_paths]
            logger.info(f"[ArchitectureExtractor] Extracted {len(embedded_image_paths)} embedded images from PDF")

        # Step 2: Extract components from structured text (LLM refinement)
        nodes = self._extract_components_from_structured(structured_doc, provider, context_pack)

        # Step 3: Vision analysis — direct image files + embedded PDF images
        if use_vision:
            if file_type == "image":
                vision_nodes = self._extract_from_vision(file_path, provider)
                nodes = self._merge_nodes(nodes, vision_nodes)
            elif embedded_image_paths:
                for img_path in embedded_image_paths:
                    vision_nodes = self._extract_from_vision(img_path, provider)
                    nodes = self._merge_nodes(nodes, vision_nodes)

        # Step 4: Infer connections using LLM + pattern matching
        edges = self._infer_edges(nodes)

        # Create canonical graph with enriched metadata
        graph = InfraGraph(
            nodes=nodes,
            edges=edges,
            provider=provider,
            source_file=str(file_path),
            extraction_method="docling+vision+llm" if use_vision else "docling+llm"
        )

        logger.info(f"[ArchitectureExtractor] Extracted {len(nodes)} nodes, {len(edges)} edges")
        return graph
    
    def _detect_file_type(self, file_path: Path) -> str:
        """Detect file type."""
        suffix = file_path.suffix.lower()
        if suffix == ".pdf":
            return "pdf"
        elif suffix in [".docx", ".doc"]:
            return "docx"
        elif suffix in [".png", ".jpg", ".jpeg", ".svg"]:
            return "image"
        elif suffix in [".txt", ".md"]:
            return "text"
        else:
            return "unknown"
    
    def _extract_structured_document(self, file_path: Path, file_type: str) -> Dict:
        """Extract rich structured content from document using the unified helper.

        🟢 BEGINNER: Returns dict with text/headings/tables/images/page_count.
        Image extraction is OFF here — embedded images are pulled separately
        via _extract_images_from_pdf() in the parent flow.
        """
        from app.utils.document_extract import extract_document, headings_to_outline  # noqa: F401

        structured = {
            "text": "",
            "headings": [],
            "tables": [],
            "images": [],
            "page_count": 0,
        }

        extracted = extract_document(file_path, extract_images=False)
        if extracted.error and not extracted.text:
            logger.error(f"[ArchitectureExtractor] Extraction failed: {extracted.error}")
            return structured

        structured["text"] = extracted.text
        structured["headings"] = [(h.text, h.level) for h in extracted.headings]
        structured["tables"] = list(extracted.tables)
        structured["page_count"] = extracted.page_count

        logger.info(
            f"[ArchitectureExtractor] method={extracted.method} | "
            f"chars={len(structured['text'])} | headings={len(structured['headings'])} | "
            f"tables={len(structured['tables'])} | pages={structured['page_count']}"
        )
        return structured

    def _extract_images_from_pdf(self, file_path: Path) -> List[Path]:
        """🟢 BEGINNER: Extract embedded images via the unified helper (pymupdf)."""
        from app.utils.document_extract import _extract_pdf_images
        target_dir = file_path.parent / f"{file_path.stem}_images"
        return [Path(p) for p in _extract_pdf_images(file_path, target_dir)]

    def _fallback_extract_text(self, file_path: Path, file_type: str) -> str:
        """🟢 BEGINNER: Kept for backward compatibility — the unified helper now
        already does Docling → pdfplumber fallback internally, so this just
        delegates to it."""
        from app.utils.document_extract import extract_document
        return extract_document(file_path, extract_images=False).text
    
    def _extract_components_from_structured(self, structured_doc: Dict, provider: CloudProvider, context_pack: dict = None) -> List[GraphNode]:
        """Extract infrastructure components using Bedrock Claude LLM with rich structured document input."""
        nodes = []
        text = structured_doc.get("text", "")
        if not text or len(text) < 50:
            return nodes

        try:
            prompt = self._build_extraction_prompt(structured_doc, provider, context_pack)

            response = self.bedrock_client.invoke_model(
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

            response_body = json.loads(response['body'].read().decode())
            response_text = response_body['content'][0]['text']

            components = self._parse_llm_response(response_text)

            for i, comp in enumerate(components):
                raw_provider = comp.get('provider', provider.value)
                try:
                    node_provider = CloudProvider(raw_provider.lower())
                except Exception:
                    node_provider = provider
                node = GraphNode(
                    id=comp.get('id', f"llm-{i}"),
                    provider=node_provider,
                    service=comp.get('service', 'unknown').lower().replace(' ', '_'),
                    label=comp.get('label', comp.get('service', 'Unknown')),
                    properties={
                        "source": "llm_extraction",
                        "type": comp.get('type', 'unknown'),
                        "description": comp.get('description', ''),
                        "confidence": comp.get('confidence', 0.8),
                        "confidence_rationale": comp.get('confidence_rationale', ''),
                        "configuration": comp.get('configuration', {}),
                        "environment": comp.get('environment', 'production'),
                        "tier": comp.get('tier', 'production'),
                        "labels": comp.get('labels', []),
                        "ports": comp.get('ports', []),
                        "security_group_refs": comp.get('security_group_refs', []),
                        "iam_role_refs": comp.get('iam_role_refs', []),
                    }
                )
                nodes.append(node)

            logger.info(f"[ArchitectureExtractor] LLM extracted {len(nodes)} components")

        except Exception as e:
            logger.error(f"[ArchitectureExtractor] LLM extraction failed: {e}")
            nodes = self._keyword_fallback(text, provider)

        return nodes
    
    def _build_extraction_prompt(self, structured_doc: Dict, provider: CloudProvider, context_pack: dict = None) -> str:
        """Build a world-class LLM prompt for infrastructure extraction with dynamic context."""
        text = structured_doc.get("text", "")
        headings = structured_doc.get("headings", [])
        tables = structured_doc.get("tables", [])
        page_count = structured_doc.get("page_count", 0)
        
        # Build headings block
        headings_block = ""
        if headings:
            headings_block = "\n## DOCUMENT STRUCTURE (Headings)\n"
            for h_text, level in headings[:20]:
                indent = "  " * (level - 1) if level > 1 else ""
                headings_block += f"{indent}- {h_text}\n"
        
        # Build tables block
        tables_block = ""
        if tables:
            tables_block = f"\n## CONFIGURATION TABLES ({len(tables)} found)\n"
            for i, table_md in enumerate(tables[:3]):
                tables_block += f"\n### Table {i+1}\n{table_md[:1500]}\n"
        
        # Build context block from vision analysis
        context_block = ""
        if context_pack:
            comps = context_pack.get("components", [])
            conns = context_pack.get("connections", [])
            if comps or conns:
                context_block = f"""
## KNOWN CONTEXT (from previous vision analysis)
Detected Components ({len(comps)}):
"""
                for c in comps[:8]:
                    context_block += f"- {c.get('name', 'unknown')} ({c.get('type', 'unknown')})\n"
                if conns:
                    context_block += f"\nKnown Connections ({len(conns)}):\n"
                    for cn in conns[:5]:
                        context_block += f"- {cn.get('source', '?')} -> {cn.get('target', '?')}\n"
                context_block += "\nUse this context to validate and enrich your extraction. Resolve conflicts in favor of the document text.\n"

        return f"""You are a senior cloud infrastructure architect billing $500/hour. Analyze the following document and extract every infrastructure component with production-grade precision.

Use the DOCUMENT STRUCTURE headings to understand architecture tiers.
Use the CONFIGURATION TABLES for concrete values (CIDRs, instance types, ports).

## DOCUMENT TEXT
---
{text[:6000]}
---
{headings_block}
{tables_block}

## METADATA
- Cloud Provider: {provider.value.upper()}
- Pages: {page_count}
- Document headings: {len(headings)}
- Configuration tables: {len(tables)}

## QUALITY BAR
For EVERY component you MUST include:
- Exact Terraform resource type (e.g., "aws_db_instance" not just "RDS")
- Concrete configuration: instance class, engine version, CIDR, storage type
- Purpose / role in the architecture (1 sentence)
- Confidence score (0.0–1.0) with a 1-sentence rationale
- Environment tag (dev/staging/prod)

## OUTPUT SCHEMA
Return ONLY a JSON array. No markdown fences, no commentary.

```json
[
  {{
    "id": "prod-web-vpc",
    "service": "vpc",
    "label": "Production Web VPC",
    "type": "network",
    "provider": "{provider.value}",
    "description": "Primary VPC hosting the web tier and database subnets",
    "configuration": {{
      "cidr": "10.0.0.0/16",
      "tenancy": "default",
      "enable_dns_hostnames": true
    }},
    "environment": "production",
    "tier": "production",
    "confidence": 0.98,
    "confidence_rationale": "Explicitly labeled VPC with CIDR block in network diagram section"
  }},
  {{
    "id": "web-alb",
    "service": "alb",
    "label": "Web Application Load Balancer",
    "type": "load_balancing",
    "provider": "{provider.value}",
    "description": "Internet-facing ALB distributing traffic to EC2 auto-scaling group",
    "configuration": {{
      "scheme": "internet-facing",
      "idle_timeout": 60,
      "deletion_protection": false
    }},
    "environment": "production",
    "tier": "production",
    "confidence": 0.95,
    "confidence_rationale": "ALB referenced in load balancing section with listener rules"
  }}
]
```

## RULES
1. Output ONLY the JSON array. No preamble, no postscript. No markdown fences.
2. Limit to maximum 20 most important components. Deduplicate — one entry per service type.
3. If a CIDR or instance type is not specified, infer a reasonable production default and mark confidence < 0.9.
4. Every component MUST have a confidence_rationale explaining WHY you believe it exists.
5. Focus on actual infrastructure (VPC, EC2, S3, RDS, ALB, Lambda, IAM, KMS, etc.), not business logic.
6. Do NOT include generic placeholders — every component must have specific, actionable configuration.
{context_block}"""
    
    def _parse_llm_response(self, response_text: str) -> List[Dict]:
        """Parse JSON from LLM response, handling markdown fences."""
        try:
            # Strip markdown code fences (```json ... ``` or ``` ... ```)
            cleaned = re.sub(r'^```(?:json)?\s*', '', response_text.strip(), flags=re.IGNORECASE)
            cleaned = re.sub(r'```\s*$', '', cleaned.strip())
            cleaned = cleaned.strip()

            # Try to find JSON array in cleaned response
            json_match = re.search(r'\[[\s\S]*\]', cleaned)
            if json_match:
                return json.loads(json_match.group())
            # Try full cleaned response as JSON
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.warning(f"[ArchitectureExtractor] Failed to parse LLM response as JSON: {e}")
            logger.debug(f"[ArchitectureExtractor] Raw LLM response (first 300 chars): {response_text[:300]}")
            return []
    
    def _keyword_fallback(self, text: str, provider: CloudProvider) -> List[GraphNode]:
        """Fallback keyword extraction when LLM fails. Uses broader pattern matching."""
        nodes = []
        text_lower = text.lower()

        # Map of regex patterns → (service, type, label)
        patterns = {
            "vpc|virtual private cloud":                                        ("vpc",             "network",         "VPC"),
            "ec2|elastic compute|compute instance|virtual server|vm instance":  ("ec2",             "compute",         "EC2 Instance"),
            "rds|relational database|aurora|postgres|mysql|sql database":       ("rds",             "database",        "RDS Database"),
            "s3|simple storage|blob storage|object storage|storage bucket":     ("s3",              "storage",         "S3 Bucket"),
            "eks|kubernetes|k8s|container orchestration":                       ("eks",             "compute",         "EKS Cluster"),
            "lambda|serverless function|function app":                          ("lambda",          "compute",         "Lambda Function"),
            "cloudfront|cdn|content delivery":                                  ("cloudfront",      "cdn",             "CloudFront CDN"),
            "alb|application load balancer|load balancer|elb|nlb":              ("alb",             "load_balancing",  "Application Load Balancer"),
            "iam|identity access|role policy|permission":                       ("iam",             "security",        "IAM"),
            "kms|key management|encryption key|ssl/tls":                        ("kms",             "security",        "KMS"),
            "waf|web application firewall|firewall":                            ("waf",             "security",        "WAF"),
            "dynamodb|nosql|document db|key-value":                             ("dynamodb",        "database",        "DynamoDB"),
            "elasticache|redis|memcached|in-memory cache":                      ("elasticache",     "database",        "ElastiCache"),
            "route53|dns|domain name":                                          ("route53",         "dns",             "Route 53"),
            "api gateway|rest api|graphql|endpoint":                            ("api_gateway",     "edge",            "API Gateway"),
            "sns|notification|pub/sub|event bus|messaging":                     ("sns",             "messaging",       "SNS"),
            "sqs|message queue|queue|buffer":                                   ("sqs",             "messaging",       "SQS"),
            "cloudwatch|monitoring|logging|observability|metrics":              ("cloudwatch",      "monitoring",      "CloudWatch"),
            "subnet|private subnet|public subnet":                              ("subnet",          "network",         "Subnet"),
            "nat gateway|internet gateway|igw|nat":                             ("nat_gateway",     "network",         "NAT Gateway"),
            "auto scaling|asg|scaling group|elasticity":                        ("autoscaling",     "compute",         "Auto Scaling"),
            "efs|file system|nfs|shared storage":                               ("efs",             "storage",         "EFS"),
            "secrets manager|parameter store|vault|credential":                 ("secrets_manager", "security",        "Secrets Manager"),
            "cognito|authn|authz|user pool|identity provider|oauth|oidc":       ("cognito",        "security",        "Cognito"),
        }

        found_services = set()
        node_counter = 0

        for pattern_str, (service, svc_type, label) in patterns.items():
            if re.search(pattern_str, text_lower):
                if service not in found_services:
                    found_services.add(service)
                    nodes.append(GraphNode(
                        id=f"fallback-{service}-{node_counter}",
                        provider=provider,
                        service=service,
                        label=label,
                        properties={
                            "source": "keyword_fallback",
                            "type": svc_type,
                            "confidence": 0.5,
                            "confidence_rationale": f"Detected via keyword pattern: {pattern_str}"
                        }
                    ))
                    node_counter += 1

        logger.info(f"[ArchitectureExtractor] Keyword fallback found {len(nodes)} components")
        return nodes
    
    def _extract_from_vision(self, file_path: Path, provider: CloudProvider) -> List[GraphNode]:
        """Extract components using Vision service for any image file.
        Called for direct image uploads AND for embedded images extracted from PDFs."""
        nodes = []
        
        try:
            from app.services.vision_service import VisionService
            
            vision_service = VisionService()
            file_path = Path(file_path)
            
            # Analyze any image file (png, jpg, svg, or extracted PDF page images)
            if file_path.exists() and file_path.suffix.lower() in [".png", ".jpg", ".jpeg", ".svg", ".gif", ".webp", ".bmp"]:
                logger.info(f"[ArchitectureExtractor] Running vision analysis on: {file_path.name}")
                analysis = vision_service.analyze_diagram(str(file_path))
                nodes = self._vision_to_nodes(analysis, provider)
                logger.info(f"[ArchitectureExtractor] Vision extracted {len(nodes)} components from {file_path.name}")
            else:
                logger.warning(f"[ArchitectureExtractor] Skipping vision for non-image file: {file_path}")
        
        except Exception as e:
            logger.error(f"[ArchitectureExtractor] Vision extraction failed for {file_path}: {e}")
        
        return nodes
    
    def _vision_to_nodes(self, analysis: Dict, provider: CloudProvider) -> List[GraphNode]:
        """Convert Vision analysis output to GraphNodes."""
        nodes = []
        components = analysis.get("components", [])
        
        for i, comp in enumerate(components):
            node_id = f"vision-{i}"
            node = GraphNode(
                id=node_id,
                provider=provider,
                service=comp.get("type", "unknown").lower(),
                label=comp.get("name", f"Component {i}"),
                properties={
                    "source": "vision_analysis",
                    "position": comp.get("position", {}),
                    "confidence": comp.get("confidence", 0.0)
                }
            )
            nodes.append(node)
        
        return nodes
    
    def _merge_nodes(self, nodes1: List[GraphNode], nodes2: List[GraphNode]) -> List[GraphNode]:
        """Merge two node lists, avoiding duplicates and merging properties."""
        merged = {}

        for node in nodes1 + nodes2:
            key = node.service.lower().strip()
            if not key:
                continue
            if key not in merged:
                merged[key] = node
                continue

            existing = merged[key]
            # Keep the node with higher confidence, but merge properties
            if node.properties.get("confidence", 0) > existing.properties.get("confidence", 0):
                # Merge lists from existing into new winner
                new_props = dict(node.properties)
                for list_key in ["labels", "ports", "security_group_refs", "iam_role_refs"]:
                    old_set = set(existing.properties.get(list_key, []))
                    new_set = set(node.properties.get(list_key, []))
                    new_props[list_key] = list(old_set | new_set)
                # Merge configuration dict
                old_config = existing.properties.get("configuration", {})
                new_config = node.properties.get("configuration", {})
                merged_config = {**old_config, **new_config}
                new_props["configuration"] = merged_config
                # Mark dual source
                new_props["sources"] = list(dict.fromkeys(
                    [existing.properties.get("source", ""), node.properties.get("source", "")]
                ))
                node.properties = new_props
                merged[key] = node
            else:
                # Merge lists from node into existing
                for list_key in ["labels", "ports", "security_group_refs", "iam_role_refs"]:
                    old_set = set(existing.properties.get(list_key, []))
                    new_set = set(node.properties.get(list_key, []))
                    existing.properties[list_key] = list(old_set | new_set)
                # Merge configuration
                old_config = existing.properties.get("configuration", {})
                new_config = node.properties.get("configuration", {})
                existing.properties["configuration"] = {**old_config, **new_config}
                # Mark dual source
                sources = list(dict.fromkeys(
                    [existing.properties.get("source", ""), node.properties.get("source", "")]
                ))
                existing.properties["sources"] = sources

        return list(merged.values())
    
    def _infer_edges(self, nodes: List[GraphNode]) -> List[GraphEdge]:
        """Infer connections between components using LLM + pattern hybrid."""
        edges = []

        # Phase 1: LLM-based edge inference for richer connections
        try:
            llm_edges = self._infer_edges_with_llm(nodes)
            edges.extend(llm_edges)
        except Exception as e:
            logger.warning(f"[ArchitectureExtractor] LLM edge inference failed: {e}, falling back to patterns")

        # Phase 2: Pattern-based fallback for common infrastructure relationships
        pattern_edges = self._infer_edges_from_patterns(nodes)

        # Merge: LLM edges take priority; pattern edges fill gaps
        seen = set((e.source, e.target, e.relationship) for e in edges)
        for edge in pattern_edges:
            key = (edge.source, edge.target, edge.relationship)
            if key not in seen:
                edges.append(edge)
                seen.add(key)

        return edges

    def _infer_edges_with_llm(self, nodes: List[GraphNode]) -> List[GraphEdge]:
        """Use Claude to infer rich connections with protocols, ports, and rationale."""
        if len(nodes) < 2:
            return []

        node_list = []
        for n in nodes:
            node_list.append({
                "id": n.id,
                "service": n.service,
                "label": n.label,
                "type": n.properties.get("type", "unknown"),
                "configuration": n.properties.get("configuration", {}),
            })

        prompt = f"""You are a cloud network architect. Given the following infrastructure components, infer ALL plausible connections between them.

Components:
{json.dumps(node_list, indent=2)}

For each connection, provide:
- source: component ID
- target: component ID
- relationship: descriptive type (e.g., "serves_traffic_to", "reads_from", "writes_to", "deployed_in", "manages")
- protocol: HTTP, HTTPS, TCP, UDP, etc.
- port: port number
- direction: forward, bidirectional, reverse
- rationale: 1 sentence explaining WHY this connection exists

Return ONLY a JSON array. No markdown fences.

Example:
[
  {{"source": "web-alb", "target": "web-asg", "relationship": "serves_traffic_to", "protocol": "HTTP", "port": 80, "direction": "forward", "rationale": "ALB forwards HTTP requests to target group instances"}},
  {{"source": "web-asg", "target": "app-db", "relationship": "reads_from", "protocol": "TCP", "port": 5432, "direction": "bidirectional-read", "rationale": "Application servers query PostgreSQL for user data"}}
]"""

        response = self.bedrock_client.invoke_model(
            modelId=self.model_id,
            contentType="application/json",
            accept="application/json",
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 3000,
                "messages": [{"role": "user", "content": prompt}]
            })
        )

        response_body = json.loads(response['body'].read().decode())
        response_text = response_body['content'][0]['text']

        json_match = re.search(r'\[[\s\S]*\]', response_text)
        if not json_match:
            return []

        connections = json.loads(json_match.group())
        edges = []
        node_ids = {n.id for n in nodes}

        for conn in connections:
            src = conn.get("source", "")
            tgt = conn.get("target", "")
            if src in node_ids and tgt in node_ids and src != tgt:
                edge = GraphEdge(
                    source=src,
                    target=tgt,
                    relationship=conn.get("relationship", "connects_to"),
                    properties={
                        "protocol": conn.get("protocol", "TCP"),
                        "port": conn.get("port", 0),
                        "direction": conn.get("direction", "forward"),
                        "rationale": conn.get("rationale", ""),
                        "inferred": True,
                        "inference_method": "llm",
                    }
                )
                edges.append(edge)

        logger.info(f"[ArchitectureExtractor] LLM inferred {len(edges)} connections")
        return edges

    def _infer_edges_from_patterns(self, nodes: List[GraphNode]) -> List[GraphEdge]:
        """Pattern-based edge inference as fallback."""
        edges = []

        # Richer patterns with protocol and port info
        patterns = [
            (["eks", "gke", "aks"], ["vpc", "vnet"], "deployed_in", "TCP", 0, "bidirectional"),
            (["rds", "sql database", "cosmos db", "cloud sql"], ["vpc", "vnet"], "deployed_in", "TCP", 0, "bidirectional"),
            (["ec2", "vm", "compute engine"], ["vpc", "vnet"], "deployed_in", "TCP", 0, "bidirectional"),
            (["alb", "nlb", "load balancer", "app gateway"], ["vpc", "vnet"], "deployed_in", "TCP", 0, "bidirectional"),
            (["alb", "nlb", "load balancer", "app gateway"], ["ec2", "vm", "compute engine", "auto_scaling_group"], "serves_traffic_to", "HTTP", 80, "forward"),
            (["alb", "nlb", "load balancer", "app gateway"], ["ec2", "vm", "compute engine", "auto_scaling_group"], "serves_traffic_to", "HTTPS", 443, "forward"),
            (["ec2", "vm", "compute engine", "auto_scaling_group"], ["rds", "sql database", "cosmos db", "cloud sql"], "reads_from", "TCP", 5432, "bidirectional-read"),
            (["ec2", "vm", "compute engine", "auto_scaling_group"], ["rds", "sql database", "cosmos db", "cloud sql"], "reads_from", "TCP", 3306, "bidirectional-read"),
            (["lambda", "function app", "cloud functions"], ["s3", "blob storage", "cloud storage"], "writes_to", "HTTPS", 443, "write"),
            (["lambda", "function app", "cloud functions"], ["dynamodb", "cosmos db", "firestore"], "reads_from", "HTTPS", 443, "bidirectional-read"),
            (["lambda", "function app", "cloud functions"], ["sns", "event grid", "pub/sub"], "publishes_to", "HTTPS", 443, "forward"),
            (["api gateway"], ["lambda", "function app", "cloud functions"], "invokes", "HTTPS", 443, "forward"),
            (["cloudfront", "cdn"], ["s3", "blob storage", "cloud storage"], "caches_from", "HTTPS", 443, "forward"),
        ]

        for source_services, target_services, relationship, protocol, port, direction in patterns:
            source_nodes = [n for n in nodes if any(s in n.service for s in source_services)]
            target_nodes = [n for n in nodes if any(s in n.service for s in target_services)]

            for source in source_nodes:
                for target in target_nodes:
                    if source.id != target.id:
                        edge = GraphEdge(
                            source=source.id,
                            target=target.id,
                            relationship=relationship,
                            properties={
                                "protocol": protocol,
                                "port": port,
                                "direction": direction,
                                "inferred": True,
                                "inference_method": "pattern",
                            }
                        )
                        edges.append(edge)

        return edges
