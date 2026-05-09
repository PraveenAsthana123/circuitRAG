# RESOURCES: readonly
"""
Drill: locked contracts for typed agent outputs.

Negative assertions enforce: missing required field → reject; out-of-range
confidence → reject; unknown extra field → reject; bad enum literal → reject.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from pydantic import ValidationError  # noqa: E402

from agent_cli.schemas import (  # noqa: E402
    AdvisoryOutput,
    CoderOutput,
    CouncilDecision,
    MonitoringOutput,
    PlannerOutput,
    StrategyOutput,
)

GREEN = "\033[32m"
RED = "\033[31m"
BOLD = "\033[1m"
NC = "\033[0m"


def step(t): print(f"\n{BOLD}── {t} ──{NC}")
def ok(m): print(f"  {GREEN}✓ {m}{NC}")
def fail(m):
    print(f"  {RED}✗ {m}{NC}")
    raise SystemExit(1)


def main() -> int:
    step("1. StrategyOutput accepts well-formed input")
    s = StrategyOutput(
        objective="Build RAG", approach="hybrid", decision="hybrid RAG",
        kpi=["latency<2s"], timeline="3 months",
    )
    if s.objective != "Build RAG":
        fail("StrategyOutput parse wrong")
    ok("StrategyOutput valid object created")

    step("2. NEGATIVE — StrategyOutput missing kpi (min_length=1) rejects")
    try:
        StrategyOutput(objective="x", approach="x", decision="x",
                       kpi=[], timeline="1m")
    except ValidationError:
        ok("empty kpi rejected")
    else:
        fail("empty kpi accepted")

    step("3. PlannerOutput valid")
    p = PlannerOutput(
        phases=["design", "build", "test"], timeline="4w", confidence=0.9,
    )
    if p.confidence != 0.9:
        fail("confidence wrong")
    ok(f"PlannerOutput parsed; phases={len(p.phases)}")

    step("4. NEGATIVE — PlannerOutput confidence > 1.0 rejected")
    try:
        PlannerOutput(phases=["x"], timeline="1d", confidence=1.5)
    except ValidationError:
        ok("confidence > 1.0 rejected")
    else:
        fail("out-of-range confidence accepted")

    step("5. NEGATIVE — extra field rejected (extra='forbid')")
    try:
        PlannerOutput(
            phases=["x"], timeline="1d", confidence=0.9,
            evil_field="injected",  # type: ignore[call-arg]
        )
    except ValidationError:
        ok("extra field rejected")
    else:
        fail("schema accepted unknown field — injection vector")

    step("6. AdvisoryOutput valid + trade_off dict")
    a = AdvisoryOutput(
        decision="hybrid RAG", recommendation="Go with hybrid",
        trade_off={"cost": "med", "accuracy": "high"}, confidence=0.88,
    )
    if a.trade_off["cost"] != "med":
        fail("trade_off lost")
    ok("AdvisoryOutput parsed with trade_off")

    step("7. CoderOutput valid")
    c = CoderOutput(
        task_id="T001", files_created=["a.py"],
        code_summary="impl x", tests_added=True, drill_added=True,
    )
    if not c.drill_added:
        fail("drill flag dropped")
    ok("CoderOutput valid; drill_added=True locked")

    step("8. NEGATIVE — MonitoringOutput rejects bad system_status")
    try:
        MonitoringOutput(system_status="fine")  # type: ignore[arg-type]
    except ValidationError:
        ok("bad system_status enum rejected")
    else:
        fail("invalid enum accepted")

    step("9. CouncilDecision — well-formed")
    d = CouncilDecision(
        council_id="C001", task_id="T101",
        agents=["primary_expert", "opponent", "research"],
        debate_rounds=3, final_decision="approve_with_changes",
        confidence=0.87,
        recommended_action="Proceed after adding rollback",
        scores={"correctness": 22.0, "evidence": 18.0, "risk": 16.0,
                "completeness": 12.0, "cost": 8.0, "clarity": 9.0},
    )
    if sum(d.scores.values()) > 100:
        fail("scores sum > 100 unexpected")
    ok(f"CouncilDecision parsed; sum_scores={sum(d.scores.values())}")

    step("10. NEGATIVE — CouncilDecision rejects out-of-range score")
    try:
        CouncilDecision(
            council_id="C", task_id="T", agents=["a"],
            final_decision="approve", confidence=0.9,
            recommended_action="x",
            scores={"correctness": 150.0},  # out of [0, 100]
        )
    except ValidationError:
        ok("out-of-range score rejected by validator")
    else:
        fail("score 150 accepted")

    step("11. NEGATIVE — CouncilDecision rejects bad final_decision enum")
    try:
        CouncilDecision(
            council_id="C", task_id="T", agents=["a"],
            final_decision="ship_it",  # type: ignore[arg-type]
            confidence=0.9, recommended_action="x",
        )
    except ValidationError:
        ok("bad final_decision rejected")
    else:
        fail("invalid enum accepted")

    print(f"\n{BOLD}{GREEN}ALL 11 SCHEMA STEPS PASSED{NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
