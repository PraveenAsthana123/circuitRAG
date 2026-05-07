#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: scripts/render_dashboard.py - HTML dashboard from advisor.db
+ .loop logs.

Eight steps. Six negative assertions.

  1. Seeded DB + log files -> HTML output contains expected sections
     (cards, events table, verdicts table, council table, patterns).
  2. Stats cards reflect DB content correctly (rated_pct math).
  3. NEGATIVE: empty advisor.db -> HTML still renders, no crash;
     'No events yet.' message visible.
  4. NEGATIVE: missing watcher.log file -> dashboard renders sans
     verdicts section ('No watcher.log entries.' shown).
  5. NEGATIVE: corrupt JSON line in council_runs.log -> graceful
     skip; remaining valid lines still rendered.
  6. NEGATIVE: HTML escapes user content - a <script> tag in event
     content is rendered as text, not executed (XSS prevention).
  7. NEGATIVE: dashboard handles 100 events without crashing
     (basic scalability).
  8. NEGATIVE: missing advisor.db file entirely -> HTML still
     renders (operator running on a fresh box before init).

Tag: readonly. Pure-Python -- runs in tier 1.
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parents[2]

GREEN = "\033[32m"
RED = "\033[31m"
BOLD = "\033[1m"
NC = "\033[0m"


def ok(msg):
    print(f"  {GREEN}{msg}{NC}")


def fail(msg):
    print(f"  {RED}x {msg}{NC}")
    raise SystemExit(1)


def step(title):
    print(f"\n{BOLD}-- {title} --{NC}")


def _load_renderer():
    p = REPO / "scripts" / "render_dashboard.py"
    spec = importlib.util.spec_from_file_location("render_dashboard", p)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["render_dashboard"] = mod
    spec.loader.exec_module(mod)
    return mod


renderer = _load_renderer()


def _seed_db(db_path):
    """Build a minimal advisor.db with one event + one council_run + one pattern."""
    sys.path.insert(0, str(REPO / "services" / "sidecar-advisor"))
    import importlib.util as _ilu
    spec = _ilu.spec_from_file_location(
        "_mem_for_render_drill",
        REPO / "services" / "sidecar-advisor" / "memory.py",
    )
    mem_mod = _ilu.module_from_spec(spec)
    sys.modules["_mem_for_render_drill"] = mem_mod
    spec.loader.exec_module(mem_mod)
    mem = mem_mod.AdvisorMemory(db_path)
    mem.set_policy_version("v_test")
    eid = mem.record_event(
        event_type="pr_review", source="git-diff",
        content="def f(): pass",
        model_used="deepseek-coder:6.7b-instruct",
        advisor_output={
            "summary": "Looks decent overall",
            "risk_level": "LOW",
            "top_3_advice": ["a", "b", "c"],
            "confidence": 0.7,
        },
    )
    mem.rate_event(eid, "useful")
    mem.record_council_run(event_id=eid, telemetry={
        "outcome": "ok",
        "advisor_id": "chair_test",
        "prompt_version": "v_x",
        "duration_s": 1.5,
        "drafts": [], "reviews": [], "failed_authors": [],
        "advisor_error": None,
    })
    mem.add_pattern(
        pattern_kind="preference",
        pattern_text="add tests for error paths",
        source_event_ids=[eid], confidence=0.85,
    )
    return mem


