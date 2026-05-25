"""
================================================================================
  backend/app/core/circuit_breaker.py — CIRCUIT BREAKER FOR LLM CALLS
================================================================================

PURPOSE:
  Prevents cascading failures and wasted spend when an LLM provider is down.
  Three states: CLOSED (normal) → OPEN (failing, reject calls) → HALF_OPEN (test one call).

CONNECTIONS:
  • llm_gateway.py → checks breaker state before every call
  • config.py → thresholds and cooldown settings
================================================================================
"""
import logging
import time
from enum import Enum
from typing import Dict

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"       # Normal — calls go through
    OPEN = "open"           # Failing — reject immediately, use fallback
    HALF_OPEN = "half_open" # Testing — allow one call to check recovery


class ModelCircuit:
    """Circuit breaker for a single model/provider."""

    def __init__(self, name: str, failure_threshold: int = 3, cooldown_seconds: int = 30):
        self.name = name
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.last_success_time = 0.0
        self.total_failures = 0
        self.total_successes = 0

    @property
    def is_available(self) -> bool:
        """Check if this model can accept calls."""
        if self.state == CircuitState.CLOSED:
            return True
        if self.state == CircuitState.OPEN:
            # Check if cooldown has passed → transition to HALF_OPEN
            if time.time() - self.last_failure_time > self.cooldown_seconds:
                self.state = CircuitState.HALF_OPEN
                logger.info(f"[CircuitBreaker:{self.name}] OPEN → HALF_OPEN (cooldown expired)")
                return True
            return False
        if self.state == CircuitState.HALF_OPEN:
            return True  # Allow one test call
        return False

    def record_success(self):
        """Call succeeded — reset failure count, close circuit."""
        self.failure_count = 0
        self.last_success_time = time.time()
        self.total_successes += 1
        if self.state != CircuitState.CLOSED:
            logger.info(f"[CircuitBreaker:{self.name}] → CLOSED (success)")
            self.state = CircuitState.CLOSED

    def record_failure(self, error: str = ""):
        """Call failed — increment counter, potentially open circuit."""
        self.failure_count += 1
        self.last_failure_time = time.time()
        self.total_failures += 1

        if self.state == CircuitState.HALF_OPEN:
            # Test call failed — go back to OPEN
            self.state = CircuitState.OPEN
            logger.warning(f"[CircuitBreaker:{self.name}] HALF_OPEN → OPEN (test failed: {error})")
        elif self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
            logger.warning(f"[CircuitBreaker:{self.name}] CLOSED → OPEN (failures={self.failure_count}: {error})")

    def get_status(self) -> dict:
        """Return current status for monitoring."""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "total_failures": self.total_failures,
            "total_successes": self.total_successes,
            "last_failure": self.last_failure_time,
            "last_success": self.last_success_time,
        }


# ── Global circuit breakers (one per model) ───────────────────────────────────
# Cooldowns tuned from observed Bedrock latency:
#   • Sonnet timeouts last ~3-4 min, so 120s cooldown gives the endpoint time
#     to recover without making the user wait through another timeout cycle
#     when Sonnet is in the fallback chain.
#   • Haiku is reliable; default 30s cooldown is enough.
#   • Gemini is the last-resort fallback; longer cooldown reduces flapping.
_breakers: Dict[str, ModelCircuit] = {
    "sonnet": ModelCircuit("sonnet", failure_threshold=2, cooldown_seconds=120),
    "haiku": ModelCircuit("haiku", failure_threshold=3, cooldown_seconds=30),
    "gemini": ModelCircuit("gemini", failure_threshold=3, cooldown_seconds=60),
}


def get_breaker(model: str) -> ModelCircuit:
    """Get the circuit breaker for a model."""
    if model not in _breakers:
        _breakers[model] = ModelCircuit(model)
    return _breakers[model]


def get_all_status() -> list:
    """Get status of all circuit breakers (for monitoring endpoint)."""
    return [b.get_status() for b in _breakers.values()]
