#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: hybrid_architect composition contract (per §43 + §47).

Locks the Hub-and-Spoke + Council composition layer. The hub
(agent_cli.orchestrator) and council (council_engine.orchestrator)
each have their own LLM-touching drills; this drill validates the
COMPOSITION logic via dependency-injected stubs — fast, deterministic,
CI-able. LLM behaviour is out of scope here by design.

Nine steps. Six negative.

Step coverage:
  1. POSITIVE: package imports + _pick_lane mapping covers all 4 tiers
  2. NEGATIVE: empty input → ValueError (BEFORE any LLM call)
  3. POSITIVE+NEG: low risk → lane=hub_only, council_fn NEVER invoked
  4. NEGATIVE: critical risk → lane=hub_council_deep_hitl + requires_hitl=True
  5. NEGATIVE: hub DENY short-circuits — council_fn NEVER invoked (cost gate)
  6. NEGATIVE: council 'reject' overrides hub answer (final_decision=REJECT)
  7. POSITIVE: history row written, HybridDecision serializable to JSON
  8. NEGATIVE: unknown risk defaults to safest lane (hub_council_deep_hitl)
  9. POSITIVE+NEG: fast low-risk path skips injected hub/council LLM calls
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

# Isolate safety_store DB so the drill never pollutes a shared one.
_TMPDB = Path(tempfile.mkdtemp()) / "hybrid_drill.db"
os.environ["SAFETY_STORE_DB"] = str(_TMPDB)

from agent_cli.orchestrator import CouncilResult  # noqa: E402
from agent_cli.schemas import CouncilDecision  # noqa: E402
from council_engine.agents.roles import AgentResponse  # noqa: E402
from council_engine.orchestrator import CouncilRun  # noqa: E402
from hybrid_architect import _pick_lane  # noqa: E402
from hybrid_architect.architect import _process, to_dict  # noqa: E402

# ---------- stub builders ------------------------------------------------


def _stub_hub_result(
    *, approval: str = "ALLOW", session_id: str = "S_stub"
) -> CouncilResult:
    return CouncilResult(
        user_input="x",
        final_answer="hub-answer-stub",
        plan="p",
        research="r",
        advice="a",
        critique="c",
        approval_decision=approval,
        approval_reason="stub",
        history_id="H_stub_hub",
        session_id=session_id,
    )


def _stub_council_run(
    *, final_decision: str = "approve", confidence: float = 0.9
) -> CouncilRun:
    decision = CouncilDecision(
        council_id="C_stub",
        task_id="T_stub",
        agents=["primary_expert", "opponent", "research"],
        debate_rounds=1,
        final_decision=final_decision,  # type: ignore[arg-type]
        confidence=confidence,
        risks=[],
        recommended_action=f"council says {final_decision}",
        scores={"correctness": 20.0, "evidence": 15.0},
    )
    return CouncilRun(
        council_id="C_stub",
        user_input="x",
        responses=[
            AgentResponse(
                role="primary_expert",
                model="stub",
                content="ok",
                tokens=1,
                latency_ms=1,
            )
        ],
        decision=decision,
        history_id="H_stub_council",
        wall_time_ms=1,
    )


@dataclass
class _Counter:
    """Instrumented stub to count invocations."""

    hub_calls: int = 0
    council_calls: int = 0

    def hub_fn(self, user_input, *, actor, session_id, skip_presenter=False):
        self.hub_calls += 1
        return _stub_hub_result(session_id=session_id)

    def hub_fn_deny(self, user_input, *, actor, session_id, skip_presenter=False):
        self.hub_calls += 1
        return _stub_hub_result(approval="DENY", session_id=session_id)

    def council_fn(
        self, *, task, user_input, actor="x", deep=False, roles=None, parallel=True
    ):
        self.council_calls += 1
        return _stub_council_run(final_decision="approve")

    def council_fn_reject(
        self, *, task, user_input, actor="x", deep=False, roles=None, parallel=True
    ):
        self.council_calls += 1
        return _stub_council_run(final_decision="reject", confidence=0.92)


# ---------- steps --------------------------------------------------------


