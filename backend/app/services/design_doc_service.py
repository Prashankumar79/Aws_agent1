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
from app.core.config import settings

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# SHARED SYSTEM PROMPT — 8 lines, applied to every call
# ─────────────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a principal cloud architect at a Fortune-500 company writing an architecture design document that will be reviewed by engineering leadership, security teams, and auditors.

WRITING STANDARDS:
- Use Markdown. ## for sections, ### for subsections, properly formatted tables with | header | separators.
- Be deeply specific — name EXACT services, instance types, SKUs, config values, and ARN patterns.
- Be brutally honest — call out every gap, risk, and missing control clearly.
- No filler phrases. No generic advice. Every sentence must be actionable or informative.
- Use > [!WARNING] for security vulnerabilities and production-blocking issues.
- Use > [!IMPORTANT] for architectural decisions that need immediate attention.
- Tables MUST use proper Markdown format: header row, separator row (|---|---|), then data rows.
- For status/health indicators: use ✅ (pass), ⚠️ (needs attention), ❌ (critical gap).
- Include specific metrics, thresholds, and SLA numbers where applicable.
- Reference AWS/Azure Well-Architected Framework pillars when relevant.
- Return only the Markdown content for your assigned section. No preamble, no "Here is..." intros."""


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

Write exactly these sections:

## 1. Executive Summary
4–5 sentences for a non-technical CEO. Cover: what the system does, who it serves, expected scale (users/RPS/data volume), current production-readiness score (1–5), and one critical action item.
No jargon. If you use an acronym, explain it in parentheses.

## 2. What This System Does

### 2.1 The Big Picture
2–3 paragraphs using a real-world analogy (e.g., "Think of it as a post office..."). Prose only, no bullets. End with the key architectural insight.

### 2.2 Key Actors & Stakeholders
| Actor | Role | Primary Actions | Frequency | SLA Expectation |
|-------|------|-----------------|-----------|-----------------|
(Fill with specific actors inferred from the architecture)

### 2.3 Business Value & Problem Statement
Three concise paragraphs: (1) what existed before / manual pain points, (2) what this architecture automates or enables, (3) quantifiable business value (cost savings, speed improvement, reliability gain).

## 3. Architecture Overview

### 3.1 Architecture Pattern
Name the canonical pattern (e.g., "Event-Driven Microservices", "Three-Tier Web Application", "Serverless Data Pipeline"). Explain in 2–3 sentences why this pattern fits the scale and use case.

### 3.2 Deployment Topology
| Dimension | Detail |
|-----------|--------|
| Cloud Provider | ... |
| Region Strategy | ... |
| Account Structure | ... |
| Availability Zones | ... |
| Network Topology | ... |
| Environment Separation | ... |

### 3.3 Service Inventory
| # | Service Name | {cloud} Service | Layer | Purpose | Criticality |
|---|-------------|-----------------|-------|---------|-------------|
Layer categories: Edge / Compute / Data / Messaging / Security / Observability / Management / Networking
Criticality: CRITICAL / HIGH / MEDIUM / LOW"""


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

Write exactly these sections:

## 4. Data Flow Analysis

### 4.1 Overview
2–3 sentences: topology shape, where data enters, where it rests.

### 4.2 Flows
For each distinct flow:
#### Flow N: [Name]
- **Trigger:** what starts it
- **Criticality:** CRITICAL / HIGH / MEDIUM / LOW
- Step table: Step | From | To | Action | Protocol | Encrypted ✅/❌
- **Plain story:** 3–5 sentences narrating the relay race
- **Data at rest:** final persistence location
- **Failure mode:** what breaks if this flow fails

### 4.3 Cross-Account / Cross-Region
Mechanism, trust relationship, security controls. Skip if none.

## 5. Security Assessment

### 5.1 Posture Summary
> [!IMPORTANT]
> One clear sentence on overall security posture. Followed by 2–3 specific callouts on what's implemented well and what's critically missing.

### 5.2 Security Controls Matrix
| Control | Type | Protects | Status | Gap / Notes |
|---------|------|----------|--------|-------------|
(Preventive, Detective, Corrective controls — at least 8 rows)

### 5.3 Identity & Access Management
- Least-privilege assessment (specific over-permissioned roles if any)
- Cross-account trust relationships and scoping
- Permission boundaries and service control policies
- MFA enforcement status

### 5.4 Network Security
- Public exposure surface (list all internet-facing endpoints)
- Security group analysis (overly permissive rules)
- Network segmentation and micro-segmentation
- VPC isolation and subnet strategy

### 5.5 Data Protection
| Data Category | At Rest | In Transit | Key Management | Rotation |
|--------------|---------|------------|----------------|----------|
(Cover all data stores. Specify encryption standard: AES-256, TLS 1.3, etc.)

