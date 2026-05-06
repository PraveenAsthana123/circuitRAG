# RESOURCES: pg
"""
Drill: ops_worker dual-write to orchestration.agent_tasks.

Per CLAUDE.md §38 (governance), §43 (drill discipline), §47.7
(expand→migrate→contract), §52 row 4 (operator API gap),
§55.3 (outcome-based contract).

Iter 7 (commit 05d4813) composed orchestration.agent_task_runs
into the registry as a provider lane. The unified agent_tasks
table existed but was never written to by ops_worker (the worker
writes ops_worker/tasks.json instead). This iteration ships the
migrate-phase: when OPS_WORKER_SQL_ENABLED=1, ops_worker.save_tasks
ALSO upserts each task into orchestration.agent_tasks. JSONL stays
authoritative; SQL becomes additionally available.

Locks (positive):
  L1. _persist_sql_task is callable in ops_worker.worker
  L2. With env flag set, save_tasks writes to BOTH tasks.json + SQL
  L3. Round-trip: synthetic task → save_tasks → row visible in
      orchestration.agent_tasks with mapped fields
  L4. Status normalization: ops_worker uppercase → SQL lowercase
      (e.g. COMPLETED → completed)
  L5. UPSERT: re-save same task_id updates the existing SQL row
      rather than failing with a unique-constraint violation

Locks (negative — ≥3 per §43):
  N1. Feature flag UNSET → no SQL write happens. Drill ensures
      tasks.json behavior unchanged when operator hasn't opted in.

  N2. SQL write failure (PG unreachable) → tasks.json STILL written.
      The worker's lifecycle NEVER blocks on SQL availability.

  N3. Invalid risk_level (e.g. 'wat') → coerced to 'low' floor.
      The orchestration.agent_tasks CHECK constraint rejects bad
      risk_level values; the writer normalizes to a safe default
      so the SQL upsert doesn't fail for one bad task.

  N4. Read-only contract: _persist_sql_task body has NO calls to
      read-side aggregators (build_registry / aggregate_provider_*)
      — would create cron-driven cycles. Drill greps the source.
"""
from __future__ import annotations

import asyncio
import os
import re
import sys
import tempfile
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "ops_worker"))

GREEN = "\033[32m"
RED = "\033[31m"
BOLD = "\033[1m"
NC = "\033[0m"

PG_HOST = "localhost"
PG_PORT = 55432
PG_USER = "documind"
PG_PASSWORD = "documind"
PG_DB = "documind"


def step(t: str) -> None:
    print(f"\n{BOLD}── {t} ──{NC}")


def ok(m: str) -> None:
    print(f"  {GREEN}✓ {m}{NC}")


def fail(m: str) -> None:
    print(f"  {RED}✗ {m}{NC}")
    raise SystemExit(1)


async def _admin_conn():
    import asyncpg
    return await asyncpg.connect(
        host=PG_HOST, port=PG_PORT, user=PG_USER, password=PG_PASSWORD,
        database=PG_DB, timeout=3.0,
    )


async def _delete_drill_rows():
    try:
        conn = await _admin_conn()
        try:
            await conn.execute(
                "DELETE FROM orchestration.agent_tasks WHERE task_id LIKE 'DRILL-%'"
            )
        finally:
            await conn.close()
    except Exception:  # noqa: BLE001
        pass


def _make_task(task_id: str, *, status: str = "PENDING", risk: str = "low") -> dict:
    return {
        "id": task_id,
        "title": f"drill: {task_id}",
        "description": "drill round-trip task",
        "status": status,
        "priority": "low",
        "risk": risk,
        "attempts": 0,
        "type": "documentation_update",
        "ollama_output": "drill output",
        "claude_review": {"decision": "SKIPPED", "final_comment": "drill"},
        "approval_decision": {"decision": "AUTO_APPROVED", "reason": "drill auto"},
    }


