# Design Document: Security Guardrails

## Overview

This design introduces a comprehensive security and guardrail system for the Terraform Generator application, protecting confidential enterprise data from exposure to LLM providers. The system operates as a multi-layered defense pipeline integrated into the existing LLM Gateway (`llm_gateway.py`), ensuring that all data flowing to external AI services is sanitized, masked, and validated.

The architecture follows a "defense-in-depth" strategy with five core pillars: (1) Input Sanitization against prompt injection, (2) Data Serialization & Masking to prevent confidential data leakage, (3) Scoped Permissions for tool/service access control, (4) Guardrails against jailbreak attempts, and (5) Trusted Source Validation for RAG retrieval. Each layer operates independently so that a bypass of one layer does not compromise the entire system.

The system integrates transparently with the existing `LLMGateway.call()` method, requiring no changes to downstream consumers (agents, services, API endpoints). All security processing happens within the gateway before any data leaves the application boundary.

## Architecture

```mermaid
graph TD
    subgraph "Application Boundary (Trusted Zone)"
        API[FastAPI Endpoints] --> GW[LLM Gateway]
        GW --> SL[Security Layer]
        
        subgraph "Security Pipeline"
            SL --> IS[Input Sanitizer]
            IS --> GR[Guardrail Engine]
            GR --> DM[Data Masker]
            DM --> SP[Scope Validator]
            SP --> TV[Trust Validator]
        end
        
        TV --> |"Sanitized & Masked"| LLM_CALL[Model Invocation]
        LLM_CALL --> RM[Response Masker]
        RM --> API
    end

    subgraph "External (Untrusted Zone)"
        LLM_CALL --> BEDROCK[AWS Bedrock]
        LLM_CALL --> GEMINI[Google Gemini]
    end

    subgraph "Data Stores"
        RAG_DB[(Qdrant Vector DB)]
        TV --> |"Source Validation"| RAG_DB
        POLICY[(Policy Store)]
        GR --> POLICY
        SP --> POLICY
    end
```

## Sequence Diagrams

### Main Security Pipeline Flow

```mermaid
sequenceDiagram
    participant C as Caller (Agent/Service)
    participant GW as LLM Gateway
    participant IS as Input Sanitizer
    participant GR as Guardrail Engine
    participant DM as Data Masker
    participant SP as Scope Validator
    participant TV as Trust Validator
    participant LLM as AWS Bedrock / Gemini

    C->>GW: gateway.call(messages, task_type, context)
    GW->>IS: sanitize_input(messages)
    IS-->>IS: detect_injection_patterns()
    IS-->>IS: neutralize_control_sequences()
    IS-->>GW: SanitizedInput | RejectedInput
    
    alt Input Rejected
        GW-->>C: SecurityError("Prompt injection detected")
    end

    GW->>GR: check_guardrails(sanitized_messages, task_type)
    GR-->>GR: check_jailbreak_patterns()
    GR-->>GR: validate_intent_alignment()
    GR-->>GW: Allowed | Blocked(reason)
    
    alt Guardrail Blocked
        GW-->>C: SecurityError("Request violates guardrails")
    end

    GW->>SP: validate_scope(task_type, caller_context)
    SP-->>SP: check_permission_boundary()
    SP-->>GW: Authorized | Denied

    GW->>DM: mask_sensitive_data(messages, context)
    DM-->>DM: detect_secrets(regex + entropy)
    DM-->>DM: mask_pii(patterns)
    DM-->>DM: redact_confidential_fields()
    DM-->>GW: MaskedPayload + MaskRegistry

    GW->>TV: validate_sources(context)
    TV-->>TV: check_source_trust_level()
    TV-->>GW: Validated | Rejected

    GW->>LLM: invoke_model(masked_payload)
    LLM-->>GW: raw_response
    
    GW->>DM: unmask_response(raw_response, MaskRegistry)
    DM-->>GW: final_response
    GW-->>C: final_response
```

### RAG Retrieval Trust Validation Flow

```mermaid
sequenceDiagram
    participant RS as RAG Service
    participant TV as Trust Validator
    participant QD as Qdrant
    participant PS as Policy Store

    RS->>TV: validate_retrieval_sources(query, results)
    TV->>PS: get_trusted_sources()
    PS-->>TV: TrustPolicy(allowed_collections, source_hashes)
    
    loop For each retrieved chunk
        TV-->>TV: verify_source_collection(chunk)
        TV-->>TV: verify_document_hash(chunk)
        TV-->>TV: check_injection_in_chunk(chunk)
    end
    
    TV-->>RS: FilteredResults(trusted_only)
```

## Components and Interfaces

### Component 1: Input Sanitizer (`security/input_sanitizer.py`)

**Purpose**: Detects and neutralizes prompt injection attacks in user-provided input before it reaches the LLM. Operates on raw message content using pattern matching, heuristic analysis, and structural validation.

**Interface**:
```python
from dataclasses import dataclass
from enum import Enum
from typing import List, Dict, Optional

class ThreatLevel(Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

@dataclass
class SanitizationResult:
    is_safe: bool
    threat_level: ThreatLevel
    sanitized_messages: List[Dict[str, str]]
    detected_threats: List[str]
    original_hash: str  # SHA-256 of original for audit

class InputSanitizer:
    def sanitize(self, messages: List[Dict[str, str]]) -> SanitizationResult:
        """Main entry point: sanitize all messages in a conversation."""
        ...

    def detect_injection(self, text: str) -> tuple[bool, List[str]]:
        """Detect prompt injection patterns in a single text block."""
        ...

    def neutralize_control_sequences(self, text: str) -> str:
        """Remove or escape control characters and injection markers."""
        ...
```

**Responsibilities**:
- Detect known prompt injection patterns (role overrides, instruction leaks, delimiter attacks)
- Neutralize Unicode control characters and zero-width characters
- Detect and block encoded payloads (base64, hex-encoded instructions)
- Score threat level based on pattern density and confidence
- Maintain audit trail of all detected threats

### Component 2: Guardrail Engine (`security/guardrail_engine.py`)

**Purpose**: Enforces behavioral boundaries on LLM interactions, preventing jailbreak attempts and ensuring requests stay within the application's intended scope (Terraform/infrastructure generation).

