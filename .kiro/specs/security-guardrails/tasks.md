# Implementation Plan: Security Guardrails

## Overview

This plan implements a comprehensive security and guardrail layer for the Terraform Generator's FastAPI backend. The system integrates transparently into the existing `LLMGateway.call()` method as a multi-layered defense pipeline. Implementation proceeds bottom-up: foundational models and configuration first, then individual security components, then the orchestrator that wires them together, and finally integration with existing endpoints.

All new code lives under `backend/app/security/` with integration points in `backend/app/core/llm_gateway.py`, `backend/app/core/config.py`, and `backend/app/main.py`.

## Tasks

- [ ] 1. Set up security module structure and configuration
  - [ ] 1.1 Create security module directory and base configuration models
    - Create `backend/app/security/__init__.py` with module docstring
    - Create `backend/app/security/config.py` with `SecurityConfig` Pydantic model containing all feature flags (`ENABLE_TERRAFORM_GUARD`, `ENABLE_PROMPT_GUARD`, `ENABLE_PII_REDACTION`, `ENABLE_RATE_LIMITING`, `ENABLE_CONFIDENCE_GATE`, `ENABLE_RESOURCE_QUOTAS`, `ENABLE_AUDIT_LOGGING`) and thresholds
    - Add security environment variables to `backend/app/core/config.py` Settings class (prefix with `SECURITY_`)
    - Create `backend/app/security/models.py` with shared data models: `ThreatLevel` enum, `SanitizationResult`, `MaskRule`, `MaskRegistry`, `MaskingResult`, `GuardrailPolicy`, `GuardrailResult`, `ScopePolicy`, `ScopeResult`, `TrustLevel`, `TrustResult`, `SecurityContext`, `SecuredPayload`, `SecurityAuditEntry`
    - _Requirements: 13.1, 13.2, 13.3, 13.4_

  - [ ] 1.2 Create threat detection pattern definitions
    - Create `backend/app/security/patterns.py` with pre-compiled `INJECTION_PATTERNS` list (role_override, delimiter_escape, data_exfiltration, encoding_attack, jailbreak_roleplay)
    - Define `MASK_RULES` list with regex patterns for AWS Account IDs, ARNs, emails, private IPs, passwords, phone numbers, credit cards, and AWS access keys
    - Define `JAILBREAK_PATTERNS` list with DAN variants, role-play exploits, developer mode, system prompt extraction patterns
    - Define `TERRAFORM_VIOLATION_PATTERNS` dict mapping severity levels (CRITICAL, HIGH, MEDIUM) to their detection regexes
    - _Requirements: 1.5, 2.1-2.8, 4.1-4.3, 9.3_

  - [ ] 1.3 Create scope permission matrix and policy definitions
    - Create `backend/app/security/policies.py` with `SCOPE_POLICIES` dict mapping task types (`template_compression`, `terraform_chat`, `design_doc_section`, `rag_synthesis`) to their `ScopePolicy` objects
    - Define `Permission` enum with all permission types (READ_TEMPLATES, READ_DIAGRAMS, READ_RAG_DOCS, WRITE_TERRAFORM, WRITE_DESIGN_DOC, ACCESS_COMPANY_DATA, ACCESS_SECRETS)
    - Ensure no task type ever has `ACCESS_SECRETS` in its allowed permissions
    - _Requirements: 10.1, 10.3_

- [ ] 2. Implement Input Sanitizer component
  - [ ] 2.1 Implement the InputSanitizer class with injection scoring
    - Create `backend/app/security/input_sanitizer.py`
    - Implement `sanitize()` method that processes a list of messages and returns `SanitizationResult`
    - Implement `detect_injection()` that scores text 0-100 based on pattern matches and their severity weights
    - Implement `neutralize_control_sequences()` to strip zero-width characters and Unicode control sequences
    - Implement Unicode NFKC normalization as the first processing step
    - Implement `calculate_shannon_entropy()` helper for detecting encoded payloads
    - Score logic: >70 → reject, 30-70 → strip patterns and allow, <30 → pass through unchanged
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7_

  - [ ]* 2.2 Write property test for injection score bounds
    - **Property 3: Injection Score Bounds**
    - Use `hypothesis.strategies.text()` to generate arbitrary strings
    - Assert that `detect_injection()` always returns a score between 0 and 100 inclusive
    - **Validates: Requirements 1.1**

  - [ ]* 2.3 Write property test for low-score text passthrough
    - **Property 5: Low-Score Text Passthrough**
    - Generate benign infrastructure-related text strings (no injection patterns)
    - Assert that text with score <30 passes through without modification (after NFKC normalization)
    - **Validates: Requirements 1.4**

  - [ ]* 2.4 Write property test for idempotent sanitization
    - **Property 6: Idempotent Sanitization**
    - Generate arbitrary message lists using hypothesis
    - Assert that `sanitize(sanitize(M)).sanitized_messages == sanitize(M).sanitized_messages`
    - **Validates: Requirements 1.3, 1.6**

  - [ ]* 2.5 Write property test for Unicode normalization
    - **Property 7: Unicode Normalization and Zero-Width Removal**
    - Generate text containing non-NFKC Unicode and zero-width characters (U+200B, U+200C, U+200D, U+FEFF)
    - Assert output is NFKC-normalized and contains no zero-width characters
    - **Validates: Requirements 1.6**

  - [ ]* 2.6 Write property test for injection pattern detection completeness
    - **Property 8: Injection Pattern Detection Completeness**
    - Generate text that embeds known injection patterns (role override, delimiter escape, etc.)
    - Assert that the sanitizer detects them and produces a non-zero injection score
    - **Validates: Requirements 1.5, 9.3**

