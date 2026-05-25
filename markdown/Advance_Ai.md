# InfraSketch — Advanced AI/LLM Production Concepts

> Living document tracking AI/LLM production concepts applied and planned for the InfraSketch architecture generation platform.
> **Last updated:** May 2026  
> **Status legend:** ✅ Implemented | 🔄 Partial / In Progress | ❌ Not Implemented | 📝 Planned

---

## 1. Gateway & Infrastructure Layer

| # | Concept | Status | Implementation Notes |
|---|---|---|---|
| 1.1 | **API Gateway** | ❌ | FastAPI routes directly. No abstraction layer for auth, routing, or throttling. |
| 1.2 | **Request Routing** | ❌ | Single monolithic backend; no path-based or model-based routing. |
| 1.3 | **Model Gateway** | 🔄 | Bedrock is the primary model provider. `bedrock_service.py` wraps `invoke_model`, but no provider-switching logic (OpenAI, Azure, local). File: `backend/app/services/bedrock_service.py` |
| 1.4 | **Prompt Service** | ✅ | Dedicated `prompt_analyzer.py` extracts structured requirements from free-text user prompts. File: `backend/app/agents/nodes/prompt_analyzer.py` |
| 1.5 | **Inference Service** | ✅ | Synchronous Bedrock calls via `invoke()` and streaming via `invoke_model_with_response_stream`. File: `backend/app/services/bedrock_service.py`, `backend/app/services/design_doc_service.py` |
| 1.6 | **Retrieval Service** | 🔄 | RAG config exists (`CHROMA_PERSIST_DIR`, `EMBEDDING_MODEL`) but not actively wired into the generation pipeline. File: `backend/app/core/config.py` |
| 1.7 | **Ranking Service** | ❌ | No result ranking or re-ranking of generated prompts. |
| 1.8 | **Feature Store** | ❌ | No centralized feature store for prompt embeddings or user preferences. |
| 1.9 | **Offline Pipelines** | ❌ | No batch processing for large document corpora or scheduled retraining. |
| 1.10 | **Online Serving** | ✅ | Real-time streaming design doc generation + synchronous chat. Files: `backend/app/api/v1/jobs.py` SSE endpoint, `backend/app/services/terraform_chat.py` |
| 1.11 | **Async Processing** | ✅ | BackgroundTasks for architecture diagram pipeline. File: `backend/app/api/v1/jobs.py` `_run_architecture_diagram_job()` |
| 1.12 | **Queueing** | ❌ | Background tasks use in-memory FastAPI `BackgroundTasks`. No Redis/SQS/RabbitMQ for durable queues. |
| 1.13 | **Streaming Responses** | ✅ | SSE streaming for design doc sections. Client receives live chunks. File: `backend/app/api/v1/jobs.py` `streamDesignDocSections` |
| 1.14 | **Rate Limiting** | ❌ | No request throttling on any endpoint. Vulnerable to abuse. |
| 1.15 | **Fan-out / Fan-in** | ✅ | LangGraph multi-agent pipeline: Vision → Prompt Analysis → Context Fusion → Haiku Compression → Design Doc → Terraform Prompts. File: `backend/app/agents/` |
| 1.16 | **Batch Inference** | ❌ | All inference is per-request. No batching of multiple diagrams or documents. |
| 1.17 | **Real-time Inference** | ✅ | Synchronous Bedrock calls for chat and per-section design doc generation. |
| 1.18 | **Human-in-the-loop** | ❌ | No review/approval workflow before Terraform code is generated. |
| 1.19 | **Fallback Workflows** | ✅ | Multiple fallback layers: LLM→keyword extraction, JSON→numbered list, rich fallback prompts by cloud provider. Files: `backend/app/services/architecture_extractor.py`, `backend/app/agents/nodes/terraform_prompt_agent.py` |

---

## 2. Cost & Performance