**Interface**:
```python
from dataclasses import dataclass
from typing import List, Dict, Optional

@dataclass
class GuardrailPolicy:
    name: str
    allowed_topics: List[str]  # e.g., ["terraform", "infrastructure", "cloud"]
    blocked_patterns: List[str]
    max_message_length: int
    require_task_alignment: bool

@dataclass
class GuardrailResult:
    allowed: bool
    reason: Optional[str]
    violated_policies: List[str]
    confidence: float  # 0.0 to 1.0

class GuardrailEngine:
    def __init__(self, policies: List[GuardrailPolicy]):
        ...

    def check(
        self,
        messages: List[Dict[str, str]],
        task_type: str,
    ) -> GuardrailResult:
        """Evaluate messages against all active guardrail policies."""
        ...

    def check_jailbreak(self, text: str) -> tuple[bool, float]:
        """Detect jailbreak attempts using pattern + heuristic analysis."""
        ...

    def validate_task_alignment(
        self, messages: List[Dict[str, str]], task_type: str
    ) -> bool:
        """Ensure the request aligns with the declared task_type scope."""
        ...
```

**Responsibilities**:
- Detect jailbreak patterns (DAN, role-play exploits, system prompt extraction)
- Validate that requests align with declared task types
- Enforce topic boundaries (only infrastructure/Terraform-related content)
- Rate-limit suspicious patterns per session
- Block attempts to extract system prompts or internal configuration

### Component 3: Data Masker (`security/data_masker.py`)

**Purpose**: Serializes and masks confidential data before it leaves the application boundary. Ensures secrets, PII, internal IPs, and proprietary configuration never reach LLM providers. Maintains a reversible mask registry for response reconstruction.

**Interface**:
```python
from dataclasses import dataclass, field
from typing import List, Dict, Set, Optional
import re

@dataclass
class MaskRule:
    name: str
    pattern: re.Pattern
    replacement_template: str  # e.g., "[MASKED_SECRET_{n}]"
    category: str  # "secret", "pii", "internal_ip", "proprietary"

@dataclass
class MaskRegistry:
    """Reversible mapping of masked tokens to original values."""
    mappings: Dict[str, str] = field(default_factory=dict)  # token -> original
    categories: Dict[str, List[str]] = field(default_factory=dict)

    def add(self, token: str, original: str, category: str) -> None:
        ...

    def unmask(self, text: str) -> str:
        """Restore original values in a response text."""
        ...

@dataclass
class MaskingResult:
    masked_messages: List[Dict[str, str]]
    masked_context: str
    registry: MaskRegistry
    stats: Dict[str, int]  # category -> count masked

class DataMasker:
    def __init__(self, rules: List[MaskRule], custom_patterns: Optional[Dict] = None):
        ...

    def mask_messages(
        self,
        messages: List[Dict[str, str]],
        context: str = "",
    ) -> MaskingResult:
        """Mask all sensitive data in messages and context."""
        ...

    def detect_secrets(self, text: str) -> List[tuple[str, str, int]]:
        """Detect secrets using regex patterns + Shannon entropy analysis."""
        ...

    def unmask_response(self, response: str, registry: MaskRegistry) -> str:
        """Restore masked values in LLM response using the registry."""
        ...
```

**Responsibilities**:
- Detect and mask AWS credentials, API keys, tokens, passwords
- Mask PII (emails, phone numbers, names in specific contexts)
- Redact internal IP addresses, CIDR ranges marked as confidential
- Mask proprietary configuration values (database connection strings, internal URLs)
- Use Shannon entropy analysis to detect high-entropy strings (likely secrets)
- Maintain reversible registry so responses can reference masked values correctly
- Never store the registry beyond the request lifecycle

### Component 4: Scope Validator (`security/scope_validator.py`)

**Purpose**: Enforces scoped permissions for tool and service access. Each task type has a defined permission boundary that limits what data and operations the LLM can access.

**Interface**:
```python
from dataclasses import dataclass
from typing import List, Dict, Set, Optional
from enum import Enum

class Permission(Enum):
    READ_TEMPLATES = "read_templates"
    READ_DIAGRAMS = "read_diagrams"
    READ_RAG_DOCS = "read_rag_docs"
    WRITE_TERRAFORM = "write_terraform"
    WRITE_DESIGN_DOC = "write_design_doc"
    ACCESS_COMPANY_DATA = "access_company_data"
    ACCESS_SECRETS = "access_secrets"  # NEVER granted to LLM tasks

@dataclass
class ScopePolicy:
    task_type: str
    allowed_permissions: Set[Permission]
    max_context_bytes: int
    allowed_data_categories: Set[str]
    denied_data_categories: Set[str]

@dataclass
class ScopeResult:
    authorized: bool
    granted_permissions: Set[Permission]
    denied_reason: Optional[str]
    context_trimmed: bool  # True if context was truncated to fit scope

class ScopeValidator:
    def __init__(self, policies: Dict[str, ScopePolicy]):
        ...

    def validate(
        self,
        task_type: str,
        requested_data: Dict[str, any],
        caller_context: Optional[Dict] = None,
    ) -> ScopeResult:
        """Validate that the task has permission to access requested data."""
        ...

    def filter_context(
        self,
        context: str,
        task_type: str,
    ) -> str:
        """Remove data from context that exceeds the task's scope."""
        ...
```

**Responsibilities**:
- Define permission boundaries per task type (e.g., `terraform_chat` cannot access company secrets)
- Prevent privilege escalation between task types
- Filter context to only include data within the task's allowed scope
- Enforce maximum context size per task type
- Log all scope violations for security audit

### Component 5: Trust Validator (`security/trust_validator.py`)

**Purpose**: Validates that RAG retrieval results come from trusted, verified sources. Prevents retrieval injection attacks where malicious content in the vector database could manipulate LLM behavior.

