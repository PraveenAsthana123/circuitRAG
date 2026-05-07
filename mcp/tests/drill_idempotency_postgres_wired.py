#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: PostgresIdempotencyStore wired into POST /api/v1/agentic/tasks.

Closes the §52 honesty gap on idempotency.md:

  Pre-fix: PostgresIdempotencyStore class existed (P0 #34 nominally
  closed) but the route handler did NOT call it — every request
  bypassed idempotency entirely. Multi-pod deploys would see
  duplicate task creation on retry.

  Fix (this commit's iteration 1B):
    1. main.py constructs PostgresIdempotencyStore (DB up) or
       InMemoryIdempotencyStore (dev fallback) and stores on app.state
    2. POST /api/v1/agentic/tasks accepts X-Idempotency-Key header,
       hashes the body, calls lookup_or_reserve / save_record
    3. Conflict raises HTTP 409 with IDEMPOTENCY_CONFLICT error_code
    4. Cache hit returns the cached task_id (no second creation)

Eight steps. Six negative assertions.

  1. POSITIVE: main.py imports + wires the idempotency machinery
  2. POSITIVE: app.state.idempotency_store reachable through lifespan
  3. NEGATIVE: POST without X-Idempotency-Key creates a task as
     before (no regression on §28 backward-compat contract)
  4. NEGATIVE: POST with same key + same body twice returns the
     SAME task_id (cache hit; no duplicate creation)
  5. NEGATIVE: POST with same key + DIFFERENT body returns HTTP 409
     + error_code=IDEMPOTENCY_CONFLICT
  6. NEGATIVE: cache hit returns 200 (FastAPI POST default), not 201,
     because the task already existed; the body_hash match means we
     return the cached row, not re-create
  7. NEGATIVE: idempotency_store record persists across requests
     within the same process — concrete evidence the wiring is on
     the request hot path, not just instantiated in lifespan
  8. NEGATIVE: hash_body produces stable hashes — field-order
     non-determinism would silently break idempotency
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SVC = REPO / "services" / "agent-orchestrator-svc"

sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "libs" / "py"))
sys.path.insert(0, str(SVC))

os.environ["DOCUMIND_PROMETHEUS_PORT"] = "0"