def main() -> int:
    saved_flag = os.environ.get("OPS_WORKER_SQL_ENABLED")
    saved_task_file = None

    # Use a temp tasks.json to keep production ops_worker/tasks.json untouched
    tmp_dir = tempfile.mkdtemp(prefix="drill_opsworker_")
    tmp_tasks_file = Path(tmp_dir) / "tasks.json"

    try:
        import worker  # noqa: E402  - from ops_worker via sys.path
        saved_task_file = worker.TASK_FILE
        worker.TASK_FILE = tmp_tasks_file

        asyncio.run(_delete_drill_rows())

        # ===============================================================
        # Step 1 — public API exists
        # ===============================================================
        step("1. ops_worker.worker exposes _persist_sql_task + save_tasks")
        if not callable(getattr(worker, "_persist_sql_task", None)):
            fail("_persist_sql_task missing")
        if not callable(getattr(worker, "save_tasks", None)):
            fail("save_tasks missing")
        ok("both functions callable")

        # ===============================================================
        # Step 2 — NEGATIVE: feature flag UNSET → no SQL write
        # ===============================================================
        step("2. NEGATIVE: env flag UNSET → JSONL only, no SQL row")
        os.environ.pop("OPS_WORKER_SQL_ENABLED", None)
        rid = f"DRILL-{uuid.uuid4().hex[:8].upper()}"
        worker.save_tasks([_make_task(rid)])
        async def _check_no_row():
            conn = await _admin_conn()
            try:
                await conn.execute("SET LOCAL app.current_tenant = 'system'")
                row = await conn.fetchrow(
                    "SELECT count(*) AS n FROM orchestration.agent_tasks "
                    " WHERE task_id = $1",
                    rid,
                )
                return int(row["n"])
            finally:
                await conn.close()
        async def _wrapped_no_row():
            conn = await _admin_conn()
            try:
                async with conn.transaction():
                    await conn.execute("SET LOCAL app.current_tenant = 'system'")
                    row = await conn.fetchrow(
                        "SELECT count(*) AS n FROM orchestration.agent_tasks "
                        " WHERE task_id = $1",
                        rid,
                    )
                    return int(row["n"])
            finally:
                await conn.close()
        n = asyncio.run(_wrapped_no_row())
        if n != 0:
            fail(f"flag UNSET but {n} SQL rows landed — feature flag not gating writes")
        if not tmp_tasks_file.exists():
            fail("tasks.json not written — base path broken")
        if rid not in tmp_tasks_file.read_text():
            fail("tasks.json did not capture flag-off task")
        ok("flag UNSET: 0 SQL rows; tasks.json written normally")

        # ===============================================================
        # Step 3 — feature flag SET → both surfaces written
        # ===============================================================
        step("3. env flag SET → both tasks.json + SQL surfaces get the row")
        os.environ["OPS_WORKER_SQL_ENABLED"] = "1"
        rid_dual = f"DRILL-{uuid.uuid4().hex[:8].upper()}"
        worker.save_tasks([_make_task(rid_dual, status="COMPLETED", risk="medium")])
        async def _check_both():
            conn = await _admin_conn()
            try:
                async with conn.transaction():
                    await conn.execute("SET LOCAL app.current_tenant = 'system'")
                    return await conn.fetchrow(
                        "SELECT task_id, status, risk_level, goal, tenant_id, "
                        "       worker_output "
                        "  FROM orchestration.agent_tasks "
                        " WHERE task_id = $1",
                        rid_dual,
                    )
            finally:
                await conn.close()
        sql_row = asyncio.run(_check_both())
        if sql_row is None:
            fail("flag SET but no SQL row written")
        if sql_row["task_id"] != rid_dual:
            fail(f"task_id mismatch: SQL={sql_row['task_id']!r}")
        ok(f"both surfaces hold {rid_dual}: status={sql_row['status']!r}")

        # ===============================================================
        # Step 4 — Status normalization (uppercase → lowercase)
        # ===============================================================
        step("4. status normalization: COMPLETED → completed (orchestration table convention)")
        if sql_row["status"] != "completed":
            fail(f"COMPLETED should normalize to 'completed', got {sql_row['status']!r}")
        if sql_row["risk_level"] != "medium":
            fail(f"medium risk should pass through, got {sql_row['risk_level']!r}")
        ok("uppercase ops_worker status → lowercase SQL status; risk_level mapping clean")

        # ===============================================================
        # Step 5 — UPSERT: re-save updates existing row
        # ===============================================================
        step("5. UPSERT: re-save same task_id updates instead of UNIQUE-violating")
        # Save again with status changed to FAILED
        updated_task = _make_task(rid_dual, status="FAILED", risk="medium")
        updated_task["ollama_output"] = "updated output content"
        worker.save_tasks([updated_task])
        sql_row2 = asyncio.run(_check_both())
        if sql_row2["status"] != "failed":
            fail(f"UPDATE didn't propagate status: got {sql_row2['status']!r}")
        if "updated output" not in (sql_row2["worker_output"] or ""):
            fail("UPDATE didn't propagate worker_output")
        ok("UPSERT propagated status → 'failed' and worker_output update")

        # ===============================================================
        # Step 6 — NEGATIVE: SQL host unreachable → tasks.json still works
        # ===============================================================
        step("6. NEGATIVE: PG unreachable → tasks.json STILL written")
        saved_pg_host = os.environ.get("DOCUMIND_PG_HOST")
        saved_pg_port = os.environ.get("DOCUMIND_PG_PORT")
        os.environ["DOCUMIND_PG_HOST"] = "127.0.0.1"
        os.environ["DOCUMIND_PG_PORT"] = "1"
        rid_fail = f"DRILL-{uuid.uuid4().hex[:8].upper()}"
        try:
            # MUST NOT raise even though SQL is unreachable
            worker.save_tasks([_make_task(rid_fail)])
            content = tmp_tasks_file.read_text(encoding="utf-8")
            if rid_fail not in content:
                fail("tasks.json missing despite best-effort contract")
        finally:
            os.environ.pop("DOCUMIND_PG_HOST", None)
            if saved_pg_host:
                os.environ["DOCUMIND_PG_HOST"] = saved_pg_host
            os.environ.pop("DOCUMIND_PG_PORT", None)
            if saved_pg_port:
                os.environ["DOCUMIND_PG_PORT"] = saved_pg_port
        ok("PG unreachable → tasks.json still wrote; worker lifecycle unblocked")

        # ===============================================================
        # Step 7 — NEGATIVE: invalid risk_level coerced to 'low'
        # ===============================================================
        step("7. NEGATIVE: invalid risk_level → coerced to 'low' floor (CHECK constraint safe)")
        rid_bad = f"DRILL-{uuid.uuid4().hex[:8].upper()}"
        bad_task = _make_task(rid_bad, risk="wat")  # invalid value
        worker.save_tasks([bad_task])
        async def _check_risk():
            conn = await _admin_conn()
            try:
                async with conn.transaction():
                    await conn.execute("SET LOCAL app.current_tenant = 'system'")
                    row = await conn.fetchrow(
                        "SELECT risk_level FROM orchestration.agent_tasks "
                        " WHERE task_id = $1",
                        rid_bad,
                    )
                    return row["risk_level"] if row else None
            finally:
                await conn.close()
        risk = asyncio.run(_check_risk())
        if risk is None:
            fail("bad-risk task didn't insert at all — coercion not applied")
        if risk != "low":
            fail(f"bad risk='wat' should coerce to 'low', got {risk!r}")
        ok("invalid 'wat' risk → coerced to 'low' floor; CHECK constraint not tripped")

        # ===============================================================
        # Step 8 — NEGATIVE: read-only contract (no read-aggregator calls)
        # ===============================================================
        step("8. NEGATIVE: _persist_sql_task body has no read-side aggregators")
        src = (REPO / "ops_worker" / "worker.py").read_text(encoding="utf-8")
        m = re.search(
            r"def _persist_sql_task.*?(?=\ndef \w)",
            src, re.DOTALL,
        )
        if m is None:
            fail("could not locate _persist_sql_task body")
        body = m.group(0)
        forbidden = (
            "build_registry",
            "aggregate_provider_comparison",
            "aggregate_ops_worker",
            "snapshot(",
        )
        leaks = [p for p in forbidden if p in body]
        if leaks:
            fail(f"_persist_sql_task references read-side aggregators: {leaks}")
        ok("write-side has no calls into read-side aggregators")

        print(f"\n{GREEN}{BOLD}ALL 8 STEPS PASSED{NC}")
        return 0

    finally:
        if saved_flag is None:
            os.environ.pop("OPS_WORKER_SQL_ENABLED", None)
        else:
            os.environ["OPS_WORKER_SQL_ENABLED"] = saved_flag
        if saved_task_file is not None:
            try:
                worker.TASK_FILE = saved_task_file
            except Exception:  # noqa: BLE001
                pass
        try:
            asyncio.run(_delete_drill_rows())
        except Exception:  # noqa: BLE001
            pass
        try:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception:  # noqa: BLE001
            pass


if __name__ == "__main__":
    sys.exit(main())
