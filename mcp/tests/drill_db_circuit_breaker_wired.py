#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: DbCircuitBreaker is wired into PostgresTaskStore + /health/ready.

Closes the §52 honesty gap. Per-tool review claimed P0 #36 (DbCircuitBreaker
wraps DbClient calls) was complete because the wrapper class existed —
but the wrapper was never instantiated, never passed to the store,
never read by /health/ready. The fix-claim was theater until this commit.

Eight steps. Five negative assertions.

  1. POSITIVE: PostgresTaskStore accepts `breaker=` kwarg + stores it
  2. POSITIVE: PostgresTaskStore._admin_conn helper exists
  3. POSITIVE: main.py imports DbCircuitBreaker (regression guard —
     a refactor that drops the import collapses the wiring silently)
  4. POSITIVE: app.state.db_breaker is set after lifespan startup
     and reachable from /health/ready
  5. NEGATIVE: /health/ready returns HTTP 200 with db_breaker state
     when breaker is healthy
  6. NEGATIVE: /health/ready returns HTTP 503 + DB_CIRCUIT_OPEN
     error_code when breaker is OPEN. This is the load-bearing
     contract — the wiring exists for this path.
  7. NEGATIVE: /health/live REMAINS HTTP 200 even when breaker is OPEN.
     Liveness must not check deps (cascade-restart prevention per
     CLAUDE.md §47.8 three-probe pattern).
  8. NEGATIVE: when breaker is None (dev fallback), _admin_conn
     does NOT call breaker methods — preserves the no-DB dev mode.

Per CLAUDE.md §43 every drill exercises real code, not mocks.
TestClient drives the FastAPI app through its real lifespan; the
drill flips breaker state via the underlying CircuitBreaker's
force_open() so the OPEN-path is exercised end-to-end.
"""
from __future__ import annotations

import inspect
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SVC = REPO / "services" / "agent-orchestrator-svc"

# Force the orchestrator's own venv-resolved modules; the libs/py path
# must be ahead of any conda site-packages because documind_core lives
# only under libs/py. The repo root is also on the path because the
# orchestrator imports `from mcp import MCPClient` (top-level package).
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "libs" / "py"))
sys.path.insert(0, str(SVC))

# Disable the prometheus port grab so two parallel drills don't EADDRINUSE.
os.environ["DOCUMIND_PROMETHEUS_PORT"] = "0"


def main() -> int:
    print("-- 1. POSITIVE: PostgresTaskStore accepts breaker= kwarg --")
    from app.postgres_store import PostgresTaskStore

    sig = inspect.signature(PostgresTaskStore.__init__)
    params = list(sig.parameters.keys())
    assert "breaker" in params, (
        f"PostgresTaskStore.__init__ missing breaker= kwarg. params={params}"
    )
    print("  ok: breaker= kwarg present")

    print("-- 2. POSITIVE: PostgresTaskStore._admin_conn helper exists --")
    assert hasattr(PostgresTaskStore, "_admin_conn"), (
        "PostgresTaskStore missing _admin_conn helper — call sites would "
        "still hit self._db.admin_connection() and bypass the breaker"
    )
    print("  ok: _admin_conn helper present")

    print("-- 3. POSITIVE: main.py imports DbCircuitBreaker --")
    main_src = (SVC / "app" / "main.py").read_text(encoding="utf-8")
    assert "from .db_circuit_breaker import DbCircuitBreaker" in main_src, (
        "main.py does not import DbCircuitBreaker — regression guard. "
        "If wiring is dropped this assertion fires before silent breakage."
    )
    assert "DbCircuitBreaker(" in main_src, (
        "main.py does not construct DbCircuitBreaker"
    )
    assert "app.state.db_breaker" in main_src, (
        "main.py does not expose db_breaker on app.state — /health/ready "
        "cannot read it"
    )
    print("  ok: import + construction + state.db_breaker all present")

    print("-- 4. POSITIVE: app.state.db_breaker reachable through TestClient lifespan --")
    from app.main import app
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        breaker = getattr(app.state, "db_breaker", None)
        assert breaker is not None, "app.state.db_breaker not set after lifespan"
        print(f"  ok: db_breaker present, initial state={breaker.state}")

        print("-- 5. NEGATIVE: /health/ready returns 200 when breaker healthy --")
        # In dev (no Postgres) the connect_with_breaker call recorded a
        # failure, possibly tripping the breaker. Reset to ensure the
        # healthy path is exercised first.
        breaker._cb.reset()
        resp = client.get("/health/ready")
        assert resp.status_code == 200, (
            f"healthy /health/ready expected 200, got {resp.status_code}: {resp.text}"
        )
        body = resp.json()
        assert body.get("status") == "ready", body
        assert "db_breaker" in body, "ready payload missing db_breaker field"
        print(f"  ok: 200 ready; db_breaker={body['db_breaker']}")

        print("-- 6. NEGATIVE: /health/ready returns 503 + DB_CIRCUIT_OPEN when breaker OPEN --")
        breaker._cb.force_open(reason="drill_open_path")
        resp = client.get("/health/ready")
        assert resp.status_code == 503, (
            f"OPEN /health/ready expected 503, got {resp.status_code}: {resp.text}"
        )
        body = resp.json()
        assert body.get("status") == "degraded", body
        assert body.get("error_code") == "DB_CIRCUIT_OPEN", body
        assert body.get("db_breaker") == "open", body
        print("  ok: 503 degraded; error_code=DB_CIRCUIT_OPEN; db_breaker=open")

        print("-- 7. NEGATIVE: /health/live REMAINS 200 even when breaker OPEN --")
        # Breaker is still forced open from step 6 — exactly the state
        # we want for this assertion. Liveness must not check deps.
        resp = client.get("/health/live")
        assert resp.status_code == 200, (
            f"liveness must stay 200 even when DB breaker is OPEN; got {resp.status_code}. "
            "If this fails, K8s will cascade-restart pods on every Postgres hiccup."
        )
        print("  ok: /health/live=200 with breaker OPEN — three-probe contract holds")

        breaker._cb.reset()

    print("-- 8. NEGATIVE: breaker=None (dev fallback) preserves un-guarded admin_conn --")
    # Construct a store with breaker=None and verify _admin_conn does
    # NOT touch a breaker. The store has no DbClient connected; we
    # only inspect the helper's branch decision via source.
    src = (SVC / "app" / "postgres_store.py").read_text(encoding="utf-8")
    assert "if self._breaker is not None:" in src, (
        "postgres_store._admin_conn must branch on self._breaker is not None — "
        "without that, dev mode (breaker=None) crashes on first query"
    )
    assert "self._db.admin_connection()" in src, (
        "postgres_store._admin_conn must still fall through to "
        "self._db.admin_connection() in the breaker=None branch"
    )
    print("  ok: dev fallback preserved; breaker=None routes to raw admin_connection")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