**Interface**:
```python
from dataclasses import dataclass
from typing import List, Dict, Optional
from enum import Enum

class TrustLevel(Enum):
    VERIFIED = "verified"      # Admin-uploaded, hash-verified
    TRUSTED = "trusted"        # Known source, not hash-verified
    UNTRUSTED = "untrusted"    # User-uploaded, unverified
    BLOCKED = "blocked"        # Known malicious or corrupted

@dataclass
class SourceMetadata:
    collection_name: str
    document_hash: str
    upload_source: str  # "admin", "user", "system"
    trust_level: TrustLevel
    indexed_at: float

@dataclass
class TrustResult:
    trusted_chunks: List[Dict]
    rejected_chunks: List[Dict]
    trust_scores: Dict[str, float]
    injection_detected: bool

class TrustValidator:
    def __init__(self, trusted_collections: List[str], source_registry: Dict):
        ...

    def validate_retrieval(
        self,
        retrieved_chunks: List[Dict],
        query: str,
    ) -> TrustResult:
        """Validate all retrieved chunks against trust policies."""
        ...

    def check_chunk_injection(self, chunk_text: str) -> tuple[bool, float]:
        """Detect if a retrieved chunk contains injection attempts."""
        ...

    def verify_document_integrity(self, doc_hash: str, collection: str) -> bool:
        """Verify document hasn't been tampered with since indexing."""
        ...
```

**Responsibilities**:
- Maintain registry of trusted document sources and their hashes
- Validate retrieved chunks come from approved collections
- Detect injection patterns within retrieved content
- Verify document integrity via hash comparison
- Filter out untrusted or tampered content before it reaches the LLM

### Component 6: Security Pipeline Orchestrator (`security/pipeline.py`)

**Purpose**: Orchestrates the security components in the correct order, integrating with the existing `LLMGateway.call()` method. Acts as the single integration point.

**Interface**:
```python
from dataclasses import dataclass
from typing import List, Dict, Optional

@dataclass
class SecurityContext:
    task_type: str
    caller_id: Optional[str]
    session_id: Optional[str]
    ip_address: Optional[str]

@dataclass
class SecuredPayload:
    messages: List[Dict[str, str]]
    context: str
    mask_registry: MaskRegistry
    security_metadata: Dict[str, any]

@dataclass
class SecurityAuditEntry:
    timestamp: float
    action: str
    task_type: str
    threats_detected: List[str]
    data_masked: Dict[str, int]
    scope_violations: List[str]
    outcome: str  # "allowed", "blocked", "masked"

class SecurityPipeline:
    def __init__(
        self,
        sanitizer: InputSanitizer,
        guardrails: GuardrailEngine,
        masker: DataMasker,
        scope_validator: ScopeValidator,
        trust_validator: TrustValidator,
    ):
        ...

    def process_outbound(
        self,
        messages: List[Dict[str, str]],
        context: str,
        security_context: SecurityContext,
    ) -> SecuredPayload:
        """Full security pipeline for outbound LLM requests."""
        ...

    def process_inbound(
        self,
        response: str,
        mask_registry: MaskRegistry,
    ) -> str:
        """Process LLM response: unmask and validate."""
        ...

    def get_audit_log(self, limit: int = 100) -> List[SecurityAuditEntry]:
        """Retrieve recent security audit entries."""
        ...
```

## Data Models

### Model 1: Security Configuration

```python
from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Set

class SecurityConfig(BaseModel):
    """Security configuration loaded from environment/config."""
    
    # Input Sanitization
    max_message_length: int = Field(default=10000, description="Max chars per message")
    injection_detection_enabled: bool = Field(default=True)
    injection_block_threshold: float = Field(default=0.7, description="0-1 confidence to block")
    
    # Data Masking
    mask_aws_credentials: bool = Field(default=True)
    mask_api_keys: bool = Field(default=True)
    mask_pii: bool = Field(default=True)
    mask_internal_ips: bool = Field(default=True)
    mask_connection_strings: bool = Field(default=True)
    custom_mask_patterns: List[str] = Field(default_factory=list)
    entropy_threshold: float = Field(default=4.5, description="Shannon entropy threshold for secret detection")
    
    # Guardrails
    allowed_topics: List[str] = Field(
        default=["terraform", "infrastructure", "cloud", "aws", "azure", "gcp",
                 "networking", "security", "iam", "kubernetes", "docker"]
    )
    jailbreak_detection_enabled: bool = Field(default=True)
    max_requests_per_minute: int = Field(default=30)
    
    # Scope Permissions
    strict_scope_enforcement: bool = Field(default=True)
    
    # Trust Validation
    trusted_rag_collections: List[str] = Field(
        default=["infra_documents", "terraform_best_practices"]
    )
    require_document_hash_verification: bool = Field(default=True)
    
    # Audit
    audit_log_enabled: bool = Field(default=True)
    audit_log_retention_days: int = Field(default=90)
```

### Model 2: Threat Detection Patterns