### 5.6 Audit, Logging & Compliance
- CloudTrail / Activity Log coverage: ✅/❌
- VPC Flow Logs: ✅/❌
- Application-level logging: ✅/❌
- Compliance frameworks applicable (SOC2, HIPAA, PCI-DSS, ISO 27001)
- Gaps that block compliance certification"""


# ─────────────────────────────────────────────────────────────────────────────
# CALL 3 — AUDIT + RECOMMENDATIONS
# HA, performance, cost, Well-Architected gaps, prioritised fixes
# Input: component list + known gaps from prior sections  (~350 tokens)
# ─────────────────────────────────────────────────────────────────────────────

AUDIT_PROMPT = """Write sections 6–12 of an architecture design document.

Cloud: {cloud}
Components: {component_names}
Architecture pattern: {pattern}

Write exactly these sections:

## 6. Reliability & High Availability

### 6.1 HA Summary
Table: Component | Redundancy | AZs | Failover Time | RPO | RTO

### 6.2 Single Points of Failure
> [!WARNING] block per SPOF: name, what breaks, blast radius.

### 6.3 Fault Tolerance
Retry, DLQ, circuit breaker, failover mechanisms visible.

### 6.4 Disaster Recovery
Backup strategy, DR region, RPO/RTO exposure.

## 7. Performance & Scalability

### 7.1 Scalability
Table: Component | Scaling Type | Trigger | Max Capacity

### 7.2 Bottlenecks
Synchronous chains, services without auto-scaling, DB connection limits.

### 7.3 Caching
What's cached, what should be cached.

## 8. Cost Analysis

### 8.1 Cost Profile
Table: Service | Billing Model | Cost Driver | Optimisation Opportunity

### 8.2 Quick Wins
Table: Opportunity | Action | Estimated Saving | Effort (Low/Med/High)

## 9. Operational Excellence

### 9.1 Observability
Table: Signal | Coverage ✅/⚠️/❌ | Tool | Gap

### 9.2 Incident Response
Runbooks, on-call, alerting escalation path.

### 9.3 Deployment Strategy
IaC tool, CI/CD pipeline, rollback approach.

## 10. Improvement Recommendations

### 10.1 🔴 Critical — Fix Before Production
For each: **Problem** | **Risk** | **Fix** | **Effort** | `Terraform hint`

### 10.2 🟠 High — Fix in Next Sprint
Same format.

### 10.3 🟡 Medium — Plan in Next Quarter
Same format but briefer.

## 11. Well-Architected Scorecard

### 11.1 Pillar Scores
| Pillar | Score (1-5) | Status | Key Finding | Priority Fix |
|--------|-------------|--------|-------------|--------------|
| Operational Excellence | ... | ✅/⚠️/❌ | ... | ... |
| Security | ... | ✅/⚠️/❌ | ... | ... |
| Reliability | ... | ✅/⚠️/❌ | ... | ... |
| Performance Efficiency | ... | ✅/⚠️/❌ | ... | ... |
| Cost Optimisation | ... | ✅/⚠️/❌ | ... | ... |
| Sustainability | ... | ✅/⚠️/❌ | ... | ... |
| **Overall** | ... | ... | ... | ... |

### 11.2 Industry Benchmark Comparison
3 focused bullets:
- **Best-in-class:** What a mature, production-hardened version of this architecture looks like
- **Gap analysis:** What 90% of production systems have that this architecture is missing
- **Strengths:** What this architecture does particularly well vs. industry standard"""


# ─────────────────────────────────────────────────────────────────────────────
# CALL 4 — GUIDANCE
# IaC code hints, ADRs, deployment steps, glossary
# Input: service list + deployment order  (~300 tokens)
# ─────────────────────────────────────────────────────────────────────────────

GUIDANCE_PROMPT = """Write the final sections of an architecture design document.

Cloud: {cloud}
Services: {service_names}
Deployment phases: {deployment_phases}

Write exactly these sections:

## 12. Infrastructure Optimisation

### 12.1 Terraform Recommendations
For the 2–3 most impactful changes, show BEFORE and AFTER HCL code.
Format EXACTLY like this (use the text labels AND fenced code blocks):

BEFORE
```hcl
resource "aws_example" "basic" {{
  # minimal config
}}
```

AFTER (production-ready)
```hcl
resource "aws_example" "production" {{
  # full production config with comments explaining each addition
}}
```

Show real, complete resources — not snippets. Include inline # comments for every significant addition.

### 12.2 Serverless Optimisation
If Lambda present: memory sizing, cold start mitigation, timeout tuning.
If not present: skip this subsection.

### 12.3 Storage & Database Optimisation
Connection pooling, storage tiering, read replicas. Skip if no DB/storage.

