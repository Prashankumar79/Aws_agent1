# Requirements Document

## Introduction

This document defines the requirements for a comprehensive security and guardrail layer for the Terraform Generator application. The system protects against prompt injection, data leakage, abuse, and unsafe infrastructure code generation across a FastAPI backend that uses AWS Bedrock Claude and Google Gemini LLMs. The security layer operates transparently within the existing LLM Gateway, enforcing input sanitization, data masking, rate limiting, output scanning, confidence gating, resource quotas, and audit logging.

## Glossary

- **Security_Pipeline**: The orchestrator component that coordinates all security checks in sequence before any data reaches external LLM providers
- **Input_Sanitizer**: The component responsible for detecting and neutralizing prompt injection attacks in user-provided text
- **Guardrail_Engine**: The component that enforces behavioral boundaries, detects jailbreak attempts, and validates topic alignment
- **Data_Masker**: The component that detects and redacts sensitive data (secrets, PII, credentials) before text reaches LLM APIs, caches, or logs
- **Scope_Validator**: The component that enforces per-task-type permission boundaries on data access
- **Trust_Validator**: The component that validates RAG retrieval results come from verified, untampered sources
- **Terraform_Scanner**: The component that scans generated HCL output for security violations including hardcoded secrets, overly permissive IAM, and missing encryption
- **Rate_Limiter**: The component that enforces per-IP and per-user request rate limits and spend caps
- **Confidence_Gate**: The component that triggers human review when vision analysis confidence scores fall below defined thresholds
- **Resource_Quota_Validator**: The component that enforces hard limits on generated infrastructure resource counts and estimated costs
- **Audit_Logger**: The component that records immutable audit entries for all LLM calls with cost, token, and model metadata
- **Vulnerability_Scanner**: The component that scans Python dependencies and generated HCL for known vulnerabilities and insecure patterns
- **Injection_Score**: A numeric value from 0 to 100 representing the likelihood that a given text contains prompt injection
- **Mask_Registry**: A reversible in-memory mapping of masked tokens to original sensitive values, scoped to a single request lifecycle
- **EARS**: Easy Approach to Requirements Syntax, a structured pattern for writing unambiguous requirements
- **HCL**: HashiCorp Configuration Language, the syntax used for Terraform infrastructure definitions
- **PII**: Personally Identifiable Information including emails, phone numbers, and credit card numbers

## Requirements

### Requirement 1: Prompt Injection Detection and Neutralization

**User Story:** As a system operator, I want all user-provided text to be scanned for prompt injection patterns, so that attackers cannot manipulate LLM behavior through crafted inputs.

#### Acceptance Criteria

1. WHEN user text is submitted to any LLM-facing endpoint, THE Input_Sanitizer SHALL compute an Injection_Score between 0 and 100 for that text
2. WHEN the Injection_Score exceeds 70, THE Input_Sanitizer SHALL reject the request and return an HTTP 400 response with a generic error message
3. WHEN the Injection_Score is between 30 and 70, THE Input_Sanitizer SHALL strip detected injection patterns from the text and allow the sanitized version to proceed
4. WHEN the Injection_Score is below 30, THE Input_Sanitizer SHALL allow the text to proceed without modification
5. WHEN processing user text, THE Input_Sanitizer SHALL detect role override patterns, delimiter escape sequences, data exfiltration attempts, encoding attacks, and jailbreak roleplay patterns
6. WHEN processing user text, THE Input_Sanitizer SHALL normalize Unicode to NFKC form and remove zero-width characters before pattern evaluation
7. WHEN processing extracted document text from uploaded files, THE Input_Sanitizer SHALL apply the same injection scoring and handling as direct user input

### Requirement 2: PII Detection and Redaction

**User Story:** As a security engineer, I want all personally identifiable information and credentials to be redacted before any text reaches LLM APIs, caches, or logs, so that sensitive data is never exposed to external providers.

#### Acceptance Criteria