```python
from dataclasses import dataclass, field
from typing import List, Pattern
import re

@dataclass
class InjectionPattern:
    """A single prompt injection detection pattern."""
    name: str
    pattern: re.Pattern
    severity: ThreatLevel
    description: str
    false_positive_rate: float  # Expected FP rate for tuning

# Pre-compiled injection detection patterns
INJECTION_PATTERNS: List[InjectionPattern] = [
    InjectionPattern(
        name="role_override",
        pattern=re.compile(
            r"(?i)(ignore\s+(all\s+)?previous|forget\s+(all\s+)?instructions|"
            r"you\s+are\s+now|new\s+instructions?|override\s+system)",
            re.IGNORECASE
        ),
        severity=ThreatLevel.HIGH,
        description="Attempts to override system role or instructions",
        false_positive_rate=0.02,
    ),
    InjectionPattern(
        name="delimiter_escape",
        pattern=re.compile(
            r"(```\s*system|<\|im_start\|>|<\|im_end\|>|\[INST\]|\[/INST\]|"
            r"<<SYS>>|<</SYS>>|Human:|Assistant:)",
            re.IGNORECASE
        ),
        severity=ThreatLevel.CRITICAL,
        description="Attempts to inject chat delimiters or system markers",
        false_positive_rate=0.01,
    ),
    InjectionPattern(
        name="data_exfiltration",
        pattern=re.compile(
            r"(?i)(reveal\s+(your|the)\s+(system|internal|secret)|"
            r"show\s+me\s+(your|the)\s+(prompt|instructions|config)|"
            r"what\s+are\s+your\s+(instructions|rules|constraints))",
            re.IGNORECASE
        ),
        severity=ThreatLevel.HIGH,
        description="Attempts to extract system prompts or configuration",
        false_positive_rate=0.05,
    ),
    InjectionPattern(
        name="encoding_attack",
        pattern=re.compile(
            r"(\\x[0-9a-f]{2}|\\u[0-9a-f]{4}|&#x?[0-9a-f]+;|"
            r"%[0-9a-f]{2}){3,}",
            re.IGNORECASE
        ),
        severity=ThreatLevel.MEDIUM,
        description="Encoded payloads that may contain hidden instructions",
        false_positive_rate=0.03,
    ),
    InjectionPattern(
        name="jailbreak_roleplay",
        pattern=re.compile(
            r"(?i)(DAN|do\s+anything\s+now|act\s+as\s+if\s+you\s+have\s+no\s+"
            r"restrictions|pretend\s+you\s+(are|can)|in\s+developer\s+mode|"
            r"bypass\s+(your|all)\s+(safety|restrictions|filters))",
            re.IGNORECASE
        ),
        severity=ThreatLevel.CRITICAL,
        description="Known jailbreak patterns (DAN, developer mode, etc.)",
        false_positive_rate=0.01,
    ),
]
```

### Model 3: Scope Permission Matrix

```python
# Task type → allowed permissions mapping
SCOPE_POLICIES: Dict[str, ScopePolicy] = {
    "template_compression": ScopePolicy(
        task_type="template_compression",
        allowed_permissions={Permission.READ_TEMPLATES},
        max_context_bytes=32_000,
        allowed_data_categories={"governance", "naming", "compliance"},
        denied_data_categories={"secrets", "credentials", "pii"},
    ),
    "terraform_chat": ScopePolicy(
        task_type="terraform_chat",
        allowed_permissions={Permission.READ_TEMPLATES, Permission.READ_RAG_DOCS, Permission.WRITE_TERRAFORM},
        max_context_bytes=64_000,
        allowed_data_categories={"governance", "naming", "infrastructure", "patterns"},
        denied_data_categories={"secrets", "credentials", "pii", "financial"},
    ),
    "design_doc_section": ScopePolicy(
        task_type="design_doc_section",
        allowed_permissions={Permission.READ_TEMPLATES, Permission.READ_DIAGRAMS, Permission.WRITE_DESIGN_DOC},
        max_context_bytes=64_000,
        allowed_data_categories={"governance", "naming", "infrastructure", "architecture"},
        denied_data_categories={"secrets", "credentials", "pii"},
    ),
    "rag_synthesis": ScopePolicy(
        task_type="rag_synthesis",
        allowed_permissions={Permission.READ_RAG_DOCS},
        max_context_bytes=32_000,
        allowed_data_categories={"documentation", "best_practices"},
        denied_data_categories={"secrets", "credentials", "pii", "internal_config"},
    ),
}
```

## Algorithmic Pseudocode

### Input Sanitization Algorithm

```python
def sanitize_input(messages: List[Dict[str, str]]) -> SanitizationResult:
    """
    ALGORITHM: Multi-pass input sanitization
    INPUT: messages — list of chat messages with role and content
    OUTPUT: SanitizationResult with sanitized messages or rejection
    
    PRECONDITIONS:
    - messages is non-empty
    - Each message has 'role' and 'content' keys
    
    POSTCONDITIONS:
    - If is_safe=True: sanitized_messages contain no known injection patterns
    - If is_safe=False: detected_threats lists all found patterns
    - original_hash preserves audit trail of input
    """
    detected_threats = []
    threat_scores = []
    original_hash = sha256(json.dumps(messages).encode()).hexdigest()
    
    for message in messages:
        content = message["content"]
        
        # Pass 1: Unicode normalization (prevent homoglyph attacks)
        content = unicodedata.normalize("NFKC", content)
        
        # Pass 2: Strip zero-width characters and control sequences
        content = remove_control_characters(content)
        
        # Pass 3: Check against injection patterns
        for pattern in INJECTION_PATTERNS:
            matches = pattern.pattern.findall(content)
            if matches:
                detected_threats.append(f"{pattern.name}: {matches[0][:50]}")
                threat_scores.append(pattern.severity.value)
        
        # Pass 4: Entropy analysis for encoded payloads
        for segment in split_into_segments(content, segment_size=200):
            entropy = calculate_shannon_entropy(segment)
            if entropy > 5.5 and has_encoding_markers(segment):
                detected_threats.append(f"high_entropy_segment: entropy={entropy:.2f}")
                threat_scores.append("medium")
        
        # Pass 5: Length validation
        if len(content) > MAX_MESSAGE_LENGTH:
            content = content[:MAX_MESSAGE_LENGTH]
            detected_threats.append("message_truncated")
    
    # Determine overall threat level
    threat_level = compute_aggregate_threat_level(threat_scores)
    is_safe = threat_level.value <= ThreatLevel.LOW.value
    
    return SanitizationResult(
        is_safe=is_safe,
        threat_level=threat_level,
        sanitized_messages=sanitized_messages,
        detected_threats=detected_threats,
        original_hash=original_hash,
    )
```

### Data Masking Algorithm

```python
def mask_sensitive_data(
    messages: List[Dict[str, str]],
    context: str,
) -> MaskingResult:
    """
    ALGORITHM: Multi-layer sensitive data masking
    INPUT: messages and context containing potentially sensitive data
    OUTPUT: MaskingResult with masked content and reversible registry
    
    PRECONDITIONS:
    - messages is a valid list of chat messages
    - Mask rules are loaded and compiled
    
    POSTCONDITIONS:
    - No AWS credentials, API keys, or PII remain in masked output
    - MaskRegistry contains all mappings for response reconstruction
    - Original data is NEVER logged or persisted
    
    LOOP INVARIANT:
    - After processing message[i], all sensitive data in messages[0..i] is masked
    - Registry contains exactly one entry per unique masked value
    """
    registry = MaskRegistry()
    mask_counter = 0
    stats = defaultdict(int)
    
    for message in messages:
        content = message["content"]
        
        # Layer 1: Regex-based pattern matching (fast, high precision)
        for rule in MASK_RULES:
            for match in rule.pattern.finditer(content):
                original = match.group()
                mask_counter += 1
                token = rule.replacement_template.format(n=mask_counter)
                registry.add(token, original, rule.category)
                content = content.replace(original, token, 1)
                stats[rule.category] += 1
        
        # Layer 2: Shannon entropy detection (catches unknown secret formats)
        for word in extract_high_entropy_tokens(content):
            if is_likely_secret(word):
                mask_counter += 1
                token = f"[MASKED_SECRET_{mask_counter}]"
                registry.add(token, word, "entropy_detected")
                content = content.replace(word, token, 1)
                stats["entropy_detected"] += 1
        
        # Layer 3: Context-aware masking (internal URLs, private IPs)
        content = mask_internal_references(content, registry, mask_counter)
        
        message["content"] = content
    
    # Also mask the context string
    masked_context = apply_masking_layers(context, registry, mask_counter)
    
    return MaskingResult(
        masked_messages=messages,
        masked_context=masked_context,
        registry=registry,
        stats=dict(stats),
    )
