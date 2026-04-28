#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: scripts/replay_verdict_log.py - parse watcher.log, find
pending REJECT verdicts, apply reverts idempotently.

Eight steps. Six negative assertions.

  1. parse_watcher_log returns one VerdictEntry per JSON line;
     all 5 fields (verdict, sha, rule_fired, reason, blocking_files)
     populated.
  2. find_pending_rejects filters APPROVE + HOLD; returns only REJECT.
  3. NEGATIVE: replayed.log shas are EXCLUDED from pending list
     (idempotency).
  4. NEGATIVE: malformed JSON line silently skipped (not crashed)
     so an operator hand-editing the log doesn't sink the replay.
  5. NEGATIVE: empty/missing watcher.log returns [] cleanly.
  6. NEGATIVE: apply_reverts continues across per-revert failures;
     successful shas land in replayed.log even if a later one fails.
  7. NEGATIVE: --apply is opt-in; default mode does NOT mutate
     replayed.log (dry-run safety).
  8. NEGATIVE: render_revert_plan handles empty rejects list +
     produces actionable git revert commands when non-empty.

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


def _load_replayer():
    p = REPO / "scripts" / "replay_verdict_log.py"
    spec = importlib.util.spec_from_file_location("replay_verdict_log", p)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["replay_verdict_log"] = mod
    spec.loader.exec_module(mod)
    return mod


rep = _load_replayer()


def _make_log(tmp: pathlib.Path, entries: list[dict]) -> pathlib.Path:
    p = tmp / "watcher.log"
    with p.open("w") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")
    return p


