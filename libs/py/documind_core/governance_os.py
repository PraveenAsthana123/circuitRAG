"""AI Governance OS — unified policy / decision / risk / compliance / audit surface.

Per CLAUDE.md §48 (the capstone maturity item) and
docs/architecture/maturity-stack.md item #48.

§48 demands FIVE engines composed into one decision flow:

    User Request → Agent → AI-OS Policy Check → Risk Evaluation
                                            ↓
                              [Allow | Block | Human Review]
                                            ↓
                                  Execution → Audit Logging

This module is the **L1 → L2 bootstrap**: a `GovernanceOS` facade
that wraps four already-existing kernels and stubs the missing one,
so every request gets one structured `GovernanceDecision` instead
of scattered policy/audit/router calls.

What's wired (real implementations):
  - Policy Engine: wraps the orchestrator's evaluate_approval_reasons
    helper (services/agent-orchestrator-svc/app/policy.py). Same
    rules; just exposed through the OS surface.
  - Audit Engine: in-memory log of GovernanceDecision rows on app
    state. Future iterations persist to orchestration.governance_audit.

What's stubbed (honest, drilled-as-stubs):
  - Risk Engine: consumes DriftReport from `drift_detection` (last
    iteration's surface) and surfaces severity. No alert wiring or
    auto-rollback yet — those are §44 L4→L5 territory.
  - Compliance Engine: GDPR / PIPEDA / ISO 42001 / NIST AI RMF
    each return `status="not_implemented"` with the framework
    reference. Honest placeholder per §35 dashboard pattern; the
    drill asserts the stub shape so the iteration that swaps in
    real logic flips the drill green naturally.
  - Decision Engine: NOT wrapped here. model_router.route() is
    already on the hot path inside service.create_task; double-
    wrapping would risk double-routing. The OS exposes the routing
    decision read-only via the audit row's `route_decision` field.

The frozen-dataclass output schema mirrors DriftReport — same
JSON-serialization contract so dashboards, alerts, the future
Compliance Engine, and external regulators all read one shape.

Drilled by `mcp/tests/drill_governance_os_facade.py` end-to-end
through TestClient, both allow-path and block-path with audit rows
written for each.
"""

from __future__ import annotations

import datetime
import threading
import uuid
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from typing import Any, Literal

Action = Literal["allow", "block", "review"]
ComplianceStatus = Literal[
    "compliant",
    "non_compliant",
    "not_implemented",
    "not_applicable",
]


COMPLIANCE_FRAMEWORKS: tuple[str, ...] = (
    "GDPR",
    "PIPEDA",
    "ISO_42001",
    "NIST_AI_RMF",
)


@dataclass(frozen=True)
class ComplianceAttestation:
    """One framework's verdict on a single decision."""

    framework: str
    status: ComplianceStatus
    reason: str
    reference: str  # e.g. "EU AI Act Art. 86" or "ISO 42001 §6.2.1"


@dataclass(frozen=True)
class RiskAssessment:
    """Risk Engine verdict — consumes DriftReport.severity from
    `drift_detection` plus inline policy-driven risk_level."""

    overall_severity: Literal["ok", "minor", "significant", "insufficient_data", "high"]
    drift_severity: str | None  # None when no drift signal available
    inline_risk_level: str | None  # task.risk_level if known
    contributing_factors: tuple[str, ...]


@dataclass(frozen=True)
class GovernanceDecision:
    """Single structured row per governed request.

    JSON-serializable (asdict + ISO timestamp). Same shape consumed
    by dashboards, alert wiring, the future Compliance Engine, and
    regulator-export.
    """

    request_id: str
    timestamp_iso: str
    action: Action
    policy_reasons: tuple[str, ...]
    risk: RiskAssessment
    compliance_attestations: tuple[ComplianceAttestation, ...]
    decision_summary: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------
# Engine implementations
# ---------------------------------------------------------------------


class PolicyEngine:
    """Wraps the existing approval-reasons helper.

    Single source of truth; no duplicate rule logic. The orchestrator's
    service.py still calls evaluate_approval_reasons directly when
    creating a task — the OS surface here is for observability /
    audit / compliance, not for gating (gating is service-layer).
    """

    def __init__(self, evaluate_fn) -> None:  # noqa: ANN001 — pluggable
        self._evaluate = evaluate_fn

    def reasons(self, state: dict[str, Any], policy) -> list[str]:  # noqa: ANN001
        return list(self._evaluate(state, policy))


class RiskEngine:
    """Consumes DriftReport.severity + inline policy-driven risk
    flags and produces a RiskAssessment.

    Decoupled from drift_detection module so unit tests + callers
    can pass a synthesized DriftReport without a Postgres connection.
    """

    SEVERITY_RANK = {
        "insufficient_data": 0,
        "ok": 0,
        "minor": 1,
        "significant": 2,
        "high": 3,
    }

    def evaluate(
        self,
        *,
        risk_level: str | None,
        drift_severity: str | None,
        contributing_factors: Iterable[str] = (),
    ) -> RiskAssessment:
        contributing = tuple(contributing_factors)
        # Pick whichever input is highest-severity for the overall.
        candidates = [drift_severity or "ok"]
        if risk_level == "high":
            candidates.append("high")
        elif risk_level == "medium":
            candidates.append("minor")
        overall = max(
            candidates,
            key=lambda s: self.SEVERITY_RANK.get(s, 0),
        )
        return RiskAssessment(
            overall_severity=overall,  # type: ignore[arg-type]
            drift_severity=drift_severity,
            inline_risk_level=risk_level,
            contributing_factors=contributing,
        )


