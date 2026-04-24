"""
documind_core
=============

Shared foundation for every Python service in DocuMind.

Nothing in here imports FastAPI — these primitives are reusable for CLI tools,
Kafka consumers, and eval workers, not just HTTP services.

The shape of this package mirrors the design areas that are cross-cutting:

| Area (spec #) | Module                        | What it provides                       |
| ------------- | ----------------------------- | -------------------------------------- |
| 3, 4, 5       | :mod:`.config`                | Pydantic Settings: single source of truth for env |
| 9             | :mod:`.exceptions`            | AppError hierarchy — domain errors only |
| 62            | :mod:`.logging_config`        | Structured JSON logs with correlation_id |
| 4, Extra CB   | :mod:`.circuit_breaker`       | CLOSED/HALF_OPEN/OPEN state machine    |
| 42, 45        | :mod:`.rate_limiter`          | Sliding-window per-tenant limiter      |
| 5             | :mod:`.rls`                   | PostgreSQL RLS helpers (set_tenant)    |
| 17, 19, 20    | :mod:`.kafka_client`          | Producer + idempotent consumer base   |
| 46            | :mod:`.db_client`             | asyncpg connection pool + RLS-aware txn |
| 40            | :mod:`.cache`                 | Redis cache-aside helper               |
| 62            | :mod:`.observability`         | OpenTelemetry + Prometheus setup       |
| Trust, auth   | :mod:`.encryption`            | Fernet at-rest secret encryption       |
| 20            | :mod:`.idempotency`           | X-Idempotency-Key storage              |

Usage: each service imports what it needs. See
``services/*/app/core/dependencies.py`` for typical wiring.
"""

__version__ = "0.1.0"

from .exceptions import (
    AppError,
    NotFoundError,
    ValidationError,
    DataError,
    ModelError,
    ExternalServiceError,
    CircuitOpenError,
    TenantIsolationError,
    RateLimitedError,
    PolicyViolationError,
)
from .circuit_breaker import CircuitBreaker, State
from .breakers import (
    RetrievalCircuitBreaker,
    TokenCircuitBreaker,
    TokenCheck,
    TokenBreakerDecision,
    AgentLoopCircuitBreaker,
    AgentStopReason,
    ObservabilityCircuitBreaker,
    CognitiveCircuitBreaker,
    CognitiveDecision,
    CognitiveReading,
    CognitiveSignal,
    CognitiveInterrupt,
    RepetitionSignal,
    CitationDeadlineSignal,
    ForbiddenPatternSignal,
    LogprobConfidenceSignal,
)
from .body_limit import BodyLimitMiddleware
from .idempotency_middleware import IdempotencyMiddleware
from .ai_governance import (
    PromptInjectionDetector,
    InjectionVerdict,
    InjectionFinding,
    AdversarialInputFilter,
    PIIScanner,
    PIIFinding,
    AIExplainer,
    Explanation,
    ChunkAttribution,
    InterpretabilityTrace,
    ReasoningStep,
    ResponsibleAIChecker,
    FairnessSignal,
)

__all__ = [
    # Exceptions
    "AppError",
    "NotFoundError",
    "ValidationError",
    "DataError",
    "ModelError",
    "ExternalServiceError",
    "CircuitOpenError",
    "TenantIsolationError",
    "RateLimitedError",
    "PolicyViolationError",
    # Base breaker
    "CircuitBreaker",
    "State",
    # Specialized breakers
    "RetrievalCircuitBreaker",
    "TokenCircuitBreaker",
    "TokenCheck",
    "TokenBreakerDecision",
    "AgentLoopCircuitBreaker",
    "AgentStopReason",
    "ObservabilityCircuitBreaker",
    # Cognitive
    "CognitiveCircuitBreaker",
    "CognitiveDecision",
    "CognitiveReading",
    "CognitiveSignal",
    "CognitiveInterrupt",
    "RepetitionSignal",
    "CitationDeadlineSignal",
    "ForbiddenPatternSignal",
    "LogprobConfidenceSignal",
    # Safety middleware
    "BodyLimitMiddleware",
    "IdempotencyMiddleware",
    # AI governance — debuggability, explainability, responsibility,
    # secure-AI, interpretability
    "PromptInjectionDetector",
    "InjectionVerdict",
    "InjectionFinding",
    "AdversarialInputFilter",
    "PIIScanner",
    "PIIFinding",
    "AIExplainer",
    "Explanation",
    "ChunkAttribution",
    "InterpretabilityTrace",
    "ReasoningStep",
    "ResponsibleAIChecker",
    "FairnessSignal",
]