### 12.4 Network Optimisation
VPC endpoints, NAT Gateway cost, PrivateLink opportunities.

## 13. Architecture Decision Records

For each significant design choice (2–4 ADRs max):
### ADR-N: [Title]
**Status:** Accepted
**Context:** situation | **Decision:** what | **Rationale:** why over alternatives
**Consequences:** ✅ positive | ⚠️ trade-off

## 14. Deployment Guide

### 14.1 Prerequisites
Numbered list: tools, permissions, accounts needed.

### 14.2 Deployment Order
Numbered phases with exact commands.
> [!WARNING] flag any two-phase deploys.

### 14.3 Rollback
Per-component rollback steps.

## 15. Glossary
Table: Term | Plain-English Explanation
Every {cloud}-specific term used in this document."""


# ─────────────────────────────────────────────────────────────────────────────
# CALL 5 — TERRAFORM PROMPTS
# 20 precise, image-aware prompts the user can fire on the Terraform chat page
# Input: full component + connection context  (~400 tokens)
# ─────────────────────────────────────────────────────────────────────────────

TERRAFORM_PROMPTS_PROMPT = """You are analysing a {cloud} architecture diagram that contains:

Components ({component_count}):
{components_text}

Connections ({connection_count}):
{connections_text}

Generate exactly 20 specific Terraform code-generation prompts. Each prompt MUST:
- Reference the EXACT services detected above (not generic examples).
- Be a complete, self-contained instruction that an AI can turn into production-ready HCL.
- Cover a different infrastructure concern.
- Be ordered from foundational → application → operational.

Use this EXACT format (one prompt per line):

1. [Networking] Create a VPC with ...
2. [Networking] Configure security groups for ...
3. [Networking] Set up NAT gateway / VPC endpoints for ...
4. [IAM] Define IAM roles and policies for ...
5. [IAM] Create KMS keys and encryption policies for ...
6. [Compute] Provision {cloud} compute resources for ...
7. [Compute] Configure auto-scaling for ...
8. [Compute] Set up container orchestration for ... (if applicable)
9. [Storage] Create storage buckets / volumes for ...
10. [Database] Provision database instances for ...
11. [Load Balancing] Set up load balancer for ...
12. [DNS & CDN] Configure DNS records / CDN for ...
13. [Messaging] Create message queues / event buses for ...
14. [Messaging] Set up notification topics for ...
15. [Monitoring] Create CloudWatch / Monitor dashboards and alarms for ...
16. [Logging] Configure centralised logging for ...
17. [CI/CD] Set up deployment pipeline for ...
18. [Backup] Configure automated backups for ...
19. [Cost] Implement cost controls and budget alerts for ...
20. [Compliance] Add compliance tags and audit trail for ...

