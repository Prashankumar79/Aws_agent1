"""
================================================================================
  backend/app/agents/nodes/terraform_prompt_agent.py  —  TERRAFORM PROMPT AGENT
================================================================================

PURPOSE:
  Extract or generate dynamic, context-aware Terraform prompts from the
  completed design document and master_context. Prompt count scales with
  architecture complexity. Each prompt includes priority, complexity,
  dependencies, and estimated resource count.

INPUT:
  state.design_doc      — the generated design document
  state.master_context   — compressed context (governance, security, naming, architecture)

OUTPUT:
  state.terraform_prompts — list of rich prompt objects
================================================================================"""
import json
import logging
import re
from typing import Any

from app.agents.state import PipelineState
from app.services.bedrock_service import BedrockService

logger = logging.getLogger(__name__)

TERRAFORM_PROMPT_EXTRACTION_PROMPT = """You are a senior Terraform engineer generating production-ready IaC prompts for enterprise deployment.

You MUST generate EXACTLY {prompt_count} highly detailed Terraform prompts by combining:
1. The ARCHITECTURE detected from the uploaded diagram/image (components, connections, data flows)
2. The ENTERPRISE TEMPLATE constraints (naming, governance, security, compliance rules)

{context_block}

DESIGN DOCUMENT (excerpt):
{design_doc_content}

Return a JSON array of EXACTLY {prompt_count} prompts with this structure:
[
  {{
    "category": "networking",
    "prompt": "Create a VPC named 'hdfc-prod-banking-vpc-ap-south-1-01' (following naming pattern) with CIDR 10.0.0.0/16. Deploy 3 public subnets (10.0.1.0/24, 10.0.2.0/24, 10.0.3.0/24) and 3 private subnets (10.0.10.0/24, 10.0.20.0/24, 10.0.30.0/24) across ap-south-1a, ap-south-1b, ap-south-1c for high availability. Include: Internet Gateway with route table for public subnets, 3 NAT Gateways (one per AZ) for private subnet egress, VPC Flow Logs enabled to CloudWatch with 90-day retention, DNS hostnames and resolution enabled, DHCP options set with custom domain. Apply tags: Environment=prod, Application=banking, CostCenter=IT-INFRA, DataClassification=confidential. Use aws_vpc, aws_subnet, aws_internet_gateway, aws_nat_gateway, aws_route_table, aws_route_table_association, aws_flow_log resources.",
    "priority": "P0",
    "complexity": "complex",
    "depends_on": [],
    "estimated_resources": 18
  }},
  ...
]

Categories: networking, iam, security, compute, storage, database, load_balancing, dns_cdn, messaging, monitoring, logging, cicd, backup, cost, compliance

Priority: P0 (must-have foundation), P1 (production-required), P2 (operational excellence)
Complexity: simple (1-3 resources), moderate (4-8 resources), complex (9+ resources or modules)
depends_on: list of categories this prompt needs completed first
estimated_resources: approximate number of Terraform resources

PRODUCTION-READY QUALITY RULES (MANDATORY):
1. Each prompt MUST be 150-300 words — extremely detailed and self-contained
2. Each prompt MUST reference EXACT Terraform resource types (e.g., aws_vpc, aws_subnet, aws_security_group)
3. Each prompt MUST include at least 5 specific configuration values (CIDR, instance type, engine version, port numbers, retention days, etc.)
4. Each prompt MUST state production requirements: encryption (KMS/CMK), multi-AZ, backup retention, monitoring, logging
5. Each prompt MUST use the EXACT naming convention from the template context above
6. Each prompt MUST include tagging strategy with Environment, Application, CostCenter, Owner tags
7. Each prompt MUST specify security hardening: encryption at rest + in transit, least-privilege IAM, network isolation
8. Each prompt MUST reference the specific services detected in the uploaded diagram — NOT generic placeholders
9. If governance rules exist, each prompt MUST comply with them (approved regions, budget constraints, etc.)
10. If compliance frameworks exist (PCI-DSS, SOC2, HIPAA), reference specific controls in relevant prompts

COVERAGE REQUIREMENTS (ensure ALL are covered across {prompt_count} prompts):
- Foundation: VPC/networking, IAM roles/policies, KMS keys (P0)
- Data: Databases, caches, storage buckets with lifecycle policies (P1)
- Compute: Servers/containers/functions with auto-scaling (P1)
- Application: Load balancers, API gateways, CDN (P1)
- Security: WAF, Security Groups, NACLs, GuardDuty, Config rules (P1)
- Operational: CloudWatch dashboards, alarms, SNS notifications (P1)
- Governance: Backup plans, cost budgets, compliance checks, audit trails (P2)
- DR/HA: Cross-region replication, failover, health checks (P2)

Return ONLY the JSON array. No markdown, no preamble, no summary. EXACTLY {prompt_count} prompts."""


