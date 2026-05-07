# RESOURCES: readonly
"""
Drill: inference-svc /api/v1/ask publishes query.generated.v1 events.

Per CLAUDE.md §43 (drill discipline; ≥3 negatives), §44 (autonomous-loop
one-thing-per-iter), §45.4 (no checkbox flips without code), §47.7
(expand-phase: lifespan ships first, route-level publish points wire on
opt-in basis), §40 (decision system: query lifecycle as business event).

Iter-50 wired the EventProducer lifespan; iter-51 is the FIRST application
of that contract. The /api/v1/ask handler now publishes a
query.generated.v1 CloudEvent on every successful ask. This drill locks:

  * The handler reads app.state.event_producer
  * The publish call uses topic + type + tenant_id + correlation_id
  * Schema fields per schemas/events/query.lifecycle.v1.json
  * Fail-safe: publish error logged, never 5xx-propagated

Locks (positive):
  L1. Source has app.state.event_producer access in /api/v1/ask
  L2. publish() call uses topic='query.lifecycle' AND type='query.generated.v1'
  L3. publish() includes data fields per schemas/events/query.lifecycle.v1.json
      (query, retrieved_chunks, prompt_version, model, tokens_*, confidence,
      latency_ms)
  L4. publish() partition key is tenant_id (per-tenant ordering)

Locks (negative — ≥3 per §43):
  N1. publish() call wrapped in try/except — observability fail-safe
      (per §47: event-bus blink doesn't 5xx the user request)
  N2. Producer-None path is handled (operator opt-out via
      DOCUMIND_KAFKA_BOOTSTRAP unset; the route still works)
  N3. tenant_id is REQUIRED before publish — never publish with empty
      tenant (downstream consumers filter by tenant; missing tenant
      breaks per-tenant ordering + RLS)
  N4. body.query truncated to ≤500 chars — full query may contain PII
      / be huge; the event is for observability, not full payload replay
      (full prompt is in governance.audit_log keyed by correlation_id)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ROUTER = REPO / "services" / "inference-svc" / "app" / "routers" / "__init__.py"
SCHEMA = REPO / "schemas" / "events" / "query.lifecycle.v1.json"

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
    if not ROUTER.exists():
        fail(f"missing: {ROUTER.relative_to(REPO)}")
    if not SCHEMA.exists():
        fail(f"missing event schema: {SCHEMA.relative_to(REPO)}")

    src = ROUTER.read_text(encoding="utf-8")

    # Locate the /api/v1/ask handler body
    ask_match = re.search(
        r'@router\.post\("/api/v1/ask".*?(?=\n@router\.post|\ndef _agent_service)',
        src, re.DOTALL,
    )
    if ask_match is None:
        fail("could not locate /api/v1/ask handler — refresh this drill")
    ask_body = ask_match.group(0)

    # ------------------------------------------------------------------
    # Step 1 — POSITIVE: handler reads app.state.event_producer
    # ------------------------------------------------------------------
    step("1. /api/v1/ask reads app.state.event_producer")
    if "event_producer" not in ask_body:
        fail(
            "/api/v1/ask handler does NOT reference event_producer; "
            "iter-50 wired the lifespan but iter-51's route hookup is missing"
        )
    if "request.app.state" not in ask_body:
        fail(
            "/api/v1/ask doesn't access via request.app.state — the lifespan "
            "stashes the producer there; route must read from there too"
        )
    ok("/api/v1/ask reads app.state.event_producer (lifespan-route handoff)")

    # ------------------------------------------------------------------
    # Step 2 — POSITIVE: publish uses correct topic + event type
    # ------------------------------------------------------------------
    step("2. publish uses topic='query.lifecycle' AND type='query.generated.v1'")
    if 'topic="query.lifecycle"' not in ask_body and "topic='query.lifecycle'" not in ask_body:
        fail("publish() missing topic='query.lifecycle'")
    if 'type="query.generated.v1"' not in ask_body and "type='query.generated.v1'" not in ask_body:
        fail("publish() missing type='query.generated.v1' (CloudEvents type)")
    ok("topic + type match schemas/events/query.lifecycle.v1.json")

    # ------------------------------------------------------------------
    # Step 3 — POSITIVE: data fields match schema
    # ------------------------------------------------------------------
    step("3. publish data fields match query.lifecycle.v1 schema")
    expected_fields = (
        "query",
        "retrieved_chunks",
        "prompt_version",
        "model",
        "tokens_prompt",
        "tokens_completion",
        "confidence",
        "latency_ms",
    )
    missing = [f for f in expected_fields if f'"{f}"' not in ask_body]
    if missing:
        fail(f"data fields missing from publish: {missing}")
    ok(f"all {len(expected_fields)} schema-required data fields in publish")

    # ------------------------------------------------------------------
    # Step 4 — POSITIVE: partition key is tenant_id
    # ------------------------------------------------------------------
    step("4. publish key=tenant_id (per-tenant ordering)")
    if not re.search(r"key\s*=\s*tenant_id", ask_body):
        fail(
            "publish() not using key=tenant_id — Kafka would round-robin "
            "across partitions and break per-tenant event ordering"
        )
    ok("partition key = tenant_id (per-tenant ordering preserved)")

    # ------------------------------------------------------------------
    # Step 5 — NEGATIVE: publish wrapped in try/except (fail-safe)
    # ------------------------------------------------------------------
    step("5. NEGATIVE: publish() wrapped in try/except (fail-safe)")
    # The publish must be in a try block; an except Exception must catch
    # broad failures so a Kafka blink doesn't 5xx the user.
    publish_block = re.search(
        r"if producer is not None:.*?return response",
        ask_body, re.DOTALL,
    )
    if publish_block is None:
        # Looser: anywhere in ask_body that contains 'producer.publish('
        if "producer.publish(" not in ask_body:
            fail("could not locate producer.publish() call")
        publish_block_text = ask_body
    else:
        publish_block_text = publish_block.group(0)
    if "try:" not in publish_block_text or "except Exception" not in publish_block_text:
        fail(
            "publish() not wrapped in try/except Exception — Kafka "
            "unreachable mid-request would 5xx the user. Per §47 fail-safe."
        )
    ok("publish wrapped in try/except Exception (5xx-resistant)")

    # ------------------------------------------------------------------
    # Step 6 — NEGATIVE: producer-None path is handled
    # ------------------------------------------------------------------
    step("6. NEGATIVE: producer-None path is handled (operator opt-out)")
    if not re.search(r"if producer is not None:", ask_body):
        fail(
            "no `if producer is not None:` guard — when operator opts out via "
            "DOCUMIND_KAFKA_BOOTSTRAP unset, the route would AttributeError "
            "trying to call .publish() on None"
        )
    ok("producer-None path guarded (operator opt-out works)")

    # ------------------------------------------------------------------
    # Step 7 — NEGATIVE: tenant_id required before publish
    # ------------------------------------------------------------------
    step("7. NEGATIVE: tenant_id is REQUIRED before publish")
    # The handler raises ValidationError on empty tenant_id BEFORE the
    # publish call. Source has the existing check, but we lock it.
    if "raise ValidationError" not in ask_body or "X-Tenant-ID" not in ask_body:
        fail(
            "handler missing X-Tenant-ID required-check; could publish with "
            "empty tenant_id and break per-tenant event ordering"
        )
    # The check must be BEFORE the publish (tenant_id used as partition key)
    tenant_check_idx = ask_body.find("raise ValidationError")
    publish_idx = ask_body.find("producer.publish(")
    if publish_idx > 0 and tenant_check_idx > 0 and tenant_check_idx > publish_idx:
        fail(
            "tenant_id required-check is AFTER publish — could publish with "
            "empty tenant before raising"
        )
    ok("tenant_id required-check fires BEFORE publish (ordering invariant held)")

    # ------------------------------------------------------------------
    # Step 8 — NEGATIVE: body.query truncated to ≤500 chars
    # ------------------------------------------------------------------
    step("8. NEGATIVE: body.query truncated in publish (PII / size guard)")
    if not re.search(r"body\.query.*\[:5\d\d\]", ask_body):
        fail(
            "body.query NOT truncated in publish payload — full query may "
            "contain PII / be huge. Full prompt belongs in governance.audit_log "
            "(keyed by correlation_id), not in the observability event."
        )
    ok("body.query truncated to ≤500 chars (PII + size guard)")

    print(f"\n{GREEN}{BOLD}ALL 8 STEPS PASSED{NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