```

### Guardrail Jailbreak Detection Algorithm

```python
def check_jailbreak(text: str) -> tuple[bool, float]:
    """
    ALGORITHM: Multi-signal jailbreak detection
    INPUT: text — user message content
    OUTPUT: (is_jailbreak, confidence) tuple
    
    PRECONDITIONS:
    - text is unicode-normalized (done by sanitizer upstream)
    - JAILBREAK_PATTERNS list is loaded
    
    POSTCONDITIONS:
    - confidence is in range [0.0, 1.0]
    - is_jailbreak is True only when confidence >= JAILBREAK_THRESHOLD
    - False positives rate < 2% on benign infrastructure prompts
    """
    signals = []
    
    # Signal 1: Pattern matching against known jailbreak templates
    pattern_score = 0.0
    for pattern in JAILBREAK_PATTERNS:
        if pattern.regex.search(text):
            pattern_score = max(pattern_score, pattern.weight)
            signals.append(("pattern", pattern.name, pattern.weight))
    
    # Signal 2: Instruction density analysis
    # Jailbreaks tend to have high density of imperative verbs
    imperative_density = count_imperatives(text) / max(word_count(text), 1)
    if imperative_density > 0.15:
        signals.append(("imperative_density", imperative_density, 0.3))
    
    # Signal 3: Role assumption detection
    # "You are now X", "Act as X", "Pretend to be X"
    role_assumption_score = detect_role_assumption(text)
    if role_assumption_score > 0.0:
        signals.append(("role_assumption", role_assumption_score, 0.4))
    
    # Signal 4: Topic divergence from infrastructure domain
    topic_relevance = compute_topic_relevance(text, ALLOWED_TOPICS)
    if topic_relevance < 0.2:
        signals.append(("topic_divergence", 1.0 - topic_relevance, 0.25))
    
    # Aggregate confidence using weighted combination
    if not signals:
        return (False, 0.0)
    
    confidence = min(1.0, sum(s[2] for s in signals) / len(signals) + pattern_score * 0.5)
    is_jailbreak = confidence >= JAILBREAK_THRESHOLD  # default: 0.7
    
    return (is_jailbreak, confidence)
```

### Trust Validation Algorithm for RAG

```python
def validate_retrieval(
    retrieved_chunks: List[Dict],
    query: str,
) -> TrustResult:
    """
    ALGORITHM: Multi-factor retrieval trust validation
    INPUT: retrieved_chunks from Qdrant, original query
    OUTPUT: TrustResult with filtered trusted chunks
    
    PRECONDITIONS:
    - retrieved_chunks each have 'payload' with source metadata
    - trusted_collections registry is loaded
    - Document hash registry is available
    
    POSTCONDITIONS:
    - trusted_chunks contains ONLY chunks from verified sources
    - rejected_chunks contains all filtered-out chunks with reasons
    - injection_detected is True if any chunk contains injection patterns
    
    LOOP INVARIANT:
    - After processing chunk[i], all chunks[0..i] are classified as trusted or rejected
    """
    trusted_chunks = []
    rejected_chunks = []
    trust_scores = {}
    injection_detected = False
    
    for chunk in retrieved_chunks:
        payload = chunk.get("payload", {})
        collection = payload.get("collection_name", "")
        doc_hash = payload.get("document_hash", "")
        source = payload.get("upload_source", "unknown")
        chunk_text = payload.get("text", "")
        
        # Check 1: Collection trust level
        if collection not in TRUSTED_COLLECTIONS:
            rejected_chunks.append({**chunk, "reject_reason": "untrusted_collection"})
            continue
        
        # Check 2: Document integrity (hash verification)
        if REQUIRE_HASH_VERIFICATION:
            if not verify_document_hash(doc_hash, collection):
                rejected_chunks.append({**chunk, "reject_reason": "hash_mismatch"})
                continue
        
        # Check 3: Source trust level
        source_trust = get_source_trust_level(source)
        if source_trust == TrustLevel.BLOCKED:
            rejected_chunks.append({**chunk, "reject_reason": "blocked_source"})
            continue
        
        # Check 4: Injection detection within chunk content
        has_injection, injection_confidence = check_chunk_injection(chunk_text)
        if has_injection:
            injection_detected = True
            rejected_chunks.append({
                **chunk,
                "reject_reason": f"injection_detected (confidence={injection_confidence:.2f})"
            })
            continue
        
        # Check 5: Relevance validation (prevent off-topic retrieval manipulation)
        relevance_score = compute_query_chunk_relevance(query, chunk_text)
        if relevance_score < MIN_RELEVANCE_THRESHOLD:
            rejected_chunks.append({**chunk, "reject_reason": "low_relevance"})
            continue
        
        # Chunk passed all checks
        trust_scores[chunk.get("id", "")] = relevance_score * source_trust_weight(source_trust)
        trusted_chunks.append(chunk)
    
    return TrustResult(
        trusted_chunks=trusted_chunks,
        rejected_chunks=rejected_chunks,
        trust_scores=trust_scores,
        injection_detected=injection_detected,
    )
```

## Key Functions with Formal Specifications

### Function 1: SecurityPipeline.process_outbound()

```python
def process_outbound(
    self,
    messages: List[Dict[str, str]],
    context: str,
    security_context: SecurityContext,
) -> SecuredPayload:
    """Full security pipeline for outbound LLM requests."""
    ...
