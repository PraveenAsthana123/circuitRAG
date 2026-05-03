"""Drift detection — Production Validation §44 maturity item.

Per CLAUDE.md §44 (Production Validation & Continuous Assurance) and
docs/architecture/maturity-stack.md item #44.

This module implements **decision-confidence drift detection** —
the first of three drift dimensions §44 demands:

  - **decision drift** (this module): how the model's confidence
    distribution shifts over time. PSI on confidence values from
    `orchestration.agent_tasks.confidence` between a baseline window
    and a current window.
  - data drift (future iteration 2D): input feature distribution
    shifts (no input fingerprint surface yet).
  - usage drift (future iteration 2E): per-tenant volume / pattern
    shifts (no tenant-grouping window yet).

PSI (Population Stability Index) is the industry-standard distribution-
shift measure for credit-scoring + ML monitoring:

  PSI < 0.1   no significant shift
  0.1-0.2     minor shift, monitor
  > 0.2       significant shift, investigate

The frozen-dataclass output schema is the **integration contract** —
#48 (AI Governance OS Risk Engine) consumes DriftReport rows; the
dashboard (2B) renders them; the alert wiring (2C) thresholds them.
JSON-serializable so OTel attributes, dashboard JSON, and alert
payloads all share one shape.

Honest dev-mode contract per §35 dashboard pattern: empty windows
return `severity="insufficient_data"` rather than crashing or
fabricating a score. The drill (`drill_drift_detection.py`) locks this
both-directions: A/A → no false-positive, A/B → real detection,
empty → insufficient_data.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Literal

Severity = Literal["ok", "minor", "significant", "insufficient_data"]


@dataclass(frozen=True)
class BaselineWindow:
    """Confidence-value distribution snapshot for a time window.

    Used both as the historical baseline and as the current-window
    sample. Same shape both ways so `compare_windows` can swap them.

    Fields:
        label: human-readable window identifier ("2026-04-01..04-30").
        values: raw confidence values (0.0..1.0). Sorted by caller
            for determinism if needed.
        count: len(values), cached so the dataclass is self-describing.
    """

    label: str
    values: tuple[float, ...]
    count: int

    def __post_init__(self) -> None:
        if self.count != len(self.values):
            raise ValueError(
                f"BaselineWindow count ({self.count}) != len(values) "
                f"({len(self.values)})"
            )
        for v in self.values:
            if v < 0.0 or v > 1.0:
                raise ValueError(
                    f"confidence value {v} outside [0, 1] — bug or DB corruption"
                )


@dataclass(frozen=True)
class DriftReport:
    """Structured drift result. JSON-serializable via asdict().

    #48 AI Governance OS Risk Engine consumes this; dashboards
    render it; alerts threshold on `severity`.
    """

    dimension: str  # "decision_confidence" for now; "data" / "usage" later
    baseline_label: str
    baseline_count: int
    current_label: str
    current_count: int
    psi: float | None  # None when severity=insufficient_data
    severity: Severity
    severity_reason: str
    threshold_minor: float = 0.1
    threshold_significant: float = 0.2

    def to_dict(self) -> dict:
        """JSON-serializable view; one dict per drift event in the
        decision audit / dashboard / alert payload."""
        return asdict(self)


def summarize_confidence_values(label: str, values: list[float]) -> BaselineWindow:
    """Build a BaselineWindow from raw confidence values.

    Filters None values upstream is the caller's job — confidence may
    be NULL for tasks that didn't run a router. We keep this strict so
    silent misses are visible.
    """
    cleaned = tuple(values)
    return BaselineWindow(label=label, values=cleaned, count=len(cleaned))


def compute_psi(
    baseline: BaselineWindow,
    current: BaselineWindow,
    *,
    n_buckets: int = 10,
    min_population_per_bucket: float = 1e-4,
) -> float:
    """Population Stability Index between two confidence distributions.

    PSI = sum over buckets of (cur_pct - base_pct) * ln(cur_pct / base_pct)

    `min_population_per_bucket` floors empty buckets to avoid log(0) blowup.
    Industry-standard floor; keeps PSI finite when one window has zero
    coverage in some confidence band.

    Returns 0.0 only when distributions are point-identical; non-zero
    otherwise (sampling noise produces tiny non-zero PSI even for the
    same underlying distribution, hence the 0.1 minor threshold).
    """
    if baseline.count == 0 or current.count == 0:
        # Caller should not invoke this when either window is empty;
        # `compare_windows` short-circuits to insufficient_data instead.
        # Defensive bound here: return 0 to keep return type stable.
        return 0.0

    # Fixed buckets across [0, 1] — confidence range is bounded so
    # equal-width buckets are simpler than equal-frequency.
    edges = [i / n_buckets for i in range(n_buckets + 1)]
    edges[-1] = 1.0 + 1e-9  # ensure value 1.0 falls in the last bucket

    def histogram(values: tuple[float, ...]) -> list[int]:
        counts = [0] * n_buckets
        for v in values:
            for i in range(n_buckets):
                if edges[i] <= v < edges[i + 1]:
                    counts[i] += 1
                    break
        return counts

    base_counts = histogram(baseline.values)
    cur_counts = histogram(current.values)

    base_total = sum(base_counts) or 1
    cur_total = sum(cur_counts) or 1

    psi = 0.0
    for i in range(n_buckets):
        base_pct = max(base_counts[i] / base_total, min_population_per_bucket)
        cur_pct = max(cur_counts[i] / cur_total, min_population_per_bucket)
        psi += (cur_pct - base_pct) * math.log(cur_pct / base_pct)
    return psi


def compare_windows(
    baseline: BaselineWindow,
    current: BaselineWindow,
    *,
    dimension: str = "decision_confidence",
    threshold_minor: float = 0.1,
    threshold_significant: float = 0.2,
    min_window_size: int = 30,
) -> DriftReport:
    """Compare two windows and emit a structured DriftReport.

    Severity ladder (PSI thresholds per industry standard):
        psi < threshold_minor                      -> "ok"
        threshold_minor <= psi < threshold_significant  -> "minor"
        psi >= threshold_significant               -> "significant"

    Edge cases that return severity='insufficient_data':
        - either window has 0 values
        - either window has fewer than min_window_size values
          (PSI on tiny samples is noise; default 30 mirrors central-
          limit-theorem rule of thumb for stable distribution stats)
    """
    if baseline.count == 0 or current.count == 0:
        reason = (
            f"empty window (baseline={baseline.count}, current={current.count}); "
            "drift cannot be computed"
        )
        return DriftReport(
            dimension=dimension,
            baseline_label=baseline.label,
            baseline_count=baseline.count,
            current_label=current.label,
            current_count=current.count,
            psi=None,
            severity="insufficient_data",
            severity_reason=reason,
            threshold_minor=threshold_minor,
            threshold_significant=threshold_significant,
        )

    if baseline.count < min_window_size or current.count < min_window_size:
        reason = (
            f"window below stability threshold (baseline={baseline.count}, "
            f"current={current.count}, min={min_window_size}); "
            "PSI on small samples is sampling noise"
        )
        return DriftReport(
            dimension=dimension,
            baseline_label=baseline.label,
            baseline_count=baseline.count,
            current_label=current.label,
            current_count=current.count,
            psi=None,
            severity="insufficient_data",
            severity_reason=reason,
            threshold_minor=threshold_minor,
            threshold_significant=threshold_significant,
        )

    psi = compute_psi(baseline, current)
    if psi < threshold_minor:
        severity: Severity = "ok"
        reason = f"psi={psi:.4f} < {threshold_minor} — no significant shift"
    elif psi < threshold_significant:
        severity = "minor"
        reason = f"psi={psi:.4f} in [{threshold_minor}, {threshold_significant}) — monitor"
    else:
        severity = "significant"
        reason = f"psi={psi:.4f} >= {threshold_significant} — investigate"

    return DriftReport(
        dimension=dimension,
        baseline_label=baseline.label,
        baseline_count=baseline.count,
        current_label=current.label,
        current_count=current.count,
        psi=psi,
        severity=severity,
        severity_reason=reason,
        threshold_minor=threshold_minor,
        threshold_significant=threshold_significant,
    )