1. THE Data_Masker SHALL detect and redact AWS Account IDs (12-digit numeric patterns) from all text before it reaches LLM APIs
2. THE Data_Masker SHALL detect and redact AWS ARNs (arn:aws:* patterns) from all text before it reaches LLM APIs
3. THE Data_Masker SHALL detect and redact email addresses from all text before it reaches LLM APIs
4. THE Data_Masker SHALL detect and redact private IP addresses (10.x.x.x, 172.16-31.x.x, 192.168.x.x) from all text before it reaches LLM APIs
5. THE Data_Masker SHALL detect and redact strings matching password patterns (password=, passwd=, secret=) from all text before it reaches LLM APIs
6. THE Data_Masker SHALL detect and redact phone numbers from all text before it reaches LLM APIs
7. THE Data_Masker SHALL detect and redact credit card numbers (Luhn-valid 13-19 digit sequences) from all text before it reaches LLM APIs
8. THE Data_Masker SHALL detect and redact AWS access keys (AKIA-prefixed 20-character strings) from all text before it reaches LLM APIs
9. WHEN sensitive data is redacted, THE Data_Masker SHALL store a reversible mapping in the Mask_Registry for response reconstruction
10. WHEN an LLM response is received, THE Data_Masker SHALL restore masked tokens using the Mask_Registry so that the caller receives correct original values
11. THE Data_Masker SHALL apply redaction before text is written to the semantic cache
12. THE Data_Masker SHALL apply redaction before text is written to application logs

### Requirement 3: Rate Limiting and Abuse Prevention

**User Story:** As a system operator, I want per-IP and per-user rate limits enforced on all API endpoints, so that no single actor can exhaust system resources or incur excessive LLM costs.

#### Acceptance Criteria

1. THE Rate_Limiter SHALL enforce a maximum of 10 requests per minute per IP address on job creation endpoints
2. THE Rate_Limiter SHALL enforce a maximum of 20 requests per minute per IP address on chat endpoints
3. THE Rate_Limiter SHALL enforce a maximum of 5 requests per minute per IP address on RAG query endpoints
4. THE Rate_Limiter SHALL enforce a maximum of 30 requests per minute per IP address on template endpoints
5. THE Rate_Limiter SHALL enforce a maximum of 50 LLM calls per hour per authenticated user
6. THE Rate_Limiter SHALL enforce a maximum daily spend of $10 per authenticated user
7. WHEN a rate limit is exceeded, THE Rate_Limiter SHALL return HTTP 429 with a Retry-After header indicating seconds until the limit resets
8. WHEN a session triggers 3 or more security violations, THE Rate_Limiter SHALL impose a 15-minute cooldown on that session
9. WHEN a session triggers 10 or more security violations, THE Rate_Limiter SHALL impose a 1-hour block on that session

### Requirement 4: Terraform Output Security Scanning

**User Story:** As a cloud architect, I want all generated Terraform HCL to be scanned for security violations before delivery to the user, so that insecure infrastructure is never deployed from generated code.

#### Acceptance Criteria

1. WHEN Terraform HCL is generated, THE Terraform_Scanner SHALL scan for hardcoded secrets, wildcard IAM policies, and missing encryption configurations and classify them as CRITICAL severity
2. WHEN Terraform HCL is generated, THE Terraform_Scanner SHALL scan for open CIDR blocks (0.0.0.0/0), public S3 bucket ACLs, and unencrypted storage resources and classify them as HIGH severity
3. WHEN Terraform HCL is generated, THE Terraform_Scanner SHALL scan for default VPC usage and missing resource tags and classify them as MEDIUM severity
4. WHEN a CRITICAL severity violation is detected, THE Terraform_Scanner SHALL automatically apply a fix to the generated HCL
5. WHEN scanning is complete, THE Terraform_Scanner SHALL store the scan results including violation count, severity breakdown, and auto-fix actions in the job dictionary
6. WHEN scanning is complete and violations exist, THE Terraform_Scanner SHALL include the violation details in the API response to the user

### Requirement 5: Confidence-Based Human Review Gate

**User Story:** As a quality assurance engineer, I want the system to halt and request human review when vision analysis confidence is low, so that unreliable AI outputs do not produce incorrect infrastructure code.

#### Acceptance Criteria

