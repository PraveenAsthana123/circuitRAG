# RESOURCES: none
"""
Drill: evaluation-svc /api/v1/evaluation/regression-gate compares
current vs baseline and fails the gate when any quality metric
regresses past tolerance.

Catalog gap (cited 3× across vLLM, rag-data-layers, AI-governance
gap reviews — last item on the convergence shortlist): the
evaluation service had ``/api/v1/evaluation/run`` (computes
metrics from datapoints) but no ``/regression-gate``. CI pipelines
had no way to fail a build on a quality drop.

This commit adds the gate endpoint. The drill verifies the
contract using FastAPI's TestClient — hermetic, no service-up
needed.

Negative-assertion §43-style:
 1. Baseline + identical-current → passed=True; all per-metric
    deltas are 0.0. NEGATIVE: the gate must NOT report a regression
    when nothing changed.
 2. Current within default tolerance (0.01 below baseline, tolerance
    is 0.02) → passed=True. Per-metric ``passed=True`` for that
    metric. Other metrics also passed.
 3. Current 0.05 below baseline on faithfulness → passed=False;
    ``failed_metrics`` contains "faithfulness"; other metrics still
    pass. NEGATIVE: the gate must NOT pass-overall when one metric
    fails.
 4. Custom tolerance: setting tolerance.faithfulness = 0.10 turns
    the same -0.05 drop into a passing run. Same data, different
    policy. Operator-configurable rollout envelope.
 5. Improvement (current > baseline) is always passed. NEGATIVE:
    a quality IMPROVEMENT must NOT trigger a gate fail (delta>=0
    is never below -tolerance).

Run:
    PYTHONPATH=/mnt/deepa/rag python mcp/tests/drill_eval_regression_gate.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "services" / "evaluation-svc"))

# evaluation-svc lifespan calls setup_observability which connects
# to OTLP — short-circuit before importing main.
os.environ.setdefault("DOCUMIND_OTEL_EXPORTER_OTLP_ENDPOINT", "")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import create_app  # type: ignore  # noqa: E402

GREEN = "\033[32m"; RED = "\033[31m"; BOLD = "\033[1m"; NC = "\033[0m"


def ok(msg: str) -> None:
    print(f"  {GREEN}✓ {msg}{NC}")


def fail(msg: str) -> None:
    print(f"  {RED}✗ {msg}{NC}")
    raise SystemExit(1)


def step(title: str) -> None:
    print(f"\n{BOLD}── {title} ──{NC}")


def _baseline() -> dict:
    return {
        "n": 100,
        "precision_at_k": 0.80,
        "recall": 0.75,
        "mrr": 0.65,
        "ndcg_at_10": 0.72,
        "faithfulness": 0.85,
        "answer_relevance": 0.78,
    }


def main() -> None:
    app = create_app()
    client = TestClient(app)

    step("0. health probe — service starts cleanly")
    r = client.get("/health")
    if r.status_code != 200:
        fail(f"/health returned {r.status_code}")
    ok("evaluation-svc TestClient up")

    step("1. Identical current+baseline → passed=True; all deltas=0")
    base = _baseline()
    r = client.post(
        "/api/v1/evaluation/regression-gate",
        json={"current": base, "baseline": base},
    )
    if r.status_code != 200:
        fail(f"gate returned {r.status_code}: {r.text[:200]}")
    body = r.json()
    if not body["passed"]:
        fail(f"identical run flagged as regression: {body}")
    if body["failed_metrics"]:
        fail(f"failed_metrics non-empty for identical run: {body['failed_metrics']}")
    for d in body["deltas"]:
        if d["delta"] != 0.0:
            fail(f"identical run reports non-zero delta: {d}")
        if not d["passed"]:
            fail(f"per-metric passed=False for identical run: {d}")
    ok(f"identical run → passed=True; all 6 deltas are 0")

    step("2. Current 0.01 below baseline (within default 0.02 tolerance) → passed")
    cur = dict(base)
    cur["faithfulness"] = base["faithfulness"] - 0.01
    cur["mrr"] = base["mrr"] - 0.01
    r = client.post(
        "/api/v1/evaluation/regression-gate",
        json={"current": cur, "baseline": base},
    )
    body = r.json()
    if not body["passed"]:
        fail(
            f"-0.01 drops within 0.02 tolerance flagged as regression: "
            f"{body}"
        )
    # Specific metrics pass with negative deltas.
    faith_d = next(d for d in body["deltas"] if d["metric"] == "faithfulness")
    if not faith_d["passed"] or abs(faith_d["delta"] - (-0.01)) > 1e-9:
        fail(f"faithfulness delta wrong: {faith_d}")
    ok(f"-0.01 drops within tolerance pass; faithfulness delta={faith_d['delta']:.3f}")

    step("3. Current 0.05 below baseline on faithfulness → fails gate")
    cur = dict(base)
    cur["faithfulness"] = base["faithfulness"] - 0.05  # past 0.02 tolerance
    r = client.post(
        "/api/v1/evaluation/regression-gate",
        json={"current": cur, "baseline": base},
    )
    body = r.json()
    if body["passed"]:
        fail(
            f"-0.05 faithfulness drop should fail the 0.02 tolerance gate, "
            f"but gate passed: {body}"
        )
    if "faithfulness" not in body["failed_metrics"]:
        fail(f"failed_metrics missing 'faithfulness': {body['failed_metrics']}")
    if len(body["failed_metrics"]) != 1:
        fail(
            f"only faithfulness should fail; got {body['failed_metrics']}. "
            f"Other metrics did not change."
        )
    # Negative: per-metric passed flag matches.
    faith_d = next(d for d in body["deltas"] if d["metric"] == "faithfulness")
    if faith_d["passed"]:
        fail(f"per-metric passed=True for failing faithfulness: {faith_d}")
    other_d = next(d for d in body["deltas"] if d["metric"] == "recall")
    if not other_d["passed"]:
        fail(f"unrelated metric flagged as failed: {other_d}")
    ok(f"faithfulness regression → passed=False; failed_metrics={body['failed_metrics']}")

    step("4. Custom tolerance turns the same -0.05 into a pass")
    cur = dict(base)
    cur["faithfulness"] = base["faithfulness"] - 0.05
    r = client.post(
        "/api/v1/evaluation/regression-gate",
        json={
            "current": cur,
            "baseline": base,
            # Operator allows up to -10% on faithfulness (e.g., model
            # upgrade trades faithfulness for answer_relevance).
            "tolerance": {"faithfulness": 0.10},
        },
    )
    body = r.json()
    if not body["passed"]:
        fail(
            f"-0.05 faithfulness drop with tolerance=0.10 should pass: "
            f"{body}"
        )
    faith_d = next(d for d in body["deltas"] if d["metric"] == "faithfulness")
    if faith_d["tolerance"] != 0.10:
        fail(f"per-metric tolerance not honored: {faith_d}")
    ok(f"same data + tolerance=0.10 → passed=True (operator-tunable envelope)")

    step("5. Improvement (current > baseline) always passes")
    cur = dict(base)
    for k in ("precision_at_k", "recall", "mrr", "ndcg_at_10", "faithfulness", "answer_relevance"):
        cur[k] = min(1.0, base[k] + 0.10)
    r = client.post(
        "/api/v1/evaluation/regression-gate",
        json={"current": cur, "baseline": base},
    )
    body = r.json()
    if not body["passed"]:
        fail(
            f"all-metrics-improved run flagged as regression: {body}. "
            f"A quality improvement must NEVER fail the gate."
        )
    if any(d["delta"] < 0 for d in body["deltas"]):
        fail(f"improvement run has negative deltas: {body['deltas']}")
    ok(f"improvements always pass (positive deltas across all 6 metrics)")

    print(f"\n{BOLD}{GREEN}════════════════════════════════════════{NC}")
    print(f"{BOLD}{GREEN}  ALL 5 EVAL-REGRESSION-GATE STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}════════════════════════════════════════{NC}")


if __name__ == "__main__":
    main()
