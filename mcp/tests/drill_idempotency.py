#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill for C2 — Idempotency-Key support (Phase C2).

Verifies:
  - migration 014 declares idempotency_keys table with composite PK
    (tenant_id, key) — bare key would collide cross-tenant.
  - app/idempotency.py exists with hash_body / lookup_or_reserve / save_record.
  - hash_body is canonical (key order doesn't change hash).
  - lookup_or_reserve returns existing on match, None on miss, raises
    IdempotencyConflict on key+different-body.

Negative assertions:
  1. Same key + DIFFERENT body MUST raise IdempotencyConflict (silent
     overwrite would break request-response invariant per §6.3).
  2. Cross-tenant key collision MUST be impossible — composite PK
     enforces (tenant_id, key) as the unique scope.
  3. body_hash MUST be deterministic — different field-order JSON of
     the SAME logical payload produces the SAME hash.

Resource tag = readonly. Pure function + SQL source check.
"""
from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
SVC = REPO / "services" / "agent-orchestrator-svc"
MIGRATION = SVC / "migrations" / "014_idempotency.sql"
MODULE = SVC / "app" / "idempotency.py"


def _import_idempotency():
    spec = importlib.util.spec_from_file_location("c2_idempotency", MODULE)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["c2_idempotency"] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    print("-- 1. POSITIVE: migration 014 exists --")
    assert MIGRATION.exists(), f"missing {MIGRATION}"
    sql = MIGRATION.read_text(encoding="utf-8")
    print(f"  ok: {MIGRATION.relative_to(REPO)} ({len(sql)} bytes)")

    print("-- 2. NEGATIVE: composite PK (tenant_id, key) — never bare key --")
    assert "PRIMARY KEY (tenant_id, key)" in sql, (
        "composite PK required; bare PRIMARY KEY (key) would collide cross-tenant"
    )
    # And NOT 'PRIMARY KEY (key)' alone.
    assert "PRIMARY KEY (key)" not in sql or "PRIMARY KEY (key)," not in sql, (
        "found bare PRIMARY KEY (key) — must be composite"
    )
    print("  ok: composite PK enforces tenant scope")

    print("-- 3. POSITIVE: RLS policy on idempotency_keys --")
    assert "ENABLE ROW LEVEL SECURITY" in sql
    assert "idempotency_keys_isolation" in sql
    print("  ok: RLS policy present")

    print("-- 4. POSITIVE: idempotency module loads --")
    mod = _import_idempotency()
    assert hasattr(mod, "hash_body")
    assert hasattr(mod, "lookup_or_reserve")
    assert hasattr(mod, "save_record")
    assert hasattr(mod, "IdempotencyConflict")
    assert hasattr(mod, "InMemoryIdempotencyStore")
    print("  ok: hash_body / lookup_or_reserve / save_record / IdempotencyConflict / InMemoryIdempotencyStore exported")

    print("-- 5. NEGATIVE: hash_body is canonical (field-order invariant) --")
    h1 = mod.hash_body({"goal": "x", "tenant_id": "acme", "risk_level": "low"})
    h2 = mod.hash_body({"risk_level": "low", "tenant_id": "acme", "goal": "x"})
    assert h1 == h2, (
        f"hash_body NOT canonical: same payload, different order, different hash. "
        f"h1={h1[:16]} h2={h2[:16]}"
    )
    print(f"  ok: hash_body deterministic across field order ({h1[:16]}...)")

    print("-- 6. POSITIVE: hash differs for different content --")
    h3 = mod.hash_body({"goal": "y", "tenant_id": "acme", "risk_level": "low"})
    assert h1 != h3, "different goal must produce different hash"
    print("  ok: different content → different hash")

    print("-- 7. POSITIVE: lookup_or_reserve miss → None --")
    store = mod.InMemoryIdempotencyStore()
    out = asyncio.run(mod.lookup_or_reserve(
        store=store, tenant_id="acme", key="key-1", body_hash=h1,
    ))
    assert out is None, f"empty store should return None, got {out!r}"
    print("  ok: empty store → None (caller proceeds with creation)")

    print("-- 8. POSITIVE: save_record + lookup → returns same record --")
    asyncio.run(mod.save_record(
        store=store, tenant_id="acme", key="key-1", task_id="task-abc", body_hash=h1,
    ))
    out = asyncio.run(mod.lookup_or_reserve(
        store=store, tenant_id="acme", key="key-1", body_hash=h1,
    ))
    assert out is not None
    assert out.task_id == "task-abc"
    print(f"  ok: same key + same body → cached task_id={out.task_id}")

    print("-- 9. NEGATIVE: same key + DIFFERENT body → IdempotencyConflict --")
    raised = False
    try:
        asyncio.run(mod.lookup_or_reserve(
            store=store, tenant_id="acme", key="key-1", body_hash=h3,  # != h1
        ))
    except mod.IdempotencyConflict:
        raised = True
    assert raised, (
        "MUST raise IdempotencyConflict on key reuse with different body — "
        "silent overwrite would corrupt request-response invariant"
    )
    print("  ok: same key + different body → IdempotencyConflict")

    print("-- 10. NEGATIVE: cross-tenant key collision impossible --")
    # Same key 'key-1', different tenant 'beta' — must be a fresh slot.
    out_beta = asyncio.run(mod.lookup_or_reserve(
        store=store, tenant_id="beta", key="key-1", body_hash=h1,
    ))
    assert out_beta is None, (
        f"COLLISION: tenant=beta sees acme's key-1 record; got {out_beta}"
    )
    print("  ok: tenant isolation in idempotency lookup")

    print()
    print("ALL 10 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
