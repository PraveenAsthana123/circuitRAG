#!/usr/bin/env python3
# RESOURCES: readonly
"""
E2E meta-drill: full Phase 4 + Phase 2A2 + Phase 1B-static chain
in one tmpdir scenario.

Per-piece drills already exercise each script in isolation. This
drill catches integration bugs the per-piece drills miss:

  * Path drift: capture_and_review writes to council_runs.log,
    render_dashboard reads from there - if either side changes
    paths, only this drill catches it.
  * Schema drift: capture_and_review writes advisor_council_runs
    rows, replay_verdict_log reads watcher.log, render_dashboard
    queries the DB - mismatch between writer + reader = silent.
  * Composition order: post-commit hook calls
    loop_watcher_hook.py FIRST then capture_and_review.py - swap
    them and the watcher.log doesn't reflect the latest commit
    until the next commit.

Six exercised steps in this local drill shape. Six negative assertions.

  1. Set up tmpdir git repo + advisor.db; make a meaningful commit.
  2. Run loop_watcher_hook.main + capture_and_review.capture_and_record
     against the same commit; both succeed.
  3. NEGATIVE: advisor.db has BOTH the event row AND the
     council_run row keyed by the same event_id (the chain's
     load-bearing FK).
  4. NEGATIVE: .loop/watcher.log AND .loop/council_runs.log
     each have ONE entry from this commit; no duplicates,
     no missing.
  5. NEGATIVE: render_dashboard.render_html includes the event
     summary AND the verdict AND the council outcome (all 3
     data sources joined).
  6. NEGATIVE: replay_verdict_log.parse_watcher_log returns the
     verdict from this commit (writer + reader file-format
     compatibility).
  7. NEGATIVE: prune_council_runs(older_than_days=0, dry_run=False)
     removes the just-written council_run; events row stays
     (separation of retention is real).
  8. NEGATIVE: drill-status writer + LoopWatcher rule 1 chain:
     write a failing-drill status; rule 1 fires REJECT verdict;
     the verdict appears in watcher.log.

Tag: readonly. Pure-Python -- runs in tier 1.
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile
import types

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


def _load_mod(rel: str, name: str):
    p = REPO / rel
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# Set up package context for sidecar relative imports (advisor + council)
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

watcher_hook = _load_mod(
    "scripts/loop_watcher_hook.py", "loop_watcher_hook_e2e",
)
capture_review = _load_mod(
    "scripts/capture_and_review.py", "capture_and_review_e2e",
)
render = _load_mod(
    "scripts/render_dashboard.py", "render_dashboard_e2e",
)
replay = _load_mod(
    "scripts/replay_verdict_log.py", "replay_verdict_log_e2e",
)

AdvisorMemory = memory_mod.AdvisorMemory
Advisor = advisor_mod.Advisor


def _git(args, cwd):
    return subprocess.run(
        ["git", *args], capture_output=True, text=True,
        cwd=str(cwd), check=True,
    )


def _init_repo(d):
    _git(["init", "--initial-branch=main"], d)
    _git(["config", "user.email", "e2e@e2e.local"], d)
    _git(["config", "user.name", "e2e"], d)
    _git(["config", "commit.gpgsign", "false"], d)


def _stub_advisor(policy):
    async def gen(model, prompt, timeout_s):
        if prompt.rstrip().endswith("JSON:"):
            return ('{"summary":"e2e summary","risk_level":"LOW",'
                    '"top_3_advice":["a","b","c"],"confidence":0.8}')
        if "SCORE: <integer 0-10>" in prompt:
            return "ok\nSCORE: 7"
        return f"draft from {model}"
    return Advisor(policy, generate_fn=gen)


async def main():
    import yaml
    policy = yaml.safe_load(
        (REPO / "services" / "sidecar-advisor" / "policy.yaml").read_text()
    )

    # Step 1 + 2: spin up repo, run both hooks
    step(
        "1+2. tmpdir git + advisor.db; loop_watcher_hook + "
        "capture_and_review both run cleanly"
    )
    with tempfile.TemporaryDirectory() as tmp:
        d = pathlib.Path(tmp)
        _init_repo(d)
        # Initial commit
        (d / "src.py").write_text("def f(): return 1\n")
        _git(["add", "."], d)
        _git(["commit", "-m", "feat: init"], d)
        # Substantive change
        (d / "src.py").write_text(
            "def f(x: int) -> int:\n"
            "    if x < 0:\n        raise ValueError('neg')\n"
            "    if x > 100:\n        raise OverflowError('big')\n"
            "    return x * 2\n"
        )
        _git(["add", "."], d)
        _git(["commit", "-m", "feat: validate input"], d)

        # Run watcher (with synthetic args bypassing real git+drill paths)
        sha = _git(["rev-parse", "HEAD"], d).stdout.strip()
        msg = _git(["log", "-1", "--format=%B", "HEAD"], d).stdout.strip()
        files = [
            ln.strip() for ln in
            _git(["show", "--name-only", "--format=", "HEAD"], d)
            .stdout.splitlines() if ln.strip()
        ]

        watcher_log = d / ".loop" / "watcher.log"
        council_log = d / ".loop" / "council_runs.log"

        # Run watcher
        watcher_entry = watcher_hook.main(
            commit_sha=sha, commit_message=msg, files_touched=files,
            drill_status_path=d / ".loop" / "drill_status.json",
            log_path=watcher_log,
            recent_files_per_commit=[],
            policy_path=d / "no_policy.md",  # missing -> no scope ext
        )
        if watcher_entry["verdict"] != "APPROVE":
            # Files src.py is unknown disposition (default gated) so HOLD
            # is also acceptable. Just verify the chain ran.
            pass

        # Run capture_and_review
        mem = AdvisorMemory(d / "advisor.db")
        mem.set_policy_version("v_e2e")
        advisor = _stub_advisor(policy)
        cap_result = await capture_review.capture_and_record(
            repo=d, advisor=advisor, memory=mem,
            council_log_path=council_log, fire_council=True,
        )
        if cap_result.filtered:
            fail(f"meaningful diff filtered: {cap_result.reason}")
        if not cap_result.fired:
            fail(f"council didn't fire: {cap_result}")
        ok(
            f"watcher verdict={watcher_entry['verdict']}; "
            f"capture fired event_id={cap_result.event_id} "
            f"council_run_id={cap_result.council_run_id}"
        )

        # Step 3: DB has event + council_run linked
        step("3. NEGATIVE: advisor.db has event + council_run linked by FK")
        events = mem.recent_events(limit=10)
        if len(events) != 1:
            fail(f"expected 1 event, got {len(events)}")
        eid = events[0]["id"]
        if eid != cap_result.event_id:
            fail(
                f"event_id drift: capture says {cap_result.event_id}, "
                f"DB says {eid}"
            )
        runs = mem.get_council_runs(event_id=eid)
        if len(runs) != 1:
            fail(f"expected 1 council_run for event {eid}, got {len(runs)}")
        ok(f"FK link intact: event_id={eid} -> council_run_id={runs[0]['id']}")

        # Step 4: both logs have one entry
        step("4. NEGATIVE: watcher.log + council_runs.log each have 1 entry")
        watcher_lines = watcher_log.read_text().strip().splitlines()
        council_lines = council_log.read_text().strip().splitlines()
        if len(watcher_lines) != 1:
            fail(f"watcher.log: expected 1 line, got {len(watcher_lines)}")
        if len(council_lines) != 1:
            fail(f"council_runs.log: expected 1 line, got {len(council_lines)}")
        # Each line is valid JSON
        json.loads(watcher_lines[0])
        json.loads(council_lines[0])
        ok(f"both logs have exactly 1 valid JSON line each")

        # Step 5: render_dashboard joins all 3 sources
        step(
            "5. NEGATIVE: render_dashboard joins event + verdict + council"
        )
        html_out = render.render_html(
            db_path=d / "advisor.db",
            watcher_log_path=watcher_log,
            council_log_path=council_log,
        )
        if "e2e summary" not in html_out:
            fail("event summary missing from rendered HTML")
        # Verdict (APPROVE or HOLD) + the rule_fired number
        if "verdict-" not in html_out:
            fail("verdict CSS class missing - watcher entry not rendered")
        if "Recent council runs" not in html_out:
            fail("council section missing")
        # The capture's reason mentions risk=LOW
        if "risk-LOW" not in html_out and "council_completed" not in html_out:
            fail("council outcome not surfaced in HTML")
        ok(f"HTML joins all 3 sources (event + verdict + council)")

        # Step 6: replay_verdict_log parses the watcher.log
        step(
            "6. NEGATIVE: replay_verdict_log.parse_watcher_log parses "
            "watcher_hook's output (writer + reader format compatible)"
        )
        verdicts = replay.parse_watcher_log(watcher_log)
        if len(verdicts) != 1:
            fail(f"replay parsed {len(verdicts)} verdicts, expected 1")
        v = verdicts[0]
        if v.commit_sha != sha[:12]:
            fail(f"sha drift: parser={v.commit_sha}, original={sha[:12]}")
        if v.verdict not in ("APPROVE", "HOLD", "REJECT"):
            fail(f"verdict format drift: {v.verdict}")
        ok(f"parser found verdict={v.verdict} sha={v.commit_sha}")

        # Step 7: prune deletes OLD council_run; events row stays.
        # Insert a synthetic backdated row so prune has a clearly-old
        # target (the just-written council_run lands in the same
        # iso-second as `now`, so older_than_days=0 wouldn't delete it).
        step(
            "7. NEGATIVE: prune deletes backdated council_run; "
            "event row + fresh council_run preserved"
        )
        import sqlite3 as _sqlite3
        from datetime import datetime as _dt, timedelta as _td, timezone as _tz
        old_iso = (
            _dt.now(_tz.utc) - _td(days=120)
        ).isoformat(timespec="seconds")
        with _sqlite3.connect(str(d / "advisor.db")) as conn:
            conn.execute(
                """
                INSERT INTO advisor_council_runs (
                    event_id, created_at, outcome, advisor_id,
                    prompt_version, duration_s, advisor_error,
                    failed_authors, drafts_json, reviews_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    eid, old_iso, "ok", "chair_old", "v_old",
                    1.0, None, "[]", "[]", "[]",
                ),
            )
        prune_result = mem.prune_council_runs(
            older_than_days=90, dry_run=False,
        )
        if prune_result["deleted"] != 1:
            fail(
                f"prune should delete 1 backdated council_run, "
                f"got {prune_result}"
            )
        events_after = mem.recent_events(limit=10)
        if len(events_after) != 1:
            fail(f"prune deleted events: {len(events_after)} (expected 1)")
        runs_after = mem.get_council_runs(event_id=eid)
        if len(runs_after) != 1:
            fail(
                f"prune deleted the fresh council_run too: got "
                f"{len(runs_after)}, expected 1"
            )
        ok(
            f"prune deleted 1 backdated council_run; event_id={eid} "
            f"+ fresh council_run preserved (retention separation honoured)"
        )

        # Step 8: rule 1 chain - drill failure -> REJECT in watcher.log
        step(
            "8. NEGATIVE: drill_status writer -> LoopWatcher rule 1 -> "
            "REJECT verdict appears in watcher.log"
        )
        # Write a failing-drill status file
        status_path = d / ".loop" / "drill_status.json"
        status_path.write_text(json.dumps({
            "failed_drills": ["drill_xyz"],
            "total_drills": 30,
        }))
        # New commit
        (d / "src.py").write_text(
            (d / "src.py").read_text() + "\nNEW = 'line'\n"
        )
        _git(["add", "."], d)
        _git(["commit", "-m", "fix: tweak"], d)
        sha2 = _git(["rev-parse", "HEAD"], d).stdout.strip()
        # Rerun watcher with the failing-drill status
        entry2 = watcher_hook.main(
            commit_sha=sha2, commit_message="fix: tweak",
            files_touched=["src.py"],
            drill_status_path=status_path,
            log_path=watcher_log,
            recent_files_per_commit=[],
            policy_path=d / "no_policy.md",
        )
        if entry2["verdict"] != "REJECT":
            fail(
                f"rule 1 chain broken: drill_status says FAILED but "
                f"verdict={entry2['verdict']}"
            )
        if entry2["rule_fired"] != 1:
            fail(f"rule_fired should be 1, got {entry2['rule_fired']}")
        if "drill_xyz" not in entry2["drill_failures"]:
            fail(f"drill name lost: {entry2['drill_failures']}")
        # Watcher log now has 2 entries
        all_lines = watcher_log.read_text().strip().splitlines()
        if len(all_lines) != 2:
            fail(f"watcher.log should have 2 entries, has {len(all_lines)}")
        # Replay parser sees both
        all_verdicts = replay.parse_watcher_log(watcher_log)
        rejects = [v for v in all_verdicts if v.verdict == "REJECT"]
        if len(rejects) != 1:
            fail(f"replay should find 1 REJECT, found {len(rejects)}")
        ok(
            f"rule 1 chain: failing drill -> REJECT (rule 1) -> "
            f"watcher.log -> replay parser surfaced"
        )

    print(f"\n{BOLD}{GREEN}{'=' * 50}{NC}")
    print(f"{BOLD}{GREEN}  ALL 8 E2E LOOP-CHAIN STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}  (6 negative assertions: 3, 4, 5, 6, 7, 8){NC}")
    print(f"{BOLD}{GREEN}{'=' * 50}{NC}")


if __name__ == "__main__":
    asyncio.run(main())