1. WHEN any single component in vision analysis has a confidence score below 0.40, THE Confidence_Gate SHALL trigger a hard stop and set the job status to "needs_review"
2. WHEN more than 3 components in vision analysis have confidence scores below 0.65, THE Confidence_Gate SHALL trigger a soft stop and set the job status to "needs_review"
3. WHEN a job status is set to "needs_review", THE Confidence_Gate SHALL record the specific components and confidence scores that triggered the review
4. WHILE a job has status "needs_review", THE Security_Pipeline SHALL prevent further pipeline processing until an administrator approves or rejects the job

### Requirement 6: Resource Quota and Blast Radius Limits

**User Story:** As a platform operator, I want hard limits on the scale of generated infrastructure, so that a single generation request cannot produce dangerously large or expensive deployments.

#### Acceptance Criteria

1. THE Resource_Quota_Validator SHALL enforce a maximum of 50 EC2 instances per generation request
2. THE Resource_Quota_Validator SHALL enforce a maximum of 1000 GB total storage per generation request
3. THE Resource_Quota_Validator SHALL enforce a maximum of 100 total resources per generation request
4. THE Resource_Quota_Validator SHALL enforce a maximum estimated monthly cost of $5000 per generation request
5. WHEN a resource quota is exceeded, THE Resource_Quota_Validator SHALL reject the generation and return an error specifying which limit was exceeded
6. WHEN a resource quota is exceeded, THE Resource_Quota_Validator SHALL suggest a reduced scope that fits within the limits

### Requirement 7: Audit Logging of LLM Calls

**User Story:** As a compliance officer, I want an immutable audit trail of all LLM interactions, so that usage, costs, and security events can be reviewed and investigated.

#### Acceptance Criteria

1. WHEN an LLM call is made, THE Audit_Logger SHALL create an immutable record containing timestamp, job_id, input token count, output token count, estimated cost, model identifier, and cache hit status
2. THE Audit_Logger SHALL store audit records in a SQLite database
3. THE Audit_Logger SHALL retain audit records for 90 days
4. WHEN audit records exceed 90 days of age, THE Audit_Logger SHALL delete them during a scheduled cleanup
5. THE Audit_Logger SHALL expose an admin-only API endpoint for querying audit records by date range, job_id, or model
6. THE Audit_Logger SHALL record security events including injection detections, jailbreak attempts, and scope violations alongside LLM call records

### Requirement 8: Dependency and Generated Code Vulnerability Scanning

**User Story:** As a security engineer, I want Python dependencies and generated HCL to be scanned for known vulnerabilities, so that the application does not ship or produce code with exploitable weaknesses.

#### Acceptance Criteria

1. WHEN a CI build runs, THE Vulnerability_Scanner SHALL execute pip-audit against the Python dependency list and fail the build if critical vulnerabilities are found
2. WHEN Terraform HCL is generated, THE Vulnerability_Scanner SHALL scan for deprecated provider arguments
3. WHEN Terraform HCL is generated, THE Vulnerability_Scanner SHALL scan for insecure TLS configurations (TLS versions below 1.2)
4. WHEN Terraform HCL is generated, THE Vulnerability_Scanner SHALL scan for missing encryption in transit settings
5. WHEN Terraform HCL is generated, THE Vulnerability_Scanner SHALL scan for publicly exposed database endpoints

### Requirement 9: Guardrail Engine and Jailbreak Prevention

**User Story:** As a system operator, I want the system to detect and block jailbreak attempts and off-topic requests, so that the LLM is only used for its intended infrastructure generation purpose.

#### Acceptance Criteria

1. WHEN a jailbreak pattern is detected with confidence at or above 0.7, THE Guardrail_Engine SHALL block the request and return a generic safe message
2. WHEN a request topic does not align with infrastructure, Terraform, or cloud-related subjects, THE Guardrail_Engine SHALL block the request
3. THE Guardrail_Engine SHALL detect known jailbreak patterns including DAN variants, role-play exploits, developer mode requests, and system prompt extraction attempts
4. WHEN a guardrail violation occurs, THE Guardrail_Engine SHALL log the violation with the detected pattern category and confidence score

