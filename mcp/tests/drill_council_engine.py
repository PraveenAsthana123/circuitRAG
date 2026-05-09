# RESOURCES: ollama
"""
Drill: council engine MVP — phase 1 + 2 contract.

Steps
=====
1. when_to_council selects high-risk tasks
2. NEGATIVE: when_to_council skips low-risk tasks
3. agent role invocation produces non-empty content + latency_ms > 0
4. NEGATIVE: unknown role raises ValueError
5. judge returns weighted scores summing into a confidence in [0, 1]
6. judge fallback on bad input: never AUTO_APPROVES, always returns
   final_decision='revise' on failure (NEVER 'approve')
7. orchestrator end-to-end: run_council writes a history row + decision
   parses to CouncilDecision schema
8. NEGATIVE: scores never exceed weights (correctness ≤ 25, evidence ≤ 20, ...)
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

# isolate history DB
_TMPDB = Path(tempfile.mkdtemp()) / "council_drill.db"
os.environ["SAFETY_STORE_DB"] = str(_TMPDB)

from agent_cli.schemas import CouncilDecision  # noqa: E402
from council_engine import (  # noqa: E402
    DEFAULT_ROLES,
    DIM_WEIGHTS,
    judge,
    run_council,
    when_to_council,
)
from council_engine.agents.roles import run_role  # noqa: E402
from safety_store import history as _history_mod  # noqa: E402

_history_mod.DB_PATH = _TMPDB

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
    step("1. when_to_council selects high-risk tasks")
    if not when_to_council({"id": "T", "risk": "high"}):
        fail("high-risk task should trigger council")
    if not when_to_council({"id": "T", "type": "production_deploy", "risk": "low"}):
        fail("production_deploy type should trigger council")
    ok("high-risk + production_deploy both trigger council")

    step("2. NEGATIVE — low-risk task does NOT trigger council")
    if when_to_council({"id": "T", "risk": "low"}):
        fail("low-risk task should NOT trigger council (cost guard)")
    ok("low-risk task skipped (cost guard holds)")

    step("3. agent role: primary_expert produces non-empty content")
    try:
        resp = run_role("primary_expert", "Should we cache embeddings?")
    except Exception as e:  # noqa: BLE001
        fail(f"role call failed (Ollama down?): {e}")
    if not resp.content or len(resp.content) < 10:
        fail(f"empty/short content: {resp.content!r}")
    if resp.latency_ms <= 0:
        fail(f"latency_ms not recorded: {resp.latency_ms}")
    ok(f"primary_expert: {len(resp.content)} chars in {resp.latency_ms}ms")

    step("4. NEGATIVE — unknown role raises ValueError")
    try:
        run_role("supreme_overlord", "x")
    except ValueError:
        ok("unknown role rejected")
    else:
        fail("unknown role accepted — closed-set broken")

    step("5. judge: weighted scores → confidence in [0, 1]")
    # Build a minimal AgentResponse list — real Ollama call to the judge.
    from council_engine.agents.roles import AgentResponse
    fakes = [
        AgentResponse(role="primary_expert", model="x", content="cache always",
                      tokens=10, latency_ms=10),
        AgentResponse(role="opponent", model="x", content="cache stale risk",
                      tokens=10, latency_ms=10),
        AgentResponse(role="research", model="x", content="GPTCache pattern works",
                      tokens=10, latency_ms=10),
    ]
    j = judge(user_input="Should we cache embeddings?", agent_responses=fakes)
    if not (0.0 <= j.confidence <= 1.0):
        fail(f"confidence out of [0,1]: {j.confidence}")
    if j.final_decision not in {"approve", "approve_with_changes",
                                "revise", "reject", "escalate"}:
        fail(f"final_decision not in closed set: {j.final_decision}")
    ok(f"final={j.final_decision}  confidence={j.confidence}  scores={j.scores_pct}")

    step("6. NEGATIVE — judge fallback on bad LLM never AUTO_APPROVES")
    # We can't easily induce a real LLM failure here, so test the
    # fallback contract directly via the judge module's exception path.
    # importlib avoids name collision with the `judge` function re-exported
    # in council_engine/__init__.py.
    import importlib
    judge_module = importlib.import_module("council_engine.judge")
    saved = judge_module._llm_judge
    judge_module._llm_judge = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("simulated"))
    try:
        j2 = judge(user_input="x", agent_responses=fakes)
    finally:
        judge_module._llm_judge = saved
    if j2.final_decision != "revise":
        fail(f"fallback should be 'revise'; got {j2.final_decision}")
    if "judge_failed" not in (j2.risks[0] if j2.risks else ""):
        fail(f"fallback risks should mark judge_failed; got {j2.risks}")
    ok(f"fallback held: final={j2.final_decision} risk[0]={j2.risks[0]}")

    step("7. orchestrator end-to-end: run_council → history + CouncilDecision")
    task = {"id": "T_drill_council", "risk": "high",
            "type": "production_deploy", "title": "deploy v2"}
    run = run_council(task=task, user_input="Should we deploy v2 now?")
    if not run.history_id.startswith("HIST_"):
        fail(f"history not written: {run.history_id}")
    # Schema is the contract — re-instantiate to assert
    decision_dict = run.decision.model_dump()
    rebuilt = CouncilDecision(**decision_dict)
    if rebuilt.council_id != run.decision.council_id:
        fail("CouncilDecision round-trip failed")
    if len(rebuilt.agents) != len(DEFAULT_ROLES):
        fail(f"agents mismatch: {rebuilt.agents}")
    ok(f"council_id={run.council_id}  decision={rebuilt.final_decision}  "
       f"wall={run.wall_time_ms}ms")

    step("8. NEGATIVE — weighted score never exceeds DIM_WEIGHTS ceiling")
    for dim, weight in DIM_WEIGHTS.items():
        score = run.decision.scores.get(dim, 0.0)
        if score > weight + 0.001:  # float guard
            fail(f"dim={dim} score={score} > weight={weight}")
    total = sum(run.decision.scores.values())
    if total > 100.001:
        fail(f"sum of scores={total} exceeds 100")
    ok(f"all 6 dims within ceiling; sum={total:.2f}")

    print(f"\n{BOLD}{GREEN}ALL 8 COUNCIL-ENGINE STEPS PASSED{NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