def main():
    # Step 1: parse all JSON lines into VerdictEntry
    step("1. parse_watcher_log returns one VerdictEntry per JSON line")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = pathlib.Path(tmp)
        log_path = _make_log(tmp_dir, [
            {
                "timestamp": "2026-04-28T10:00:00+00:00",
                "commit_sha": "abc123def456",
                "verdict": "APPROVE",
                "rule_fired": 6,
                "reason": "all rules passed",
                "blocking_files": [],
                "drill_outcome": "green",
            },
            {
                "timestamp": "2026-04-28T10:01:00+00:00",
                "commit_sha": "bad999000111",
                "verdict": "REJECT",
                "rule_fired": 1,
                "reason": "drill_failed: drill_x",
                "blocking_files": [],
                "drill_outcome": "FAILED",
            },
            {
                "timestamp": "2026-04-28T10:02:00+00:00",
                "commit_sha": "hold111222333",
                "verdict": "HOLD",
                "rule_fired": 3,
                "reason": "scope_extension_needed",
                "blocking_files": ["services/frontend/x.tsx"],
            },
        ])
        entries = rep.parse_watcher_log(log_path)
        if len(entries) != 3:
            fail(f"expected 3 entries, got {len(entries)}")
        verdicts = [e.verdict for e in entries]
        if verdicts != ["APPROVE", "REJECT", "HOLD"]:
            fail(f"verdict order drift: {verdicts}")
        if entries[1].rule_fired != 1:
            fail(f"REJECT entry rule_fired wrong: {entries[1].rule_fired}")
        if entries[2].blocking_files != ["services/frontend/x.tsx"]:
            fail(f"blocking_files lost: {entries[2].blocking_files}")
        ok(f"3 entries parsed; verdicts={verdicts}")

    # Step 2: find_pending_rejects filters APPROVE + HOLD
    step("2. find_pending_rejects returns ONLY REJECT verdicts")
    rejects = rep.find_pending_rejects(entries, replayed=set())
    if len(rejects) != 1:
        fail(f"expected 1 REJECT, got {len(rejects)}")
    if rejects[0].commit_sha != "bad999000111":
        fail(f"wrong reject sha: {rejects[0].commit_sha}")
    if rejects[0].verdict != "REJECT":
        fail(f"non-REJECT leaked through filter: {rejects[0].verdict}")
    ok(f"1 REJECT surfaced; APPROVE + HOLD filtered out")

    # Step 3: replayed shas excluded
    step("3. NEGATIVE: replayed.log shas EXCLUDED from pending (idempotent)")
    rejects_all = rep.find_pending_rejects(entries, replayed=set())
    rejects_replayed = rep.find_pending_rejects(
        entries, replayed={"bad999000111"},
    )
    if len(rejects_all) != 1 or len(rejects_replayed) != 0:
        fail(
            f"idempotency broken: all={len(rejects_all)} "
            f"replayed={len(rejects_replayed)}"
        )
    ok(f"replayed sha excluded; pending list shrinks 1 -> 0")

    # Step 4: malformed JSON line skipped
    step("4. NEGATIVE: malformed JSON line skipped (graceful, not crash)")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = pathlib.Path(tmp)
        # Mix valid + invalid lines
        log_path = tmp_dir / "watcher.log"
        with log_path.open("w") as f:
            f.write(json.dumps({
                "verdict": "APPROVE", "commit_sha": "good1",
                "timestamp": "2026-04-28T10:00:00+00:00",
                "rule_fired": 6, "reason": "ok", "blocking_files": [],
            }) + "\n")
            f.write("THIS IS NOT JSON {[}\n")  # malformed
            f.write("\n")  # blank
            f.write(json.dumps({
                "verdict": "REJECT", "commit_sha": "bad1",
                "timestamp": "2026-04-28T10:01:00+00:00",
                "rule_fired": 1, "reason": "fail", "blocking_files": [],
            }) + "\n")
        entries = rep.parse_watcher_log(log_path)
        if len(entries) != 2:
            fail(f"malformed line broke parsing: {len(entries)} entries")
        if [e.commit_sha for e in entries] != ["good1", "bad1"]:
            fail(f"entry order wrong: {[e.commit_sha for e in entries]}")
        ok(f"malformed line skipped; 2 valid entries surfaced")

    # Step 5: empty / missing log
    step("5. NEGATIVE: empty/missing watcher.log returns [] (no error)")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = pathlib.Path(tmp)
        # Empty file
        empty_log = tmp_dir / "empty.log"
        empty_log.write_text("")
        if rep.parse_watcher_log(empty_log) != []:
            fail("empty log not parsed as []")
        # Missing file
        missing_log = tmp_dir / "ghost.log"
        if rep.parse_watcher_log(missing_log) != []:
            fail("missing log not handled gracefully")
        # Empty replayed.log
        if rep.load_replayed_set(missing_log) != set():
            fail("missing replayed.log not handled gracefully")
        ok(f"empty + missing log handled cleanly")

    # Step 6: apply_reverts continues past per-revert failures
    step("6. NEGATIVE: apply_reverts captures per-revert failure; siblings continue")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = pathlib.Path(tmp)
        replayed_log = tmp_dir / "replayed.log"
        # Synthetic rejects
        rejects = [
            rep.VerdictEntry(
                timestamp="2026-04-28T10:00:00+00:00",
                commit_sha="sha_ok_1", verdict="REJECT", rule_fired=1,
                reason="r", blocking_files=[], raw={},
            ),
            rep.VerdictEntry(
                timestamp="2026-04-28T10:01:00+00:00",
                commit_sha="sha_BAD",  verdict="REJECT", rule_fired=1,
                reason="r", blocking_files=[], raw={},
            ),
            rep.VerdictEntry(
                timestamp="2026-04-28T10:02:00+00:00",
                commit_sha="sha_ok_3", verdict="REJECT", rule_fired=1,
                reason="r", blocking_files=[], raw={},
            ),
        ]

        def fake_revert(sha):
            if "BAD" in sha:
                return False, "merge conflict"
            return True, None

        results = rep.apply_reverts(
            rejects, revert_fn=fake_revert, replayed_log=replayed_log,
        )
        if len(results) != 3:
            fail(f"expected 3 results, got {len(results)}")
        # 2 successes, 1 failure - none should sink the others
        successes = [r for r in results if r.success]
        failures = [r for r in results if not r.success]
        if len(successes) != 2 or len(failures) != 1:
            fail(f"results split wrong: {len(successes)} ok / {len(failures)} fail")
        if failures[0].commit_sha != "sha_BAD":
            fail(f"wrong failure sha: {failures[0].commit_sha}")
        if "merge conflict" not in failures[0].error:
            fail(f"error message lost: {failures[0].error}")
        # Successful shas in replayed.log; failed sha NOT
        on_disk = replayed_log.read_text()
        if "sha_ok_1" not in on_disk or "sha_ok_3" not in on_disk:
            fail(f"successful shas missing from replayed.log: {on_disk!r}")
        if "sha_BAD" in on_disk:
            fail(
                f"failed sha leaked into replayed.log: {on_disk!r}. "
                f"Idempotency broken - re-run wouldn't retry the bad one."
            )
        ok(f"2 reverted, 1 failed; only successes in replayed.log")

    # Step 7: --apply is opt-in (dry-run does NOT mutate replayed.log)
    step("7. NEGATIVE: dry-run mode (no --apply) does NOT mutate replayed.log")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = pathlib.Path(tmp)
        # Set up watcher.log + replayed.log
        log_path = _make_log(tmp_dir, [
            {
                "timestamp": "x", "commit_sha": "drysha",
                "verdict": "REJECT", "rule_fired": 1,
                "reason": "r", "blocking_files": [],
            },
        ])
        replayed_log = tmp_dir / "replayed.log"
        # Run cli() in dry-run mode by patching argv
        import io
        import contextlib
        original_argv = sys.argv
        try:
            sys.argv = [
                "replay_verdict_log.py",
                "--watcher-log", str(log_path),
                "--replayed-log", str(replayed_log),
                # no --apply
            ]
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                exit_code = rep.cli()
        finally:
            sys.argv = original_argv
        if exit_code != 0:
            fail(f"dry-run should exit 0, got {exit_code}")
        # replayed.log should NOT have been written
        if replayed_log.exists():
            fail(
                f"dry-run wrote to replayed.log - safety violation. "
                f"Operator hasn't consented to revert yet."
            )
        # Output should mention pending REJECT
        out = buf.getvalue()
        if "drysha" not in out:
            fail(f"dry-run output should list pending REJECT sha: {out!r}")
        if "git revert" not in out:
            fail(f"dry-run should suggest git revert command: {out!r}")
        ok(f"dry-run lists pending without mutating replayed.log")

    # Step 8: render_revert_plan edge cases
    step("8. NEGATIVE: render_revert_plan handles empty + non-empty cleanly")
    empty = rep.render_revert_plan([])
    if "No pending" not in empty and "Nothing" not in empty:
        fail(f"empty plan should say 'no pending' / 'nothing': {empty!r}")
    nonempty = rep.render_revert_plan([
        rep.VerdictEntry(
            timestamp="x", commit_sha="abc123",
            verdict="REJECT", rule_fired=1,
            reason="drill_failed", blocking_files=[], raw={},
        ),
    ])
    if "git revert --no-edit abc123" not in nonempty:
        fail(f"plan should include actionable revert command: {nonempty!r}")
    if "rule_fired=1" not in nonempty:
        fail(f"plan should include rule_fired: {nonempty!r}")
    ok(f"render_revert_plan: empty + non-empty both formatted cleanly")

    print(f"\n{BOLD}{GREEN}{'=' * 50}{NC}")
    print(f"{BOLD}{GREEN}  ALL 8 REPLAY-VERDICT-LOG STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}  (6 negative assertions: 3, 4, 5, 6, 7, 8){NC}")
    print(f"{BOLD}{GREEN}{'=' * 50}{NC}")


if __name__ == "__main__":
    main()