class ComplianceEngine:
    """Stub today; real attestation in §48 L2→L3 iteration.

    Returns `status='not_implemented'` for every framework with a
    reference to the actual specification clause. The drill asserts
    this exact shape so the future iteration that swaps in real
    logic flips the drill from `not_implemented` -> `compliant`/
    `non_compliant` naturally.

    Why stub instead of "compliant": claiming GDPR-compliant without
    a real check is a §52 honesty bug AND an EU AI Act Art. 50
    violation (false transparency). `not_implemented` is honest.
    """

    REFERENCES: dict[str, str] = {
        "GDPR": "Regulation (EU) 2016/679 Art. 22 (automated decisions)",
        "PIPEDA": "Personal Information Protection and Electronic Documents Act §5",
        "ISO_42001": "ISO/IEC 42001:2023 §6 (planning) §8 (operation)",
        "NIST_AI_RMF": "NIST AI 100-1 §3 (Govern) §4 (Map) §5 (Measure) §6 (Manage)",
    }

    def attest(self, decision_state: dict[str, Any]) -> tuple[ComplianceAttestation, ...]:
        return tuple(
            ComplianceAttestation(
                framework=name,
                status="not_implemented",
                reason=(
                    "ComplianceEngine stub at §48 L1→L2; real attestation "
                    "lands in L2→L3 iteration"
                ),
                reference=ref,
            )
            for name, ref in self.REFERENCES.items()
        )


class AuditEngine:
    """In-memory append-only log of GovernanceDecision rows.

    Single mutex around the list for thread safety under uvicorn's
    asyncio + worker threads. Future iteration persists to
    orchestration.governance_audit (DB table); the in-memory store
    is a deliberate scaffold per the L1→L2 cadence.
    """

    def __init__(self, max_rows: int = 10000) -> None:
        self._rows: list[GovernanceDecision] = []
        self._lock = threading.Lock()
        self._max = max_rows

    def log(self, decision: GovernanceDecision) -> None:
        with self._lock:
            self._rows.append(decision)
            # Bound memory; FIFO eviction of oldest rows.
            if len(self._rows) > self._max:
                del self._rows[: len(self._rows) - self._max]

    def recent(self, limit: int = 50) -> list[GovernanceDecision]:
        with self._lock:
            return list(self._rows[-limit:])

    def count(self) -> int:
        with self._lock:
            return len(self._rows)


# ---------------------------------------------------------------------
# Facade
# ---------------------------------------------------------------------


class GovernanceOS:
    """The §48 unified surface. Composes the four engines (Policy,
    Risk, Compliance, Audit) and emits one GovernanceDecision per
    governed request.

    Decision Engine is intentionally NOT here — model_router.route()
    is already on the hot path inside service.create_task; the OS
    consumes its routing decision read-only via the audit row.

    Usage from a route handler:

        decision = governance_os.evaluate(
            request_id=correlation_id,
            request_state=state_dict,
            policy=policy_view,
            drift_severity=most_recent_drift_severity_or_None,
        )
        # `decision` is observable today; gating action lives in
        # service.create_task. Future L2→L3 iteration moves the gate
        # into this method.
    """

    def __init__(
        self,
        *,
        policy_engine: PolicyEngine,
        risk_engine: RiskEngine,
        compliance_engine: ComplianceEngine,
        audit_engine: AuditEngine,
    ) -> None:
        self._policy = policy_engine
        self._risk = risk_engine
        self._compliance = compliance_engine
        self._audit = audit_engine

    @property
    def audit(self) -> AuditEngine:
        return self._audit

    def evaluate(
        self,
        *,
        request_id: str | None = None,
        request_state: dict[str, Any],
        policy,  # AgenticPolicyView
        drift_severity: str | None = None,
    ) -> GovernanceDecision:
        request_id = request_id or str(uuid.uuid4())
        timestamp = datetime.datetime.now(datetime.UTC).isoformat()

        # Policy reasons (existing rules; single source of truth).
        reasons = self._policy.reasons(request_state, policy)

        # Risk assessment.
        risk = self._risk.evaluate(
            risk_level=request_state.get("risk_level"),
            drift_severity=drift_severity,
            contributing_factors=(
                tuple(reasons) if reasons else ()
            ),
        )

        # Compliance attestations.
        attestations = self._compliance.attest(request_state)

        # Action ladder. L1→L2: report-only — block ONLY if
        # require_human_approval is already set; otherwise allow.
        # L2→L3 will move the actual gate into this method.
        if request_state.get("require_human_approval"):
            action: Action = "review"
        elif reasons:
            action = "review"
        else:
            action = "allow"

        # Hard-block when risk is critical AND there's no review path.
        if (
            risk.overall_severity in ("significant", "high")
            and not request_state.get("require_human_approval")
            and not reasons
        ):
            action = "block"
            reasons = ["risk severity is significant/high without review path"]

        decision = GovernanceDecision(
            request_id=request_id,
            timestamp_iso=timestamp,
            action=action,
            policy_reasons=tuple(reasons),
            risk=risk,
            compliance_attestations=attestations,
            decision_summary=(
                f"action={action} risk={risk.overall_severity} "
                f"policy_reasons={len(reasons)} "
                f"compliance_stubs={len(attestations)}"
            ),
        )
        self._audit.log(decision)
        return decision


def build_governance_os(*, policy_evaluate_fn) -> GovernanceOS:  # noqa: ANN001
    """Convenience factory — pass the orchestrator's
    `evaluate_approval_reasons` (or any compatible callable) and get
    a fully wired OS back.
    """
    return GovernanceOS(
        policy_engine=PolicyEngine(policy_evaluate_fn),
        risk_engine=RiskEngine(),
        compliance_engine=ComplianceEngine(),
        audit_engine=AuditEngine(),
    )