def _compute_prompt_count(components: list) -> int:
    """Always generate exactly 15 production-ready prompts."""
    return 15


def _build_context_block(master: dict) -> str:
    """Build a structured context block from master_context for the terraform prompt LLM.
    Combines template constraints + image/diagram analysis for production-ready prompts."""
    lines = []

    # User's raw intent — the most important context signal
    raw_intent = master.get("raw_intent")
    user_prompt_raw = master.get("user_prompt_raw", "")
    if raw_intent:
        lines.append(f"CLIENT'S GOAL: {raw_intent}")
        lines.append("")
    if user_prompt_raw:
        lines.append(f"CLIENT'S EXACT REQUEST: \"{user_prompt_raw[:500]}\"")
        lines.append("")

    # Naming standards — critical for prompt quality
    naming = master.get("naming_standards", {})
    if naming and any(v for v in naming.values() if v):
        lines.append("NAMING CONVENTION (MANDATORY — use in ALL resource names):")
        if naming.get("pattern"):
            lines.append(f"  Pattern: {naming['pattern']}")
        if naming.get("examples"):
            examples = naming["examples"]
            lines.append(f"  Examples: {', '.join(examples[:5]) if isinstance(examples, list) else examples}")
        if naming.get("separator"):
            lines.append(f"  Separator: {naming['separator']}")
        for key in ["case_rule", "prefix_suffix_rules", "max_length"]:
            if naming.get(key):
                lines.append(f"  {key}: {naming[key]}")
        lines.append("")

    # Terraform rules from template
    tf_rules = master.get("terraform_rules", {})
    if tf_rules and any(v for v in tf_rules.values() if v):
        lines.append("TERRAFORM/IaC RULES (from enterprise template):")
        for key, value in tf_rules.items():
            if value:
                lines.append(f"  • {key}: {value}")
        lines.append("")

    # Governance from template
    governance = master.get("governance", {})
    if governance:
        rules = governance.get("rules", [])
        if isinstance(rules, list) and rules:
            lines.append("GOVERNANCE RULES (from enterprise template):")
            for rule in rules[:15]:
                lines.append(f"  • {rule}")
        else:
            non_empty = {k: v for k, v in governance.items() if v and k != "rules"}
            if non_empty:
                lines.append("GOVERNANCE:")
                for key, value in non_empty.items():
                    lines.append(f"  • {key}: {value}")
        for key in ["environment_strategy", "tagging_policy", "approved_regions", "budget_constraints"]:
            val = governance.get(key)
            if val:
                label = key.replace("_", " ").title()
                lines.append(f"  {label}: {val if isinstance(val, str) else ', '.join(val)}")
        lines.append("")

    # Security from template
    security = master.get("security", {})
    if security:
        sec_rules = security.get("rules", [])
        if isinstance(sec_rules, list) and sec_rules:
            lines.append("SECURITY CONSTRAINTS (from enterprise template):")
            for rule in sec_rules[:15]:
                lines.append(f"  • {rule}")
        else:
            non_empty = {k: v for k, v in security.items() if v and k != "rules"}
            if non_empty:
                lines.append("SECURITY:")
                for key, value in non_empty.items():
                    lines.append(f"  • {key}: {value}")
        for key in ["encryption_standard", "iam_policy", "secret_management", "mfa_policy"]:
            val = security.get(key)
            if val:
                lines.append(f"  {key.replace('_', ' ').title()}: {val}")
        net_rules = security.get("network_rules", [])
        if isinstance(net_rules, list) and net_rules:
            lines.append("  Network Rules:")
            for nr in net_rules:
                lines.append(f"    - {nr}")
        lines.append("")

    # Compliance
    compliance = master.get("compliance", {})
    if compliance:
        frameworks = compliance.get("frameworks", []) if isinstance(compliance, dict) else compliance
        controls = compliance.get("specific_controls", []) if isinstance(compliance, dict) else []
        if frameworks:
            lines.append(f"COMPLIANCE FRAMEWORKS: {', '.join(frameworks) if isinstance(frameworks, list) else frameworks}")
        if controls:
            lines.append(f"SPECIFIC CONTROLS: {'; '.join(controls[:10])}")
        lines.append("")

    # User requirements (from compressed prompt)
    requirements = master.get("requirements", {})
    if requirements:
        lines.append("USER REQUIREMENTS:")
        for category, items in requirements.items():
            if isinstance(items, list) and items:
                lines.append(f"  {category}: {'; '.join(str(i) for i in items)}")
            elif isinstance(items, dict) and any(v for v in items.values() if v):
                for k, v in items.items():
                    if v:
                        lines.append(f"  {category}.{k}: {v}")
            elif items and not isinstance(items, (dict, list)):
                lines.append(f"  {category}: {items}")
        lines.append("")

    # Architecture intelligence from image/diagram analysis
    architecture = master.get("architecture", {})
    if architecture:
        lines.append("DETECTED ARCHITECTURE (from uploaded diagram/image):")
        for category, services in architecture.items():
            if not services:
                continue
            if isinstance(services, list):
                svc_names = []
                for svc in services:
                    if isinstance(svc, dict):
                        svc_names.append(f"{svc.get('service', '?')} ({svc.get('detail', '')})")
                    else:
                        svc_names.append(str(svc))
                lines.append(f"  [{category}]: {'; '.join(svc_names)}")
            elif isinstance(services, str):
                lines.append(f"  [{category}]: {services}")
        lines.append("")

    # Critical fields (components and connections from image)
    critical = master.get("critical_fields", {})
    if critical:
        comps = critical.get("components", [])
        conns = critical.get("connections", [])
        cloud = critical.get("cloud_provider", "aws")
        if comps:
            lines.append(f"DETECTED COMPONENTS ({len(comps)} from diagram, cloud={cloud}):")
            for comp in comps[:25]:
                name = comp.get("name", "?")
                svc_type = comp.get("type", comp.get("service_type", "?"))
                lines.append(f"  • {name} ({svc_type})")
            lines.append("")
        if conns:
            lines.append(f"DETECTED CONNECTIONS ({len(conns)} from diagram):")
            for conn in conns[:20]:
                src = conn.get("source", "?")
                tgt = conn.get("target", "?")
                conn_type = conn.get("type", conn.get("connection_type", ""))
                lines.append(f"  • {src} → {tgt} [{conn_type}]")
            lines.append("")

    if lines:
        lines.insert(0, "=== ENTERPRISE CONTEXT (from uploaded diagram + attached template) ===")
        lines.append("⚠️ CRITICAL: Every prompt MUST respect the naming convention, governance rules, security constraints, and reference the exact services detected in the diagram above.")
        lines.append("⚠️ CRITICAL: Generate EXACTLY the requested number of prompts. Each must be 150-300 words, production-ready, and self-contained.")

    return "\n".join(lines)


