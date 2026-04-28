#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: scripts/capture_and_review.py - end-to-end pipeline from
`git commit` to council telemetry persisted in advisor.db.

Phase 2A2 closes the auto-feed loop: Phase 2A's capture_diff +
Phase 2D's council + Phase 2E's audit table all wire together.
This drill exercises that wiring with a real git repo in tmpdir,
real AdvisorMemory + Advisor (with stub generator), and
synthesised diffs.

Eight steps. Six negative assertions.

  1. Meaningful diff -> council fires -> event recorded ->
     council_run row recorded -> council_runs.log appended.
  2. files_touched flows from capture into the log entry.
  3. NEGATIVE: doc-only diff -> filtered (no council call,
     no event row, only filter-log entry).
  4. NEGATIVE: tiny diff (< MIN_PAYLOAD_LINES) -> filtered.
  5. NEGATIVE: --no-council mode records event but skips council;
     no advisor_council_runs row.
  6. NEGATIVE: capture_and_record never raises - council error
     captured in result.reason; event still recorded.
  7. NEGATIVE: council_runs.log APPENDS across invocations
     (each commit -> one new line, not overwrite).
  8. NEGATIVE: capture in non-git directory -> result.filtered=True
     with reason capture_error; no DB writes.

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
pipeline = _load_mod(
    "scripts/capture_and_review.py",
    "capture_and_review",
)

AdvisorMemory = memory_mod.AdvisorMemory
Advisor = advisor_mod.Advisor


def _git(args, cwd):
    return subprocess.run(
        ["git", *args], capture_output=True, text=True,
        cwd=str(cwd), check=True,
    )


def _init_repo(tmp_dir):
    _git(["init", "--initial-branch=main"], tmp_dir)
    _git(["config", "user.email", "t@t.local"], tmp_dir)
    _git(["config", "user.name", "T"], tmp_dir)
    _git(["config", "commit.gpgsign", "false"], tmp_dir)


def _commit_file(tmp_dir, name, content, message):
    p = tmp_dir / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    _git(["add", "."], tmp_dir)
    _git(["commit", "-m", message], tmp_dir)


def _make_stub_advisor(policy):
    """Build an Advisor whose generate_fn returns a canned chair JSON."""
    chair_response = (
        '{"summary":"caught some issues","risk_level":"MEDIUM",'
        '"top_3_advice":["a1","a2","a3"],"confidence":0.7}'
    )

    async def gen(model, prompt, timeout_s):
        if prompt.rstrip().endswith("JSON:"):
            return chair_response
        if "SCORE: <integer 0-10>" in prompt:
            return "ok\nSCORE: 7"
        return f"draft from {model}"

    return Advisor(policy, generate_fn=gen)


