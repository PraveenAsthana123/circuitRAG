# RESOURCES: readonly
"""
Drill: risk classifier — keyword + action + type floors.

Negative assertions: destructive verbs ALWAYS classify critical;
benign tasks NEVER over-classify; max-of-floors semantics holds.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from risk_classifier import classify, classify_task  # noqa: E402

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
    step("1. benign description → low")
    r = classify(description="Add a docstring to the route() function")
    if r.level != "low":
        fail(f"benign over-classified as {r.level}; triggers={r.triggers}")
    ok(f"low (triggers={r.triggers})")

    step("2. NEGATIVE — destructive verb in description → critical")
    r = classify(description="rm -rf /var/log/audit and restart")
    if r.level != "critical":
        fail(f"destructive should be critical; got {r.level}")
    ok(f"critical (triggers={r.triggers[:2]})")

    step("3. action floor for delete_history → critical (regardless of text)")
    r = classify(action="delete_history", description="just a small thing")
    if r.level != "critical":
        fail(f"delete_history floor not respected; got {r.level}")
    ok("critical (triggers contain action_floor)")

    step("4. type floor for production_deploy → critical")
    r = classify(task_type="production_deploy", description="benign words")
    if r.level != "critical":
        fail(f"production_deploy type floor not respected; got {r.level}")
    ok("critical via type floor")

    step("5. high action — code_merge → high")
    r = classify(action="code_merge")
    if r.level != "high":
        fail(f"code_merge should be high; got {r.level}")
    ok("high via action floor")

    step("6. medium pattern — 'modify schema' → medium")
    r = classify(description="modify schema for the users table")
    if r.level != "medium":
        fail(f"modify→medium expected; got {r.level}")
    ok(f"medium (triggers={r.triggers[:1]})")

    step("7. NEGATIVE — empty inputs → low (default)")
    r = classify()
    if r.level != "low":
        fail(f"empty inputs should default low; got {r.level}")
    ok("default low")

    step("8. classify_task convenience: max(action_floor, type_floor, text)")
    r = classify_task({
        "action": "code_merge",      # high
        "type": "documentation_update",  # low
        "description": "rm -rf /",   # critical
        "title": "important",
    })
    if r.level != "critical":
        fail(f"max() semantics broke: text=critical should win; got {r.level}")
    ok("max-of-floors holds: critical wins over high+low")

    step("9. NEGATIVE — score is 1..4 and matches level rank")
    for level, expected_score in [("low", 1), ("medium", 2), ("high", 3), ("critical", 4)]:
        # synthesize a task that lands at each level
        if level == "critical":
            r = classify(description="rm -rf /")
        elif level == "high":
            r = classify(action="code_merge")
        elif level == "medium":
            r = classify(description="modify schema")
        else:
            r = classify()
        if r.score != expected_score:
            fail(f"level={r.level} but score={r.score}, expected {expected_score}")
    ok("score matches level rank for all 4 tiers")

    step("10. NEGATIVE — classifier never returns level outside the closed set")
    for case in [
        {"description": "do whatever"},
        {"action": "unknown_action"},
        {"task_type": "unknown_type"},
        {"description": "x" * 5000},
    ]:
        r = classify(**case)
        if r.level not in {"low", "medium", "high", "critical"}:
            fail(f"unexpected level={r.level} for case={case}")
    ok("level is always in {low, medium, high, critical}")

    print(f"\n{BOLD}{GREEN}ALL 10 RISK-CLASSIFIER STEPS PASSED{NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
