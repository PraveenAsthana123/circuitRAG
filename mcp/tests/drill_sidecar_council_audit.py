#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: Sidecar Advisor — council telemetry persisted to audit table.

Locks the Phase 2E contract:

  Advisor.review(event_type=pr_review)
    → returns (parsed, raw, model, duration, council_telemetry)
    → caller persists the user-visible event:
        event_id = memory.record_event(advisor_output=parsed, ...)
    → caller persists the council telemetry:
        memory.record_council_run(event_id=event_id, telemetry=council_telemetry)
    → advisor_council_runs row joins back via event_id

Eight steps. Five negative assertions.

  1. Migration 002 creates advisor_council_runs table + 4 indexes.
  2. record_council_run inserts a row with telemetry fields
     preserved (outcome, advisor_id, prompt_version, duration_s,
     drafts_json, reviews_json, failed_authors).
  3. NEGATIVE: row inserts even when outcome=advisor_failed +
     advisor_error is non-empty. Audit must NOT skip failure rows.
  4. NEGATIVE: row inserts when event_id is None (operator
     backfill / replay scenario). FK is nullable.
  5. get_council_runs(event_id=X) returns exactly the rows for
     that event. NEGATIVE: cross-event leak would mean a single
     run's drafts could surface against a different user's event.
  6. get_council_runs(outcome="partial") filters correctly.
   The outcome column is what dashboards group by.
  7. NEGATIVE: a non-pr_review review() call returns
     council_telemetry=None — single-agent path doesn't produce
     a council_run row, so dashboard counts are honest.
  8. NEGATIVE: telemetry with missing fields (e.g. drafts=[]
     because every author crashed) still inserts cleanly with
     empty JSON arrays — partial telemetry is data, not a crash.

Tag: readonly. Pure-Python — runs in tier 1.

Run:
    python3 mcp/tests/drill_sidecar_council_audit.py
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import pathlib
import sys
import tempfile
import types

REPO = pathlib.Path(__file__).resolve().parents[2]

GREEN = "\033[32m"
RED = "\033[31m"
BOLD = "\033[1m"
NC = "\033[0m"


def ok(msg: str) -> None:
    print(f"  {GREEN}✓ {msg}{NC}")


def fail(msg: str) -> None:
    print(f"  {RED}✗ {msg}{NC}")
    raise SystemExit(1)


def step(title: str) -> None:
    print(f"\n{BOLD}── {title} ──{NC}")


# ── Module loader ────────────────────────────────────────────────
def _load_mod(rel: str, name: str):
    p = REPO / rel
    spec = importlib.util.spec_from_file_location(name, p)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load spec from {p}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# Set up package context for advisor + council relative imports
_pkg = types.ModuleType("sidecar_advisor_pkg")
_pkg.__path__ = [str(REPO / "services" / "sidecar-advisor")]
sys.modules["sidecar_advisor_pkg"] = _pkg

memory_mod = _load_mod(
    "services/sidecar-advisor/memory.py",
    "sidecar_advisor_pkg.memory",
)
sys.modules["sidecar_advisor_pkg.memory"] = memory_mod
advisor_mod = _load_mod(
    "services/sidecar-advisor/advisor.py",
    "sidecar_advisor_pkg.advisor",
)
sys.modules["sidecar_advisor_pkg.advisor"] = advisor_mod
council_mod = _load_mod(
    "services/sidecar-advisor/council.py",
    "sidecar_advisor_pkg.council",
)
sys.modules["sidecar_advisor_pkg.council"] = council_mod

AdvisorMemory = memory_mod.AdvisorMemory
Advisor = advisor_mod.Advisor


# ── Helpers ──────────────────────────────────────────────────────
def _make_canned_telemetry(
    outcome: str = "ok",
    advisor_error: str | None = None,
    failed_authors: list[str] | None = None,
    drafts: list[dict] | None = None,
    reviews: list[dict] | None = None,
    duration_s: float = 1.5,
    prompt_version: str = "v_abc123",
    advisor_id: str = "pr_review_chair",
) -> dict:
    """Build a representative council telemetry dict for tests."""
    return {
        "outcome": outcome,
        "duration_s": duration_s,
        "prompt_version": prompt_version,
        "advisor_id": advisor_id,
        "advisor_error": advisor_error,
        "failed_authors": failed_authors or [],
        "drafts": drafts if drafts is not None else [
            {
                "author_id": "code_reviewer",
                "model_used": "deepseek-coder:6.7b-instruct",
                "text": "looks reasonable",
                "duration_s": 0.5,
                "error": None,
            },
            {
                "author_id": "security_auditor",
                "model_used": "codellama:7b-instruct",
                "text": "no obvious issues",
                "duration_s": 0.6,
                "error": None,
            },
        ],
        "reviews": reviews if reviews is not None else [
            {
                "reviewer_id": "consistency_check",
                "draft_author_id": "code_reviewer",
                "score": 7.0,
                "critique": "actionable",
                "error": None,
            },
        ],
    }