| # | Concept | Status | Implementation Notes |
|---|---|---|---|
| 2.1 | **Token Budgeting** | 🔄 | `max_tokens` set per LLM call (2500–4000 per section), but no global or per-user token budget tracking. File: `backend/app/services/design_doc_service.py` |
| 2.2 | **Prompt Compression** | ✅ | Haiku compresses template + vision + user prompt into `master_context`. Reduces token count for downstream Claude calls. Files: `backend/app/services/haiku_service.py`, `backend/app/agents/nodes/haiku_compression.py` |
| 2.3 | **Prompt Caching** | ❌ | Every request hits Bedrock fresh. No cache for identical or similar prompts. |
| 2.4 | **Semantic Caching** | ❌ | No embedding-based deduplication of similar user prompts or diagram analyses. |
| 2.5 | **Response Caching** | ❌ | No caching of design doc sections or Terraform prompts across users/sessions. |
| 2.6 | **Batch Requests** | ❌ | No batching of multiple diagram analyses or design doc sections into single LLM calls. |
| 2.7 | **Model Quantization** | ❌ | Uses full-precision Claude models via Bedrock. No quantized local models. |
| 2.8 | **Distillation** | ❌ | No teacher-student distillation; Haiku is used for compression, not distillation of Claude outputs. |
| 2.9 | **Latency Budgets** | ❌ | No SLOs or deadline propagation across the pipeline. Slow Bedrock calls block everything. |
| 2.10 | **Cold Starts** | 🔄 | FastAPI + LangGraph state is in-memory; server restart clears all jobs. No warm pool of model connections. |
| 2.11 | **GPU Utilization** | ❌ | Not applicable (cloud API usage), but no tracking of inference cost per GPU-hour equivalent. |
| 2.12 | **Throughput** | ❌ | No throughput metrics or capacity planning for concurrent requests. |
| 2.13 | **Cost per Query** | ❌ | No tracking of input/output tokens or estimated AWS Bedrock cost per request. |
| 2.14 | **Cost per User** | ❌ | No user-level cost attribution or billing integration. |
| 2.15 | **Model Selection** | ✅ | Different models for different tasks: Gemini for vision, Haiku for compression, Claude Sonnet for generation. File: `backend/app/core/config.py` |
| 2.16 | **Inference Scaling** | ❌ | Single-threaded per job; no horizontal scaling of inference workers. |
| 2.17 | **Backpressure** | ❌ | No mechanism to shed load or queue requests when Bedrock is throttled. |
| 2.18 | **Load Shedding** | ❌ | No graceful degradation under high load; all requests are processed equally. |

---

## 3. Evaluation & Quality

| # | Concept | Status | Implementation Notes |
|---|---|---|---|
| 3.1 | **Offline Evals** | ❌ | No golden dataset or automated evaluation of design doc quality. |
| 3.2 | **Online Evals** | ❌ | No real-time quality scoring of generated outputs. |
| 3.3 | **Golden Dataset** | ❌ | No curated set of expected outputs for regression testing. |
| 3.4 | **Human Review** | 🔄 | Users can review Terraform prompts before generating code, but no structured review workflow. |
| 3.5 | **LLM-as-Judge** | ❌ | No automated quality scoring of generated design docs or Terraform prompts. |
| 3.6 | **A/B Testing** | ❌ | No framework for testing prompt variations or model versions against each other. |
| 3.7 | **Regression Testing** | ❌ | No tests to verify prompt quality doesn't degrade after code changes. |
| 3.8 | **Answer Relevance** | ❌ | No metric to measure if generated Terraform matches the user's architecture. |
| 3.9 | **Factual Accuracy** | 🔄 | Confidence scores from vision analysis, but no verification of generated claims (CIDRs, ARNs, etc.). |
| 3.10 | **Faithfulness** | ❌ | No check that generated Terraform only uses services detected in the diagram. |
| 3.11 | **Groundedness** | 🔄 | Dynamic context injection ensures prompts reference actual detected components, but no automatic verification. File: `backend/app/services/design_doc_service.py` `_build_dynamic_context()` |
| 3.12 | **Toxicity Checks** | ❌ | No input/output content filtering beyond AWS Bedrock's built-in safeguards. |
| 3.13 | **Safety Checks** | 🔄 | CIS hardening enforced in system prompts; no automated safety verification. File: `backend/app/services/terraform_chat.py` |
| 3.14 | **Drift Detection** | ❌ | No monitoring if LLM output quality or style degrades over time. |
| 3.15 | **Feedback Loops** | ❌ | No way for users to rate prompt quality or flag incorrect outputs. |
| 3.16 | **Confidence Scoring** | ✅ | Vision analysis returns confidence per component. File: `backend/app/services/vision_service.py` |
| 3.17 | **Escalation Criteria** | ❌ | No automatic escalation of low-confidence detections to human review. |
| 3.18 | **Quality Monitoring** | 🔄 | Extensive logging, but no dashboards or alerts for quality metrics. |