- [ ] 3. Implement Data Masker component
  - [ ] 3.1 Implement the DataMasker class with regex-based masking
    - Create `backend/app/security/data_masker.py`
    - Implement `mask_messages()` that applies all `MASK_RULES` patterns to message content
    - Implement `detect_secrets()` using regex patterns + Shannon entropy analysis (threshold 4.5)
    - Implement `MaskRegistry` class with `add()` and `unmask()` methods for reversible token mapping
    - Implement `unmask_response()` that restores masked tokens in LLM responses
    - Ensure same sensitive value appearing multiple times gets the same mask token
    - Ensure MaskRegistry is never persisted to disk, database, or logs
    - _Requirements: 2.1-2.12, 14.1-14.4_

  - [ ]* 3.2 Write property test for no sensitive data leakage
    - **Property 1: No Sensitive Data Leakage**
    - Generate text containing synthetic AWS Account IDs, ARNs, emails, private IPs, passwords, phone numbers, credit cards, and AWS access keys using hypothesis strategies
    - Assert that after masking, none of the original sensitive patterns remain in the output
    - **Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8**

  - [ ]* 3.3 Write property test for mask roundtrip reversibility
    - **Property 2: Mask Roundtrip Reversibility**
    - Generate arbitrary text containing sensitive data patterns
    - Assert that `unmask(mask(text), registry) == original_text`
    - **Validates: Requirements 2.9, 2.10, 14.1**

  - [ ]* 3.4 Write property test for consistent mask tokens
    - **Property 20: Consistent Mask Tokens for Repeated Values**
    - Generate text where the same sensitive value (e.g., same email) appears multiple times
    - Assert that all occurrences are replaced with the same mask token
    - **Validates: Requirements 14.4**

- [ ] 4. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 5. Implement Guardrail Engine component
  - [ ] 5.1 Implement the GuardrailEngine class with jailbreak detection
    - Create `backend/app/security/guardrail_engine.py`
    - Implement `check()` method that evaluates messages against all active guardrail policies
    - Implement `check_jailbreak()` with multi-signal detection: pattern matching, imperative density analysis, role assumption detection, and topic divergence scoring
    - Implement `validate_task_alignment()` to ensure requests match declared task_type scope (infrastructure/Terraform/cloud topics only)
    - Confidence aggregation: weighted combination of signals, block when >= 0.7
    - Return generic safe message on block: "I can only help with infrastructure and Terraform-related questions."
    - _Requirements: 9.1, 9.2, 9.3, 9.4_

  - [ ]* 5.2 Write property test for jailbreak blocking threshold
    - **Property 21: Jailbreak Blocking Threshold**
    - Generate text containing known jailbreak patterns that should produce confidence >= 0.7
    - Assert that the engine blocks the request and returns a generic safe message
    - **Validates: Requirements 9.1**

- [ ] 6. Implement Scope Validator component
  - [ ] 6.1 Implement the ScopeValidator class with permission enforcement
    - Create `backend/app/security/scope_validator.py`
    - Implement `validate()` method that checks task_type against `SCOPE_POLICIES`
    - Implement `filter_context()` that silently removes data outside the task's allowed categories
    - Enforce maximum context size limits per task type (truncate if exceeded)
    - Return "insufficient context" error only when ALL context is removed
    - Never allow any task type to access "secrets" or "credentials" categories
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_

  - [ ]* 6.2 Write property test for scope isolation
    - **Property 9: Scope Isolation**
    - Generate task types and data categories, including "secrets" and "credentials"
    - Assert that data with disallowed categories is always removed from context
    - Assert that no task type ever passes through "secrets" or "credentials" data
    - **Validates: Requirements 10.1, 10.2, 10.3**

