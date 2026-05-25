"""
================================================================================
  backend/app/services/design_doc_service.py  —  AI DESIGN DOC GENERATOR
================================================================================

PURPOSE:
  Stage 2 of the main pipeline. Takes the structured vision analysis output
  and generates a comprehensive, multi-section architecture design document
  using AWS Bedrock Claude, streamed in real time to the frontend.

ARCHITECTURE DECISION: 4 Chained Focused Prompts instead of 1 giant prompt
  Why? Claude has a finite context window. One 15-section document prompt
  would exceed token limits AND produce worse results (the model loses focus
  on each section). Instead, we fire 4 smaller, tightly-scoped calls:

    Call 1 — SNAPSHOT  (sections 1–3): Executive summary, system overview, service inventory
    Call 2 — FLOWS     (sections 4–5): Data flows, security assessment
    Call 3 — AUDIT     (sections 6–11): HA, performance, cost, recommendations
    Call 4 — GUIDANCE  (sections 12–15): Terraform hints, ADRs, deployment guide

  Each call gets ~300–400 tokens of input context (only what it needs).
  Outputs are stitched together into one Markdown document.

CONNECTIONS TO OTHER FILES:
  • core/config.py   → AWS_BEDROCK_MODEL, AWS credentials
  • api/v1/jobs.py   → calls generate_design_document_streamed() for SSE
  • vision_service.py → its output dict is the input to this service

KEY METHODS:
  generate_design_document()          → sync, returns full doc dict (used in fallback)
  generate_design_document_streamed() → generator, yields SSE strings for real-time UI
  _call()                             → single sync Bedrock call with retry
  _call_streaming()                   → single streaming Bedrock call

SSE EVENT PROTOCOL (consumed by DesignDocPage.tsx):
  {"type": "section_start", "section": "snapshot", "title": "Architecture Snapshot"}
  {"type": "delta", "text": "<text chunk>"}   ← many of these per section
  {"type": "section_end", "section": "snapshot"}
  ... repeat for flows, audit, guidance ...
  [DONE]   ← final sentinel that tells the frontend to stop streaming
================================================================================
"""

import json
import time
import logging
import boto3
from concurrent.futures import ThreadPoolExecutor, as_completed
from app.core.config import settings

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# SHARED SYSTEM PROMPT — 8 lines, applied to every call
# ─────────────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a principal cloud architect at a Fortune-500 consultancy writing an architecture design document that will be reviewed by engineering VPs, CISOs, compliance auditors, and DevOps teams who will implement it.

═══ DYNAMIC CONTEXT INTEGRATION (MANDATORY) ═══
Every prompt includes a "=== MANDATORY REQUIREMENTS ===" block. You MUST:
1. If naming convention exists → use that EXACT pattern in every resource name, ARN, and Terraform example.
   Example: if pattern is "{env}-{app}-{svc}-{resource}", write "prod-myapp-api-sg" not "my-security-group".
2. If compliance frameworks are listed → cross-reference specific controls (e.g., "SOC2 CC6.1") in security sections.
3. If governance rules exist → design around them. If "no public IPs on compute" is a rule, state it and show the private architecture.
4. If the user's raw intent is provided → ensure every section directly addresses their stated goals and priorities.
5. If architecture intelligence includes data flows → trace them through your analysis with protocol and encryption at each hop.

═══ QUALITY BAR ═══
DEPTH: Write as if you are being paid $500/hour and the client will reject generic advice.
- Name EXACT services with version/tier: "RDS PostgreSQL 15.4 db.r6g.xlarge Multi-AZ" not "a database".
- Name EXACT instance sizes: "t3.medium" not "an appropriately sized instance".
- Name EXACT config values: "gp3 with 3000 IOPS and 125 MiB/s throughput" not "provisioned storage".
- Name EXACT ARN patterns: "arn:aws:s3:::prod-myapp-data-*" not "the S3 bucket".
- Give specific CIDR ranges: "10.0.0.0/16 with /24 subnets" not "a VPC with subnets".

HONESTY: Be brutally honest about gaps — this document protects the client from production outages.
- Every > [!WARNING] must state the blast radius ("affects all 3 AZs", "30-minute RTO breach").
- Every recommendation must include effort estimate (hours, not "low/medium/high").

REASONING: For every architectural decision, briefly state WHY (1 sentence) — not just WHAT.
- "Using gp3 instead of gp2 because it provides 3x baseline IOPS at 20% lower cost."
- "Placing RDS in private subnets because CIS 4.1 requires no direct internet access to databases."

═══ FORMAT STANDARDS ═══
- Markdown: ## sections, ### subsections, properly formatted tables with | header | separator rows.
- Status indicators: ✅ (implemented), ⚠️ (needs attention), ❌ (critical gap / missing).
- Callout blocks: > [!WARNING] for security/production blockers, > [!IMPORTANT] for urgent decisions.
- Tables MUST have header row + separator row (|---|---|) + data rows. No malformed tables.
- Code blocks: use ```hcl for Terraform, ```bash for commands. Every code block must be complete and runnable.
- Return ONLY the Markdown content for your assigned sections. No preamble, no "Here is..." intros, no closing remarks."""


# ─────────────────────────────────────────────────────────────────────────────
# CALL 1 — SNAPSHOT
# What the system is, who uses it, service inventory
# Input: component list + connection list  (~300 tokens)
# ─────────────────────────────────────────────────────────────────────────────

SNAPSHOT_PROMPT = """Write sections 1–3 of an architecture design document.

Cloud: {cloud}
Components ({component_count}):
{components_text}

Connections ({connection_count}):
{connections_text}

Write exactly these sections with DEEP specificity:

## 1. Executive Summary
5–6 sentences for a non-technical CEO. MUST include:
- What the system does (one sentence, no jargon)
- Who it serves and at what scale (specific numbers: users, RPS, data volume — infer from architecture complexity)
- Current production-readiness score (1–5) with justification
- Top risk and its business impact (e.g., "single-AZ database risks 4-hour outage")
- One critical action item with estimated effort
If you use an acronym, explain it in parentheses.

## 2. What This System Does

### 2.1 The Big Picture
2–3 paragraphs using a real-world analogy (e.g., "Think of it as a post office..."). End with the KEY architectural insight — what makes this design interesting, risky, or innovative. Prose only, no bullets.

### 2.2 Key Actors & Stakeholders
| Actor | Role | Primary Actions | Frequency | SLA Expectation |
|-------|------|-----------------|-----------|-----------------|
Fill with SPECIFIC actors inferred from the architecture (e.g., "End User via Mobile App", "CI/CD Pipeline", "Operations On-Call Engineer"). Include at least 4 actors. SLA must have specific numbers (e.g., "< 200ms P99 response", "99.95% uptime").

### 2.3 Business Value & Problem Statement
Three concise paragraphs:
1. **Before state**: What existed before — manual pain points, scaling limits, cost inefficiencies. Be specific.
2. **What this enables**: What this architecture automates or unlocks. Reference specific components.
3. **Quantified value**: Cost savings (monthly $), speed improvement (% or ms), reliability gain (9s of uptime). Estimate based on architecture complexity.

## 3. Architecture Overview

### 3.1 Architecture Pattern
Name the canonical pattern (e.g., "Event-Driven Microservices", "Three-Tier Web Application", "Serverless Data Pipeline").
Explain in 3–4 sentences: (1) why this pattern fits, (2) what trade-offs it introduces, (3) when you'd outgrow it.