---

## 4. Reliability & Security

| # | Concept | Status | Implementation Notes |
|---|---|---|---|
| 4.1 | **Timeouts** | ❌ | No HTTP or Bedrock call timeouts set. A stuck Bedrock call blocks the worker indefinitely. |
| 4.2 | **Retries** | ✅ | Bedrock `invoke()` has 2-attempt retry with 4s backoff on `ThrottlingException`. File: `backend/app/services/bedrock_service.py:304-330` |
| 4.3 | **Circuit Breakers** | ❌ | No failure isolation; one Bedrock outage crashes all generation endpoints. |
| 4.4 | **Failover** | ❌ | Single AWS region; no cross-region or cross-provider fallback. |
| 4.5 | **Model Fallbacks** | ❌ | If Claude Sonnet fails, no automatic fallback to Haiku or Gemini. |
| 4.6 | **Graceful Degradation** | ✅ | Multiple fallback layers: Docling→pdfplumber/docx, LLM→keyword, JSON→numbered list. Files: `backend/app/services/architecture_extractor.py`, `backend/app/api/v1/jobs.py` |
| 4.7 | **Observability** | ✅ | Extensive structured logging with pipeline stage tracking across all nodes. Files: All `backend/app/agents/nodes/*.py` |
| 4.8 | **Tracing** | 🔄 | Job IDs propagate through the pipeline, but no distributed trace IDs (OpenTelemetry/Jaeger). |
| 4.9 | **Prompt Logs** | ✅ | Raw LLM responses stored in state (`raw_response`, `design_docs_json`). File: `backend/app/api/v1/jobs.py` |
| 4.10 | **Token Metrics** | ❌ | No tracking of input/output tokens per request or cumulative usage. |
| 4.11 | **Error Budgets** | ❌ | No defined acceptable error rate or SLO for generation quality. |
| 4.12 | **PII Redaction** | ❌ | User prompts and uploaded files are processed raw; no PII scanning or redaction. |
| 4.13 | **Data Privacy** | 🔄 | In-memory job storage (no persistence), but no encryption at rest or formal data handling policy. |
| 4.14 | **Access Control** | 🔄 | `company_id` for multi-tenant template scoping, but no RBAC or OAuth. File: `backend/app/agents/state.py` |
| 4.15 | **Prompt Injection** | ❌ | No input sanitization or adversarial prompt detection. |
| 4.16 | **Jailbreak Defense** | ❌ | No defense against users trying to extract system prompts or bypass restrictions. |
| 4.17 | **Audit Logs** | 🔄 | Pipeline logs contain job IDs and stages, but no immutable audit trail of who generated what. |
| 4.18 | **Compliance** | 🔄 | Compliance frameworks extracted from templates and enforced in prompts, but no automated compliance verification. File: `backend/app/services/haiku_service.py` |

---

## 5. Prompt Engineering & Context Management