- [ ] 7. Implement Trust Validator component
  - [ ] 7.1 Implement the TrustValidator class with RAG retrieval validation
    - Create `backend/app/security/trust_validator.py`
    - Implement `validate_retrieval()` that checks each chunk against: collection trust list, document hash integrity, injection pattern detection, and relevance scoring
    - Implement `check_chunk_injection()` that reuses InputSanitizer patterns on chunk text
    - Implement `verify_document_integrity()` for hash comparison
    - Return empty results with message when all chunks fail validation
    - Raise alert for admin review when injection detected in stored chunks
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5_

  - [ ]* 7.2 Write property test for trust filtering correctness
    - **Property 10: Trust Filtering Correctness**
    - Generate mock retrieved chunks with varying trust levels, collections, and injection content
    - Assert that only chunks satisfying ALL trust criteria appear in trusted_chunks
    - **Validates: Requirements 11.1, 11.2, 11.3**

- [ ] 8. Implement Terraform Output Security Scanner
  - [ ] 8.1 Implement the TerraformScanner class with severity classification
    - Create `backend/app/security/terraform_scanner.py`
    - Implement `scan_hcl()` that checks generated HCL against `TERRAFORM_VIOLATION_PATTERNS`
    - Classify violations: CRITICAL (hardcoded secrets, wildcard IAM `"*"`, missing encryption), HIGH (open CIDR `0.0.0.0/0`, public S3 ACL, unencrypted storage), MEDIUM (default VPC, missing tags)
    - Implement `auto_fix_critical()` that applies automatic fixes for CRITICAL violations (e.g., replace hardcoded secrets with variable references, replace wildcard IAM with least-privilege placeholder)
    - Store scan results (violation count, severity breakdown, auto-fix actions) in job dictionary
    - Include violation details in API response when violations exist
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

  - [ ]* 8.2 Write property test for Terraform severity classification
    - **Property 14: Terraform Severity Classification**
    - Generate HCL snippets containing hardcoded secrets, wildcard IAM, open CIDRs, public S3, default VPC, missing tags
    - Assert correct severity classification for each violation type
    - **Validates: Requirements 4.1, 4.2, 4.3**

  - [ ]* 8.3 Write property test for critical violation auto-fix
    - **Property 15: Critical Violation Auto-Fix**
    - Generate HCL with CRITICAL violations
    - Assert that after auto-fix, the same CRITICAL violation pattern is no longer present
    - **Validates: Requirements 4.4**

- [ ] 9. Implement Vulnerability Scanner for HCL
  - [ ] 9.1 Implement the VulnerabilityScanner class for generated code
    - Create `backend/app/security/vulnerability_scanner.py`
    - Implement `scan_hcl_vulnerabilities()` that detects: deprecated provider arguments, TLS versions below 1.2, missing encryption in transit, publicly exposed database endpoints
    - Return structured results with violation type, location, and remediation suggestion
    - _Requirements: 8.2, 8.3, 8.4, 8.5_

  - [ ]* 9.2 Write property test for HCL vulnerability detection
    - **Property 22: HCL Vulnerability Detection**
    - Generate HCL containing deprecated arguments, TLS <1.2, missing encryption in transit, public DB endpoints
    - Assert that each vulnerability type is detected and reported
    - **Validates: Requirements 8.2, 8.3, 8.4, 8.5**

- [ ] 10. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 11. Implement Rate Limiter and Abuse Prevention
  - [ ] 11.1 Implement the RateLimiter class with per-IP and per-user limits
    - Create `backend/app/security/rate_limiter.py`
    - Implement per-IP rate limits: 10/min for job creation, 20/min for chat, 5/min for RAG, 30/min for templates
    - Implement per-user limit: 50 LLM calls/hour per authenticated user
    - Implement per-user daily spend cap: $10/day per authenticated user
    - Return HTTP 429 with `Retry-After` header (seconds until reset) when limits exceeded
    - Implement violation-based cooldown: 3 violations → 15-min cooldown, 10 violations → 1-hour block
    - Use in-memory storage (dict with TTL) for rate tracking; consider `slowapi` library for FastAPI integration
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9_

  - [ ]* 11.2 Write property test for rate limit response format
    - **Property 18: Rate Limit Response Format**
    - Simulate requests exceeding rate limits
    - Assert HTTP 429 response with `Retry-After` header containing a positive integer
    - **Validates: Requirements 3.7**