def _make_chair_response() -> str:
    return (
        '{"summary":"good","risk_level":"LOW",'
        '"top_3_advice":["a","b","c"],"confidence":0.7}'
    )


# ── Drill ────────────────────────────────────────────────────────
async def main() -> None:
    # ── Step 1: migration 002 creates table + indexes ───────────
    step("1. migration 002 creates advisor_council_runs table + 4 indexes")
    with tempfile.TemporaryDirectory() as tmp:
        db_path = pathlib.Path(tmp) / "step1.db"
        mem = AdvisorMemory(db_path)
        # Probe the schema directly via SQLite master
        import sqlite3
        conn = sqlite3.connect(str(db_path))
        try:
            tables = {
                r[0] for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            if "advisor_council_runs" not in tables:
                fail(
                    f"advisor_council_runs not created by migration 002. "
                    f"Tables: {sorted(tables)}"
                )
            indexes = {
                r[0] for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='index' "
                    "AND tbl_name='advisor_council_runs'"
                ).fetchall()
            }
            expected = {
                "idx_council_runs_event_id",
                "idx_council_runs_outcome",
                "idx_council_runs_created_at",
                "idx_council_runs_advisor_id",
            }
            missing_idx = expected - indexes
            if missing_idx:
                fail(
                    f"missing indexes: {missing_idx}. "
                    f"Dashboard queries (filter by outcome / event_id / "
                    f"created_at) will full-table-scan without these."
                )
        finally:
            conn.close()
        ok(f"table + 4 indexes present: {sorted(expected)}")

    # ── Step 2: record_council_run preserves telemetry fields ───
    step(
        "2. record_council_run preserves outcome, prompt_version, "
        "duration_s, drafts_json, reviews_json, failed_authors"
    )
    with tempfile.TemporaryDirectory() as tmp:
        mem = AdvisorMemory(pathlib.Path(tmp) / "step2.db")
        mem.set_policy_version("v1")
        # Seed an event row to attach the council run to
        event_id = mem.record_event(
            event_type="pr_review",
            source="manual",
            content="diff --git a/foo.py b/foo.py\n@@ -1 +1 @@\n-old\n+new",
            model_used="deepseek-coder:6.7b-instruct",
            advisor_output={
                "summary": "test", "risk_level": "LOW",
                "top_3_advice": ["a"], "confidence": 0.5,
            },
        )
        telemetry = _make_canned_telemetry()
        run_id = mem.record_council_run(event_id=event_id, telemetry=telemetry)
        if run_id <= 0:
            fail(f"record_council_run returned bad id: {run_id}")

        rows = mem.get_council_runs(event_id=event_id)
        if len(rows) != 1:
            fail(f"expected 1 council run, got {len(rows)}")
        row = rows[0]
        # All fields preserved through JSON roundtrip
        if row["outcome"] != "ok":
            fail(f"outcome lost: {row['outcome']!r}")
        if row["prompt_version"] != "v_abc123":
            fail(f"prompt_version lost: {row['prompt_version']!r}")
        if abs(row["duration_s"] - 1.5) > 0.001:
            fail(f"duration_s drift: {row['duration_s']}")
        if row["advisor_id"] != "pr_review_chair":
            fail(f"advisor_id lost: {row['advisor_id']!r}")

        drafts = json.loads(row["drafts_json"])
        if len(drafts) != 2:
            fail(f"drafts count drift: {len(drafts)}")
        author_ids = {d["author_id"] for d in drafts}
        if author_ids != {"code_reviewer", "security_auditor"}:
            fail(f"draft author_ids drift: {author_ids}")
        # model_used preserved per-draft
        if drafts[0]["model_used"] != "deepseek-coder:6.7b-instruct":
            fail(f"per-draft model_used lost: {drafts[0]}")

        reviews = json.loads(row["reviews_json"])
        if len(reviews) != 1 or reviews[0]["score"] != 7.0:
            fail(f"review fields drift: {reviews}")
        ok(
            f"row id={run_id} preserves 2 drafts + 1 review with "
            f"per-author model_used + scores"
        )

    # ── Step 3: NEGATIVE — failure rows still persist ───────────
    step(
        "3. NEGATIVE: outcome=advisor_failed + advisor_error → "
        "row STILL inserts (audit must not skip failures)"
    )
    with tempfile.TemporaryDirectory() as tmp:
        mem = AdvisorMemory(pathlib.Path(tmp) / "step3.db")
        mem.set_policy_version("v1")
        event_id = mem.record_event(
            event_type="pr_review", source="manual",
            content="x", model_used="deepseek-coder:6.7b-instruct",
            advisor_output=None,
        )
        failure_telemetry = _make_canned_telemetry(
            outcome="advisor_failed",
            advisor_error="RuntimeError: chair crashed",
            failed_authors=[],
        )
        run_id = mem.record_council_run(
            event_id=event_id, telemetry=failure_telemetry,
        )
        if run_id <= 0:
            fail("failure-mode row didn't insert")
        row = mem.get_council_runs(event_id=event_id)[0]
        if row["outcome"] != "advisor_failed":
            fail(f"outcome lost: {row['outcome']!r}")
        if row["advisor_error"] != "RuntimeError: chair crashed":
            fail(
                f"advisor_error lost: {row['advisor_error']!r}. "
                f"Without this, the dashboard can't tell why a chair "
                f"failed — only that it failed."
            )
        ok(
            f"failure row inserted with advisor_error preserved "
            f"(audit doesn't skip)"
        )

    # ── Step 4: NEGATIVE — event_id=None inserts ────────────────
    step(
        "4. NEGATIVE: event_id=None (operator backfill) → row STILL "
        "inserts; FK is nullable"
    )
    with tempfile.TemporaryDirectory() as tmp:
        mem = AdvisorMemory(pathlib.Path(tmp) / "step4.db")
        mem.set_policy_version("v1")
        run_id = mem.record_council_run(
            event_id=None,
            telemetry=_make_canned_telemetry(),
        )
        if run_id <= 0:
            fail("event_id=None row didn't insert")
        rows = mem.get_council_runs(event_id=None)
        # event_id=None filters for rows where event_id IS NULL — matches
        if len(rows) != 1:
            # SQLite "= NULL" doesn't match NULLs; our get_council_runs
            # passes event_id=None as a filter that's only added when
            # not None. So passing event_id=None means "no event_id
            # filter" — that's the convention. Verify the row exists
            # with NO filter.
            rows = mem.get_council_runs()
            if len(rows) != 1:
                fail(f"event_id=None row not findable: {rows}")
        ok(f"event_id=None row inserted (id={run_id})")

    # ── Step 5: NEGATIVE — get_council_runs filters by event_id ─
    step(
        "5. NEGATIVE: get_council_runs(event_id=X) returns ONLY rows "
        "for that event (no cross-event leak)"
    )
    with tempfile.TemporaryDirectory() as tmp:
        mem = AdvisorMemory(pathlib.Path(tmp) / "step5.db")
        mem.set_policy_version("v1")
        e1 = mem.record_event(
            event_type="pr_review", source="manual", content="x1",
            model_used="m", advisor_output=None,
        )
        e2 = mem.record_event(
            event_type="pr_review", source="manual", content="x2",
            model_used="m", advisor_output=None,
        )
        mem.record_council_run(event_id=e1, telemetry=_make_canned_telemetry())
        mem.record_council_run(event_id=e1, telemetry=_make_canned_telemetry())
        mem.record_council_run(event_id=e2, telemetry=_make_canned_telemetry())
        rows_e1 = mem.get_council_runs(event_id=e1)
        rows_e2 = mem.get_council_runs(event_id=e2)
        if len(rows_e1) != 2:
            fail(f"event_id={e1} should have 2 runs, got {len(rows_e1)}")
        if len(rows_e2) != 1:
            fail(f"event_id={e2} should have 1 run, got {len(rows_e2)}")
        # NEGATIVE: every returned row's event_id matches the filter
        leaked = [r for r in rows_e1 if r["event_id"] != e1]
        if leaked:
            fail(
                f"event_id filter leaked rows from other events: {leaked}"
            )
        ok(
            f"event_id={e1}: {len(rows_e1)} runs; event_id={e2}: "
            f"{len(rows_e2)} runs; no cross-event leak"
        )

    # ── Step 6: get_council_runs(outcome=...) filters ───────────
    step("6. get_council_runs(outcome='partial') filters correctly")
    with tempfile.TemporaryDirectory() as tmp:
        mem = AdvisorMemory(pathlib.Path(tmp) / "step6.db")
        mem.set_policy_version("v1")
        for outcome in ("ok", "partial", "advisor_failed", "ok"):
            mem.record_council_run(
                event_id=None,
                telemetry=_make_canned_telemetry(outcome=outcome),
            )
        partial_runs = mem.get_council_runs(outcome="partial")
        ok_runs = mem.get_council_runs(outcome="ok")
        all_runs = mem.get_council_runs()
        if len(partial_runs) != 1:
            fail(f"partial filter wrong: {len(partial_runs)} (expected 1)")
        if len(ok_runs) != 2:
            fail(f"ok filter wrong: {len(ok_runs)} (expected 2)")
        if len(all_runs) != 4:
            fail(f"unfiltered should be 4, got {len(all_runs)}")
        ok(
            f"outcome filter: ok={len(ok_runs)}, "
            f"partial={len(partial_runs)}, all={len(all_runs)}"
        )

    # ── Step 7: NEGATIVE — single-agent path returns telemetry=None ─
    step(
        "7. NEGATIVE: single-agent route (event_type='code') returns "
        "council_telemetry=None — no spurious council audit row"
    )
    import yaml
    policy = yaml.safe_load(
        (REPO / "services" / "sidecar-advisor" / "policy.yaml").read_text()
    )

    async def _stub_gen(model: str, prompt: str, timeout_s: float) -> str:
        return _make_chair_response()

    advisor = Advisor(policy, generate_fn=_stub_gen)
    parsed, raw, model_used, duration, telemetry = await advisor.review(
        event_type="code", content="def foo(): pass",
    )
    if telemetry is not None:
        fail(
            f"single-agent route should return telemetry=None, got "
            f"{telemetry!r}. Council runs would be over-counted on "
            f"the dashboard."
        )
    ok(f"single-agent path: telemetry=None (no spurious council row)")

    # And the council path returns telemetry as a dict
    parsed2, raw2, model2, dur2, telemetry2 = await advisor.review(
        event_type="pr_review", content="diff text",
    )
    if not isinstance(telemetry2, dict):
        fail(f"council path should return dict telemetry, got {type(telemetry2)}")
    if "drafts" not in telemetry2 or "reviews" not in telemetry2:
        fail(f"council telemetry missing drafts/reviews: {telemetry2}")
    ok(
        f"council path: telemetry contains "
        f"drafts({len(telemetry2['drafts'])}) + "
        f"reviews({len(telemetry2['reviews'])})"
    )

    # ── Step 8: NEGATIVE — partial telemetry inserts cleanly ────
    step(
        "8. NEGATIVE: telemetry with empty drafts (all_authors_failed) "
        "still inserts as empty JSON array, not a crash"
    )
    with tempfile.TemporaryDirectory() as tmp:
        mem = AdvisorMemory(pathlib.Path(tmp) / "step8.db")
        partial_tel = _make_canned_telemetry(
            outcome="all_authors_failed",
            failed_authors=["code_reviewer", "security_auditor", "test_advisor"],
            drafts=[],   # all crashed before producing
            reviews=[],
        )
        run_id = mem.record_council_run(event_id=None, telemetry=partial_tel)
        if run_id <= 0:
            fail("all_authors_failed row didn't insert")
        row = mem.get_council_runs()[0]
        drafts = json.loads(row["drafts_json"])
        reviews = json.loads(row["reviews_json"])
        failed = json.loads(row["failed_authors"])
        if drafts != []:
            fail(f"empty drafts not preserved as []: {drafts}")
        if reviews != []:
            fail(f"empty reviews not preserved as []: {reviews}")
        if set(failed) != {"code_reviewer", "security_auditor", "test_advisor"}:
            fail(f"failed_authors lost: {failed}")
        ok(
            f"all_authors_failed row: drafts=[], reviews=[], "
            f"failed_authors={sorted(failed)}"
        )

    print(f"\n{BOLD}{GREEN}{'=' * 50}{NC}")
    print(f"{BOLD}{GREEN}  ALL 8 COUNCIL-AUDIT STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}  (5 negative assertions: 3, 4, 5, 7, 8){NC}")
    print(f"{BOLD}{GREEN}{'=' * 50}{NC}")


if __name__ == "__main__":
    asyncio.run(main())
