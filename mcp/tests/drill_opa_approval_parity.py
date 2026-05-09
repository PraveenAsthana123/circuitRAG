# RESOURCES: readonly
"""
Drill: OPA + inline approval engines produce IDENTICAL decisions.

When DOCUMIND_APPROVAL_ENGINE=opa flips the default, this drill is the
gate. If parity breaks, the flag MUST stay on inline.

Steps
=====
1. positive: opa binary on PATH and policy.rego parses
2. positive: inline AUTO_APPROVED case matches OPA
3. positive: blocked action — both DENY
4. positive: human_required action — both HUMAN_REQUIRED
5. positive: high risk — both HUMAN_REQUIRED
6. positive: tests fail — both REVISION_REQUIRED
7. positive: confidence below min — both REVISION_REQUIRED
8. NEGATIVE: cross-product sample of 12 inputs ALL match between engines
9. NEGATIVE: OPA fallback — when policy.rego is moved aside, agent.decide
   falls back to inline and logs a warning (no crash)
"""
from __future__ import annotations

import sys
from itertools import product
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from approval_agent import agent as approval_agent  # noqa: E402
from approval_agent import opa_client  # noqa: E402
from approval_agent.agent import decide  # noqa: E402

GREEN = "\033[32m"
RED = "\033[31m"
BOLD = "\033[1m"
NC = "\033[0m"


def step(t): print(f"\n{BOLD}── {t} ──{NC}")
def ok(m): print(f"  {GREEN}✓ {m}{NC}")
def fail(m):
    print(f"  {RED}✗ {m}{NC}")
    raise SystemExit(1)


CASES = [
    # (label, task_kwargs, test_result, conf, expected)
    ("low/auto", {"action": "recommendation", "type": "documentation_update",
                  "risk": "low"}, "PASS", 0.9, "AUTO_APPROVED"),
    ("blocked", {"action": "delete_history", "type": "delete",
                 "risk": "low"}, "PASS", 0.9, "DENY"),
    ("human-action", {"action": "code_merge", "type": "code_merge",
                      "risk": "low"}, "PASS", 0.9, "HUMAN_REQUIRED"),
    ("high-risk", {"action": "recommendation", "type": "documentation_update",
                   "risk": "high"}, "PASS", 0.9, "HUMAN_REQUIRED"),
    ("test-fail", {"action": "recommendation", "type": "documentation_update",
                   "risk": "low"}, "FAIL", 0.9, "REVISION_REQUIRED"),
    ("low-conf", {"action": "recommendation", "type": "documentation_update",
                  "risk": "low"}, "PASS", 0.5, "REVISION_REQUIRED"),
]


def _both(case):
    label, t, tr, cf, expected = case
    inline = decide(task={"id": "T", **t},
                    test_result=tr, confidence=cf,
                    engine="inline").decision
    opa = decide(task={"id": "T", **t},
                 test_result=tr, confidence=cf,
                 engine="opa").decision
    return label, inline, opa, expected


def main() -> int:
    step("1. opa binary on PATH and policy.rego parses")
    if not opa_client.opa_available():
        fail(f"opa unavailable; bin={opa_client.OPA_BINARY} "
             f"policy={opa_client.POLICY_PATH}")
    # Smoke: minimal eval to confirm policy parses
    try:
        opa_client.evaluate(
            task={"action": "recommendation", "type": "documentation_update",
                  "risk": "low"},
            test_result="PASS", governance_result="ALLOW",
            reviewer_decision="APPROVED", confidence=0.9,
        )
    except opa_client.OpaError as e:
        fail(f"policy.rego does not eval cleanly: {e}")
    ok(f"opa {opa_client.OPA_BINARY} loads policy.rego")

    for i, case in enumerate(CASES, start=2):
        step(f"{i}. {case[0]} — both engines agree on {case[-1]}")
        label, inline, opa, expected = _both(case)
        if inline != expected:
            fail(f"inline gave {inline}, expected {expected}")
        if opa != expected:
            fail(f"opa gave {opa}, expected {expected}")
        if inline != opa:
            fail(f"PARITY BROKEN: inline={inline}  opa={opa}")
        ok(f"both backends → {expected}")

    step("8. NEGATIVE — 12-input cross-product: every result matches")
    actions = ["recommendation", "code_merge"]
    risks = ["low", "medium", "high"]
    confs = [0.5, 0.9]
    types_ = ["documentation_update"]
    mismatches = []
    for action, risk, conf, type_ in product(actions, risks, confs, types_):
        t = {"id": "X", "action": action, "type": type_, "risk": risk}
        i = decide(task=t, confidence=conf, engine="inline").decision
        o = decide(task=t, confidence=conf, engine="opa").decision
        if i != o:
            mismatches.append((t, conf, i, o))
    if mismatches:
        fail(f"{len(mismatches)} mismatch(es); first: {mismatches[0]}")
    ok("all 12 inputs match between inline + opa")

    step("9. NEGATIVE — fallback when policy missing: inline still works")
    saved = approval_agent.APPROVAL_ENGINE
    approval_agent.APPROVAL_ENGINE = "opa"
    # Move policy aside temporarily
    real_path = opa_client.POLICY_PATH
    aside = real_path.with_suffix(".rego.disabled")
    try:
        real_path.rename(aside)
        result = decide(
            task={"id": "T", "action": "recommendation",
                  "type": "documentation_update", "risk": "low"},
            test_result="PASS", confidence=0.9, engine="opa",
        )
        # Should fall back to inline → AUTO_APPROVED
        if result.decision != "AUTO_APPROVED":
            fail(f"fallback didn't reach inline; got {result.decision}")
        if "opa:" in result.reason:
            fail(f"reason claims opa-source despite missing policy: {result.reason}")
    finally:
        if aside.exists():
            aside.rename(real_path)
        approval_agent.APPROVAL_ENGINE = saved
    ok("opa unavailable → graceful fallback to inline")

    print(f"\n{BOLD}{GREEN}ALL 9 OPA-PARITY STEPS PASSED{NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