- [ ] 12. Implement Confidence Gate for Human Review
  - [ ] 12.1 Implement the ConfidenceGate class with hard/soft stop logic
    - Create `backend/app/security/confidence_gate.py`
    - Implement `evaluate_confidence()` that checks vision analysis component confidence scores
    - Hard stop: any single component confidence < 0.40 → set job status to "needs_review"
    - Soft stop: more than 3 components with confidence < 0.65 → set job status to "needs_review"
    - Record triggering components and their confidence scores in the job dictionary
    - Block further pipeline processing while job has "needs_review" status until admin approves/rejects
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

  - [ ]* 12.2 Write property test for confidence gate triggering
    - **Property 16: Confidence Gate Triggering**
    - Generate sets of component confidence scores with values below thresholds
    - Assert that hard stop triggers when any component < 0.40
    - Assert that soft stop triggers when >3 components < 0.65
    - **Validates: Requirements 5.1, 5.2, 5.3**

- [ ] 13. Implement Resource Quota Validator
  - [ ] 13.1 Implement the ResourceQuotaValidator class with blast radius limits
    - Create `backend/app/security/resource_quota.py`
    - Implement `validate_resources()` that checks: max 50 EC2 instances, max 1000 GB storage, max 100 total resources, max $5000/month estimated cost
    - Return error specifying which limit was exceeded when quota is violated
    - Implement `suggest_reduced_scope()` that proposes a scaled-down version fitting within limits
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

  - [ ]* 13.2 Write property test for resource quota enforcement
    - **Property 17: Resource Quota Enforcement**
    - Generate resource specifications exceeding each limit type
    - Assert rejection with correct identification of which limit was exceeded
    - **Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5**

- [ ] 14. Implement Audit Logger
  - [ ] 14.1 Implement the AuditLogger class with SQLite storage
    - Create `backend/app/security/audit_logger.py`
    - Create SQLite database at `backend/storage/audit/security_audit.db`
    - Implement `log_llm_call()` that records: timestamp, job_id, input_tokens, output_tokens, estimated_cost, model_id, cache_hit status
    - Implement `log_security_event()` for injection detections, jailbreak attempts, scope violations
    - Implement `cleanup_old_records()` that deletes records older than 90 days
    - Implement `query_audit_log()` with filters: date range, job_id, model
    - Ensure audit logs never contain actual sensitive data (only masked references)
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6_

  - [ ] 14.2 Create admin API endpoint for audit log queries
    - Add `GET /api/v1/admin/audit-logs` endpoint to `backend/app/api/v1/admin.py`
    - Accept query parameters: `start_date`, `end_date`, `job_id`, `model`, `event_type`
    - Require admin authentication (existing `require_api_key` dependency)
    - Return paginated results with total count
    - _Requirements: 7.5_

  - [ ]* 14.3 Write property test for audit completeness
    - **Property 11: Audit Completeness**
    - Simulate calls to `process_outbound()` with various outcomes (allowed, blocked, errored)
    - Assert that exactly one audit entry is created per call regardless of outcome
    - **Validates: Requirements 7.1, 12.3**