### 3.2 Deployment Topology
| Dimension | Detail | Rationale |
|-----------|--------|-----------|
| Cloud Provider | ... | ... |
| Primary Region | ... | latency / compliance reason |
| Account Structure | single / multi-account | ... |
| Availability Zones | number and strategy | ... |
| Network Topology | VPC layout, CIDR scheme | ... |
| Environment Separation | dev/staging/prod strategy | ... |
| DR Region | if applicable | RPO/RTO justification |

### 3.3 Service Inventory
| # | Service Name | {cloud} Service | Tier/Size | Layer | Purpose | Criticality | Monthly Est. |
|---|-------------|-----------------|-----------|-------|---------|-------------|--------------|
Layer categories: Edge / Compute / Data / Messaging / Security / Observability / Management / Networking
Criticality: CRITICAL / HIGH / MEDIUM / LOW
Tier/Size: Exact SKU (e.g., "db.r6g.xlarge", "t3.medium", "m6i.large") — infer reasonable defaults if not specified.
Monthly Est.: Rough cost estimate per service (e.g., "$150/mo", "$45/mo")"""


# ─────────────────────────────────────────────────────────────────────────────
# CALL 2 — DATA FLOW + SECURITY
# How data moves, where it's exposed, what's protected
# Input: connections + component names  (~400 tokens)
# ─────────────────────────────────────────────────────────────────────────────

FLOW_PROMPT = """Write sections 4–6 of an architecture design document.

Cloud: {cloud}
Components: {component_names}
Connections: {connections_text}
Cross-account flows: {cross_account}

Write exactly these sections with DEEP specificity:

## 4. Data Flow Analysis

### 4.1 Overview
3–4 sentences: topology shape (hub-spoke, mesh, linear), where data enters the system, where it rests at the end, and the dominant data pattern (request-response, event-driven, batch).

### 4.2 Flows
For each distinct flow (identify at least 3):
#### Flow N: [Descriptive Name]
- **Trigger:** What starts it (user action, cron, event, API call)
- **Criticality:** CRITICAL / HIGH / MEDIUM / LOW — with business impact if flow fails
- **Data classification:** PII / PHI / Financial / Internal / Public
- **Latency budget:** Expected end-to-end latency (e.g., "< 500ms P95")

| Step | From | To | Action | Protocol | Port | Encrypted | Auth Method |
|------|------|----|--------|----------|------|-----------|-------------|
(Trace EVERY hop including load balancers, NAT gateways, proxies)

- **Plain story:** 3–5 sentences narrating the complete journey of a request through this flow
- **Data at rest:** Final persistence location + encryption method + retention period
- **Failure mode:** What breaks, blast radius, and recovery mechanism
- **Bottleneck risk:** Which hop is the likely throughput bottleneck and why

### 4.3 Cross-Account / Cross-Region
Mechanism (VPC peering, PrivateLink, Transit Gateway), trust relationship (IAM roles, resource policies), security controls. Skip if none detected.

## 5. Security Assessment

### 5.1 Posture Summary
> [!IMPORTANT]
> One clear sentence rating the overall security posture (Strong / Adequate / Weak / Critical Gaps).
> Followed by: (1) what's implemented well, (2) what's critically missing, (3) estimated effort to reach production-ready security.

### 5.2 Security Controls Matrix
| Control | Type | Protects | Status | Implementation Detail | Gap / Remediation |
|---------|------|----------|--------|-----------------------|-------------------|
Type: Preventive / Detective / Corrective / Recovery
At least 10 rows covering: encryption, IAM, network, logging, backup, secrets, vulnerability scanning.
Status must be ✅/⚠️/❌. Implementation Detail must name the specific {cloud} service.

### 5.3 Identity & Access Management
- Least-privilege assessment: List specific roles, whether they follow least-privilege, and what to restrict
- Cross-account trust: Trust policies, external ID usage, condition keys
- Permission boundaries: Are they used? Should they be?
- Service-linked roles vs custom roles: Which services use which
- MFA enforcement: Console users, CLI users, programmatic access
- Secrets rotation: How are access keys, DB passwords, API tokens managed?

### 5.4 Network Security
- **Public attack surface**: List ALL internet-facing endpoints with port, protocol, and protection (WAF, Shield, rate limiting)
- **Security group audit**: Any rule allowing 0.0.0.0/0? On which ports? Remediation steps.
- **Network segmentation**: Public/private/isolated subnet strategy. Are databases truly isolated?
- **VPC endpoints**: Which {cloud} services use VPC endpoints vs NAT Gateway? Cost and security implications.
- **DNS security**: DNSSEC, private hosted zones, split-horizon DNS

### 5.5 Data Protection
| Data Store | Data Class | At Rest Encryption | In Transit | Key Management | Key Rotation | Backup Encrypted |
|-----------|------------|-------------------|------------|----------------|--------------|------------------|
Cover ALL data stores. Specify exact encryption standard (AES-256-GCM, TLS 1.3, etc.)
Key Management must name exact service (KMS, CloudHSM, Secrets Manager).

### 5.6 Threat Model (STRIDE)
| Component | Spoofing | Tampering | Repudiation | Info Disclosure | DoS | Elevation | Mitigation |
|-----------|----------|-----------|-------------|-----------------|-----|-----------|-------------|
Cover the 3–5 most critical components. Each cell: ✅ mitigated / ⚠️ partial / ❌ unmitigated.

### 5.7 Audit, Logging & Compliance
- CloudTrail / Activity Log: ✅/❌ — all regions? Multi-account? S3 log archive?
- VPC Flow Logs: ✅/❌ — which VPCs? S3 or CloudWatch destination?
- Application logging: ✅/❌ — structured? Centralized? Retention period?
- Compliance frameworks: List applicable frameworks and map current gaps to specific controls
- **Compliance readiness score**: X/10 with justification"""


# ─────────────────────────────────────────────────────────────────────────────
# CALL 3 — AUDIT + RECOMMENDATIONS
# HA, performance, cost, Well-Architected gaps, prioritised fixes
# Input: component list + known gaps from prior sections  (~350 tokens)
# ─────────────────────────────────────────────────────────────────────────────

AUDIT_PROMPT = """Write sections 6–12 of an architecture design document.

Cloud: {cloud}
Components: {component_names}
Architecture pattern: {pattern}

Write exactly these sections with DEEP specificity:

## 6. Reliability & High Availability

### 6.1 HA Summary
| Component | Redundancy | AZs | Failover Time | RPO | RTO | HA Pattern | Gap |
|-----------|------------|-----|---------------|-----|-----|------------|-----|
For every stateful service, specify exact RPO/RTO targets (e.g., "RPO: 5 min, RTO: 15 min") and the HA pattern (active-active, active-passive, pilot-light).

### 6.2 Single Points of Failure
> [!WARNING] block per SPOF:
> **Component:** exact service name
> **What breaks:** specific user-facing impact
> **Blast radius:** number of users / % of traffic affected
> **Remediation:** specific fix with effort estimate (hours)

### 6.3 Fault Tolerance Mechanisms
| Mechanism | Implemented | Service | Configuration | Gap |
|-----------|-------------|---------|---------------|-----|
Cover: retry policies (with backoff config), DLQ (max receives, redrive policy), circuit breakers, health checks (interval, threshold), graceful degradation.

### 6.4 Disaster Recovery
- **DR strategy:** Pilot Light / Warm Standby / Multi-Site Active-Active
- **Backup schedule:** Per service (e.g., "RDS: automated daily + 35-day retention + cross-region replication")
- **Recovery runbook:** Step-by-step failover procedure (5-7 numbered steps)
- **DR testing cadence:** How often should DR be tested? Last test date if known.

## 7. Performance & Scalability