def generate_terraform_prompts(state: PipelineState) -> PipelineState:
    """LangGraph node: generate rich, context-aware Terraform prompts from design doc + master_context."""
    job_id = state["job_id"]
    design_doc = state.get("design_doc", {})
    master = state.get("master_context", {})
    fused = state.get("fused_context", {})

    logger.info(f"🚀 [AGENT:TerraformPrompts] STARTED  | job_id={job_id} | has_doc={bool(design_doc)} | content_len={len(design_doc.get('content', ''))} | has_master_context={bool(master)}")

    # Use existing prompts from design doc if they're already rich enough
    existing_prompts = design_doc.get("terraform_prompts", [])
    if existing_prompts and len(existing_prompts) >= 15:
        # Verify prompts are detailed enough (at least 100 chars each)
        detailed_count = sum(1 for p in existing_prompts if len(p.get("prompt", "")) >= 100)
        if detailed_count >= 12:
            # Ensure existing prompts have the new fields
            enriched = []
            for p in existing_prompts:
                enriched.append({
                    "category": p.get("category", "general"),
                    "prompt": p.get("prompt", ""),
                    "priority": p.get("priority", "P1"),
                    "complexity": p.get("complexity", "moderate"),
                    "depends_on": p.get("depends_on", []),
                    "estimated_resources": p.get("estimated_resources", 1),
                })
            logger.info(f"✅ [AGENT:TerraformPrompts] COMPLETED | job_id={job_id} | mode=from_design_doc | count={len(enriched)}")
            return {**state, "terraform_prompts": enriched, "pipeline_stage": "TERRAFORM_PROMPTS_GENERATED"}

    # Generate via LLM using master_context + design doc
    content = design_doc.get("content", "")
    if not content:
        logger.warning(f"[TerraformPromptAgent:{job_id}] No design doc content, using fallback")
        return {**state, "terraform_prompts": _fallback_prompts(fused, master), "pipeline_stage": "TERRAFORM_PROMPTS_GENERATED"}

    try:
        bedrock = BedrockService()

        # Compute dynamic prompt count from component complexity
        critical = master.get("critical_fields", {})
        components = critical.get("components", fused.get("components", []))
        prompt_count = _compute_prompt_count(components)

        # Build rich context block from master_context
        context_block = _build_context_block(master)

        full_prompt = TERRAFORM_PROMPT_EXTRACTION_PROMPT.format(
            prompt_count=prompt_count,
            context_block=context_block,
            design_doc_content=content[:25000],
        )

        messages = [{"role": "user", "content": full_prompt}]
        response = bedrock.invoke(messages, max_tokens=8000)

        prompts = _extract_prompts_from_response(response)

        if not prompts:
            prompts = _fallback_prompts(fused, master)

        logger.info(f"✅ [AGENT:TerraformPrompts] COMPLETED | job_id={job_id} | mode=llm_generated | count={len(prompts)}")
        return {**state, "terraform_prompts": prompts, "pipeline_stage": "TERRAFORM_PROMPTS_GENERATED"}

    except Exception as e:
        logger.error(f"[TerraformPromptAgent:{job_id}] Error: {e}", exc_info=True)
        fallback = _fallback_prompts(fused, master)
        logger.info(f"⚠️  [AGENT:TerraformPrompts] COMPLETED (fallback) | job_id={job_id} | count={len(fallback)} | error={e}")
        return {**state, "terraform_prompts": fallback, "pipeline_stage": "TERRAFORM_PROMPTS_GENERATED", "error": f"Terraform prompt generation warning: {e}"}