### Requirement 10: Scope-Based Data Access Control

**User Story:** As a security architect, I want each LLM task type to have strict permission boundaries on what data it can access, so that a compromised or manipulated task cannot access data outside its scope.

#### Acceptance Criteria

1. THE Scope_Validator SHALL enforce that each task type can only access data categories defined in its scope policy
2. WHEN a task type attempts to access data outside its allowed categories, THE Scope_Validator SHALL silently remove that data from the context
3. THE Scope_Validator SHALL enforce that no task type can access data categorized as "secrets" or "credentials"
4. WHEN all context is removed due to scope violations, THE Scope_Validator SHALL return a generic "insufficient context" error to the caller
5. THE Scope_Validator SHALL enforce maximum context size limits per task type

### Requirement 11: RAG Retrieval Trust Validation

**User Story:** As a security engineer, I want all RAG retrieval results validated against a trust registry, so that malicious or tampered content in the vector database cannot manipulate LLM responses.

#### Acceptance Criteria

1. WHEN chunks are retrieved from the vector database, THE Trust_Validator SHALL verify each chunk originates from a collection in the trusted collections list
2. WHEN hash verification is enabled, THE Trust_Validator SHALL verify each retrieved chunk's document hash matches the registered hash
3. WHEN a retrieved chunk contains detected injection patterns, THE Trust_Validator SHALL reject that chunk and flag the incident
4. WHEN all retrieved chunks fail trust validation, THE Trust_Validator SHALL return empty results with a message indicating no verified sources were found
5. WHEN injection is detected in stored chunks, THE Trust_Validator SHALL raise an alert for administrator review

### Requirement 12: Security Pipeline Orchestration and Fail-Closed Behavior

**User Story:** As a platform operator, I want the security pipeline to operate transparently within the LLM Gateway and fail closed on any error, so that no unprotected data ever reaches external LLM providers.

#### Acceptance Criteria

1. THE Security_Pipeline SHALL process all outbound LLM requests through the sequence: Input Sanitizer, Guardrail Engine, Data Masker, Scope Validator, Trust Validator
2. IF any security component raises an unexpected exception, THEN THE Security_Pipeline SHALL block the request entirely rather than sending unprotected data
3. WHEN a request is processed, THE Security_Pipeline SHALL create exactly one audit entry regardless of whether the request was allowed, blocked, or errored
4. THE Security_Pipeline SHALL not mutate the original messages passed by the caller
5. THE Security_Pipeline SHALL integrate transparently with the existing LLMGateway.call() method without requiring changes to downstream consumers

### Requirement 13: Security Feature Configuration

**User Story:** As a system administrator, I want each security feature to be independently toggleable via configuration flags, so that features can be enabled or disabled without code changes.

#### Acceptance Criteria

1. THE Security_Pipeline SHALL read configuration flags ENABLE_TERRAFORM_GUARD, ENABLE_PROMPT_GUARD, ENABLE_PII_REDACTION, ENABLE_RATE_LIMITING, ENABLE_CONFIDENCE_GATE, ENABLE_RESOURCE_QUOTAS, and ENABLE_AUDIT_LOGGING from the application configuration
2. WHEN a configuration flag is set to false, THE Security_Pipeline SHALL skip the corresponding security check entirely
3. WHEN the application starts, THE Security_Pipeline SHALL log which security features are enabled and which are disabled
4. THE Security_Pipeline SHALL load security thresholds and patterns from environment variables without requiring application restart for threshold changes

### Requirement 14: Mask Reversibility and Request Isolation

**User Story:** As a developer, I want masked data to be perfectly reversible within a request and never persisted beyond it, so that callers receive correct responses and sensitive data is not stored.

#### Acceptance Criteria

1. FOR ALL text values masked by the Data_Masker, unmasking with the corresponding Mask_Registry SHALL produce the exact original value
2. THE Data_Masker SHALL not persist the Mask_Registry to disk, database, or logs
3. THE Data_Masker SHALL scope each Mask_Registry to a single request lifecycle
4. WHEN the same sensitive value appears multiple times in a request, THE Data_Masker SHALL use the same mask token for all occurrences