- [ ] 15. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 16. Implement Security Pipeline Orchestrator
  - [ ] 16.1 Implement the SecurityPipeline class that wires all components together
    - Create `backend/app/security/pipeline.py`
    - Implement `process_outbound()` that runs the full sequence: Input Sanitizer → Guardrail Engine → Data Masker → Scope Validator → Trust Validator
    - Implement `process_inbound()` that unmasks LLM responses using the MaskRegistry
    - Implement fail-closed behavior: if ANY component raises an unexpected exception, block the request entirely
    - Deep-copy original messages before processing (never mutate caller's data)
    - Create exactly one audit entry per call regardless of outcome
    - Implement `get_security_pipeline()` singleton factory that initializes all components
    - Check configuration flags and skip disabled components
    - Log which security features are enabled/disabled on startup
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 13.1, 13.2, 13.3_

  - [ ]* 16.2 Write property test for fail-closed on exception
    - **Property 12: Fail-Closed on Exception**
    - Mock security components to raise unexpected exceptions
    - Assert that the pipeline blocks the request and never sends unprotected data
    - **Validates: Requirements 12.2**

  - [ ]* 16.3 Write property test for original message immutability
    - **Property 13: Original Message Immutability**
    - Generate message lists and pass them through the pipeline
    - Assert that the original list and its contents remain unchanged after processing
    - **Validates: Requirements 12.4**

  - [ ]* 16.4 Write property test for configuration flag bypass
    - **Property 19: Configuration Flag Bypass**
    - Set various feature flags to false
    - Assert that disabled features do not modify the request
    - **Validates: Requirements 13.2**

- [ ] 17. Integrate Security Pipeline with LLM Gateway
  - [ ] 17.1 Modify LLMGateway.call() to invoke the security pipeline
    - Edit `backend/app/core/llm_gateway.py`
    - Import `get_security_pipeline` and `SecurityContext` from `app.security.pipeline`
    - Add security pipeline call BEFORE the cache check in `call()` method
    - Pass `task_type`, caller context, session info to `SecurityContext`
    - Use `secured.messages` and `secured.context` for all downstream operations
    - Store `secured.mask_registry` for response unmasking
    - After receiving LLM response, call `process_inbound()` to unmask before returning
    - Ensure streaming mode also applies masking per-chunk
    - _Requirements: 12.5_

  - [ ] 17.2 Integrate Rate Limiter as FastAPI middleware
    - Edit `backend/app/main.py`
    - Add rate limiting middleware using the RateLimiter class
    - Configure per-endpoint rate limits based on router prefix (jobs=10/min, chat=20/min, rag=5/min, templates=30/min)
    - Wire violation tracking to the security audit logger
    - _Requirements: 3.1, 3.2, 3.3, 3.4_

  - [ ] 17.3 Integrate Confidence Gate into the pipeline graph
    - Edit `backend/app/agents/pipeline_graph.py` (or the relevant pipeline runner)
    - Add confidence gate check after vision analysis node completes
    - Set job status to "needs_review" when gate triggers
    - Halt pipeline execution until admin approval
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

  - [ ] 17.4 Integrate Terraform Scanner into job pipeline
    - Edit `backend/app/api/v1/jobs.py` or the terraform generation service
    - Call `TerraformScanner.scan_hcl()` on all generated Terraform output before returning to user
    - Auto-fix CRITICAL violations before delivery
    - Include scan results and violation details in the job response
    - _Requirements: 4.4, 4.5, 4.6_

  - [ ] 17.5 Integrate Trust Validator with RAG service
    - Edit `backend/app/api/v1/rag.py` or the RAG query service
    - Call `TrustValidator.validate_retrieval()` on all Qdrant results before synthesis
    - Use only trusted chunks for LLM context
    - Log and alert on injection detection in stored chunks
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5_

- [ ] 18. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 19. Add CI integration and pip-audit scanning
  - [ ] 19.1 Add pip-audit to CI pipeline and update dependencies
    - Edit `.github/workflows/ci.yml` to add a `pip-audit` step that fails on critical vulnerabilities
    - Add `pip-audit` and `hypothesis` to dev dependencies in `requirements-dev.txt` (or equivalent)
    - Add `slowapi` to production dependencies for rate limiting
    - _Requirements: 8.1_

  - [ ] 19.2 Add security startup logging and .env.example updates
    - Update `backend/.env.example` with all new `SECURITY_*` environment variables and their defaults
    - Add startup log in `backend/app/main.py` lifespan that reports which security features are enabled
    - _Requirements: 13.3, 13.4_

- [ ] 20. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation after each major component group
- Property tests validate universal correctness properties from the design document using the `hypothesis` library
- Unit tests validate specific examples and edge cases
- All new code goes under `backend/app/security/` — no changes to existing business logic except integration points in tasks 17.x
- The security pipeline is designed to be transparent: existing consumers of `LLMGateway.call()` require zero changes
- Rate limiting uses in-memory storage suitable for single-instance deployment; for multi-instance, swap to Redis later
- The MaskRegistry is request-scoped and garbage-collected after each request — no persistence risk

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.3"] },
    { "id": 2, "tasks": ["2.1", "3.1"] },
    { "id": 3, "tasks": ["2.2", "2.3", "2.4", "2.5", "2.6", "3.2", "3.3", "3.4"] },
    { "id": 4, "tasks": ["5.1", "6.1", "7.1"] },
    { "id": 5, "tasks": ["5.2", "6.2", "7.2"] },
    { "id": 6, "tasks": ["8.1", "9.1", "11.1", "12.1", "13.1"] },
    { "id": 7, "tasks": ["8.2", "8.3", "9.2", "11.2", "12.2", "13.2"] },
    { "id": 8, "tasks": ["14.1"] },
    { "id": 9, "tasks": ["14.2", "14.3"] },
    { "id": 10, "tasks": ["16.1"] },
    { "id": 11, "tasks": ["16.2", "16.3", "16.4"] },
    { "id": 12, "tasks": ["17.1", "17.2", "17.3", "17.4", "17.5"] },
    { "id": 13, "tasks": ["19.1", "19.2"] }
  ]
}
```
