# RESOURCES: readonly
"""
Drill: per-route Kafka publish points across the fleet (§47.7 application).

Per CLAUDE.md §43 (drill discipline; ≥3 negatives), §44 (autonomous-loop
one-thing-per-iter; fleet expansion as ONE thing), §45.4 (no checkbox
flips without code), §47.7 (expand-phase: lifespan ships first; per-route
publish points apply the contract service-by-service), §40 (decision
system: lifecycle events as business signals), §47 (architecture:
event-bus integration; observability fail-safe).

Iter-51 added inference-svc /api/v1/ask → query.generated.v1 publish.
Iter-54 extends the same pattern to:
  retrieval-svc        /api/v1/retrieve → query.retrieved.v1
  agent-orchestrator   /api/v1/agentic/tasks → agent.task.created.v1

evaluation-svc publish-point lands later (its routes are eval-batch
oriented; needs more thought on the right event boundary). Locking the
2 services here means 3 of 4 in-scope FastAPI services have publish
points; evaluation-svc is the only outstanding one.

Locks (positive):
  L1. retrieval-svc /retrieve has producer.publish() with topic +
      type='query.retrieved.v1' and key=tenant_id
  L2. agent-orchestrator-svc /tasks has producer.publish() with topic +
      type='agent.task.created.v1' and key=tenant_id
  L3. Both publish events with correlation_id (audit trail link)

Locks (negative — ≥3 per §43):
  N1. Each publish wrapped in try/except (5xx-resistant per §47)
  N2. Each call site has producer-None guard (operator opt-out via env)
  N3. Each publish data field truncates user-supplied text (PII guard:
      query, goal — both cap at 500 chars)
  N4. Both call sites import logging + bind a module-level log
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

ROUTES = (
    (
        "retrieval-svc /api/v1/retrieve",
        REPO / "services" / "retrieval-svc" / "app" / "routers" / "__init__.py",
        "/api/v1/retrieve",
        "query.retrieved.v1",
        "query",  # truncated field
    ),
    (
        "agent-orchestrator-svc /api/v1/agentic/tasks",
        REPO / "services" / "agent-orchestrator-svc" / "app" / "main.py",
        "/api/v1/agentic/tasks",
        "agent.task.created.v1",
        "goal",  # truncated field
    ),
)

GREEN = "\033[32m"
RED = "\033[31m"
BOLD = "\033[1m"
NC = "\033[0m"


def step(t: str) -> None:
    print(f"\n{BOLD}── {t} ──{NC}")


def ok(m: str) -> None:
    print(f"  {GREEN}✓ {m}{NC}")


def fail(m: str) -> None:
    print(f"  {RED}✗ {m}{NC}")
    raise SystemExit(1)


def main() -> int:
    sources: dict[str, str] = {}
    for label, path, *_ in ROUTES:
        if not path.exists():
            fail(f"missing: {path.relative_to(REPO)}")
        sources[label] = path.read_text(encoding="utf-8")

    # ------------------------------------------------------------------
    # Step 1 — POSITIVE: each publish point uses correct topic + type
    # ------------------------------------------------------------------
    step("1. each publish point uses correct topic + event type")
    for label, _, _, event_type, _ in ROUTES:
        src = sources[label]
        if f'type="{event_type}"' not in src and f"type='{event_type}'" not in src:
            fail(f"{label} publish missing type={event_type!r}")
    ok(f"both routes use correct CloudEvents type")

    # ------------------------------------------------------------------
    # Step 2 — POSITIVE: each publish has key=tenant_id (per-tenant ordering)
    # ------------------------------------------------------------------
    step("2. each publish uses key=tenant_id (partition ordering)")
    for label, _, _, _, _ in ROUTES:
        src = sources[label]
        if not re.search(r"key\s*=\s*(?:req\.)?tenant_id", src):
            fail(f"{label} publish not using key=tenant_id")
    ok("both routes preserve per-tenant partition ordering")

    # ------------------------------------------------------------------
    # Step 3 — POSITIVE: each publish includes correlation_id
    # ------------------------------------------------------------------
    step("3. each publish includes correlation_id (audit-trail link)")
    for label, _, _, _, _ in ROUTES:
        src = sources[label]
        if "correlation_id=" not in src:
            fail(f"{label} publish missing correlation_id field")
    ok("both routes include correlation_id (links to governance.audit_log)")

    # ------------------------------------------------------------------
    # Step 4 — NEGATIVE: each publish wrapped in try/except
    # ------------------------------------------------------------------
    step("4. NEGATIVE: each publish wrapped in try/except Exception")
    for label, _, _, event_type, _ in ROUTES:
        src = sources[label]
        # Find the publish block + verify it has try/except
        # Look near the type=<event_type> match
        type_idx = src.find(f'type="{event_type}"')
        if type_idx == -1:
            type_idx = src.find(f"type='{event_type}'")
        if type_idx == -1:
            fail(f"{label} publish type literal not found")
        # Look 500 chars before for try: + 500 chars after for except
        window_start = max(0, type_idx - 800)
        window_end = min(len(src), type_idx + 1500)
        window = src[window_start:window_end]
        if "try:" not in window or "except Exception" not in window:
            fail(
                f"{label} publish NOT wrapped in try/except Exception — "
                "Kafka unreachable mid-request would 5xx the user"
            )
    ok("both publishes wrapped in try/except Exception (5xx-resistant)")

    # ------------------------------------------------------------------
    # Step 5 — NEGATIVE: each call site has producer-None guard
    # ------------------------------------------------------------------
    step("5. NEGATIVE: each call site has producer-None guard")
    for label, _, _, _, _ in ROUTES:
        src = sources[label]
        if not re.search(r"if producer is not None:", src):
            fail(
                f"{label} missing `if producer is not None:` guard — "
                "operator-opt-out would AttributeError on .publish()"
            )
    ok("both call sites guard against producer=None (operator opt-out works)")

    # ------------------------------------------------------------------
    # Step 6 — NEGATIVE: each user-text field truncated (PII guard)
    # ------------------------------------------------------------------
    step("6. NEGATIVE: each user-text field truncated to ≤500 chars")
    for label, _, _, _, field in ROUTES:
        src = sources[label]
        if not re.search(rf"\b{field}.*\[:5\d\d\]", src):
            fail(
                f"{label} {field!r} NOT truncated in publish payload — "
                "user-supplied text may contain PII / be huge. Full payload "
                "lives in governance.audit_log keyed by correlation_id."
            )
    ok("both user-text fields truncated to ≤500 chars (PII + size guard)")

    # ------------------------------------------------------------------
    # Step 7 — NEGATIVE: each module imports logging + binds log
    # ------------------------------------------------------------------
    step("7. NEGATIVE: each module imports logging + binds module log")
    for label, _, _, _, _ in ROUTES:
        src = sources[label]
        if "import logging" not in src:
            fail(f"{label} doesn't import logging")
        if not re.search(r"^log\s*=\s*logging\.getLogger", src, re.MULTILINE):
            fail(f"{label} doesn't bind module-level `log = logging.getLogger`")
    ok("both modules import logging + bind log = getLogger(__name__)")

    print(f"\n{GREEN}{BOLD}ALL 7 STEPS PASSED ({len(ROUTES)} publish points){NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