### 7.1 Scalability Matrix
| Component | Scaling Type | Min | Max | Trigger Metric | Threshold | Cool-down | Bottleneck Risk |
|-----------|-------------|-----|-----|----------------|-----------|-----------|-----------------|
Scaling Type: Horizontal / Vertical / Serverless auto. Include specific metric names (e.g., "CPUUtilization > 70%").

### 7.2 Performance Bottleneck Analysis
For each bottleneck identified:
- **Bottleneck:** exact component and constraint (e.g., "RDS max_connections = 150")
- **Impact:** what happens when limit is reached
- **Mitigation:** specific config change, service upgrade, or architectural change
- **Monitoring:** what CloudWatch/monitoring metric to alert on

### 7.3 Caching Strategy
| Layer | What to Cache | Tool | TTL | Invalidation Strategy | Expected Hit Rate |
|-------|--------------|------|-----|----------------------|-------------------|
Include: DNS caching, CDN caching, application caching (ElastiCache/DAX), database query caching.

## 8. Cost Analysis

### 8.1 Cost Breakdown
| Service | Billing Model | Instance/Size | Qty | Monthly Est. | Cost Driver | % of Total |
|---------|--------------|---------------|-----|-------------|-------------|-----------|
Include ALL services. Monthly Est. must be a specific dollar amount based on detected tier/size.

### 8.2 Cost Optimization Opportunities
| # | Opportunity | Current Cost | Optimized Cost | Saving | Action | Effort (hrs) |
|---|------------|-------------|---------------|--------|--------|-------------|
At least 5 opportunities. Include: Reserved Instances, Savings Plans, right-sizing, spot instances, storage tiering, NAT Gateway alternatives.

### 8.3 Total Cost of Ownership
- **Monthly estimate:** $X (dev) / $Y (staging) / $Z (production)
- **Annual estimate:** $X
- **Cost per user/request:** $X per 1M requests

## 9. Operational Excellence

### 9.1 Observability Stack
| Signal | Coverage | Tool | Metric/Log/Trace Examples | Gap | Priority |
|--------|----------|------|--------------------------|-----|----------|
Signals: Metrics, Logs, Traces, Synthetics, RUM. Coverage: ✅/⚠️/❌.

### 9.2 Incident Response
- **Alerting chain:** PagerDuty/OpsGenie → On-call → Escalation (with specific thresholds)
- **Runbook template:** For the top 3 failure scenarios, provide: Symptom → Diagnosis → Fix → Verification steps
- **MTTR target:** X minutes for P1, Y minutes for P2

### 9.3 Deployment Strategy
- **IaC tool:** Terraform / CloudFormation / Pulumi — with state management approach
- **CI/CD pipeline:** Source → Build → Test → Deploy stages with specific tools
- **Deployment pattern:** Blue-green / Canary / Rolling — with rollback trigger
- **Feature flags:** Are they used? Should they be?

## 10. Improvement Recommendations

### 10.1 🔴 Critical — Fix Before Production
For each (at least 3):
| Problem | Risk (if unfixed) | Fix | Effort (hrs) | Terraform Hint |
|---------|-------------------|-----|-------------|----------------|
Terraform Hint: actual HCL snippet or resource type (e.g., `aws_rds_cluster` with `multi_az = true`)

### 10.2 🟠 High — Fix in Next Sprint
Same format (at least 3).

### 10.3 🟡 Medium — Plan in Next Quarter
Same format (at least 2, briefer).

## 11. Well-Architected Scorecard

### 11.1 Pillar Scores
| Pillar | Score (1-5) | Status | Key Finding | Priority Fix | Effort (hrs) |
|--------|-------------|--------|-------------|--------------|-------------|
| Operational Excellence | ... | ✅/⚠️/❌ | specific finding | specific fix | ... |
| Security | ... | ✅/⚠️/❌ | ... | ... | ... |
| Reliability | ... | ✅/⚠️/❌ | ... | ... | ... |
| Performance Efficiency | ... | ✅/⚠️/❌ | ... | ... | ... |
| Cost Optimisation | ... | ✅/⚠️/❌ | ... | ... | ... |
| Sustainability | ... | ✅/⚠️/❌ | ... | ... | ... |
| **Overall** | ... | ... | ... | ... | ... |

### 11.2 Industry Benchmark Comparison
- **Best-in-class:** What a mature Fortune-500 version of this architecture looks like (name specific services/patterns)
- **Gap analysis:** The 3 most critical gaps vs. industry standard, with specific remediation
- **Strengths:** What this architecture does particularly well — be specific (e.g., "subnet isolation is better than 70% of production architectures we audit")
- **Maturity level:** 1 (Ad-hoc) → 5 (Optimized) — with justification"""


# ─────────────────────────────────────────────────────────────────────────────
# CALL 4 — GUIDANCE
# IaC code hints, ADRs, deployment steps, glossary
# Input: service list + deployment order  (~300 tokens)
# ─────────────────────────────────────────────────────────────────────────────

GUIDANCE_PROMPT = """Write the final sections of an architecture design document.

Cloud: {cloud}
Services: {service_names}
Deployment phases: {deployment_phases}

Write exactly these sections with DEEP specificity:

## 12. Infrastructure Optimisation

### 12.1 Terraform Recommendations
For the 3–4 most impactful changes, show BEFORE and AFTER HCL code.
Format EXACTLY like this:

**Recommendation N: [Title — e.g., "Enable Multi-AZ for RDS"]**
**Impact:** What this fixes and why it matters
**Effort:** X hours

BEFORE
```hcl
resource "aws_example" "basic" {{
  # minimal config — explain what's wrong
}}
```

AFTER (production-ready)
```hcl
resource "aws_example" "production" {{
  # full production config
  # every added line has an inline comment explaining WHY
  # include all required arguments, not just the changed ones
}}
```

CRITICAL: Show REAL, COMPLETE resources with actual values (instance types, CIDR ranges, ARNs).
If a naming convention exists in the dynamic context, use it in all resource names.
Include `tags` block in every AFTER example.

### 12.2 Serverless Optimisation
If Lambda/Cloud Functions present: memory profiling strategy, cold start mitigation (provisioned concurrency thresholds), timeout tuning, layer optimization. Include specific numbers.
If not present: skip this subsection.

### 12.3 Storage & Database Optimisation
- Connection pooling: RDS Proxy / PgBouncer — when to use, connection limits
- Storage tiering: S3 Intelligent-Tiering / Glacier lifecycle rules with specific day thresholds
- Read replicas: when to add, cross-AZ vs cross-region, lag monitoring
- Index optimization: specific indexes to create based on access patterns

### 12.4 Network Optimisation
- VPC endpoints: List EVERY {cloud} service that should use a VPC endpoint (with monthly cost saving vs NAT)
- NAT Gateway: Multi-AZ NAT cost analysis, alternatives (NAT instances for dev)
- PrivateLink: Which internal services should use PrivateLink and why
- Data transfer: Cross-AZ transfer costs, S3 gateway endpoint savings

## 13. Architecture Decision Records

For each significant design choice (3–4 ADRs):
### ADR-N: [Specific Title]
**Status:** Accepted | **Date:** [infer from context or use "Current"]
**Context:** The specific technical/business situation that forced this decision (2–3 sentences)
**Alternatives Considered:**
1. [Option A] — pros and cons (1 sentence each)
2. [Option B] — pros and cons
3. [Chosen option] — why it won

**Decision:** What was decided and how it will be implemented (1–2 sentences)
**Consequences:**
- ✅ [specific positive outcome]
- ✅ [another positive outcome]
- ⚠️ [trade-off that must be monitored]
**Revisit trigger:** When should this decision be re-evaluated? (e.g., "When traffic exceeds 10K RPS")