def _extract_prompts_from_response(response: str) -> list[dict]:
    """Parse JSON array of rich prompts from LLM response."""
    try:
        json_match = re.search(r'\[\s*\{[\s\S]*\}\s*\]', response)
        if json_match:
            prompts = json.loads(json_match.group())
            if isinstance(prompts, list) and len(prompts) > 0:
                valid = []
                for p in prompts:
                    if isinstance(p, dict) and "prompt" in p:
                        valid.append({
                            "category": p.get("category", "general"),
                            "prompt": p["prompt"],
                            "priority": p.get("priority", "P1"),
                            "complexity": p.get("complexity", "moderate"),
                            "depends_on": p.get("depends_on", []),
                            "estimated_resources": p.get("estimated_resources", 1),
                        })
                return valid
        return []
    except Exception:
        return []


def _fallback_prompts(fused: dict, master: dict = None) -> list[dict]:
    """Generate context-aware fallback prompts with rich schema when LLM generation fails."""
    master = master or {}
    components = fused.get("components", master.get("critical_fields", {}).get("components", []))
    cloud = fused.get("cloud_provider", master.get("critical_fields", {}).get("cloud_provider", "aws"))

    # Get naming pattern for use in prompts
    naming = master.get("naming_standards", {})
    name_hint = ""
    if naming and naming.get("pattern"):
        name_hint = f" Use naming pattern '{naming['pattern']}'."

    prompts = []

    # Foundation: Networking (P0)
    net_prompts = {
        "gcp": f"Create a VPC network with 2 public and 2 private subnets across us-central1-a and us-central1-b. Include Cloud Router, Cloud NAT for private subnet egress, and firewall rules blocking all ingress except port 443.{name_hint}",
        "azure": f"Create a Virtual Network (10.0.0.0/16) with 2 public subnets and 2 private subnets across Availability Zones 1 and 2. Include Azure NAT Gateway, NSGs, and route tables with UDRs.{name_hint}",
        "aws": f"Create a VPC (10.0.0.0/16) with 2 public subnets (10.0.1.0/24, 10.0.2.0/24) and 2 private subnets (10.0.10.0/24, 10.0.20.0/24) across us-east-1a/1b. Include IGW, 2 NAT Gateways (one per AZ), route tables, and VPC flow logs to CloudWatch.{name_hint}",
    }
    prompts.append({"category": "networking", "prompt": net_prompts.get(cloud, net_prompts["aws"]), "priority": "P0", "complexity": "moderate", "depends_on": [], "estimated_resources": 12})

    # Foundation: IAM (P0)
    iam_prompts = {
        "gcp": f"Create GCP IAM service accounts with least-privilege custom roles for compute, database, and storage access. Include workload identity bindings.{name_hint}",
        "azure": f"Create Azure managed identities and custom RBAC roles for compute, database, and storage. Implement permission boundaries using Azure Policy.{name_hint}",
        "aws": f"Create IAM roles with least-privilege policies for EC2/ECS task execution, RDS access, and S3 operations. Include permission boundaries and service-linked roles.{name_hint}",
    }
    prompts.append({"category": "iam", "prompt": iam_prompts.get(cloud, iam_prompts["aws"]), "priority": "P0", "complexity": "moderate", "depends_on": [], "estimated_resources": 8})

    # Service-specific prompts from detected components
    service_map = {
        "aws": {
            "ec2": ("compute", "Create an EC2 instance (t3.medium) in a private subnet with encrypted EBS volumes (gp3, AES-256), IMDSv2 required, and a security group allowing only ALB ingress on port 8080.", "P1", "simple", ["networking", "iam"], 4),
            "s3": ("storage", "Create an S3 bucket with versioning enabled, SSE-KMS encryption, public access blocked (all 4 settings), lifecycle rules (IA after 30d, Glacier after 90d), and access logging to a separate log bucket.", "P1", "moderate", ["iam"], 5),
            "rds": ("database", "Create an RDS PostgreSQL 15 instance (db.r6g.large) in private subnets with Multi-AZ, automated backups (35-day retention), encryption at rest (KMS), performance insights enabled, and a db subnet group.", "P1", "moderate", ["networking", "iam"], 6),
            "lambda": ("compute", "Create a Lambda function (Python 3.12, 512MB memory, 30s timeout) with a dedicated IAM role, VPC access in private subnets, environment variables from SSM, and a CloudWatch log group with 14-day retention.", "P1", "moderate", ["networking", "iam"], 5),
            "dynamodb": ("database", "Create a DynamoDB table with on-demand billing, point-in-time recovery, SSE with KMS, and a global secondary index. Enable DynamoDB Streams for change data capture.", "P1", "simple", ["iam"], 3),
            "alb": ("load_balancing", "Create an ALB in public subnets with HTTPS listener (ACM certificate), target group with health checks (/health, 30s interval), sticky sessions, and access logging to S3.", "P1", "moderate", ["networking"], 7),
            "cloudfront": ("dns_cdn", "Create a CloudFront distribution with S3 origin (OAC), custom domain with ACM certificate, WAF web ACL, and cache policy for static assets (max-age 86400).", "P1", "moderate", ["storage"], 5),
            "ecs": ("compute", "Create an ECS Fargate cluster with a task definition (256 CPU, 512 MiB), service with desired count 2, auto-scaling (target tracking on CPU 70%), and ALB integration.", "P1", "complex", ["networking", "iam", "load_balancing"], 10),
            "eks": ("compute", "Create an EKS cluster (v1.29) with managed node groups (t3.large, min 2, max 6), OIDC provider, EBS CSI driver addon, CoreDNS, and kube-proxy. Enable envelope encryption with KMS.", "P1", "complex", ["networking", "iam"], 12),
            "sqs": ("messaging", "Create an SQS standard queue with DLQ (maxReceiveCount: 3), encryption (SSE-KMS), visibility timeout 300s, and message retention 14 days.", "P1", "simple", ["iam"], 3),
        },
        "gcp": {
            "gce": ("compute", "Create a Compute Engine instance (e2-medium) with encrypted persistent disk, service account with least-privilege, and firewall rules.", "P1", "simple", ["networking", "iam"], 4),
            "gcs": ("storage", "Create a Cloud Storage bucket with versioning, uniform bucket-level access, CMEK encryption, and lifecycle rules.", "P1", "simple", ["iam"], 3),
            "cloud sql": ("database", "Create a Cloud SQL PostgreSQL 15 instance with private IP, automated backups, HA configuration, and SSL enforcement.", "P1", "moderate", ["networking", "iam"], 5),
            "cloud run": ("compute", "Create a Cloud Run service with VPC connector, min/max instances, IAM invoker binding, and custom domain.", "P1", "moderate", ["networking", "iam"], 5),
            "pub/sub": ("messaging", "Create a Pub/Sub topic with subscription, dead-letter policy, message retention 7d, and CMEK encryption.", "P1", "simple", ["iam"], 3),
        },
        "azure": {
            "vm": ("compute", "Create an Azure VM (Standard_D2s_v3) with managed disk encryption, NSG, and managed identity.", "P1", "simple", ["networking", "iam"], 4),
            "storage": ("storage", "Create an Azure Storage account with blob containers, soft delete (14d), CMEK encryption, and private endpoint.", "P1", "moderate", ["networking", "iam"], 5),
            "sql": ("database", "Create an Azure SQL Database (S2 tier) with private endpoint, TDE, automated backups, and AAD authentication.", "P1", "moderate", ["networking", "iam"], 5),
            "function": ("compute", "Create an Azure Function App (Python 3.11) with managed identity, VNet integration, and Application Insights.", "P1", "moderate", ["networking", "iam"], 5),
            "service bus": ("messaging", "Create an Azure Service Bus namespace with queue, DLQ, and managed identity access.", "P1", "simple", ["iam"], 3),
        },
    }

    svc_map = service_map.get(cloud, service_map["aws"])
    used_categories = {"networking", "iam"}
    for comp in components:
        comp_type = comp.get("type", "").lower()
        comp_name = comp.get("name", "").lower()
        for key, (category, prompt_text, priority, complexity, deps, est) in svc_map.items():
            if key in comp_type or key in comp_name:
                if category not in used_categories or len(prompts) < 15:
                    prompts.append({"category": category, "prompt": prompt_text + name_hint, "priority": priority, "complexity": complexity, "depends_on": deps, "estimated_resources": est})
                    used_categories.add(category)
                break

    # Always include security, monitoring, logging, backup (P1/P2)
    defaults = {
        "aws": [
            ("security", "Create KMS keys with automatic rotation for data encryption. Create WAF web ACL with rate limiting and managed rule groups (AWSManagedRulesCommonRuleSet).", "P1", "moderate", ["iam"], 4),
            ("monitoring", "Create CloudWatch dashboards with widgets for CPU, memory, network, and error rates. Create alarms for P1 metrics (5xx rate > 1%, CPU > 80%, disk > 85%).", "P1", "moderate", [], 8),
            ("logging", "Enable VPC flow logs (ALL traffic), S3 access logging, CloudTrail (all regions, multi-account), and CloudWatch log groups with 90-day retention.", "P1", "moderate", ["networking", "storage"], 6),
            ("backup", "Create AWS Backup plan with daily backups (35-day retention), cross-region copy to DR region, and backup vault with KMS encryption.", "P2", "moderate", ["database", "storage"], 4),
            ("compliance", "Enable AWS Config with conformance pack, CloudTrail with S3 log archive, and AWS Security Hub with CIS benchmark.", "P2", "moderate", ["iam", "logging"], 5),
        ],
        "gcp": [
            ("security", "Create Cloud KMS key rings with automatic rotation. Configure Cloud Armor security policies with rate limiting.", "P1", "moderate", ["iam"], 4),
            ("monitoring", "Create Cloud Monitoring dashboards, alert policies, and uptime checks for all services.", "P1", "moderate", [], 6),
            ("logging", "Enable Cloud Audit Logs, VPC Flow Logs, and create Cloud Logging sinks with 90-day retention.", "P1", "moderate", ["networking"], 5),
            ("backup", "Configure automated backups for Cloud SQL and Filestore with cross-region replication.", "P2", "simple", ["database"], 3),
        ],
        "azure": [
            ("security", "Create Azure Key Vault with RBAC, soft delete, and purge protection. Configure Azure WAF policy.", "P1", "moderate", ["iam"], 4),
            ("monitoring", "Create Azure Monitor dashboards, alert rules, and action groups for critical metrics.", "P1", "moderate", [], 6),
            ("logging", "Create Log Analytics workspace, enable NSG flow logs, and configure diagnostic settings for all resources.", "P1", "moderate", ["networking"], 5),
            ("backup", "Create Azure Backup vault with policies for VMs, SQL databases, and blob storage.", "P2", "moderate", ["database", "storage"], 4),
        ],
    }
    for cat, prompt_text, priority, complexity, deps, est in defaults.get(cloud, defaults["aws"]):
        if cat not in used_categories:
            prompts.append({"category": cat, "prompt": prompt_text + name_hint, "priority": priority, "complexity": complexity, "depends_on": deps, "estimated_resources": est})
            used_categories.add(cat)

    return prompts