Replace the "..." with architecture-specific details drawn from the components above.
Return ONLY the 20 numbered prompts. No preamble, no summary."""


# ─────────────────────────────────────────────────────────────────────────────
# GENERATOR
# ─────────────────────────────────────────────────────────────────────────────

class DesignDocGenerator:
    """
    Generates architecture design documents via 4 chained focused Bedrock calls.
    Each call gets only the context slice it needs.
    """

    def __init__(self):
        """Initialize Bedrock client for design document generation."""
        try:
            self.bedrock_client = boto3.client(
                'bedrock-runtime',
                region_name=settings.AWS_DEFAULT_REGION,
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            )
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
        cloud_label = "AWS" if cloud.lower() == "aws" else "Azure"

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

        # 4 focused calls — each ~300–400 tokens input
        snapshot = self._call(SNAPSHOT_PROMPT.format(
            cloud            = cloud_label,
            component_count  = len(components),
            components_text  = components_text,
            connection_count = len(connections),
            connections_text = connections_text,
        ), max_tokens=1800)

        flows = self._call(FLOW_PROMPT.format(
            cloud             = cloud_label,
            component_names   = component_names,
            connections_text  = connections_text,
            cross_account     = self._detect_cross_account(connections),
        ), max_tokens=2000)

        audit = self._call(AUDIT_PROMPT.format(
            cloud           = cloud_label,
            component_names = component_names,
            pattern         = self._infer_pattern(components, connections),
        ), max_tokens=2500)

        guidance = self._call(GUIDANCE_PROMPT.format(
            cloud              = cloud_label,
            service_names      = service_names,
            deployment_phases  = self._infer_phases(components),
        ), max_tokens=1800)

        terraform_prompts = self._call(TERRAFORM_PROMPTS_PROMPT.format(
            cloud              = cloud_label,
            component_count    = len(components),
            components_text    = components_text,
            connection_count   = len(connections),
            connections_text   = connections_text,
        ), max_tokens=3500)

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
        """Single Bedrock call. Returns text or empty string on failure."""
        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens":        max_tokens,
            "temperature":       0.2,
            "system":            SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": prompt}],
        })

        for attempt in range(2):
            try:
                resp = self.bedrock_client.invoke_model(
                    modelId     = self.bedrock_model,
                    contentType = "application/json",
                    accept      = "application/json",
                    body        = body,
                )
                body_parsed = json.loads(resp["body"].read())
                text        = body_parsed["content"][0]["text"]
                usage       = body_parsed.get("usage", {})
                logger.info(
                    f"[DesignDoc] call ok — "
                    f"in={usage.get('input_tokens','?')} "
                    f"out={usage.get('output_tokens','?')}"
                )
                return text

            except Exception as e:
                if "ThrottlingException" in str(e) and attempt == 0:
                    logger.warning("[DesignDoc] Throttled — retrying in 4s")
                    time.sleep(4)
                else:
                    logger.error(f"[DesignDoc] Bedrock call failed: {e}")
                    return ""

        return ""

    def _call_streaming(self, prompt: str, max_tokens: int = 2048):
        """
        Streaming Bedrock call — yields text chunks as they arrive.
        Used for ChatGPT-like real-time rendering.
        """
        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens":        max_tokens,
            "temperature":       0.2,
            "system":            SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": prompt}],
        })

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
                        yield text
        except Exception as e:
            logger.error(f"[DesignDoc] Streaming Bedrock call failed: {e}")
            yield ""

    def _parse_json(self, text: str) -> dict:
        """Parse JSON from text, stripping markdown fences if present."""
        try:
            clean = text.strip()
            if clean.startswith("```"):
                clean = clean.split("```", 2)[1]
                if clean.lower().startswith("json"):
                    clean = clean[4:]
            return json.loads(clean.strip())
        except Exception as e:
            logger.error(f"[DesignDoc] JSON parse failed: {e}")
            return {}

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
        components  = vision_analysis.get("analysis", {}).get("components", [])
        connections = vision_analysis.get("analysis", {}).get("connections", [])
        cloud_label = "AWS" if cloud.lower() == "aws" else "Azure"

        components_text  = self._fmt_components(components)
        connections_text = self._fmt_connections(connections)
        component_names  = ", ".join(c.get("name", "?") for c in components[:20])
        service_names    = ", ".join(
            c.get("name", "?") for c in components
            if c.get("type", "") not in ("Actor", "External")
        )[:300]

        SECTION_TITLES = {
            "snapshot":           "Architecture Snapshot",
            "flows":              "Data & Traffic Flows",
            "audit":              "Security & Compliance Audit",
            "guidance":           "Operational Guidance",
            "terraform_prompts": "Terraform Generation Prompts",
        }

        calls = [
            ("snapshot", SNAPSHOT_PROMPT.format(
                cloud=cloud_label,
                component_count=len(components),
                components_text=components_text,
                connection_count=len(connections),
                connections_text=connections_text,
            ), 1800),
            ("flows", FLOW_PROMPT.format(
                cloud=cloud_label,
                component_names=component_names,
                connections_text=connections_text,
                cross_account=self._detect_cross_account(connections),
            ), 2000),
            ("audit", AUDIT_PROMPT.format(
                cloud=cloud_label,
                component_names=component_names,
                pattern=self._infer_pattern(components, connections),
            ), 2500),
            ("guidance", GUIDANCE_PROMPT.format(
                cloud=cloud_label,
                service_names=service_names,
                deployment_phases=self._infer_phases(components),
            ), 1800),
            ("terraform_prompts", TERRAFORM_PROMPTS_PROMPT.format(
                cloud=cloud_label,
                component_count=len(components),
                components_text=components_text,
                connection_count=len(connections),
                connections_text=connections_text,
            ), 3500),
        ]

        for section_name, prompt, max_tokens in calls:
            title = SECTION_TITLES.get(section_name, section_name)
            yield f"data: {json.dumps({'type': 'section_start', 'section': section_name, 'title': title})}\n\n"

            try:
                for text_chunk in self._call_streaming(prompt, max_tokens=max_tokens):
                    if text_chunk:
                        yield f"data: {json.dumps({'type': 'delta', 'text': text_chunk})}\n\n"
            except Exception as e:
                logger.error(f"[DesignDoc] Stream error in {section_name}: {e}")
                # Fallback to non-streaming call
                raw = self._call(prompt, max_tokens=max_tokens)
                if raw:
                    yield f"data: {json.dumps({'type': 'delta', 'text': raw})}\n\n"

            yield f"data: {json.dumps({'type': 'section_end', 'section': section_name})}\n\n"

        yield "data: [DONE]\n\n"

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