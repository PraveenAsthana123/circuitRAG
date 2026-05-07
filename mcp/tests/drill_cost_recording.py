#!/usr/bin/env python3
# RESOURCES: readonly
"""Source-level drill for migration 008 + cost-recording wiring (Phase A5).

Verifies:
- migrations/008_routing_costs.sql exists, declares all 4 new columns,
  and uses ADD COLUMN IF NOT EXISTS (idempotent + backward-compat).
- TaskRunView (app/models.py) has the four new fields with nullable types.
- postgres_store.py INSERT/UPDATE references the new columns.
- _row_to_task_run reads the new columns defensively (won't crash on
  pre-A5 rows where columns don't yet exist).

Negative assertions:
  1. Migration uses ADD COLUMN IF NOT EXISTS — re-running the migration
     after partial apply MUST be safe. A bare 'ADD COLUMN' (without
     IF NOT EXISTS) would crash on second run.
  2. New columns are NULLable (no NOT NULL DEFAULT 0). Adding NOT NULL
     would force a table rewrite on existing rows — bad for §28
     non-blocking migration policy.
  3. INSERT statement references all 4 new columns — proves wiring is
     complete, not just schema-shape.

Resource tag = readonly. No DB connection.

Why source-level: the actual migration applies at service startup via
scripts/bootstrap.py + db_client.run_migrations. We drill the SQL +
code shape; the migration's runtime behavior is exercised by service
boot in tests/test_smoke.py (which already passes).
"""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SVC = REPO / "services" / "agent-orchestrator-svc"
MIGRATION = SVC / "migrations" / "008_routing_costs.sql"
MODELS = SVC / "app" / "models.py"
STORE = SVC / "app" / "postgres_store.py"


def must_contain(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise AssertionError(f"missing {label}: {needle!r}")


def must_not_contain(text: str, needle: str, label: str) -> None:
    if needle in text:
        raise AssertionError(f"forbidden {label}: {needle!r}")


def main() -> int:
    print("-- 1. POSITIVE: migration file exists --")
    assert MIGRATION.exists(), f"missing {MIGRATION}"
    sql = MIGRATION.read_text(encoding="utf-8")
    print(f"  ok: {MIGRATION.relative_to(REPO)} ({len(sql)} bytes)")

    print("-- 2. POSITIVE: 4 new columns declared --")
    for col in ("tokens_in", "tokens_out", "cost_usd_cents", "routing_decision"):
        must_contain(sql, col, f"column {col}")
    print("  ok: tokens_in / tokens_out / cost_usd_cents / routing_decision")

    print("-- 3. NEGATIVE: ADD COLUMN must be IF NOT EXISTS (idempotent) --")
    # Every ADD COLUMN occurrence must be followed by IF NOT EXISTS.
    # We check by counting: if there are any 'ADD COLUMN ' (with space)
    # NOT followed by 'IF NOT EXISTS', it's a bug.
    import re
    occurrences = re.findall(r"ADD COLUMN\s+(IF NOT EXISTS\s+)?\S+", sql, flags=re.IGNORECASE)
    bare_adds = [o for o in occurrences if "IF NOT EXISTS" not in o.upper()]
    assert not bare_adds, (
        f"bare ADD COLUMN found ({bare_adds}); migration must be idempotent"
    )
    print(f"  ok: all {len(occurrences)} ADD COLUMN clauses use IF NOT EXISTS")

    print("-- 4. NEGATIVE: new columns are NULLable (no NOT NULL DEFAULT) --")
    # Crude but effective: split on commas in the ADD clause and verify
    # 'NOT NULL DEFAULT' doesn't appear on any of our 4 column lines.
    forbidden_combos = [
        "tokens_in INTEGER NOT NULL",
        "tokens_out INTEGER NOT NULL",
        "cost_usd_cents INTEGER NOT NULL",
        "routing_decision JSONB NOT NULL",
    ]
    for fc in forbidden_combos:
        must_not_contain(sql, fc, f"NOT NULL on new column ({fc})")
    print("  ok: all 4 new columns nullable per §28 expand-migrate-contract")

    print("-- 5. POSITIVE: TaskRunView has 4 new fields --")
    models_text = MODELS.read_text(encoding="utf-8")
    for field in ("tokens_in:", "tokens_out:", "cost_usd_cents:", "routing_decision:"):
        must_contain(models_text, field, f"TaskRunView field {field}")
    print("  ok: TaskRunView surfaces all 4 cost fields")

    print("-- 6. POSITIVE: postgres_store INSERT writes new columns --")
    store_text = STORE.read_text(encoding="utf-8")
    # The save_task_run INSERT must reference all 4 columns; we look for
    # a single column list in the INSERT clause that names them.
    insert_block = store_text.split("INSERT INTO orchestration.agent_task_runs", 1)[1][:1500]
    for col in ("tokens_in", "tokens_out", "cost_usd_cents", "routing_decision"):
        must_contain(insert_block, col, f"INSERT column {col}")
    print("  ok: INSERT writes tokens + cost + routing_decision")

    print("-- 7. POSITIVE: ON CONFLICT updates new columns --")
    # The same INSERT block has ON CONFLICT ... DO UPDATE SET — verify
    # the new columns are also in the UPDATE list (else upserts of
    # existing runs would lose cost data).
    for col in ("tokens_in = EXCLUDED.tokens_in", "cost_usd_cents = EXCLUDED.cost_usd_cents"):
        must_contain(insert_block, col, f"ON CONFLICT update for {col}")
    print("  ok: ON CONFLICT updates cost columns (no upsert data loss)")

    print("-- 8. POSITIVE: SELECT lists new columns --")
    select_block = store_text.split("SELECT run_id, tenant_id, task_id", 1)[1][:600]
    for col in ("tokens_in", "tokens_out", "cost_usd_cents", "routing_decision"):
        must_contain(select_block, col, f"SELECT column {col}")
    print("  ok: SELECT pulls all 4 new columns")

    print("-- 9. POSITIVE: row decoder defensive against missing columns --")
    # Locate the function definition (not the call site). Walk to the
    # 'def _row_to_task_run' marker so we read the actual body.
    func_marker = "def _row_to_task_run("
    idx = store_text.find(func_marker)
    assert idx >= 0, "_row_to_task_run definition not found"
    # Slurp the function body (next ~50 lines should cover it).
    decoder_block = store_text[idx:idx + 1800]
    has_defensive = (
        "_maybe(" in decoder_block
        or "row.get(" in decoder_block
        or "except (KeyError" in decoder_block
        or "except KeyError" in decoder_block
    )
    assert has_defensive, (
        "_row_to_task_run lacks defensive read for new columns — "
        "rolling deploy would crash on pre-008 rows. "
        f"first 400 chars of decoder: {decoder_block[:400]!r}"
    )
    print("  ok: defensive column read present (rolling-deploy safe)")

    print()
    print("ALL 9 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