async def main():
    import yaml
    policy = yaml.safe_load(
        (REPO / "services" / "sidecar-advisor" / "policy.yaml").read_text()
    )

    # Step 1: meaningful diff -> council fires + records everything
    step("1. meaningful diff -> council fires -> event + council_run + log")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = pathlib.Path(tmp)
        _init_repo(tmp_dir)
        _commit_file(tmp_dir, "foo.py", "x=1\n", "feat: init")
        # Substantial change
        (tmp_dir / "foo.py").write_text(
            "def calculate(items: list) -> int:\n"
            "    if not items:\n"
            "        return 0\n"
            "    total = sum(items)\n"
            "    if total > 1000:\n"
            "        raise ValueError('overflow')\n"
            "    return total\n"
        )
        _git(["add", "."], tmp_dir)
        _git(["commit", "-m", "feat: enrich foo"], tmp_dir)

        mem = AdvisorMemory(tmp_dir / "advisor.db")
        mem.set_policy_version("v1")
        advisor = _make_stub_advisor(policy)
        log_path = tmp_dir / "council_runs.log"

        result = await pipeline.capture_and_record(
            repo=tmp_dir, advisor=advisor, memory=mem,
            council_log_path=log_path, fire_council=True,
        )
        if not result.fired:
            fail(f"council should fire on meaningful diff: {result}")
        if result.filtered:
            fail(f"meaningful diff should NOT be filtered: {result}")
        if result.risk_level != "MEDIUM":
            fail(f"risk_level should be MEDIUM (chair stub), got {result.risk_level}")
        if result.event_id is None:
            fail("event_id should be populated when fired=True")
        if result.council_run_id is None:
            fail("council_run_id should be populated when fired=True")
        # Verify DB rows exist
        events = mem.recent_events(limit=10)
        if len(events) != 1:
            fail(f"expected 1 event in DB, got {len(events)}")
        if events[0]["event_type"] != "pr_review":
            fail(f"event_type wrong: {events[0]['event_type']}")
        if events[0]["source"] != "git-diff":
            fail(f"source wrong: {events[0]['source']}")
        runs = mem.get_council_runs(event_id=result.event_id)
        if len(runs) != 1:
            fail(f"expected 1 council_run, got {len(runs)}")
        ok(f"event_id={result.event_id} council_run_id={result.council_run_id} risk={result.risk_level}")

    # Step 2: files_touched flows through
    step("2. files_touched flows from capture into the log entry")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = pathlib.Path(tmp)
        _init_repo(tmp_dir)
        _commit_file(tmp_dir, "init.py", "x=1\n", "feat: init")
        for name in ["a.py", "b.py", "nested/c.py"]:
            (tmp_dir / name).parent.mkdir(parents=True, exist_ok=True)
            (tmp_dir / name).write_text(
                "def func():\n    return 1\n\nCONST = 42\n"
                "def other():\n    pass\n"
            )
        _git(["add", "."], tmp_dir)
        _git(["commit", "-m", "feat: 3 files"], tmp_dir)

        mem = AdvisorMemory(tmp_dir / "advisor.db")
        mem.set_policy_version("v1")
        advisor = _make_stub_advisor(policy)
        log_path = tmp_dir / "council_runs.log"
        result = await pipeline.capture_and_record(
            repo=tmp_dir, advisor=advisor, memory=mem,
            council_log_path=log_path,
        )
        expected = {"a.py", "b.py", "nested/c.py"}
        if set(result.files_touched) != expected:
            fail(f"files_touched drift: {result.files_touched}")
        # Log entry should also have files
        log_lines = log_path.read_text().strip().splitlines()
        log_entry = json.loads(log_lines[-1])
        if set(log_entry["files"]) != expected:
            fail(f"log files drift: {log_entry['files']}")
        ok(f"files in result + log: {sorted(result.files_touched)}")

    # Step 3: doc-only diff filtered
    step("3. NEGATIVE: doc-only diff filtered (no council, no event)")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = pathlib.Path(tmp)
        _init_repo(tmp_dir)
        _commit_file(tmp_dir, "README.md", "# Title\n", "feat: init")
        (tmp_dir / "README.md").write_text(
            "# Title\n\n## A\nstuff\n## B\nmore\n## C\nyet more\n## D\nlast\n"
        )
        _git(["add", "."], tmp_dir)
        _git(["commit", "-m", "docs: expand"], tmp_dir)

        mem = AdvisorMemory(tmp_dir / "advisor.db")
        mem.set_policy_version("v1")
        advisor = _make_stub_advisor(policy)
        result = await pipeline.capture_and_record(
            repo=tmp_dir, advisor=advisor, memory=mem,
            council_log_path=tmp_dir / "council_runs.log",
        )
        if result.fired:
            fail(f"doc-only diff should NOT fire council: {result}")
        if not result.filtered:
            fail(f"doc-only diff should be filtered: {result}")
        if result.event_id is not None:
            fail(f"doc-only filter should skip event row: event_id={result.event_id}")
        events = mem.recent_events(limit=10)
        if events:
            fail(f"DB should have 0 events for filtered diff, got {len(events)}")
        ok(f"doc-only filtered cleanly; reason={result.reason}")

    # Step 4: tiny diff filtered
    step("4. NEGATIVE: tiny diff filtered")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = pathlib.Path(tmp)
        _init_repo(tmp_dir)
        _commit_file(tmp_dir, "tiny.py", "x = 1\n", "feat: init")
        (tmp_dir / "tiny.py").write_text("x = 2\n")  # 1-line change
        _git(["add", "."], tmp_dir)
        _git(["commit", "-m", "fix: tiny"], tmp_dir)

        mem = AdvisorMemory(tmp_dir / "advisor.db")
        mem.set_policy_version("v1")
        advisor = _make_stub_advisor(policy)
        result = await pipeline.capture_and_record(
            repo=tmp_dir, advisor=advisor, memory=mem,
            council_log_path=tmp_dir / "council_runs.log",
        )
        if result.fired or not result.filtered:
            fail(f"tiny diff should be filtered: {result}")
        ok(f"tiny diff filtered (saves council LLM cost)")

    # Step 5: --no-council mode
    step("5. NEGATIVE: --no-council records event but skips council")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = pathlib.Path(tmp)
        _init_repo(tmp_dir)
        _commit_file(tmp_dir, "x.py", "x=1\n", "feat: init")
        (tmp_dir / "x.py").write_text(
            "def f():\n    return 1\n\ndef g():\n    return 2\n"
            "def h():\n    return 3\n"
        )
        _git(["add", "."], tmp_dir)
        _git(["commit", "-m", "feat: f/g/h"], tmp_dir)

        mem = AdvisorMemory(tmp_dir / "advisor.db")
        mem.set_policy_version("v1")
        advisor = _make_stub_advisor(policy)
        result = await pipeline.capture_and_record(
            repo=tmp_dir, advisor=advisor, memory=mem,
            council_log_path=tmp_dir / "council_runs.log",
            fire_council=False,
        )
        if result.fired:
            fail(f"fire_council=False should skip council: {result}")
        if result.event_id is None:
            fail(f"--no-council should still record event: {result}")
        events = mem.recent_events(limit=10)
        if len(events) != 1:
            fail(f"expected 1 event, got {len(events)}")
        runs = mem.get_council_runs(event_id=result.event_id)
        if runs:
            fail(f"should be 0 council_runs for --no-council: {len(runs)}")
        ok(f"event recorded; no council_run row (saves LLM cost on bulk imports)")

    # Step 6: council error gracefully captured
    step("6. NEGATIVE: council error captured in reason; never raises")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = pathlib.Path(tmp)
        _init_repo(tmp_dir)
        _commit_file(tmp_dir, "y.py", "x=1\n", "feat: init")
        (tmp_dir / "y.py").write_text(
            "def a():\n    pass\n\ndef b():\n    pass\n\n"
            "def c():\n    pass\n"
        )
        _git(["add", "."], tmp_dir)
        _git(["commit", "-m", "feat: y"], tmp_dir)

        mem = AdvisorMemory(tmp_dir / "advisor.db")
        mem.set_policy_version("v1")

        # Build an advisor whose review() raises directly
        class _RaisingAdvisor:
            async def review(self, *, event_type, content):
                raise RuntimeError("simulated council total failure")

        result = await pipeline.capture_and_record(
            repo=tmp_dir,
            advisor=_RaisingAdvisor(),
            memory=mem,
            council_log_path=tmp_dir / "council_runs.log",
            fire_council=True,
        )
        # Should not raise; should populate reason
        if "council_error" not in result.reason:
            fail(f"council error not captured in reason: {result.reason}")
        # Event should still be recorded (we recorded it BEFORE firing)
        if result.event_id is None:
            fail(f"event should be recorded even on council error: {result}")
        ok(f"council exception captured; event still in DB; reason={result.reason[:80]!r}")

    # Step 7: log appends
    step("7. NEGATIVE: council_runs.log APPENDS across invocations")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = pathlib.Path(tmp)
        _init_repo(tmp_dir)
        _commit_file(tmp_dir, "first.py", "x=1\n", "feat: init")
        log_path = tmp_dir / "council_runs.log"
        mem = AdvisorMemory(tmp_dir / "advisor.db")
        mem.set_policy_version("v1")
        advisor = _make_stub_advisor(policy)
        # 3 separate invocations, each on a different commit
        for i, src in enumerate([
            "def f1():\n    return 1\ndef f1b():\n    return 2\ndef f1c():\n    return 3\n",
            "def f2():\n    return 1\ndef f2b():\n    return 2\ndef f2c():\n    return 3\n",
            "def f3():\n    return 1\ndef f3b():\n    return 2\ndef f3c():\n    return 3\n",
        ], 1):
            (tmp_dir / "first.py").write_text(src)
            _git(["add", "."], tmp_dir)
            _git(["commit", "-m", f"feat: change {i}"], tmp_dir)
            await pipeline.capture_and_record(
                repo=tmp_dir, advisor=advisor, memory=mem,
                council_log_path=log_path, fire_council=True,
            )
        lines = log_path.read_text().strip().splitlines()
        if len(lines) != 3:
            fail(f"expected 3 log lines after 3 invocations, got {len(lines)}")
        for ln in lines:
            entry = json.loads(ln)  # each line valid JSON
            if not entry.get("fired"):
                fail(f"each invocation should have fired=True: {entry}")
        ok(f"3 invocations -> 3 log lines (append, not overwrite)")

    # Step 8: non-git directory
    step("8. NEGATIVE: non-git directory -> filtered with capture_error reason")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = pathlib.Path(tmp)
        # Don't init git
        mem = AdvisorMemory(tmp_dir / "advisor.db")
        mem.set_policy_version("v1")
        advisor = _make_stub_advisor(policy)
        result = await pipeline.capture_and_record(
            repo=tmp_dir, advisor=advisor, memory=mem,
            council_log_path=tmp_dir / "council_runs.log",
            fire_council=True,
        )
        if result.fired:
            fail(f"non-git dir should not fire council: {result}")
        if not result.filtered:
            fail(f"non-git dir should filter: {result}")
        if "capture_error" not in result.reason:
            fail(f"reason should mention capture_error: {result.reason}")
        events = mem.recent_events(limit=10)
        if events:
            fail(f"non-git capture should NOT write events: {len(events)}")
        ok(f"non-git capture filtered cleanly; no DB writes")

    print(f"\n{BOLD}{GREEN}{'=' * 50}{NC}")
    print(f"{BOLD}{GREEN}  ALL 8 CAPTURE-AND-REVIEW STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}  (6 negative assertions: 3, 4, 5, 6, 7, 8){NC}")
    print(f"{BOLD}{GREEN}{'=' * 50}{NC}")


if __name__ == "__main__":
    asyncio.run(main())