def main() -> int:
    print("-- 1. POSITIVE: main.py wires idempotency machinery --")
    main_src = (SVC / "app" / "main.py").read_text(encoding="utf-8")
    for needle in (
        "from .idempotency import",
        "from .idempotency_postgres import PostgresIdempotencyStore",
        "lookup_or_reserve",
        "save_record",
        "hash_body",
        "IdempotencyConflict",
        "app.state.idempotency_store",
        'alias="X-Idempotency-Key"',
    ):
        assert needle in main_src, (
            f"main.py missing wiring contract: {needle!r}. "
            "Without this the route bypasses idempotency entirely."
        )
    print("  ok: imports + state binding + header alias all present")

    print("-- 2. POSITIVE: app.state.idempotency_store after lifespan --")
    from app.idempotency import (
        IdempotencyRecord,
        InMemoryIdempotencyStore,
        hash_body,
    )
    from app.idempotency_postgres import PostgresIdempotencyStore
    from app.main import app
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        idem = getattr(app.state, "idempotency_store", None)
        assert idem is not None, "app.state.idempotency_store not set by lifespan"
        assert isinstance(idem, (PostgresIdempotencyStore, InMemoryIdempotencyStore)), (
            f"unexpected idempotency_store type: {type(idem).__name__}"
        )
        # In dev (no Postgres) we expect InMemoryIdempotencyStore.
        store_kind = type(idem).__name__
        print(f"  ok: store wired ({store_kind})")

        print("-- 3. NEGATIVE: POST without X-Idempotency-Key creates unconditionally (§28 compat) --")
        payload = {
            "tenant_id": "drill-tenant",
            "goal": "drill: idempotency baseline",
        }
        r1 = client.post("/api/v1/agentic/tasks", json=payload)
        assert r1.status_code == 200, f"baseline create expected 200; got {r1.status_code}: {r1.text}"
        r2 = client.post("/api/v1/agentic/tasks", json=payload)
        assert r2.status_code == 200, f"second create expected 200; got {r2.status_code}: {r2.text}"
        assert r1.json()["task_id"] != r2.json()["task_id"], (
            "no-header POST should create distinct tasks; got duplicate task_id"
        )
        print(f"  ok: distinct task_ids without key — {r1.json()['task_id'][:8]}, {r2.json()['task_id'][:8]}")

        print("-- 4. NEGATIVE: same key + same body returns SAME task_id (cache hit) --")
        payload_keyed = {
            "tenant_id": "drill-tenant",
            "goal": "drill: idempotency cache-hit",
        }
        headers = {"X-Idempotency-Key": "drill-key-001"}
        ra = client.post("/api/v1/agentic/tasks", json=payload_keyed, headers=headers)
        assert ra.status_code == 200, f"first keyed create expected 200; got {ra.status_code}: {ra.text}"
        rb = client.post("/api/v1/agentic/tasks", json=payload_keyed, headers=headers)
        assert rb.status_code == 200, f"second keyed POST expected 200; got {rb.status_code}: {rb.text}"
        assert ra.json()["task_id"] == rb.json()["task_id"], (
            f"cache hit failed — task_ids differ: {ra.json()['task_id']} vs {rb.json()['task_id']}. "
            "Idempotency wiring is broken."
        )
        cached_task_id = ra.json()["task_id"]
        print(f"  ok: same-body POST x2 returns same task_id={cached_task_id[:8]}")

        print("-- 5. NEGATIVE: same key + different body returns HTTP 409 IDEMPOTENCY_CONFLICT --")
        payload_diff = {
            "tenant_id": "drill-tenant",
            "goal": "drill: DIFFERENT body — should conflict",
        }
        rc = client.post("/api/v1/agentic/tasks", json=payload_diff, headers=headers)
        assert rc.status_code == 409, (
            f"body mismatch should be 409; got {rc.status_code}: {rc.text}. "
            "Without this, two different requests with the same key would silently overwrite."
        )
        body = rc.json()
        # FastAPI wraps detail as a dict when raised that way
        detail = body.get("detail")
        assert isinstance(detail, dict), f"detail must be dict for structured error_code; got {type(detail)}: {body}"
        assert detail.get("error_code") == "IDEMPOTENCY_CONFLICT", (
            f"expected error_code=IDEMPOTENCY_CONFLICT; got {detail}"
        )
        print("  ok: 409 + error_code=IDEMPOTENCY_CONFLICT on body mismatch")

        print("-- 6. NEGATIVE: cache-hit response is 200 (returned, not re-created) --")
        # Already implicitly verified in step 4 (status_code == 200 on rb)
        # but be explicit about the contract: cache hit returns 200 with
        # the same row, NOT 201 (would imply new creation).
        assert rb.status_code == 200, "cache hit must be 200, not 201 (which would imply re-creation)"
        print("  ok: cache hit returns 200 — no re-creation")

        print("-- 7. NEGATIVE: idempotency record persists across requests in-process --")
        # The fact that step 4's rb returned ra's task_id IS the proof
        # the record persisted. Reinforce by reading the store directly.
        record = await_run_async(
            idem.get("drill-tenant", "drill-key-001")
        )
        assert record is not None, "store has no record for drill-key-001 — wiring is broken"
        assert record.task_id == cached_task_id, (
            f"persisted task_id mismatch: store={record.task_id} vs response={cached_task_id}"
        )
        assert isinstance(record, IdempotencyRecord)
        print(f"  ok: store.get returned IdempotencyRecord(task_id={record.task_id[:8]})")

        print("-- 8. NEGATIVE: hash_body is field-order stable --")
        h1 = hash_body({"tenant_id": "x", "goal": "y", "k": [1, 2, 3]})
        h2 = hash_body({"goal": "y", "k": [1, 2, 3], "tenant_id": "x"})
        assert h1 == h2, (
            "hash_body must be field-order stable. "
            "If it isn't, two requests with the same logical body but "
            "different JSON ordering would mismatch + 409 each other."
        )
        print(f"  ok: identical hash for re-ordered fields ({h1[:12]}...)")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


def await_run_async(coro):
    """Tiny sync->async bridge for the drill: TestClient runs in its
    own loop; we just need a one-off result from a coroutine here."""
    import asyncio
    return asyncio.get_event_loop().run_until_complete(coro)


if __name__ == "__main__":
    raise SystemExit(main())