```

**Preconditions:**
- `messages` is non-empty and each message has `role` and `content` keys
- `security_context.task_type` is a recognized task type in SCOPE_POLICIES
- All security components (sanitizer, guardrails, masker, scope, trust) are initialized

**Postconditions:**
- If successful: returned `SecuredPayload.messages` contain NO sensitive data patterns
- If blocked: raises `SecurityError` with specific violation details
- `SecuredPayload.mask_registry` contains all reversible mappings
- Audit entry is created regardless of outcome
- Original messages are NOT mutated (deep copy used internally)

**Loop Invariants:** N/A (sequential pipeline, no loops)

### Function 2: DataMasker.detect_secrets()

```python
def detect_secrets(self, text: str) -> List[tuple[str, str, int]]:
    """Detect secrets using regex patterns + Shannon entropy analysis.
    
    Returns list of (secret_value, category, position) tuples.
    """
    ...
```

**Preconditions:**
- `text` is a valid string (may be empty)
- MASK_RULES are compiled and available

**Postconditions:**
- Returns list of detected secrets with their categories and positions
- Each detected secret has Shannon entropy >= `entropy_threshold` OR matches a known pattern
- Position values are valid indices within the input text
- No false negatives for patterns matching AWS key format (`AKIA...`), standard API key formats

**Loop Invariants:**
- After scanning position `i`, all secrets starting before position `i` are detected
- No overlapping detections (earlier match takes precedence)

### Function 3: InputSanitizer.detect_injection()

```python
def detect_injection(self, text: str) -> tuple[bool, List[str]]:
    """Detect prompt injection patterns in a single text block."""
    ...
```

**Preconditions:**
- `text` is unicode-normalized (NFKC)
- `text` length <= MAX_MESSAGE_LENGTH (enforced by caller)

**Postconditions:**
- Returns `(True, threats)` if any pattern matches with severity >= MEDIUM
- Returns `(False, [])` if no significant patterns detected
- `threats` list contains human-readable descriptions of each detected pattern
- Detection runs in O(n * p) time where n = len(text), p = number of patterns

**Loop Invariants:**
- After checking pattern[i], all patterns[0..i] have been evaluated against the full text

### Function 4: Shannon Entropy Calculator

```python
def calculate_shannon_entropy(text: str) -> float:
    """Calculate Shannon entropy of a text string.
    
    High entropy (>4.5) suggests random/encrypted content (likely a secret).
    Normal English text has entropy ~3.5-4.0.
    """
    ...
```

**Preconditions:**
- `text` is non-empty string
- `text` contains only printable characters (control chars stripped upstream)

**Postconditions:**
- Returns float in range [0.0, 8.0] (log2 of 256 possible byte values)
- For uniform random strings: entropy approaches 8.0
- For English prose: entropy is typically 3.5-4.5
- For secrets/keys: entropy is typically 4.5-6.5
- Computation is O(n) where n = len(text)

**Loop Invariants:**
- After processing character[i], frequency table reflects exact counts for chars[0..i]

## Example Usage

### Integration with Existing LLM Gateway

```python
# In backend/app/core/llm_gateway.py — modified call() method

from app.security.pipeline import get_security_pipeline, SecurityContext

class LLMGateway:
    def call(
        self,
        messages: List[Dict[str, str]],
        task_type: str = "general",
        max_tokens: int = 4000,
        context: str = "",
        skip_cache: bool = False,
        stream: bool = False,
    ) -> str:
        prompt_text = messages[-1]["content"] if messages else ""

        # ── NEW: Security Pipeline (before cache check) ──────────────
        security = get_security_pipeline()
        security_ctx = SecurityContext(
            task_type=task_type,
            caller_id=None,  # Set from request context if available
            session_id=None,
            ip_address=None,
        )
        
        secured = security.process_outbound(
            messages=messages,
            context=context,
            security_context=security_ctx,
        )
        # Use secured payload for all downstream operations
        messages = secured.messages
        context = secured.context
        mask_registry = secured.mask_registry
        # ─────────────────────────────────────────────────────────────

        # Step 1: Check cache (existing logic, unchanged)
        if not skip_cache and not stream:
            cache = get_cache()
            cached = cache.get(prompt_text, context, task_type)
            if cached is not None:
                self._track_cost(0, 0, "cache_hit")
                return cached

        # ... existing model selection, budget, invocation logic ...

        # ── NEW: Unmask response before returning ────────────────────
        response = security.process_inbound(response, mask_registry)
        # ─────────────────────────────────────────────────────────────

        return response
```

### Configuring Security via Environment Variables

```python
# In backend/.env
SECURITY_INJECTION_DETECTION=true
SECURITY_JAILBREAK_DETECTION=true
SECURITY_DATA_MASKING=true
SECURITY_MASK_AWS_CREDENTIALS=true
SECURITY_MASK_PII=true
SECURITY_MASK_INTERNAL_IPS=true
SECURITY_ENTROPY_THRESHOLD=4.5
SECURITY_INJECTION_BLOCK_THRESHOLD=0.7
SECURITY_STRICT_SCOPE=true
SECURITY_TRUSTED_COLLECTIONS=infra_documents,terraform_best_practices
SECURITY_AUDIT_LOG=true
SECURITY_AUDIT_RETENTION_DAYS=90
SECURITY_MAX_MESSAGE_LENGTH=10000
```

### Using the Data Masker Standalone

```python
from app.security.data_masker import DataMasker, MASK_RULES

masker = DataMasker(rules=MASK_RULES)

# Mask sensitive content before sending to LLM
messages = [
    {"role": "user", "content": "Deploy to vpc-12345 with key AKIAIOSFODNN7EXAMPLE"}
]

result = masker.mask_messages(messages)
# result.masked_messages[0]["content"] == 
#   "Deploy to [MASKED_INTERNAL_1] with key [MASKED_AWS_KEY_1]"
# result.registry can unmask the response later

# After LLM responds with masked tokens, restore them
llm_response = "I'll configure [MASKED_INTERNAL_1] with the provided credentials"
final = masker.unmask_response(llm_response, result.registry)
# final == "I'll configure vpc-12345 with the provided credentials"
```

### RAG Trust Validation Integration

```python
# In backend/app/services/rag_service.py — modified query() method

from app.security.trust_validator import get_trust_validator