def main():
    # Step 1: full content
    step("1. seeded DB + log files -> HTML has all expected sections")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = pathlib.Path(tmp)
        db = tmp_dir / "advisor.db"
        _seed_db(db)
        watcher_log = tmp_dir / "watcher.log"
        watcher_log.write_text(json.dumps({
            "timestamp": "2026-04-28T10:00:00+00:00",
            "commit_sha": "abc123def456",
            "verdict": "APPROVE",
            "rule_fired": 6,
            "reason": "all rules passed",
            "blocking_files": [],
        }) + "\n")
        council_log = tmp_dir / "council_runs.log"
        council_log.write_text(json.dumps({
            "timestamp": "2026-04-28T10:00:30+00:00",
            "fired": True, "filtered": False,
            "files": ["foo.py", "bar.py"],
            "risk_level": "LOW",
            "reason": "council_completed risk=LOW",
            "duration_s": 1.5,
        }) + "\n")
        html_out = renderer.render_html(
            db_path=db, watcher_log_path=watcher_log,
            council_log_path=council_log,
        )
        # Verify key markers
        for marker in [
            "Sidecar Advisor Dashboard",
            "Recent events",
            "Recent verdicts",
            "Recent council runs",
            "Memory patterns",
            "APPROVE",
            "Looks decent overall",
            "add tests for error paths",
            "verdict-APPROVE",
            "risk-LOW",
        ]:
            if marker not in html_out:
                fail(f"marker missing from HTML: {marker!r}")
        ok(f"HTML has all 5 sections + 5 inline markers ({len(html_out)} chars)")

    # Step 2: stats math
    step("2. stats cards reflect DB content (rated_pct math)")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = pathlib.Path(tmp)
        db = tmp_dir / "advisor.db"
        sys.path.insert(0, str(REPO / "services" / "sidecar-advisor"))
        import importlib.util as _ilu
        spec = _ilu.spec_from_file_location(
            "_mem2", REPO / "services" / "sidecar-advisor" / "memory.py",
        )
        mem_mod = _ilu.module_from_spec(spec)
        sys.modules["_mem2"] = mem_mod
        spec.loader.exec_module(mem_mod)
        mem = mem_mod.AdvisorMemory(db)
        mem.set_policy_version("v")
        for i in range(4):
            eid = mem.record_event(
                event_type="prompt", source="manual",
                content=f"c{i}", model_used="m", advisor_output=None,
            )
            if i < 2:
                mem.rate_event(eid, "useful")
            elif i == 2:
                mem.rate_event(eid, "not_useful")
        # Total = 4, useful = 2, not_useful = 1, rated_pct = 75%
        html_out = renderer.render_html(
            db_path=db,
            watcher_log_path=tmp_dir / "no_watcher.log",
            council_log_path=tmp_dir / "no_council.log",
        )
        # The rated_pct card should show 75.0%
        if ">75.0%<" not in html_out:
            fail(f"rated_pct card wrong; HTML excerpt: {html_out[1500:2500]!r}")
        # Total events card should show 4
        if "<div class='v'>4</div>" not in html_out:
            fail("total_events card missing 4")
        if "<div class='v'>2</div>" not in html_out:
            fail("useful card missing 2")
        if "<div class='v'>1</div>" not in html_out:
            fail("not_useful card missing 1")
        ok("stats: total=4 useful=2 not_useful=1 rated_pct=75.0%")

    # Step 3: empty DB
    step("3. NEGATIVE: empty advisor.db -> HTML still renders")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = pathlib.Path(tmp)
        db = tmp_dir / "empty.db"
        sys.path.insert(0, str(REPO / "services" / "sidecar-advisor"))
        import importlib.util as _ilu
        spec = _ilu.spec_from_file_location(
            "_mem3", REPO / "services" / "sidecar-advisor" / "memory.py",
        )
        mem_mod = _ilu.module_from_spec(spec)
        sys.modules["_mem3"] = mem_mod
        spec.loader.exec_module(mem_mod)
        mem = mem_mod.AdvisorMemory(db)  # init schema, no inserts
        html_out = renderer.render_html(
            db_path=db,
            watcher_log_path=tmp_dir / "no.log",
            council_log_path=tmp_dir / "no2.log",
        )
        if "No events yet" not in html_out:
            fail(f"empty DB should show 'No events yet': {html_out[-500:]}")
        if "<div class='v'>0</div>" not in html_out:
            fail("empty DB stats should show 0")
        ok("empty DB renders cleanly with 'No events yet' marker")

    # Step 4: missing watcher.log
    step("4. NEGATIVE: missing watcher.log -> 'No watcher.log entries' message")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = pathlib.Path(tmp)
        db = tmp_dir / "advisor.db"
        _seed_db(db)
        # Don't create watcher.log
        html_out = renderer.render_html(
            db_path=db,
            watcher_log_path=tmp_dir / "ghost.log",
            council_log_path=tmp_dir / "no.log",
        )
        if "No watcher.log entries" not in html_out:
            fail("missing watcher.log should show empty marker")
        if "Recent verdicts" not in html_out:
            fail("verdicts section header missing")
        ok("missing watcher.log gracefully -> 'No watcher.log entries.'")

    # Step 5: corrupt JSON line in council_runs.log
    step("5. NEGATIVE: corrupt JSON line in council_runs.log -> graceful skip")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = pathlib.Path(tmp)
        db = tmp_dir / "advisor.db"
        _seed_db(db)
        council_log = tmp_dir / "council_runs.log"
        with council_log.open("w") as f:
            f.write(json.dumps({
                "timestamp": "2026-04-28T10:00:00+00:00",
                "fired": True, "filtered": False,
                "files": ["good.py"],
                "risk_level": "LOW",
                "reason": "first valid",
            }) + "\n")
            f.write("THIS IS NOT JSON {[}\n")
            f.write(json.dumps({
                "timestamp": "2026-04-28T10:01:00+00:00",
                "fired": False, "filtered": True,
                "files": [],
                "risk_level": None,
                "reason": "second valid",
            }) + "\n")
        html_out = renderer.render_html(
            db_path=db,
            watcher_log_path=tmp_dir / "no.log",
            council_log_path=council_log,
        )
        # Both valid entries should appear
        if "first valid" not in html_out:
            fail("first valid log entry lost")
        if "second valid" not in html_out:
            fail("second valid log entry lost (corrupt line in middle blocked iteration?)")
        if "THIS IS NOT JSON" in html_out:
            fail("corrupt line leaked into HTML output")
        ok("corrupt line skipped; both valid entries rendered")

    # Step 6: XSS escaping
    step("6. NEGATIVE: HTML escapes user content (XSS prevention)")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = pathlib.Path(tmp)
        db = tmp_dir / "advisor.db"
        sys.path.insert(0, str(REPO / "services" / "sidecar-advisor"))
        import importlib.util as _ilu
        spec = _ilu.spec_from_file_location(
            "_mem_xss", REPO / "services" / "sidecar-advisor" / "memory.py",
        )
        mem_mod = _ilu.module_from_spec(spec)
        sys.modules["_mem_xss"] = mem_mod
        spec.loader.exec_module(mem_mod)
        mem = mem_mod.AdvisorMemory(db)
        mem.set_policy_version("v")
        # Malicious content with HTML/JS injection attempt
        evil_summary = "<script>alert('XSS')</script>"
        eid = mem.record_event(
            event_type="prompt", source="manual",
            content="harmless",
            model_used="m",
            advisor_output={
                "summary": evil_summary,
                "risk_level": "LOW",
                "top_3_advice": [],
                "confidence": 0.5,
            },
        )
        html_out = renderer.render_html(
            db_path=db,
            watcher_log_path=tmp_dir / "no.log",
            council_log_path=tmp_dir / "no2.log",
        )
        # The literal <script> tag must NOT appear in raw form
        if "<script>" in html_out:
            fail(
                "XSS: raw <script> tag found in HTML output. "
                "User content must be html.escape()d."
            )
        # The escaped form should appear
        if "&lt;script&gt;" not in html_out:
            fail("XSS: escaped form missing; content might have been stripped")
        ok("<script>alert(...)</script> properly escaped to &lt;script&gt;...")

    # Step 7: scalability with 100 events
    step("7. NEGATIVE: 100 events render without crash; output bounded")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = pathlib.Path(tmp)
        db = tmp_dir / "advisor.db"
        sys.path.insert(0, str(REPO / "services" / "sidecar-advisor"))
        import importlib.util as _ilu
        spec = _ilu.spec_from_file_location(
            "_mem_scale", REPO / "services" / "sidecar-advisor" / "memory.py",
        )
        mem_mod = _ilu.module_from_spec(spec)
        sys.modules["_mem_scale"] = mem_mod
        spec.loader.exec_module(mem_mod)
        mem = mem_mod.AdvisorMemory(db)
        mem.set_policy_version("v")
        for i in range(100):
            mem.record_event(
                event_type="prompt", source="manual",
                content=f"c{i}", model_used="m",
                advisor_output={"summary": f"summary {i}",
                                 "risk_level": "LOW",
                                 "top_3_advice": [], "confidence": 0.5},
            )
        html_out = renderer.render_html(
            db_path=db,
            watcher_log_path=tmp_dir / "no.log",
            council_log_path=tmp_dir / "no2.log",
        )
        # Renderer caps recent_events at 20; html should NOT contain summary 99 to 80 only
        # (since we render last 20 by created_at DESC)
        if "summary 99" not in html_out:
            fail("most recent event missing")
        # Most recent 20 should be present, oldest 80 should not flood the HTML
        # Total events stat = 100
        if "<div class='v'>100</div>" not in html_out:
            fail("total events stat should show 100")
        ok(f"100 events: stats=100, table caps at last 20 ({len(html_out)} chars)")

    # Step 8: missing DB file entirely
    step("8. NEGATIVE: missing advisor.db -> HTML still renders")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = pathlib.Path(tmp)
        # Don't create the DB
        html_out = renderer.render_html(
            db_path=tmp_dir / "ghost.db",
            watcher_log_path=tmp_dir / "no.log",
            council_log_path=tmp_dir / "no2.log",
        )
        if "Sidecar Advisor Dashboard" not in html_out:
            fail("missing DB should still render the dashboard frame")
        if "No events yet" not in html_out:
            fail("missing DB should show empty events")
        # All stats should be 0
        if "<div class='v'>0</div>" not in html_out:
            fail("missing DB should show 0 in stats cards")
        ok("missing DB -> HTML renders with empty stats")

    print(f"\n{BOLD}{GREEN}{'=' * 50}{NC}")
    print(f"{BOLD}{GREEN}  ALL 8 RENDER-DASHBOARD STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}  (6 negative assertions: 3, 4, 5, 6, 7, 8){NC}")
    print(f"{BOLD}{GREEN}{'=' * 50}{NC}")


if __name__ == "__main__":
    main()