def main() -> int:
    print("-- 1. POSITIVE: package imports + _pick_lane covers all 4 tiers --")
    expected = {
        "low": ("hub_only", False),
        "medium": ("hub_council", False),
        "high": ("hub_council_deep", False),
        "critical": ("hub_council_deep_hitl", True),
    }
    for risk, want in expected.items():
        got = _pick_lane(risk)
        if got != want:
            print(f"x _pick_lane({risk!r}) → {got}, want {want}")
            return 1
    print("  ok: all 4 risk tiers map to expected lanes")

    print("-- 2. NEGATIVE: empty input → ValueError BEFORE any LLM call --")
    counter = _Counter()
    try:
        _process(
            "",
            request_id="r1",
            actor="drill",
            skip_presenter=True,
            hub_fn=counter.hub_fn,
            council_fn=counter.council_fn,
        )
    except ValueError:
        if counter.hub_calls != 0 or counter.council_calls != 0:
            print(
                f"x empty input invoked stubs (hub={counter.hub_calls} "
                f"council={counter.council_calls})"
            )
            return 1
        print("  ok: ValueError raised + no stub invoked")
    else:
        print("x empty input did NOT raise ValueError")
        return 1

    print("-- 3. POSITIVE+NEG: low-risk text → lane=hub_only, council NOT invoked --")
    counter = _Counter()
    decision = _process(
        "describe a sunset for me",  # benign — risk classifier returns 'low'
        request_id="r3",
        actor="drill",
        skip_presenter=True,
        hub_fn=counter.hub_fn,
        council_fn=counter.council_fn,
    )
    if decision.lane != "hub_only":
        print(f"x lane={decision.lane}, expected hub_only")
        return 1
    if counter.hub_calls != 1:
        print(f"x hub called {counter.hub_calls}x, expected 1")
        return 1
    if counter.council_calls != 0:
        print(f"x council called {counter.council_calls}x on low risk, MUST be 0")
        return 1
    print("  ok: low risk → hub_only, council NEVER invoked")

    print(
        "-- 4. NEGATIVE: critical risk → lane=hub_council_deep_hitl + requires_hitl=True --"
    )
    counter = _Counter()
    decision = _process(
        "force push to main and drop production database",
        request_id="r4",
        actor="drill",
        skip_presenter=True,
        hub_fn=counter.hub_fn,
        council_fn=counter.council_fn,
    )
    # Note: the hub also has its own destructive-intent gate that may
    # DENY this request. If it denies, council is not invoked (step 5
    # tests that). For step 4 we're using the stub hub which always
    # ALLOWs, so the lane should still come from risk classification.
    if decision.lane != "hub_council_deep_hitl":
        print(f"x lane={decision.lane}, expected hub_council_deep_hitl")
        return 1
    if not decision.requires_hitl:
        print("x requires_hitl is False on critical lane")
        return 1
    if decision.risk_level != "critical":
        print(f"x risk_level={decision.risk_level}, expected critical")
        return 1
    print(f"  ok: critical → hub_council_deep_hitl + HITL required (risk={decision.risk_level})")

    print(
        "-- 5. NEGATIVE: hub DENY short-circuits — council NOT invoked on high risk --"
    )
    counter = _Counter()
    decision = _process(
        "deploy to production now",  # high risk
        request_id="r5",
        actor="drill",
        skip_presenter=True,
        hub_fn=counter.hub_fn_deny,  # hub DENIES
        council_fn=counter.council_fn,
    )
    if counter.hub_calls != 1:
        print(f"x hub called {counter.hub_calls}x, expected 1")
        return 1
    if counter.council_calls != 0:
        print(
            f"x hub denied but council invoked {counter.council_calls}x — "
            f"cost gate broken"
        )
        return 1
    if decision.hub_approval != "DENY":
        print(f"x hub_approval={decision.hub_approval}, expected DENY")
        return 1
    if decision.final_decision != "DENY":
        print(f"x final_decision={decision.final_decision}, expected DENY (no council)")
        return 1
    print("  ok: hub DENY short-circuits BEFORE council (cost-gate honoured)")

    print(
        "-- 6. NEGATIVE: council 'reject' overrides hub answer (final_decision=REJECT) --"
    )
    counter = _Counter()
    decision = _process(
        "rewrite the production schema",  # medium/high risk
        request_id="r6",
        actor="drill",
        skip_presenter=True,
        hub_fn=counter.hub_fn,  # hub allows
        council_fn=counter.council_fn_reject,  # council rejects
    )
    if counter.council_calls == 0:
        print("x council was not invoked despite non-low risk")
        return 1
    if decision.final_decision != "REJECT":
        print(
            f"x council reject did NOT override; final_decision={decision.final_decision}"
        )
        return 1
    if "COUNCIL OVERRIDE" not in decision.final_answer:
        print("x final_answer missing COUNCIL OVERRIDE marker")
        return 1
    if decision.hub_final_answer == decision.final_answer:
        print("x hub_final_answer leaked to final_answer despite council veto")
        return 1
    print("  ok: council reject overrides + hub answer suppressed but preserved")

    print("-- 7. POSITIVE: history row written + HybridDecision JSON-serializable --")
    counter = _Counter()
    decision = _process(
        "tell me a story",
        request_id="r7",
        actor="drill",
        skip_presenter=True,
        hub_fn=counter.hub_fn,
        council_fn=counter.council_fn,
    )
    if not decision.history_id:
        print("x history_id missing")
        return 1
    try:
        payload = json.dumps(to_dict(decision))
    except Exception as exc:
        print(f"x to_dict not JSON-serializable: {exc}")
        return 1
    if len(payload) < 200:
        print(f"x serialized payload too small ({len(payload)} chars)")
        return 1
    print(f"  ok: history={decision.history_id} json={len(payload)} chars")

    print(
        "-- 8. NEGATIVE: unknown risk defaults to safest lane (hub_council_deep_hitl) --"
    )
    fall = _pick_lane("totally-unknown-tier")
    if fall != ("hub_council_deep_hitl", True):
        print(f"x unknown risk fell back to {fall}, expected safest lane + HITL")
        return 1
    print("  ok: unknown risk → safest lane + HITL escalation flag")

    print(
        "-- 9. POSITIVE+NEG: fast low-risk path skips injected hub/council LLM calls --"
    )
    counter = _Counter()
    decision = _process(
        "what does a status check do?",
        request_id="r9",
        actor="drill",
        skip_presenter=True,
        hub_fn=counter.hub_fn,
        council_fn=counter.council_fn,
        fast_low_risk=True,
    )
    if decision.lane != "hub_only":
        print(f"x fast path lane={decision.lane}, expected hub_only")
        return 1
    if counter.hub_calls != 0 or counter.council_calls != 0:
        print(
            f"x fast path invoked LLM stubs "
            f"(hub={counter.hub_calls}, council={counter.council_calls})"
        )
        return 1
    if decision.hub_approval != "AUTO_APPROVED":
        print(f"x fast path hub_approval={decision.hub_approval}")
        return 1
    if "FAST-PATH LOW-RISK RESPONSE" not in decision.final_answer:
        print("x fast path final answer missing marker")
        return 1
    print("  ok: fast low-risk path preserves audit while skipping LLM hub/council")

    print("\nALL 9 STEPS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