class RAGService:
    def query(self, query: str) -> Dict:
        # ... existing retrieval logic ...
        results = self._search_qdrant(query)
        
        # NEW: Validate trust before using results
        trust_validator = get_trust_validator()
        trust_result = trust_validator.validate_retrieval(results, query)
        
        if trust_result.injection_detected:
            logger.warning(f"[RAG] Injection detected in retrieved chunks!")
            # Use only trusted chunks
            results = trust_result.trusted_chunks
        else:
            results = trust_result.trusted_chunks
        
        # Continue with only trusted results...
        return self._synthesize_response(results, query)
```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: No Sensitive Data Leakage

*For any* text containing AWS Account IDs, AWS ARNs, email addresses, private IP addresses, password patterns, phone numbers, credit card numbers, or AWS access keys, the Data_Masker output SHALL contain zero matches against any corresponding detection pattern.

**Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8**

### Property 2: Mask Roundtrip Reversibility

*For any* text containing sensitive data, masking with the Data_Masker and then unmasking the result using the corresponding Mask_Registry SHALL produce the exact original text.

**Validates: Requirements 2.9, 2.10, 14.1**

### Property 3: Injection Score Bounds

*For any* input text string, the Input_Sanitizer SHALL produce an Injection_Score that is a numeric value between 0 and 100 inclusive.

**Validates: Requirements 1.1**

### Property 4: High-Score Injection Rejection

*For any* text where the computed Injection_Score exceeds 70, the Input_Sanitizer SHALL reject the request and not allow the text to proceed to the LLM.

**Validates: Requirements 1.2**

### Property 5: Low-Score Text Passthrough

*For any* text where the computed Injection_Score is below 30, the Input_Sanitizer SHALL output the text without modification (identical to input after Unicode normalization).

**Validates: Requirements 1.4**

### Property 6: Idempotent Sanitization

*For any* message list, applying the Input_Sanitizer twice SHALL produce the same result as applying it once. Formally: `sanitize(sanitize(M)) == sanitize(M)`.

**Validates: Requirements 1.3, 1.6**

### Property 7: Unicode Normalization and Zero-Width Removal

*For any* input text containing non-NFKC Unicode or zero-width characters, the Input_Sanitizer output SHALL be in NFKC normal form and contain no zero-width characters.

**Validates: Requirements 1.6**

### Property 8: Injection Pattern Detection Completeness

*For any* text containing a known injection pattern (role override, delimiter escape, data exfiltration, encoding attack, or jailbreak roleplay) at severity >= MEDIUM, the Input_Sanitizer SHALL detect it and produce a non-zero Injection_Score.

**Validates: Requirements 1.5, 9.3**

### Property 9: Scope Isolation

*For any* task type T and data with category C where C is not in T's allowed_data_categories, the Scope_Validator SHALL remove that data from the context passed to the LLM. In particular, no task type SHALL ever access data categorized as "secrets" or "credentials".

**Validates: Requirements 10.1, 10.2, 10.3**

### Property 10: Trust Filtering Correctness

*For any* set of retrieved chunks, the Trust_Validator SHALL only include chunks in trusted_chunks that satisfy ALL of: (a) originate from a collection in the trusted collections list, (b) have a valid document hash when hash verification is enabled, and (c) contain no detected injection patterns.

**Validates: Requirements 11.1, 11.2, 11.3**

### Property 11: Audit Completeness

*For any* call to process_outbound(), the Security_Pipeline SHALL produce exactly one SecurityAuditEntry, regardless of whether the outcome is allowed, blocked, or errored.

**Validates: Requirements 7.1, 12.3**

### Property 12: Fail-Closed on Exception

*For any* unexpected exception raised by any security component during pipeline processing, the Security_Pipeline SHALL block the request entirely and never send unprotected data to the LLM.

**Validates: Requirements 12.2**

### Property 13: Original Message Immutability

*For any* message list passed to the Security_Pipeline, the original list and its contents SHALL remain unchanged after pipeline processing (deep copy used internally).

**Validates: Requirements 12.4**

### Property 14: Terraform Severity Classification

*For any* generated HCL containing hardcoded secrets, wildcard IAM, or missing encryption, the Terraform_Scanner SHALL classify them as CRITICAL. For open CIDRs, public S3, or unencrypted storage, it SHALL classify as HIGH. For default VPC or missing tags, it SHALL classify as MEDIUM.

**Validates: Requirements 4.1, 4.2, 4.3**

### Property 15: Critical Violation Auto-Fix

*For any* generated HCL containing a CRITICAL severity violation, the Terraform_Scanner auto-fix output SHALL not contain that same CRITICAL violation pattern.

**Validates: Requirements 4.4**

### Property 16: Confidence Gate Triggering

*For any* set of vision analysis components where at least one component has confidence below 0.40, OR more than 3 components have confidence below 0.65, the Confidence_Gate SHALL set the job status to "needs_review" and record the triggering components.

**Validates: Requirements 5.1, 5.2, 5.3**

### Property 17: Resource Quota Enforcement

*For any* generation request specifying more than 50 EC2 instances, more than 1000 GB storage, more than 100 total resources, or estimated monthly cost exceeding $5000, the Resource_Quota_Validator SHALL reject the request and identify which specific limit was exceeded.

**Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5**

### Property 18: Rate Limit Response Format

*For any* request that exceeds a rate limit, the Rate_Limiter SHALL return HTTP 429 with a Retry-After header containing a positive integer representing seconds until the limit resets.

**Validates: Requirements 3.7**

### Property 19: Configuration Flag Bypass

*For any* security feature with its configuration flag set to false, the Security_Pipeline SHALL skip that security check entirely and not modify the request based on that check.

**Validates: Requirements 13.2**

### Property 20: Consistent Mask Tokens for Repeated Values

*For any* text where the same sensitive value appears multiple times, the Data_Masker SHALL use the same mask token for all occurrences of that value within the same request.

**Validates: Requirements 14.4**

### Property 21: Jailbreak Blocking Threshold

*For any* text where the Guardrail_Engine computes a jailbreak confidence score at or above 0.7, the engine SHALL block the request and return a generic safe message rather than processing it.

**Validates: Requirements 9.1**

### Property 22: HCL Vulnerability Detection

*For any* generated HCL containing deprecated provider arguments, TLS versions below 1.2, missing encryption in transit, or publicly exposed database endpoints, the Vulnerability_Scanner SHALL detect and report the violation.

**Validates: Requirements 8.2, 8.3, 8.4, 8.5**

## Error Handling

### Error Scenario 1: Prompt Injection Detected

**Condition**: Input sanitizer detects injection patterns with threat level >= HIGH
**Response**: Request is immediately rejected with HTTP 400 and a generic error message (no details about which pattern triggered to avoid attacker feedback)
**Recovery**: Caller receives `SecurityError` with audit ID for investigation. The request is logged with full details in the security audit log (internal only).

### Error Scenario 2: Jailbreak Attempt Blocked

**Condition**: Guardrail engine detects jailbreak with confidence >= 0.7
**Response**: Request is blocked. Response returns a safe, generic message: "I can only help with infrastructure and Terraform-related questions."
**Recovery**: Incident is logged. If same session triggers 3+ jailbreak detections, the session is rate-limited for 15 minutes.

### Error Scenario 3: Scope Violation

**Condition**: Task type attempts to access data outside its permission boundary
**Response**: The offending data is silently removed from context (not sent to LLM). Request proceeds with reduced context.
**Recovery**: Scope violation is logged as a warning. No user-facing error unless ALL context is removed, in which case a generic "insufficient context" error is returned.

### Error Scenario 4: RAG Trust Validation Failure

**Condition**: All retrieved chunks fail trust validation (untrusted sources or injection detected)
**Response**: RAG query returns empty results with a message: "No verified sources found for this query."
**Recovery**: If injection is detected in stored chunks, an alert is raised for admin review. The affected collection is flagged for re-verification.

### Error Scenario 5: Masking Failure (Defensive)

**Condition**: Data masker encounters an unexpected error during masking
**Response**: The entire request is BLOCKED (fail-closed). No data is sent to the LLM.
**Recovery**: Error is logged with full stack trace. The system does NOT fall back to sending unmasked data.

## Testing Strategy

### Unit Testing Approach

Each security component is tested independently with comprehensive test suites:

- **Input Sanitizer**: Test against a corpus of 200+ known injection patterns, plus benign infrastructure prompts to verify low false-positive rate (<2%)
- **Data Masker**: Test with synthetic data containing AWS keys, API tokens, emails, IPs. Verify 100% detection rate for known formats. Test mask/unmask roundtrip integrity.
- **Guardrail Engine**: Test against known jailbreak datasets (DAN variants, role-play exploits). Verify blocking rate >95% on known attacks, <2% false positives on legitimate prompts.
- **Scope Validator**: Test each task type against all permission boundaries. Verify no privilege escalation paths exist.
- **Trust Validator**: Test with mock Qdrant results containing trusted, untrusted, and injected chunks.

### Property-Based Testing Approach

**Property Test Library**: `hypothesis` (Python)

Key properties to test with random generation:
- **Mask Roundtrip**: For any string S, `unmask(mask(S), registry) == S` (using `hypothesis.strategies.text()`)
- **Sanitization Idempotency**: `sanitize(sanitize(M)) == sanitize(M)` (using generated message lists)
- **Entropy Bounds**: For any string, `0.0 <= entropy(S) <= 8.0`
- **No Leakage**: For any generated AWS key pattern, masking always replaces it (using `hypothesis.strategies` with AWS key format)

### Integration Testing Approach

- End-to-end test: Send requests through the full `LLMGateway.call()` with security enabled, verify no sensitive data appears in mocked LLM invocations
- RAG pipeline test: Index a document with known content, inject a malicious chunk, verify trust validator filters it
- Performance test: Verify security pipeline adds <50ms latency to the gateway call path

## Performance Considerations

- **Latency Budget**: The entire security pipeline must complete in <50ms for the common case (no threats detected). Pattern matching uses pre-compiled regex. Entropy calculation is O(n) per segment.
- **Memory**: MaskRegistry is lightweight (dict of string→string). For a typical request with 5 masked values, registry is <1KB. Registry is garbage-collected after request completes.
- **Caching Interaction**: Security processing happens BEFORE the cache check on the prompt text. This means cached responses bypass the full pipeline on subsequent calls (only the cache key computation uses the original prompt). However, the response unmasking still applies to cached responses if the mask registry differs.
- **Pattern Compilation**: All regex patterns are compiled once at module load time (`re.compile()`). No runtime compilation.
- **Async Compatibility**: The security pipeline is synchronous (CPU-bound regex/entropy). It runs in the same thread as the gateway call. For streaming responses, masking is applied per-chunk.

## Security Considerations

- **Fail-Closed Design**: If any security component raises an unexpected exception, the request is BLOCKED. The system never falls back to sending unmasked/unsanitized data.
- **No Security Through Obscurity**: The system does not rely on hiding patterns from attackers. Even if an attacker knows the exact regex patterns, the multi-layer approach (sanitization + guardrails + masking + scope + trust) provides defense in depth.
- **Audit Trail**: Every security decision is logged with timestamp, action, threats detected, and outcome. Logs are retained for 90 days (configurable). Audit logs themselves never contain the actual sensitive data — only masked references.
- **Configuration Security**: Security configuration (thresholds, patterns, trusted collections) is loaded from environment variables and cannot be modified at runtime via API.
- **Rate Limiting**: Sessions that trigger repeated security violations are progressively rate-limited (3 violations → 15min cooldown, 10 violations → 1hr block).
- **No Sensitive Data in Logs**: The security system ensures that even error logs and stack traces do not contain unmasked sensitive values. The masker runs before any logging of message content.

## Dependencies

| Dependency | Purpose | Version |
|-----------|---------|---------|
| `re` (stdlib) | Regex pattern matching for injection/secret detection | Python 3.11+ |
| `hashlib` (stdlib) | SHA-256 hashing for audit trails and document integrity | Python 3.11+ |
| `unicodedata` (stdlib) | Unicode normalization (NFKC) for homoglyph attack prevention | Python 3.11+ |
| `pydantic` | Security configuration validation and data models | ^2.0 |
| `pydantic-settings` | Environment-based security config loading | ^2.0 |
| `hypothesis` | Property-based testing for security invariants | ^6.0 (dev) |
| `qdrant-client` | Trust validation queries against vector DB | existing |
| `sentence-transformers` | Relevance scoring for trust validation | existing |

No new external dependencies are required beyond what the project already uses. The security system is built entirely on Python stdlib + existing project dependencies.