## 14. Deployment Guide

### 14.1 Prerequisites
| # | Requirement | Version/Detail | Installation Command |
|---|------------|----------------|---------------------|
Include: Terraform version, cloud CLI, kubectl (if K8s), Docker, required IAM permissions (list exact policy ARNs).

### 14.2 Deployment Order
Numbered phases with EXACT commands:
```bash
# Phase 1: Foundation
terraform init -backend-config=backend.hcl
terraform plan -target=module.networking -out=plan.tfplan
terraform apply plan.tfplan
```
> [!WARNING] Flag any operations requiring downtime or two-phase deploys.
> [!IMPORTANT] Flag any order dependencies (e.g., "VPC must exist before RDS").

### 14.3 Rollback Procedures
| Component | Rollback Method | Command | RTO | Data Loss Risk |
|-----------|----------------|---------|-----|---------------|
Include specific `terraform state` commands for state manipulation if needed.

### 14.4 Post-Deployment Verification
Numbered checklist of health checks to run after deployment:
1. Verify [service] health endpoint returns 200
2. Confirm [database] connectivity from [compute]
3. Test [load balancer] routing...

## 15. Glossary
| Term | Plain-English Explanation | Why It Matters |
|------|--------------------------|----------------|
Every {cloud}-specific term, acronym, and architectural pattern used in this document.
"Why It Matters" column: 1 sentence on business impact (e.g., "Multi-AZ means your database survives if an entire data center goes down")."""


# ─────────────────────────────────────────────────────────────────────────────
# CALL 5 — TERRAFORM PROMPTS
# 20 precise, image-aware prompts the user can fire on the Terraform chat page
# Input: full component + connection context  (~400 tokens)
# ─────────────────────────────────────────────────────────────────────────────

TERRAFORM_PROMPTS_PROMPT = """You are a senior Terraform engineer analysing a {cloud} architecture to generate precise, production-ready IaC prompts.

You MUST generate EXACTLY {prompt_count} highly detailed Terraform prompts by combining the detected architecture from the uploaded diagram with enterprise template constraints.

Components ({component_count}):
{components_text}

Connections ({connection_count}):
{connections_text}

Generate EXACTLY {prompt_count} specific, production-ready Terraform code-generation prompts tailored to THIS architecture.

CRITICAL RULES:
- Each prompt MUST be 150-300 words — extremely detailed and self-contained
- Each prompt must reference EXACT service names detected above (not generic placeholders)
- Each prompt must be a COMPLETE, self-contained instruction that produces runnable HCL
- Include at least 5 specific configuration values per prompt: instance types, CIDR ranges, port numbers, engine versions, retention days
- If a naming convention exists in the context, EVERY resource name must follow it
- Include tagging strategy (Environment, Application, CostCenter, Owner) in every prompt
- Specify security hardening: encryption at rest + in transit, least-privilege IAM, network isolation
- State production requirements: multi-AZ, auto-scaling, backup retention, monitoring
- Order: Foundation (networking/IAM) → Data layer → Compute → Application → Operational → Governance