| # | Concept | Status | Implementation Notes |
|---|---|---|---|
| 5.1 | **Dynamic Context Injection** | ✅ | `_build_dynamic_context()` injects governance, security, naming, and architecture intelligence into every LLM prompt. File: `backend/app/services/design_doc_service.py` |
| 5.2 | **Chain-of-Thought** | ✅ | SYSTEM_PROMPT mandates reasoning for every architectural decision. File: `backend/app/services/design_doc_service.py` |
| 5.3 | **Structured Output (JSON Mode)** | ✅ | Terraform prompts returned as JSON arrays with schema validation. File: `backend/app/agents/nodes/terraform_prompt_agent.py` |
| 5.4 | **Prompt Versioning** | ❌ | Prompts are hardcoded strings; no version tracking or A/B framework. |
| 5.5 | **System Prompt Hardening** | ✅ | Strict format rules, quality bars ($500/hr), mandatory compliance cross-referencing. File: `backend/app/services/design_doc_service.py` |
| 5.6 | **Few-Shot Examples** | 🔄 | BEFORE/AFTER HCL examples in GUIDANCE_PROMPT, but no dedicated few-shot example bank. |
| 5.7 | **Prompt Chaining** | ✅ | 5 sequential focused calls (snapshot → flows → audit → guidance → terraform) instead of one giant prompt. File: `backend/app/services/design_doc_service.py` |
| 5.8 | **Context Window Management** | ✅ | Haiku compression reduces token load; sections are generated independently to stay within context limits. |

---

## Implementation Roadmap

### Phase 1 — Reliability & Observability (Next)
- [ ] Add timeouts to all Bedrock calls (`boto3` `read_timeout`, `connect_timeout`)
- [ ] Add circuit breaker around Bedrock (e.g., `pybreaker`)
- [ ] Add token metrics: input/output tokens per call, stored in job metadata
- [ ] Add cost estimation: $ per request based on token count
- [ ] Add distributed tracing (OpenTelemetry + Jaeger/Zipkin)

### Phase 2 — Caching & Performance
- [ ] Add Redis for semantic caching of similar prompts
- [ ] Add response caching for identical diagram + template combinations
- [ ] Add queueing layer (Redis/RabbitMQ) for background jobs
- [ ] Add rate limiting per IP / per user

### Phase 3 — Quality & Evaluation
- [ ] Build golden dataset of 50 architecture diagrams with expected outputs
- [ ] Add LLM-as-Judge scoring for design doc completeness
- [ ] Add user feedback endpoint (thumbs up/down per prompt)
- [ ] Add regression test suite that runs golden dataset on every PR

### Phase 4 — Security & Compliance
- [ ] Add PII redaction before sending prompts to Bedrock
- [ ] Add prompt injection detection layer
- [ ] Add immutable audit log (append-only, signed)
- [ ] Add RBAC with JWT/OAuth integration

---

## File Reference Map

| Concept Area | Primary Files |
|---|---|
| Vision / Diagram Analysis | `backend/app/services/vision_service.py`, `backend/app/agents/nodes/image_analyzer.py` |
| Prompt Analysis | `backend/app/agents/nodes/prompt_analyzer.py` |
| Context Fusion | `backend/app/agents/nodes/context_fusion.py` |
| Context Compression | `backend/app/services/haiku_service.py`, `backend/app/agents/nodes/haiku_compression.py` |
| Design Doc Generation | `backend/app/services/design_doc_service.py` |
| Terraform Prompts | `backend/app/agents/nodes/terraform_prompt_agent.py` |
| Terraform Chat | `backend/app/services/terraform_chat.py` |
| Architecture Extraction | `backend/app/services/architecture_extractor.py` |
| Draw.io Conversion | `backend/app/services/drawio_converter.py` |
| API / Job Orchestration | `backend/app/api/v1/jobs.py` |
| Bedrock Client | `backend/app/services/bedrock_service.py` |
| Config / Settings | `backend/app/core/config.py` |
| Pipeline State | `backend/app/agents/state.py` |
| Canonical Graph Model | `backend/app/models/infra_graph.py` |
| Frontend Store | `frontend/src/store/workflowStore.ts` |
| Frontend Design Doc | `frontend/src/pages/DesignDocPage.tsx` |
| Frontend Terraform Chat | `frontend/src/pages/TerraformChatPage.tsx` |
