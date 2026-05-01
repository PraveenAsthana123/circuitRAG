#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill for P0 #34 — Postgres-backed IdempotencyStore (multi-pod safe).

Verifies:
  - PostgresIdempotencyStore implements IdempotencyStore Protocol
  - Methods accept the same shapes as InMemoryIdempotencyStore
  - SQL uses parameterized queries + composite PK match
  - Uses tenant_connection (RLS-enforced)

Negative assertions:
  - SQL does NOT use f-string interpolation (no injection vector)
  - ON CONFLICT clause uses DO NOTHING (first-writer-wins, idempotent retry)
  - get/save signatures match Protocol exactly (Protocol-conformant)
"""
from __future__ import annotations

import importlib.util
import inspect
import sys
from pathlib import Path
from types import ModuleType


REPO = Path(__file__).resolve().parents[2]
SVC = REPO / "services" / "agent-orchestrator-svc"


def _load():
    pkg = "p0e_app"
    if pkg not in sys.modules:
        sys.modules[pkg] = ModuleType(pkg)
        sys.modules[pkg].__path__ = [str(SVC / "app")]
    idem_spec = importlib.util.spec_from_file_location(f"{pkg}.idempotency", SVC / "app" / "idempotency.py")
    idem = importlib.util.module_from_spec(idem_spec)
    idem.__package__ = pkg
    sys.modules[f"{pkg}.idempotency"] = idem
    idem_spec.loader.exec_module(idem)
    pg_spec = importlib.util.spec_from_file_location(f"{pkg}.idempotency_postgres", SVC / "app" / "idempotency_postgres.py")
    pg = importlib.util.module_from_spec(pg_spec)
    pg.__package__ = pkg
    sys.modules[f"{pkg}.idempotency_postgres"] = pg
    pg_spec.loader.exec_module(pg)
    return idem, pg


def main() -> int:
    idem, pg = _load()

    print("-- 1. POSITIVE: PostgresIdempotencyStore class exists --")
    assert hasattr(pg, "PostgresIdempotencyStore")
    Cls = pg.PostgresIdempotencyStore
    print("  ok: class exported")

    print("-- 2. POSITIVE: implements IdempotencyStore Protocol via duck-typing --")
    methods = [name for name, _ in inspect.getmembers(Cls, predicate=inspect.isfunction)]
    assert "get" in methods, "missing get(tenant_id, key) method"
    assert "save" in methods, "missing save(record) method"
    print(f"  ok: get + save methods present")

    print("-- 3. POSITIVE: get signature matches Protocol --")
    get_sig = inspect.signature(Cls.get)
    params = list(get_sig.parameters.keys())
    # self, tenant_id, key
    assert params == ["self", "tenant_id", "key"], (
        f"get signature mismatch: {params}"
    )
    print("  ok: get(self, tenant_id, key) signature OK")

    print("-- 4. POSITIVE: save signature matches Protocol --")
    save_sig = inspect.signature(Cls.save)
    params = list(save_sig.parameters.keys())
    assert params == ["self", "record"]
    print("  ok: save(self, record) signature OK")

    print("-- 5. NEGATIVE: SQL uses parameterized queries (NO f-string interpolation) --")
    src = (SVC / "app" / "idempotency_postgres.py").read_text(encoding="utf-8")
    # Extract SQL strings: triple-quoted blocks with INSERT/SELECT.
    import re
    sql_blocks = re.findall(r'"""([\s\S]*?)"""', src)
    for block in sql_blocks:
        if "INSERT" in block.upper() or "SELECT" in block.upper():
            # Must use $1, $2, $3, $4 placeholders, NOT f-string {var}.
            assert "{" not in block or block.count("{") == block.count("$"), (
                f"P0 #34 BROKEN: SQL block contains f-string-style {{}} interpolation: {block!r}"
            )
            assert "$1" in block or "$2" in block, (
                f"SQL must use $N placeholders: {block!r}"
            )
    print(f"  ok: {len([b for b in sql_blocks if 'INSERT' in b.upper() or 'SELECT' in b.upper()])} SQL blocks all parameterized")

    print("-- 6. NEGATIVE: ON CONFLICT uses DO NOTHING (first-writer-wins) --")
    # On retry of the same (tenant_id, key), DO NOTHING preserves the
    # original task_id (idempotent semantics). DO UPDATE would
    # overwrite — wrong for idempotency.
    assert "ON CONFLICT (tenant_id, key) DO NOTHING" in src, (
        "P0 #34 BROKEN: missing ON CONFLICT DO NOTHING (would break idempotency contract)"
    )
    assert "DO UPDATE" not in src, (
        "P0 #34 BROKEN: DO UPDATE present in idempotency table writes; "
        "should be DO NOTHING (first-writer-wins)"
    )
    print("  ok: ON CONFLICT (tenant_id, key) DO NOTHING — first-writer-wins")

    print("-- 7. NEGATIVE: uses tenant_connection (RLS-enforced) NOT admin_connection --")
    # admin_connection bypasses RLS; tenant_connection sets app.current_tenant
    # so the tenant_id filter is double-checked at the row level.
    assert "tenant_connection" in src, (
        "P0 #34 BROKEN: must use tenant_connection (RLS) not admin_connection"
    )
    assert "admin_connection" not in src, (
        "P0 #34 BROKEN: admin_connection bypasses RLS; idempotency must use tenant_connection"
    )
    print("  ok: tenant_connection (RLS-enforced) — admin_connection NOT used")

    print("-- 8. POSITIVE: returns IdempotencyRecord on get, accepts on save --")
    # Verify import points at canonical IdempotencyRecord type.
    assert "from .idempotency import IdempotencyRecord" in src
    print("  ok: re-uses canonical IdempotencyRecord (no duplicate type)")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