Return a JSON array with this EXACT structure:
[
  {{
    "category": "networking",
    "prompt": "Create a VPC named 'prod-myapp-vpc-ap-south-1-01' (following naming convention) with CIDR 10.0.0.0/16. Deploy 3 public subnets (10.0.1.0/24, 10.0.2.0/24, 10.0.3.0/24) and 3 private subnets (10.0.10.0/24, 10.0.20.0/24, 10.0.30.0/24) across 3 AZs for high availability. Include Internet Gateway, 3 NAT Gateways (one per AZ), route tables with proper associations, VPC Flow Logs to CloudWatch (90-day retention), DNS hostnames enabled. Apply tags: Environment=prod, Application=banking, CostCenter=IT-INFRA. Use aws_vpc, aws_subnet, aws_internet_gateway, aws_nat_gateway, aws_route_table, aws_route_table_association, aws_flow_log.",
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
depends_on: list of categories this prompt needs completed first (e.g., ["networking", "iam"])
estimated_resources: approximate number of Terraform resources this prompt will create

COVERAGE (ensure ALL are covered across {prompt_count} prompts):
- Foundation: VPC/networking, IAM roles/policies, KMS keys (P0)
- Data: Databases, caches, storage with lifecycle policies (P1)
- Compute: Servers/containers/functions with auto-scaling (P1)
- Application: Load balancers, API gateways, CDN (P1)
- Security: WAF, Security Groups, NACLs, GuardDuty (P1)
- Operational: CloudWatch dashboards, alarms, SNS (P1)
- Governance: Backup plans, cost budgets, compliance, audit trails (P2)

QUALITY CHECK — each prompt MUST:
- Name the exact {cloud} service and Terraform resource type (e.g., "aws_vpc", "aws_subnet")
- Include at least 5 specific configuration values
- State production-readiness requirements (encryption, multi-AZ, backup retention)
- Be actionable without any additional context
- Follow the naming convention from the enterprise template

Return ONLY the JSON array. No markdown fences, no preamble, no summary. EXACTLY {prompt_count} prompts."""


# ─────────────────────────────────────────────────────────────────────────────
# GENERATOR
# ─────────────────────────────────────────────────────────────────────────────

class DesignDocGenerator:
    """
    Generates architecture design documents via 4 chained focused Bedrock calls.
    Each call gets only the context slice it needs.
    """

    def __init__(self):
        """Initialize Bedrock client for design document generation.

        Uses the shared core.bedrock_client factory so streaming responses get
        the same 180s read_timeout (covers P99 of 5-section streamed docs)
        and zero boto3-level retries (the gateway/fallback handles that).
        """
        try:
            from app.core.bedrock_client import get_bedrock_client
            self.bedrock_client = get_bedrock_client()
            self.bedrock_model = settings.AWS_BEDROCK_MODEL
            logger.info(f"[DesignDocGenerator] Initialized with Bedrock model: {self.bedrock_model}")
        except Exception as e:
            self.bedrock_client = None
            logger.error(f"[DesignDocGenerator] Bedrock init failed: {e}")

    # ── Public entry point ────────────────────────────────────────────────────

    def generate_design_document(
        self,
        vision_analysis: dict,
        cloud: str = "aws",
    ) -> dict:
        """
        Generate a full design document via 4 focused Bedrock calls.

        Args:
            vision_analysis: Output from VisionService.analyze_diagram()
            cloud:           "aws" or "azure"

        Returns:
            { title, content, cloud, architecture_summary,
              component_count, connection_count, sections, word_count }
        """
        logger.info(f"[DesignDocGenerator] Generating design doc for {cloud}")

        if not self.bedrock_client:
            logger.error("[DesignDocGenerator] Bedrock client not available")
            raise RuntimeError("Bedrock client not available")

        components  = vision_analysis.get("analysis", {}).get("components",  [])
        connections = vision_analysis.get("analysis", {}).get("connections", [])
        cloud_map = {"aws": "AWS", "azure": "Azure", "gcp": "GCP"}
        cloud_label = cloud_map.get(cloud.lower(), cloud.upper())

        logger.info(
            f"[DesignDoc] {cloud_label} — "
            f"{len(components)} components, {len(connections)} connections"
        )

        # Precompute shared slices — each call gets only what it needs
        components_text  = self._fmt_components(components)
        connections_text = self._fmt_connections(connections)
        component_names  = ", ".join(c.get("name", "?") for c in components[:20])
        service_names    = ", ".join(
            c.get("name", "?") for c in components
            if c.get("type", "") not in ("Actor", "External")
        )[:300]

        # 5 focused calls with increased token budgets for depth
        snapshot = self._call(SNAPSHOT_PROMPT.format(
            cloud            = cloud_label,
            component_count  = len(components),
            components_text  = components_text,
            connection_count = len(connections),
            connections_text = connections_text,
        ), max_tokens=2500)

        flows = self._call(FLOW_PROMPT.format(
            cloud             = cloud_label,
            component_names   = component_names,
            connections_text  = connections_text,
            cross_account     = self._detect_cross_account(connections),
        ), max_tokens=3000)

        audit = self._call(AUDIT_PROMPT.format(
            cloud           = cloud_label,
            component_names = component_names,
            pattern         = self._infer_pattern(components, connections),
        ), max_tokens=3500)

        guidance = self._call(GUIDANCE_PROMPT.format(
            cloud              = cloud_label,
            service_names      = service_names,
            deployment_phases  = self._infer_phases(components),
        ), max_tokens=2500)

        prompt_count = self._compute_prompt_count(components)
        terraform_prompts = self._call(TERRAFORM_PROMPTS_PROMPT.format(
            cloud              = cloud_label,
            component_count    = len(components),
            components_text    = components_text,
            connection_count   = len(connections),
            connections_text   = connections_text,
            prompt_count       = prompt_count,
        ), max_tokens=4000)

        # Stitch sections together
        content = self._stitch(cloud_label, snapshot, flows, audit, guidance, terraform_prompts)

        return {
            "title":                self._extract_title(content, cloud_label),
            "content":              content,
            "cloud":                cloud_label,
            "architecture_summary": self._extract_summary(content),
            "component_count":      len(components),
            "connection_count":     len(connections),
            "sections":             self._extract_sections(content),
            "word_count":           len(content.split()),
        }

    # ── Bedrock call ──────────────────────────────────────────────────────────

    def _call(self, prompt: str, max_tokens: int = 2048) -> str:
        """Single Bedrock call with proper system prompt separation + LangSmith tracing.
        
        Uses traced_invoke() so every design doc section call appears in LangSmith.
        Also checks semantic cache first for instant responses on repeated prompts.
        """
        try:
            # Check cache first
            try:
                from app.core.semantic_cache import get_cache
                cache = get_cache()
                cached = cache.get(prompt, "design_doc", "design_doc_section")
                if cached is not None:
                    logger.info(f"[DesignDoc] Cache HIT | prompt_len={len(prompt)}")
                    return cached
            except Exception:
                pass

            # Call Bedrock with tracing
            from app.core.bedrock_client import traced_invoke
            text = traced_invoke(
                model_id=self.bedrock_model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                system=SYSTEM_PROMPT,
                temperature=0.2,
                task_name="design_doc_section",
            )

            # Store in cache (24h TTL)
            try:
                from app.core.semantic_cache import get_cache
                get_cache().put(prompt, "design_doc", "design_doc_section", text, ttl_seconds=24 * 3600)
            except Exception:
                pass

            return text
        except Exception as e:
            logger.error(f"[DesignDoc] Bedrock call failed: {e}")
            return ""

    def _call_streaming(self, prompt: str, max_tokens: int = 2048):
        """
        Streaming Bedrock call — yields text chunks as they arrive.
        Used for ChatGPT-like real-time rendering.
        
        CACHE: Checks semantic cache first. If hit, yields the cached response
        in chunks (simulating streaming). If miss, streams from Bedrock and
        stores the complete response in cache for next time.
        """
        # Check semantic cache first — same prompt = instant replay
        try:
            from app.core.semantic_cache import get_cache
            cached = get_cache().get(prompt, "design_doc", "design_doc_section")
            if cached:
                logger.info(f"[DesignDoc] Streaming cache HIT | prompt_len={len(prompt)}")
                # Yield cached response in chunks to simulate streaming
                chunk_size = 100
                for i in range(0, len(cached), chunk_size):
                    yield cached[i:i+chunk_size]
                return
        except Exception:
            pass

        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens":        max_tokens,
            "temperature":       0.2,
            "system":            SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": prompt}],
        })

        accumulated = []  # Collect full response for caching
        try:
            resp = self.bedrock_client.invoke_model_with_response_stream(
                modelId     = self.bedrock_model,
                contentType = "application/json",
                accept      = "application/json",
                body        = body,
            )
            for event in resp.get("body", []):
                chunk_bytes = event.get("chunk", {}).get("bytes", b"")
                if not chunk_bytes:
                    continue
                chunk = json.loads(chunk_bytes)
                if chunk.get("type") == "content_block_delta":
                    text = chunk.get("delta", {}).get("text", "")
                    if text:
                        accumulated.append(text)
                        yield text

            # Store complete response in cache for next time (24h TTL)
            if accumulated:
                try:
                    from app.core.semantic_cache import get_cache
                    full_response = "".join(accumulated)
                    get_cache().put(prompt, "design_doc", "design_doc_section", full_response, ttl_seconds=24 * 3600)
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"[DesignDoc] Streaming Bedrock call failed: {e}")

    def generate_from_prompt(self, prompt: str, max_tokens: int = 4096) -> str:
        """Generate design document from an externally built prompt."""
        return self._call(prompt, max_tokens=max_tokens)

    def generate_from_prompt_streamed(self, prompt: str, max_tokens: int = 4096):
        """Stream design document from an externally built prompt."""
        yield from self._call_streaming(prompt, max_tokens=max_tokens)

    def _parse_json(self, text: str) -> dict:
        """Parse JSON from text, stripping markdown fences if present."""
        try:
            clean = text.strip()
            # 🟢 BEGINNER: Claude sometimes wraps JSON in markdown code fences (```json ... ```).
            # We strip those fences before parsing.
            if clean.startswith("```"):
                clean = clean.split("```", 2)[1]
                if clean.lower().startswith("json"):
                    clean = clean[4:]
            return json.loads(clean.strip())
        except Exception as e:
            logger.error(f"[DesignDoc] JSON parse failed: {e}")
            return {}

    # ── Dynamic context builder ─────────────────────────────────────────────

    def _build_dynamic_context(self, master_context: dict) -> str:
        """
        Build a structured, prioritized directive block from master_context.
        This is prepended to every design doc prompt so Claude tailors output
        to the user's specific constraints, naming conventions, and architecture.
        
        Structure:
          === MANDATORY REQUIREMENTS === (user intent + compliance + naming)
          === GOVERNANCE CONSTRAINTS === (template rules)
          === ARCHITECTURE INTELLIGENCE === (from diagram/document analysis)
          === SECURITY POSTURE === (security rules + compliance controls)
        """
        logger.info(f"[DesignDocService] Building dynamic context | keys={list(master_context.keys())}")
        
        lines = ["=== MANDATORY REQUIREMENTS (integrate into EVERY section) ===", ""]

        # 1. User's raw intent — the most important context signal
        raw_intent = master_context.get("raw_intent")
        user_prompt_raw = master_context.get("user_prompt_raw", "")
        if raw_intent:
            lines.append(f"CLIENT'S GOAL: {raw_intent}")
            lines.append("")
        if user_prompt_raw:
            lines.append(f"CLIENT'S EXACT REQUEST: \"{user_prompt_raw[:500]}\"")
            lines.append("")

        # 2. Naming standards — must appear in every resource example
        naming = master_context.get("naming_standards", {})
        if naming and any(naming.values()):
            pattern = naming.get("pattern", "")
            examples = naming.get("examples", [])
            lines.append("NAMING CONVENTION (use in ALL resource names and examples):")
            if pattern:
                lines.append(f"  Pattern: {pattern}")
            if examples:
                lines.append(f"  Examples: {', '.join(examples[:5])}")
            for key in ["case_rule", "separator", "prefix_suffix_rules", "max_length"]:
                if naming.get(key):
                    lines.append(f"  {key}: {naming[key]}")
            lines.append("")

        # 3. Compliance — must be cross-referenced in security/audit sections
        compliance = master_context.get("compliance", {})
        if compliance:
            frameworks = compliance.get("frameworks", []) if isinstance(compliance, dict) else compliance
            controls = compliance.get("specific_controls", []) if isinstance(compliance, dict) else []
            audit_reqs = compliance.get("audit_requirements", []) if isinstance(compliance, dict) else []
            if frameworks:
                lines.append(f"COMPLIANCE FRAMEWORKS: {', '.join(frameworks) if isinstance(frameworks, list) else frameworks}")
            if controls:
                lines.append(f"SPECIFIC CONTROLS TO REFERENCE: {'; '.join(controls[:10])}")
            if audit_reqs:
                lines.append(f"AUDIT REQUIREMENTS: {'; '.join(audit_reqs[:10])}")
            if frameworks or controls:
                lines.append("")

        # 4. User requirements (from compressed prompt)
        requirements = master_context.get("requirements", {})
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

        lines.append("=== GOVERNANCE CONSTRAINTS (from enterprise template) ===")
        lines.append("")

        # 5. Governance rules (rich descriptive strings)
        governance = master_context.get("governance", {})
        if governance:
            rules = governance.get("rules", [])
            if isinstance(rules, list) and rules:
                lines.append("GOVERNANCE RULES:")
                for rule in rules:
                    lines.append(f"  • {rule}")
            else:
                for key, value in governance.items():
                    if value and key != "rules":
                        lines.append(f"  • {key}: {value}")
            for key in ["environment_strategy", "tagging_policy", "approved_regions", "budget_constraints"]:
                val = governance.get(key)
                if val:
                    label = key.replace("_", " ").title()
                    lines.append(f"  {label}: {val if isinstance(val, str) else ', '.join(val)}")
            lines.append("")

        # 6. Terraform rules
        tf_rules = master_context.get("terraform_rules", {})
        if tf_rules and any(v for v in tf_rules.values() if v):
            lines.append("TERRAFORM/IaC RULES:")
            for key, value in tf_rules.items():
                if value:
                    lines.append(f"  • {key}: {value}")
            lines.append("")

        # 7. Security constraints
        security = master_context.get("security", {})
        if security:
            sec_rules = security.get("rules", [])
            if isinstance(sec_rules, list) and sec_rules:
                lines.append("SECURITY CONSTRAINTS:")
                for rule in sec_rules:
                    lines.append(f"  • {rule}")
            else:
                for key, value in security.items():
                    if value and key != "rules":
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

        lines.append("=== ARCHITECTURE INTELLIGENCE (from diagram/document analysis) ===")
        lines.append("")

        # 8. Architecture — rich service descriptions
        architecture = master_context.get("architecture", {})
        if architecture:
            lines.append("DETECTED SERVICES:")
            for category, services in architecture.items():
                if not services:
                    continue
                if isinstance(services, list):
                    for svc in services:
                        if isinstance(svc, dict):
                            detail = svc.get("detail", "")
                            lines.append(f"  [{category}] {svc.get('service', '?')}: {detail}")
                        else:
                            lines.append(f"  [{category}] {svc}")
                elif isinstance(services, str):
                    lines.append(f"  [{category}] {services}")
            lines.append("")

        # 9. Data flows
        data_flows = master_context.get("data_flows", [])
        if data_flows:
            lines.append("DATA FLOWS:")
            for flow in data_flows[:8]:
                if isinstance(flow, dict):
                    name = flow.get("name", "unnamed")
                    path = " → ".join(flow.get("path", [])) if isinstance(flow.get("path"), list) else str(flow.get("path", ""))
                    crit = flow.get("criticality", "")
                    lines.append(f"  {name}: {path} [{crit}]")
            lines.append("")

        # 10. Topology
        topology = master_context.get("topology", {})
        if topology and any(v for v in topology.values() if v):
            lines.append("NETWORK TOPOLOGY:")
            for key, value in topology.items():
                if value:
                    if isinstance(value, list):
                        lines.append(f"  {key}: {', '.join(str(v) for v in value)}")
                    else:
                        lines.append(f"  {key}: {value}")
            lines.append("")

        # 11. Critical fields (uncompressed)
        critical_fields = master_context.get("critical_fields", {})
        if critical_fields:
            cc = critical_fields.get("component_count", 0)
            nc = critical_fields.get("connection_count", 0)
            if cc or nc:
                lines.append(f"TOTALS: {cc} components, {nc} connections")
                lines.append("")

        lines.append("⚠️ CRITICAL: Every section MUST directly address the client's goal, use the naming convention, and reference compliance controls where relevant.")
        lines.append("")

        return "\n".join(lines)

    # ── Fused-context entry point (used by multi-agent pipeline) ──────────────

    def generate_from_fused_context(
        self,
        master_context: dict,
        cloud: str = "aws",
    ) -> dict:
        """
        Generate a design document that dynamically adapts to the user's
        requirements and uploaded document content.

        Args:
            master_context: Compressed context from HaikuCompressionNode (governance, 
                          architecture, requirements, terraform_rules, etc.)
            cloud: "aws" or "azure"

        Returns:
            { title, content, cloud, architecture_summary,
              component_count, connection_count, sections, word_count }
        """
        logger.info(f"[DesignDocGenerator] Generating DYNAMIC design doc for {cloud}")

        if not self.bedrock_client:
            logger.error("[DesignDocGenerator] Bedrock client not available")
            raise RuntimeError("Bedrock client not available")

        # Extract from master_context (compressed by Haiku)
        critical_fields = master_context.get("critical_fields", {})
        components = critical_fields.get("components", [])
        connections = critical_fields.get("connections", [])
        cloud_map = {"aws": "AWS", "azure": "Azure", "gcp": "GCP"}
        cloud_label = cloud_map.get(cloud.lower(), cloud.upper())

        logger.info(
            f"[DesignDoc] DYNAMIC {cloud_label} — "
            f"{len(components)} components, {len(connections)} connections, "
            f"master_context_keys={list(master_context.keys())}"
        )

        # Build the dynamic context block once (using compressed master_context)
        dynamic_context = self._build_dynamic_context(master_context)

        # Precompute shared slices
        components_text  = self._fmt_components(components)
        connections_text = self._fmt_connections(connections)
        component_names  = ", ".join(c.get("name", "?") for c in components[:20])
        service_names    = ", ".join(
            c.get("name", "?") for c in components
            if c.get("type", "") not in ("Actor", "External")
        )[:300]

        # ── 5 parallel Bedrock calls (ThreadPoolExecutor) ─────────────────────
        # Each section is independent — no ordering dependency until _stitch.
        # Sequential total: ~25s  →  Parallel total: ~5s (limited by slowest call)
        prompt_count = self._compute_prompt_count(components)

        section_tasks = {
            "snapshot": (
                SNAPSHOT_PROMPT.format(
                    cloud            = cloud_label,
                    component_count  = len(components),
                    components_text  = components_text,
                    connection_count = len(connections),
                    connections_text = connections_text,
                ),
                2500,
            ),
            "flows": (
                FLOW_PROMPT.format(
                    cloud             = cloud_label,
                    component_names   = component_names,
                    connections_text  = connections_text,
                    cross_account     = self._detect_cross_account(connections),
                ),
                3000,
            ),
            "audit": (
                AUDIT_PROMPT.format(
                    cloud           = cloud_label,
                    component_names = component_names,
                    pattern         = self._infer_pattern(components, connections),
                ),
                3500,
            ),
            "guidance": (
                GUIDANCE_PROMPT.format(
                    cloud              = cloud_label,
                    service_names      = service_names,
                    deployment_phases  = self._infer_phases(components),
                ),
                2500,
            ),
            "terraform_prompts": (
                TERRAFORM_PROMPTS_PROMPT.format(
                    cloud              = cloud_label,
                    component_count    = len(components),
                    components_text    = components_text,
                    connection_count   = len(connections),
                    connections_text   = connections_text,
                    prompt_count       = prompt_count,
                ),
                10000,
            ),
        }

        section_results: dict[str, str] = {}
        t0 = time.time()

        with ThreadPoolExecutor(max_workers=5, thread_name_prefix="design_doc") as pool:
            future_to_key = {
                pool.submit(self._call_with_context, prompt, dynamic_context, max_tokens): key
                for key, (prompt, max_tokens) in section_tasks.items()
            }
            for future in as_completed(future_to_key):
                key = future_to_key[future]
                try:
                    section_results[key] = future.result()
                    logger.info(f"[DesignDoc] Section '{key}' done in {time.time()-t0:.1f}s")
                except Exception as exc:
                    logger.error(f"[DesignDoc] Section '{key}' failed: {exc}")
                    section_results[key] = f"\n\n> ⚠️ Section generation failed: {exc}\n\n"

        elapsed = time.time() - t0
        logger.info(f"[DesignDoc] All 5 sections completed in {elapsed:.1f}s (parallel)")

        snapshot          = section_results.get("snapshot", "")
        flows             = section_results.get("flows", "")
        audit             = section_results.get("audit", "")
        guidance          = section_results.get("guidance", "")
        terraform_prompts = section_results.get("terraform_prompts", "")

        # Stitch sections together (preserves original ordering)
        content = self._stitch(cloud_label, snapshot, flows, audit, guidance, terraform_prompts)

        return {
            "title":                self._extract_title(content, cloud_label),
            "content":              content,
            "cloud":                cloud_label,
            "architecture_summary": self._extract_summary(content),
            "component_count":      len(components),
            "connection_count":     len(connections),
            "sections":             self._extract_sections(content),
            "word_count":           len(content.split()),
        }

    def _call_with_context(self, prompt: str, dynamic_context: str, max_tokens: int = 2048) -> str:
        """Prepend dynamic context to the prompt before calling Bedrock."""
        full_prompt = f"{dynamic_context}\n\n{prompt}"
        return self._call(full_prompt, max_tokens=max_tokens)

    def generate_design_document_streamed(
        self,
        vision_analysis: dict,
        cloud: str = "aws"
    ):
        """
        Yields SSE strings with fine-grained text deltas for real-time
        ChatGPT-like streaming.

        Event types:
          section_start  — {"type":"section_start","section":"snapshot","title":"..."}
          delta          — {"type":"delta","text":"<chunk>"}
          section_end    — {"type":"section_end","section":"snapshot"}
          [DONE]         — final sentinel
        """
        # 🟢 BEGINNER: Extract components and connections from the vision analysis dict.
        components  = vision_analysis.get("analysis", {}).get("components", [])
        connections = vision_analysis.get("analysis", {}).get("connections", [])
        cloud_label = "AWS" if cloud.lower() == "aws" else "Azure"

        # 🟢 BEGINNER: Format the raw component/connection data into readable text for the AI prompt.
        components_text  = self._fmt_components(components)
        connections_text = self._fmt_connections(connections)
        component_names  = ", ".join(c.get("name", "?") for c in components[:20])
        service_names    = ", ".join(
            c.get("name", "?") for c in components
            if c.get("type", "") not in ("Actor", "External")
        )[:300]

        # 🟢 BEGINNER: Human-readable titles for each section. These appear in the frontend sidebar.
        SECTION_TITLES = {
            "snapshot":           "Architecture Snapshot",
            "flows":              "Data & Traffic Flows",
            "audit":              "Security & Compliance Audit",
            "guidance":           "Operational Guidance",
            "terraform_prompts": "Terraform Generation Prompts",
        }

        # 🟢 BEGINNER: The 5 AI calls: (section_name, formatted_prompt, max_tokens).
        # Each call is independent — if one fails, the others still run.
        prompt_count = self._compute_prompt_count(components)
        calls = [
            ("snapshot", SNAPSHOT_PROMPT.format(
                cloud=cloud_label,
                component_count=len(components),
                components_text=components_text,
                connection_count=len(connections),
                connections_text=connections_text,
            ), 2500),
            ("flows", FLOW_PROMPT.format(
                cloud=cloud_label,
                component_names=component_names,
                connections_text=connections_text,
                cross_account=self._detect_cross_account(connections),
            ), 3000),
            ("audit", AUDIT_PROMPT.format(
                cloud=cloud_label,
                component_names=component_names,
                pattern=self._infer_pattern(components, connections),
            ), 3500),
            ("guidance", GUIDANCE_PROMPT.format(
                cloud=cloud_label,
                service_names=service_names,
                deployment_phases=self._infer_phases(components),
            ), 2500),
            ("terraform_prompts", TERRAFORM_PROMPTS_PROMPT.format(
                cloud=cloud_label,
                component_count=len(components),
                components_text=components_text,
                connection_count=len(connections),
                connections_text=connections_text,
                prompt_count=prompt_count,
            ), 10000),
        ]

        # 🟢 BEGINNER: Loop over each of the 5 sections, yield SSE events to the frontend.
        for section_name, prompt, max_tokens in calls:
            title = SECTION_TITLES.get(section_name, section_name)
            # 🟢 BEGINNER: Tell the frontend: "A new section is starting."
            yield f"data: {json.dumps({'type': 'section_start', 'section': section_name, 'title': title})}\n\n"

            try:
                # 🟢 BEGINNER: Stream text chunks from Bedrock for this section.
                for text_chunk in self._call_streaming(prompt, max_tokens=max_tokens):
                    if text_chunk:
                        yield f"data: {json.dumps({'type': 'delta', 'text': text_chunk})}\n\n"
            except Exception as e:
                logger.error(f"[DesignDoc] Stream error in {section_name}: {e}")
                # 🟢 BEGINNER: Fallback: if streaming fails, do a non-streaming call and yield all text at once.
                raw = self._call(prompt, max_tokens=max_tokens)
                if raw:
                    yield f"data: {json.dumps({'type': 'delta', 'text': raw})}\n\n"

            # 🟢 BEGINNER: Tell the frontend: "This section is finished."
            yield f"data: {json.dumps({'type': 'section_end', 'section': section_name})}\n\n"

        # 🟢 BEGINNER: Final sentinel tells the frontend to close the stream and stop showing the loading spinner.
        yield "data: [DONE]\n\n"

    def generate_design_document_streamed_dynamic(
        self,
        master_context: dict,
        cloud: str = "aws",
    ):
        """
        Dynamic streaming design doc that uses master_context (compressed by Haiku).
        Injects governance, security, naming, compliance, and user requirements into
        every section prompt so the LLM tailors output to the user's constraints.

        This replaces the static generate_design_document_streamed() for pipeline calls.
        """
        critical_fields = master_context.get("critical_fields", {})
        components = critical_fields.get("components", [])
        connections = critical_fields.get("connections", [])
        cloud_map = {"aws": "AWS", "azure": "Azure", "gcp": "GCP"}
        cloud_label = cloud_map.get(cloud.lower(), cloud.upper())

        logger.info(
            f"[DesignDoc] DYNAMIC STREAMED {cloud_label} — "
            f"{len(components)} components, {len(connections)} connections, "
            f"master_context_keys={list(master_context.keys())}"
        )

        # Build the dynamic context block once
        dynamic_context = self._build_dynamic_context(master_context)

        components_text = self._fmt_components(components)
        connections_text = self._fmt_connections(connections)
        component_names = ", ".join(c.get("name", "?") for c in components[:20])
        service_names = ", ".join(
            c.get("name", "?") for c in components
            if c.get("type", "") not in ("Actor", "External")
        )[:300]

        SECTION_TITLES = {
            "snapshot":          "Architecture Snapshot",
            "flows":             "Data & Traffic Flows",
            "audit":             "Security & Compliance Audit",
            "guidance":          "Operational Guidance",
            "terraform_prompts": "Terraform Generation Prompts",
        }

        prompt_count = self._compute_prompt_count(components)
        calls = [
            ("snapshot", SNAPSHOT_PROMPT.format(
                cloud=cloud_label,
                component_count=len(components),
                components_text=components_text,
                connection_count=len(connections),
                connections_text=connections_text,
            ), 2500),
            ("flows", FLOW_PROMPT.format(
                cloud=cloud_label,
                component_names=component_names,
                connections_text=connections_text,
                cross_account=self._detect_cross_account(connections),
            ), 3000),
            ("audit", AUDIT_PROMPT.format(
                cloud=cloud_label,
                component_names=component_names,
                pattern=self._infer_pattern(components, connections),
            ), 3500),
            ("guidance", GUIDANCE_PROMPT.format(
                cloud=cloud_label,
                service_names=service_names,
                deployment_phases=self._infer_phases(components),
            ), 2500),
            ("terraform_prompts", TERRAFORM_PROMPTS_PROMPT.format(
                cloud=cloud_label,
                component_count=len(components),
                components_text=components_text,
                connection_count=len(connections),
                connections_text=connections_text,
                prompt_count=prompt_count,
            ), 10000),
        ]

        for section_name, prompt, max_tokens in calls:
            title = SECTION_TITLES.get(section_name, section_name)
            yield f"data: {json.dumps({'type': 'section_start', 'section': section_name, 'title': title})}\n\n"

            # Prepend dynamic context to every prompt
            full_prompt = f"{dynamic_context}\n\n{prompt}"

            try:
                for text_chunk in self._call_streaming(full_prompt, max_tokens=max_tokens):
                    if text_chunk:
                        yield f"data: {json.dumps({'type': 'delta', 'text': text_chunk})}\n\n"
            except Exception as e:
                logger.error(f"[DesignDoc] Dynamic stream error in {section_name}: {e}")
                raw = self._call(full_prompt, max_tokens=max_tokens)
                if raw:
                    yield f"data: {json.dumps({'type': 'delta', 'text': raw})}\n\n"

            yield f"data: {json.dumps({'type': 'section_end', 'section': section_name})}\n\n"

        yield "data: [DONE]\n\n"

    # ── Dynamic prompt count ────────────────────────────────────────────────

    @staticmethod
    def _compute_prompt_count(components: list) -> int:
        """Always generate exactly 15 production-ready prompts."""
        return 15

    # ── Input formatters ──────────────────────────────────────────────────────

    def _fmt_components(self, components: list) -> str:
        return "\n".join(
            f"  {i+1:02d}. {c.get('name','?'):<28} "
            f"type={c.get('type','Other'):<18} "
            f"conf={c.get('confidence',0):.2f}"
            for i, c in enumerate(components)
        ) or "  None detected."

    def _fmt_connections(self, connections: list) -> str:
        return "\n".join(
            f"  {i+1:02d}. {c.get('source','?'):<20} → "
            f"{c.get('target','?'):<20} ({c.get('type','CONNECTS_TO')})"
            for i, c in enumerate(connections)
        ) or "  None detected."

    def _detect_cross_account(self, connections: list) -> str:
        """Simple heuristic: look for connections mentioning 'account' or 'cross'."""
        cross = [
            c for c in connections
            if "account" in str(c).lower() or "cross" in str(c).lower()
        ]
        return f"{len(cross)} cross-account flows detected" if cross else "None detected"

    def _infer_pattern(self, components: list, connections: list) -> str:
        """Infer canonical pattern from component types."""
        types  = {c.get("type", "").lower() for c in components}
        names  = " ".join(c.get("name", "").lower() for c in components)

        if "lambda" in names and "eventbridge" in names:
            return "Event-driven serverless automation"
        if "ecs" in names or "eks" in names:
            return "Container-based microservices"
        if "step function" in names or "sfn" in names:
            return "Orchestrated workflow (Step Functions)"
        if len(connections) > len(components) * 1.5:
            return "Mesh / highly connected service graph"
        return "Multi-tier cloud application"

    def _infer_phases(self, components: list) -> str:
        """Produce a brief deployment phase description from component layers."""
        has_network  = any("vpc" in c.get("name","").lower() or
                           "subnet" in c.get("name","").lower()
                           for c in components)
        has_compute  = any(c.get("type","").lower() in ("lambda","ec2","ecs","eks")
                           for c in components)
        has_data     = any(c.get("type","").lower() in ("rds","dynamodb","s3","aurora")
                           for c in components)

        phases = []
        if has_network:
            phases.append("Phase 1: networking (VPC, subnets, gateways)")
        if has_data:
            phases.append("Phase 2: data layer (databases, storage)")
        if has_compute:
            phases.append("Phase 3: compute + application layer")
        phases.append("Phase 4: monitoring, alerting, DNS")

        return " → ".join(phases) if phases else "Single-phase deployment"

    # ── Stitching ─────────────────────────────────────────────────────────────

    def _stitch(
        self,
        cloud:    str,
        snapshot: str,
        flows:    str,
        audit:    str,
        guidance: str,
        terraform_prompts: str = "",
    ) -> str:
        header = (
            f"# {cloud} Architecture — Design Document\n\n"
            f"> **Cloud:** {cloud} | "
            f"**Document type:** Architecture Review | "
            f"**Audience:** Technical + Non-Technical\n\n---\n\n"
        )
        footer = (
            "\n\n---\n"
            "*Document generated from architecture diagram analysis.*  \n"
            "*Review and validate all assumptions before using in production.*"
        )
        sections = [s for s in [snapshot, flows, audit, guidance, terraform_prompts] if s.strip()]
        return header + "\n\n---\n\n".join(sections) + footer

    # ── Post-processing ───────────────────────────────────────────────────────

    def _extract_title(self, content: str, cloud: str) -> str:
        for line in content.splitlines():
            if line.startswith("# ") and not line.startswith("## "):
                return line.lstrip("# ").strip()
        return f"{cloud} Architecture Design Document"

    def _extract_summary(self, content: str) -> str:
        lines, collecting, result = content.splitlines(), False, []
        for line in lines:
            if "executive summary" in line.lower():
                collecting = True
                continue
            if collecting:
                if line.startswith("## ") and "executive" not in line.lower():
                    break
                if line.strip():
                    result.append(line)
                if len(result) >= 8:
                    break
        return "\n".join(result) if result else "Design document generated."

    def _extract_sections(self, content: str) -> list[str]:
        return [
            line.lstrip("# ").strip()
            for line in content.splitlines()
            if line.startswith("## ")
        ]