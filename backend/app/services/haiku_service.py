"""
================================================================================
  backend/app/services/haiku_service.py  —  HAIKU CONTEXT COMPRESSION SERVICE
================================================================================

PURPOSE:
  Dedicated service for AWS Bedrock Haiku model operations.
  Used for context compression, extraction, and filtering before final generation.

WHY HAIKU:
  Haiku is a fast, cost-effective model ideal for:
  - Summarization
  - Extraction
  - Compression
  - Deduplication
  - Semantic filtering

CONNECTIONS TO OTHER FILES:
  • core/config.py → AWS_BEDROCK_HAIKU_MODEL configuration
  • nodes/haiku_compression.py → Uses this service for compression
  • bedrock_service.py → Similar pattern but uses Sonnet for final generation

IMPORTANT:
  Haiku is used ONLY for preprocessing.
  Final generation (design doc, terraform) uses Sonnet/GPT-5.
================================================================================
"""
import boto3
import json
import logging
import re
from typing import Dict, List, Any
from app.core.config import settings

logger = logging.getLogger(__name__)


class HaikuService:
    """AWS Bedrock Haiku service for context compression and extraction."""

    def __init__(self):
        """Initialize the Haiku Bedrock client.

        Uses the shared core.bedrock_client factory so the timeout/retry
        config is consistent with every other Bedrock caller in the app.
        """
        from app.core.bedrock_client import get_bedrock_client
        self.region = settings.AWS_DEFAULT_REGION
        self.model_id = settings.AWS_BEDROCK_HAIKU_MODEL
        self.client = get_bedrock_client()
        logger.info(f"[HaikuService] Initialized with model: {self.model_id}")

    def invoke_haiku(self, messages: List[Dict[str, str]], max_tokens: int = 4000) -> str:
        """Low-level Haiku invocation. Routes through LLM Gateway for caching and circuit breaking."""
        from app.core.llm_gateway import get_gateway
        return get_gateway().call(
            messages=messages,
            task_type="template_compression",  # default; callers can override via gateway directly
            max_tokens=max_tokens,
        )

    def compress_template(self, template_content: str) -> Dict:
        """
        Extract governance rules, terraform rules, naming standards, security constraints, compliance requirements from template.
        Returns RICH descriptive rules (not booleans) so downstream LLMs can generate deeply specific content.

        Falls back to rule-based extraction if Haiku LLM call fails — ensures template is NEVER ignored.
        """
        if not template_content or not template_content.strip():
            return self._default_template_result()

        prompt = f"""You are an expert cloud governance analyst. Extract ALL actionable rules from this enterprise template.

CRITICAL: Return DESCRIPTIVE STRINGS, not booleans. Each rule should be a complete, actionable sentence.

TEMPLATE CONTENT:
{template_content}

Return structured JSON ONLY (no markdown, no explanations):
{{
  "governance": {{
    "rules": ["Multi-AZ required for all stateful services (RDS, ElastiCache, OpenSearch)", "No public subnets for databases", ...],
    "environment_strategy": "dev/staging/prod with separate accounts",
    "tagging_policy": "All resources must have: Environment, Owner, CostCenter, Project tags",
    "approved_regions": ["us-east-1", "eu-west-1"],
    "budget_constraints": "any mentioned budget limits or cost targets"
  }},
  "terraform_rules": {{
    "module_pattern": "one module per service / monolithic / layered",
    "state_backend": "S3+DynamoDB / Terraform Cloud / local",
    "provider_version": "version constraint if mentioned",
    "required_providers": ["aws", "random", ...],
    "variable_conventions": "description of variable naming and typing rules",
    "output_conventions": "what outputs to expose",
    "backend_config": "any backend configuration requirements"
  }},
  "naming_standards": {{
    "pattern": "{{env}}-{{app}}-{{service}}-{{resource}}",
    "separator": "-",
    "examples": ["prod-myapp-api-sg", "dev-myapp-rds-primary"],
    "case_rule": "lowercase / camelCase / snake_case",
    "max_length": "any length constraints",
    "prefix_suffix_rules": "any prefix/suffix requirements"
  }},
  "security": {{
    "rules": ["AES-256 encryption at rest for all storage services", "TLS 1.3 for all in-transit data", "No public IPs on compute instances", ...],
    "encryption_standard": "AES-256 / AES-256-GCM / KMS-managed",
    "iam_policy": "least-privilege with permission boundaries",
    "network_rules": ["VPC flow logs enabled", "No 0.0.0.0/0 ingress except ALB port 443", ...],
    "secret_management": "AWS Secrets Manager / SSM Parameter Store / HashiCorp Vault",
    "mfa_policy": "MFA required for all IAM users with console access"
  }},
  "compliance": {{
    "frameworks": ["SOC2", "CIS Level 1", "HIPAA", ...],
    "specific_controls": ["CC6.1 - Logical access controls", "CC7.2 - System monitoring", ...],
    "audit_requirements": ["CloudTrail enabled in all regions", "90-day log retention", ...]
  }}
}}

Rules:
- If a field is not mentioned in the template, use null (not empty string).
- For list fields, extract ALL items mentioned — do not summarize.
- Preserve exact values from the template (region names, instance types, CIDR ranges, etc.)."""
        try:
            from app.core.llm_gateway import get_gateway as _gw
            response = _gw().call(messages=[{"role": "user", "content": prompt}], task_type="template_compression", max_tokens=3000)
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                result = json.loads(json_match.group())
                # If LLM returned mostly empty result, use rule-based fallback as supplement
                if self._is_empty_template_result(result):
                    logger.warning("[HaikuService] LLM returned empty template result, using rule-based fallback")
                    return self._rule_based_template_extraction(template_content)
                return result
            else:
                logger.warning("[HaikuService] Could not extract JSON from template compression response, using rule-based fallback")
                return self._rule_based_template_extraction(template_content)
        except Exception as e:
            logger.error(f"[HaikuService] Template compression failed: {e}, using rule-based fallback")
            return self._rule_based_template_extraction(template_content)

    @staticmethod
    def _is_empty_template_result(result: Dict) -> bool:
        """Check if the LLM returned a mostly empty/useless result."""
        if not result:
            return True
        # Check if all major sections are empty
        gov = result.get("governance") or {}
        tf = result.get("terraform_rules") or {}
        naming = result.get("naming_standards") or {}
        sec = result.get("security") or {}
        comp = result.get("compliance") or {}
        sections = [gov, tf, naming, sec, comp]
        non_empty_count = sum(1 for s in sections if s and any(s.values() if isinstance(s, dict) else s))
        return non_empty_count == 0

    @staticmethod
    def _rule_based_template_extraction(template_content: str) -> Dict:
        """Extract template structure using regex rules — used as fallback when LLM fails.

        Looks for common enterprise template patterns:
        - Naming patterns like 'hdfc-{env}-{app}-...'
        - Tag requirements (Environment, CostCenter, etc.)
        - Compliance frameworks (PCI-DSS, SOC2, HIPAA, ISO27001)
        - Security keywords (encryption, KMS, multi-AZ)
        - Governance rules (regions, environment codes)
        """
        content_lower = template_content.lower()
        result = {
            "governance": {"rules": [], "approved_regions": []},
            "terraform_rules": {},
            "naming_standards": {},
            "security": {"rules": []},
            "compliance": {"frameworks": []},
        }

        # Extract naming pattern (look for patterns with curly braces or dashes)
        naming_patterns = re.findall(r'([a-z]+(?:-\{[a-z_]+\}){2,}(?:-[a-z0-9]+)*)', template_content)
        if naming_patterns:
            result["naming_standards"]["pattern"] = naming_patterns[0]
        # Look for explicit naming format declarations
        format_match = re.search(r'(?:naming format|format|pattern):\s*\n?\s*([a-z][a-z0-9\-{}_]+)', content_lower)
        if format_match and not result["naming_standards"].get("pattern"):
            result["naming_standards"]["pattern"] = format_match.group(1)

        # Extract example resource names (lines that look like 'hdfc-prod-...')
        examples = re.findall(r'(?:^|\s)([a-z]+-[a-z]+-[a-z]+-[a-z][a-z0-9\-]+)', template_content, re.MULTILINE)
        if examples:
            result["naming_standards"]["examples"] = list(dict.fromkeys(examples))[:8]

        # Detect separator and case
        if "lowercase" in content_lower or "lower case" in content_lower:
            result["naming_standards"]["case_rule"] = "lowercase only"
        if "hyphen" in content_lower or re.search(r'[a-z]-[a-z]', template_content):
            result["naming_standards"]["separator"] = "-"
        if "no underscore" in content_lower or "no spaces" in content_lower:
            result["naming_standards"]["prefix_suffix_rules"] = "no underscores, no spaces, lowercase only"

        # Extract compliance frameworks
        frameworks = []
        for fw in ["pci-dss", "pci dss", "soc2", "soc 2", "hipaa", "iso27001", "iso 27001", "gdpr", "fedramp", "nist", "cis"]:
            if fw in content_lower:
                normalized = fw.upper().replace(" ", "-").replace("ISO27001", "ISO 27001")
                if normalized not in frameworks:
                    frameworks.append(normalized)
        if frameworks:
            result["compliance"]["frameworks"] = frameworks

        # Extract approved regions
        regions = re.findall(r'\b(ap-south-\d|us-east-\d|us-west-\d|eu-west-\d|eu-central-\d|ap-southeast-\d|ap-northeast-\d|aps\d|use\d|euw\d)\b', template_content)
        if regions:
            result["governance"]["approved_regions"] = list(dict.fromkeys(regions))[:8]

        # Extract mandatory tags
        tag_section = re.search(r'(?:tagging|tag).*?(?:rules|requirements|policy)[:\s]*(.{0,800})', content_lower, re.DOTALL)
        if tag_section:
            tags = re.findall(r'(?:^|\n)\s*([A-Z][a-zA-Z]+)\s*=', template_content[tag_section.start():tag_section.start()+1000])
            if tags:
                tags_unique = list(dict.fromkeys(tags))[:10]
                result["governance"]["tagging_policy"] = f"Mandatory tags: {', '.join(tags_unique)}"

        # Extract governance rules from bullet points or numbered lists
        rules_lines = re.findall(r'(?:^|\n)\s*[\*\-•]\s*([A-Z][^\n]{20,200})', template_content)
        if rules_lines:
            governance_rules = []
            security_rules = []
            for line in rules_lines[:25]:
                line_clean = line.strip().rstrip(".,;")
                line_lower = line_clean.lower()
                if any(kw in line_lower for kw in ["encrypt", "kms", "tls", "ssl", "iam", "security", "private", "public", "mfa", "secret", "ssh"]):
                    security_rules.append(line_clean)
                else:
                    governance_rules.append(line_clean)
            if governance_rules:
                result["governance"]["rules"] = governance_rules[:15]
            if security_rules:
                result["security"]["rules"] = security_rules[:15]

        # Extract terraform-specific rules
        if "terraform" in content_lower:
            tf_section = re.search(r'terraform.*?rules?[:\s]*(.{0,1500})', content_lower, re.DOTALL)
            if tf_section:
                tf_text = template_content[tf_section.start():tf_section.start()+1500]
                tf_rules_lines = re.findall(r'(?:^|\n)\s*[\*\-•]\s*([a-zA-Z][^\n]{15,200})', tf_text)
                if tf_rules_lines:
                    result["terraform_rules"]["rules"] = "; ".join(r.strip() for r in tf_rules_lines[:10])
            if "module" in content_lower:
                result["terraform_rules"]["module_pattern"] = "Modular Terraform structure expected"
            if "variable" in content_lower:
                result["terraform_rules"]["variable_conventions"] = "Use variables for environment, application, region (no hardcoded values)"

        # Encryption defaults
        if "encryption" in content_lower or "encrypt" in content_lower:
            result["security"]["encryption_standard"] = "Encryption at rest required (KMS/CMK)"
        if "tls 1.3" in content_lower or "tls 1.2" in content_lower:
            result["security"]["network_rules"] = ["TLS encryption required for in-transit data"]
        if "secrets manager" in content_lower or "secret manager" in content_lower:
            result["security"]["secret_management"] = "AWS Secrets Manager"
        if "mfa" in content_lower:
            result["security"]["mfa_policy"] = "MFA required"

        logger.info(f"[HaikuService] Rule-based template extraction: pattern={result['naming_standards'].get('pattern')}, frameworks={result['compliance'].get('frameworks')}, rules={len(result['governance'].get('rules', []))}")
        return result

    @staticmethod
    def _default_template_result() -> Dict:
        return {
            "governance": {}, "terraform_rules": {}, "naming_standards": {},
            "security": {}, "compliance": {}
        }

    def compress_image_analysis(self, image_analysis: Dict) -> Dict:
        """
        Extract rich architecture intelligence from image analysis — service configs, data flow patterns,
        security boundaries, and deployment characteristics for high-quality design doc generation.
        """
        image_text = json.dumps(image_analysis, indent=2)[:8000]  # cap to avoid token overflow

        prompt = f"""You are a principal cloud architect analyzing an infrastructure diagram extraction.
Extract a RICH architecture intelligence profile — include specific service configurations, not just names.

IMAGE ANALYSIS:
{image_text}

Return structured JSON ONLY (no markdown):
{{
  "architecture": {{
    "compute": [{{"service": "EKS", "detail": "Kubernetes cluster with managed node groups", "tier": "application"}}],
    "database": [{{"service": "RDS PostgreSQL", "detail": "Multi-AZ with read replicas", "tier": "data"}}],
    "storage": [{{"service": "S3", "detail": "Versioned bucket for static assets", "tier": "data"}}],
    "networking": [{{"service": "VPC", "detail": "2 public + 2 private subnets across 2 AZs"}}],
    "load_balancing": [{{"service": "ALB", "detail": "Internet-facing with HTTPS listener"}}],
    "dns_cdn": [{{"service": "CloudFront", "detail": "CDN distribution with S3 origin"}}],
    "messaging": [{{"service": "SQS", "detail": "Standard queue with DLQ"}}],
    "security": [{{"service": "WAF", "detail": "Web ACL attached to ALB"}}],
    "monitoring": [{{"service": "CloudWatch", "detail": "Alarms and dashboards"}}]
  }},
  "data_flows": [
    {{"name": "User Request Flow", "path": ["CloudFront", "ALB", "EKS", "RDS"], "protocol": "HTTPS/TCP", "criticality": "HIGH"}},
    ...
  ],
  "topology": {{
    "pattern": "three-tier / microservices / serverless / event-driven",
    "public_surface": ["ALB on port 443", "CloudFront"],
    "private_services": ["EKS pods", "RDS", "ElastiCache"],
    "network_segmentation": "public/private subnet split with NAT Gateway",
    "cross_az": true,
    "cross_region": false
  }},
  "scaling": {{
    "auto_scaling_services": ["EKS HPA", "ASG for nodes"],
    "scaling_pattern": "horizontal pod autoscaling + cluster autoscaler",
    "stateless_compute": true
  }},
  "inferred_config": {{
    "estimated_environment": "production / staging / development",
    "high_availability": true,
    "disaster_recovery_pattern": "active-passive / active-active / backup-restore / none visible",
    "ci_cd_visible": false,
    "monitoring_visible": true
  }}
}}

Rules:
- Include ALL services detected, even minor ones (NAT Gateway, IGW, etc.)
- For "detail", describe the configuration visible in the diagram (e.g., "Multi-AZ", "private subnet only")
- If a field cannot be determined from the diagram, use null
- For data_flows, trace the complete request path from entry to final persistence"""
        try:
            response = __import__("app.core.llm_gateway", fromlist=["get_gateway"]).get_gateway().call(messages=[{"role": "user", "content": prompt}], task_type="template_compression", max_tokens=3000)
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                return json.loads(json_match.group())
            else:
                logger.warning("[HaikuService] Could not extract JSON from image analysis compression response")
                return self._default_image_result()
        except Exception as e:
            logger.error(f"[HaikuService] Image analysis compression failed: {e}")
            return self._default_image_result()

    @staticmethod
    def _default_image_result() -> Dict:
        return {"architecture": {}, "data_flows": [], "topology": {}, "scaling": {}, "inferred_config": {}}

    def compress_user_prompt(self, user_prompt: str) -> Dict:
        """
        Extract rich structured requirements from user prompt while preserving the raw intent.
        The raw_intent field ensures the downstream LLM understands the user's exact words and tone.
        """
        prompt = f"""You are a cloud solutions architect interpreting a client's infrastructure request.
Extract DETAILED requirements and preserve the user's original intent.

USER PROMPT:
{user_prompt}

Return structured JSON ONLY (no markdown, no explanations):
{{
  "raw_intent": "1-2 sentence summary of what the user is trying to achieve in their own words",
  "requirements": {{
    "business": ["specific business goals like 'e-commerce platform handling 10K concurrent users'", ...],
    "infrastructure": ["specific infra needs like 'Multi-AZ RDS PostgreSQL with read replicas'", ...],
    "compliance": ["specific compliance needs like 'SOC2 Type II certification required'", ...],
    "performance": ["specific perf targets like '< 200ms API response time at P99'", ...],
    "ha_dr": {{
      "availability_target": "99.99% / 99.95% / 99.9%",
      "rpo": "Recovery Point Objective if mentioned",
      "rto": "Recovery Time Objective if mentioned",
      "dr_strategy": "active-active / active-passive / pilot-light / backup-restore",
      "backup_frequency": "daily / hourly / continuous"
    }},
    "scale": {{
      "expected_users": "number or range if mentioned",
      "expected_rps": "requests per second if mentioned",
      "data_volume": "data size expectations if mentioned",
      "growth_rate": "expected growth if mentioned"
    }},
    "deployment": {{
      "preferred_services": ["any specific AWS/Azure/GCP services the user wants"],
      "excluded_services": ["any services the user explicitly doesn't want"],
      "environment_count": "number of environments (dev/staging/prod)",
      "ci_cd_preference": "any CI/CD tool preferences"
    }}
  }}
}}

Rules:
- raw_intent must capture the USER'S tone and priorities, not a generic summary
- If a field is not mentioned, use null
- Be specific: "PostgreSQL RDS" not just "database", "t3.large" not just "compute"
- Preserve exact numbers, sizes, and thresholds the user mentioned"""
        try:
            response = __import__("app.core.llm_gateway", fromlist=["get_gateway"]).get_gateway().call(messages=[{"role": "user", "content": prompt}], task_type="template_compression", max_tokens=2000)
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                result = json.loads(json_match.group())
                # Ensure raw_intent is preserved
                if not result.get("raw_intent") and user_prompt:
                    result["raw_intent"] = user_prompt[:500]
                return result
            else:
                logger.warning("[HaikuService] Could not extract JSON from user prompt compression response")
                return {"raw_intent": user_prompt[:500], "requirements": {
                    "business": [], "infrastructure": [], "compliance": [],
                    "performance": [], "ha_dr": {}, "scale": {}, "deployment": {}
                }}
        except Exception as e:
            logger.error(f"[HaikuService] User prompt compression failed: {e}")
            # Preserve raw intent even on failure — this is critical for downstream generation
            return {"raw_intent": user_prompt[:500], "requirements": {
                "business": [], "infrastructure": [], "compliance": [],
                "performance": [], "ha_dr": {}, "scale": {}, "deployment": {}
            }}

    @staticmethod
    def _default_prompt_result() -> Dict:
        return {"raw_intent": None, "requirements": {
            "business": [], "infrastructure": [], "compliance": [],
            "performance": [], "ha_dr": {}, "scale": {}, "deployment": {}
        }}

    def suggest_terraform_prompt(self, rough_prompt: str, cloud: str, resources: List[str]) -> List[str]:
        """
        Generate 3-5 refined Terraform prompts based on user's rough idea and context.
        
        Args:
            rough_prompt: User's rough prompt idea
            cloud: Cloud provider (aws, azure, gcp)
            resources: List of detected resources from diagram
            
        Returns:
            List of 3-5 refined prompt suggestions
        """
        # Auto-detect cloud from user's prompt if they mention a specific provider
        prompt_lower = rough_prompt.lower()
        if "gcp" in prompt_lower or "google cloud" in prompt_lower or "google" in prompt_lower:
            cloud = "gcp"
        elif "azure" in prompt_lower or "microsoft" in prompt_lower:
            cloud = "azure"
        elif "aws" in prompt_lower or "amazon" in prompt_lower:
            cloud = "aws"

        resources_str = ", ".join(resources) if resources else "None detected"
        cloud_label = {"aws": "AWS", "azure": "Azure", "gcp": "GCP"}.get(cloud, cloud.upper())
        
        prompt = f"""You are an expert Terraform engineer. The user has a rough idea for infrastructure they want to build. Generate 3-5 highly specific, production-ready Terraform prompts that they can use to generate code.

USER'S ROUGH IDEA:
"{rough_prompt}"

CONTEXT:
- Target Cloud Provider: {cloud_label}
- Detected Resources from Diagram: {resources_str}

RULES:
1. Each prompt must be SPECIFIC and DETAILED — include exact resource types, instance sizes, configurations
2. Each prompt must target the CORRECT cloud provider ({cloud_label}) — use the right Terraform resource names:
   - GCP: google_compute_instance, google_compute_network, google_container_cluster, etc.
   - AWS: aws_instance, aws_vpc, aws_eks_cluster, etc.
   - Azure: azurerm_virtual_machine, azurerm_virtual_network, azurerm_kubernetes_cluster, etc.
3. Include production best practices: encryption, networking, IAM, monitoring
4. Make each prompt progressively more comprehensive (simple → full production setup)
5. If the user mentions a specific service (VM, database, Kubernetes), focus on that
6. Include specific configuration values (machine types, disk sizes, regions, CIDR ranges)

Return ONLY a JSON array of 3-5 strings. No markdown fences, no explanations:
[
  "Create a {cloud_label} ... with specific details...",
  "Deploy a production-ready {cloud_label} ... with HA, encryption, monitoring...",
  "Build a complete {cloud_label} ... infrastructure with networking, IAM, compute, and observability..."
]"""
        
        try:
            response = __import__("app.core.llm_gateway", fromlist=["get_gateway"]).get_gateway().call(messages=[{"role": "user", "content": prompt}], task_type="template_compression", max_tokens=2000)
            json_match = re.search(r'\[[\s\S]*\]', response)
            if json_match:
                suggestions = json.loads(json_match.group())
                if isinstance(suggestions, list) and len(suggestions) >= 3:
                    return suggestions[:5]
            # Fallback: return manual suggestions if JSON parsing fails
            return self._fallback_suggestions(rough_prompt, cloud, resources)
        except Exception as e:
            logger.error(f"[HaikuService] Prompt suggestion failed: {e}", exc_info=True)
            return self._fallback_suggestions(rough_prompt, cloud, resources)

    def _fallback_suggestions(self, rough_prompt: str, cloud: str, resources: List[str]) -> List[str]:
        """Fallback suggestions if Haiku fails — still cloud-aware and specific."""
        # Auto-detect cloud from user's prompt
        prompt_lower = rough_prompt.lower()
        if "gcp" in prompt_lower or "google cloud" in prompt_lower or "google" in prompt_lower:
            cloud = "gcp"
        elif "azure" in prompt_lower or "microsoft" in prompt_lower:
            cloud = "azure"

        cloud_label = {"aws": "AWS", "azure": "Azure", "gcp": "GCP"}.get(cloud, cloud.upper())
        resources_str = f" integrating with {', '.join(resources[:5])}" if resources else ""

        # Generate cloud-specific fallback suggestions
        if cloud == "gcp":
            return [
                f"Create a GCP Compute Engine VM (e2-medium) in us-central1 with a custom VPC, firewall rules allowing SSH and HTTPS, and a persistent SSD boot disk. Include IAM service account with least-privilege roles.{resources_str}",
                f"Deploy a production-ready GCP infrastructure for: {rough_prompt}. Include VPC network with private subnet, Cloud NAT for egress, firewall rules, and Cloud Monitoring agent. Use google_compute_instance, google_compute_network, google_compute_firewall resources.{resources_str}",
                f"Build a complete GCP environment with: VPC network, subnet in us-central1, firewall rules (SSH, HTTP, HTTPS), Compute Engine instance with startup script, Cloud Storage bucket for backups, and IAM bindings. All resources tagged with environment=prod.{resources_str}",
            ]
        elif cloud == "azure":
            return [
                f"Create an Azure Virtual Machine (Standard_D2s_v3) in eastus with a custom VNet, NSG allowing SSH/HTTPS, managed disk, and system-assigned managed identity.{resources_str}",
                f"Deploy a production-ready Azure infrastructure for: {rough_prompt}. Include VNet with private subnet, NAT Gateway, NSG rules, and Azure Monitor diagnostics. Use azurerm_virtual_machine, azurerm_virtual_network, azurerm_network_security_group resources.{resources_str}",
                f"Build a complete Azure environment with: VNet, subnet, NSG, public IP, NIC, VM with cloud-init, Storage Account for diagnostics, and Key Vault for secrets. All resources in a dedicated resource group with tags.{resources_str}",
            ]
        else:
            return [
                f"Create an AWS EC2 instance (t3.medium) in a private subnet with encrypted EBS volume, security group allowing only ALB ingress, and IAM instance profile with SSM access.{resources_str}",
                f"Deploy a production-ready AWS infrastructure for: {rough_prompt}. Include VPC with public/private subnets, NAT Gateway, security groups, and CloudWatch monitoring. Use aws_instance, aws_vpc, aws_security_group resources.{resources_str}",
                f"Build a complete AWS environment with: VPC (10.0.0.0/16), 2 public + 2 private subnets across 2 AZs, IGW, NAT Gateway, ALB, EC2 Auto Scaling Group, RDS PostgreSQL Multi-AZ, and S3 bucket with encryption.{resources_str}",
            ]
