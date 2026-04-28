#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: services/sidecar-advisor/git_capture.py.

Spawns a real git repo in tmpdir, commits diffs, captures them.
Tier-1 friendly because git is universally available + tmpdir is
self-contained.

Eight steps. Six negative assertions.

  1. capture_diff returns the HEAD diff with content + files_touched
     populated.
  2. Files in the diff match what was actually committed.
  3. NEGATIVE: empty repo (no commits) returns DiffCapture with
     error set, no crash.
  4. NEGATIVE: initial commit (HEAD has no parent) handled
     gracefully via empty-tree diff.
  5. NEGATIVE: staged=True captures staged-but-uncommitted diff;
     plain mode does NOT see staged changes.
  6. NEGATIVE: is_likely_pr_review returns False for tiny diffs
     (< MIN_DIFF_LINES). Noise filter.
  7. NEGATIVE: is_likely_pr_review returns False for doc-only
     diffs (all files .md/.rst/.txt). Council shouldn't review
     prose.
  8. NEGATIVE: capture_diff in non-git directory returns
     DiffCapture with error set, no crash.

Tag: readonly. Pure-Python -- runs in tier 1 (git is universal).
"""
from __future__ import annotations

import importlib.util
import os
import pathlib
import subprocess
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


def _load_capture():
    p = REPO / "services" / "sidecar-advisor" / "git_capture.py"
    spec = importlib.util.spec_from_file_location("git_capture", p)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["git_capture"] = mod
    spec.loader.exec_module(mod)
    return mod


cap = _load_capture()
capture_diff = cap.capture_diff
is_likely_pr_review = cap.is_likely_pr_review


def _git(args, cwd):
    """Run a git command; raise on failure."""
    return subprocess.run(
        ["git", *args],
        capture_output=True, text=True, cwd=str(cwd), check=True,
    )


def _init_repo(tmp_dir: pathlib.Path) -> None:
    """Initialize a tmp git repo with a baseline commit."""
    _git(["init", "--initial-branch=main"], tmp_dir)
    _git(["config", "user.email", "test@test.local"], tmp_dir)
    _git(["config", "user.name", "Test User"], tmp_dir)
    _git(["config", "commit.gpgsign", "false"], tmp_dir)


def _commit_file(tmp_dir, name, content, message):
    (tmp_dir / name).write_text(content)
    _git(["add", name], tmp_dir)
    _git(["commit", "-m", message], tmp_dir)


def main():
    # Step 1: HEAD diff captures content
    step("1. capture_diff(HEAD) returns content + files_touched")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = pathlib.Path(tmp)
        _init_repo(tmp_dir)
        _commit_file(tmp_dir, "foo.py", "def foo(): pass\n", "feat: init")
        # Make a meaningful change
        (tmp_dir / "foo.py").write_text(
            "def foo() -> int:\n    return 42\n\n"
            "def bar() -> str:\n    return 'hi'\n"
        )
        (tmp_dir / "bar.py").write_text("BAR = 1\n")
        _git(["add", "."], tmp_dir)
        _git(["commit", "-m", "feat: enrich foo + add bar"], tmp_dir)

        capture = capture_diff(repo=tmp_dir, ref="HEAD")
        if capture.error:
            fail(f"capture errored: {capture.error}")
        if not capture.content.strip():
            fail("capture content empty")
        if capture.source != "git-diff-head":
            fail(f"source wrong: {capture.source}")
        if capture.line_count < 3:
            fail(f"line_count suspicious: {capture.line_count}")
        if not capture.sha or len(capture.sha) != 12:
            fail(f"sha wrong: {capture.sha!r}")
        ok(f"capture: {len(capture.content)} chars, {capture.line_count} lines, sha={capture.sha}")

    # Step 2: files_touched matches the commit
    step("2. files_touched matches what was actually committed")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = pathlib.Path(tmp)
        _init_repo(tmp_dir)
        _commit_file(tmp_dir, "foo.py", "x=1\n", "feat: init")
        (tmp_dir / "foo.py").write_text("x=2\n")
        (tmp_dir / "bar.py").write_text("y=1\n")
        (tmp_dir / "baz/qux.py").parent.mkdir(parents=True, exist_ok=True)
        (tmp_dir / "baz/qux.py").write_text("z=1\n")
        _git(["add", "."], tmp_dir)
        _git(["commit", "-m", "feat: 3 files"], tmp_dir)
        capture = capture_diff(repo=tmp_dir, ref="HEAD")
        expected = {"foo.py", "bar.py", "baz/qux.py"}
        actual = set(capture.files_touched)
        if actual != expected:
            fail(f"files_touched mismatch: got {actual}, expected {expected}")
        ok(f"files_touched = {sorted(actual)}")

    # Step 3: empty repo (no commits)
    step("3. NEGATIVE: empty repo (no commits) returns error, no crash")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = pathlib.Path(tmp)
        _git(["init", "--initial-branch=main"], tmp_dir)
        _git(["config", "user.email", "t@t.local"], tmp_dir)
        _git(["config", "user.name", "T"], tmp_dir)
        capture = capture_diff(repo=tmp_dir, ref="HEAD")
        if capture.error is None:
            fail(f"empty repo should set error, got {capture}")
        if capture.content.strip():
            fail(f"empty repo should have empty content: {capture.content!r}")
        ok(f"empty repo: error={capture.error[:60]!r}")

    # Step 4: initial commit (HEAD has no parent)
    step("4. NEGATIVE: initial commit (no parent) handled via empty-tree diff")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = pathlib.Path(tmp)
        _init_repo(tmp_dir)
        _commit_file(tmp_dir, "first.py", "FIRST = True\n", "feat: initial commit")
        capture = capture_diff(repo=tmp_dir, ref="HEAD")
        if capture.error:
            fail(f"initial-commit case errored: {capture.error}")
        if "first.py" not in capture.files_touched:
            fail(f"first.py missing from files_touched: {capture.files_touched}")
        if "FIRST = True" not in capture.content:
            fail(f"diff content lost on initial commit: {capture.content[:200]!r}")
        ok(f"initial commit: {len(capture.files_touched)} files, content captured")

    # Step 5: staged vs HEAD modes
    step("5. NEGATIVE: staged=True captures staged-only; plain mode skips it")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = pathlib.Path(tmp)
        _init_repo(tmp_dir)
        _commit_file(tmp_dir, "f.py", "x=1\n", "feat: init")
        # Stage a change without committing
        (tmp_dir / "f.py").write_text("x=2\nUNCOMMITTED = True\n")
        _git(["add", "f.py"], tmp_dir)
        # Plain mode: HEAD diff is the FIRST commit's diff (empty repo
        # before that), so should NOT contain UNCOMMITTED
        head_capture = capture_diff(repo=tmp_dir, ref="HEAD", staged=False)
        if "UNCOMMITTED" in head_capture.content:
            fail(
                f"plain HEAD captured staged content; should not. "
                f"content: {head_capture.content[:200]!r}"
            )
        # Staged mode: should include UNCOMMITTED
        staged_capture = capture_diff(repo=tmp_dir, ref="HEAD", staged=True)
        if "UNCOMMITTED" not in staged_capture.content:
            fail(
                f"staged mode missed UNCOMMITTED line. "
                f"content: {staged_capture.content[:300]!r}"
            )
        if staged_capture.source != "git-diff-staged":
            fail(f"wrong source for staged mode: {staged_capture.source}")
        ok(f"staged + HEAD modes correctly distinguished")

    # Step 6: tiny diffs filtered
    step("6. NEGATIVE: is_likely_pr_review returns False for tiny diffs")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = pathlib.Path(tmp)
        _init_repo(tmp_dir)
        _commit_file(tmp_dir, "tiny.py", "x=1\n", "feat: init")
        # 1-line change
        (tmp_dir / "tiny.py").write_text("x=2\n")
        _git(["add", "tiny.py"], tmp_dir)
        _git(["commit", "-m", "fix: tiny"], tmp_dir)
        capture = capture_diff(repo=tmp_dir, ref="HEAD")
        if is_likely_pr_review(capture):
            fail(
                f"tiny diff (1-line) should NOT be sent to council; "
                f"is_likely_pr_review returned True. line_count="
                f"{capture.line_count}"
            )
        ok(f"tiny diff ({capture.line_count} lines) filtered out (noise)")

    # Step 7: doc-only diffs filtered
    step("7. NEGATIVE: is_likely_pr_review returns False for doc-only diffs")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = pathlib.Path(tmp)
        _init_repo(tmp_dir)
        _commit_file(tmp_dir, "README.md", "# Title\n", "feat: init")
        # Multi-line doc change (passes line_count threshold)
        (tmp_dir / "README.md").write_text(
            "# Title\n\n"
            "## Section 1\n"
            "Some content here.\n"
            "More content.\n"
            "Even more lines.\n"
            "## Section 2\n"
            "Other content.\n"
        )
        (tmp_dir / "CHANGELOG.md").write_text(
            "# Changelog\n\n"
            "## v0.2\n"
            "- changed thing\n"
            "## v0.1\n"
            "- initial\n"
        )
        _git(["add", "."], tmp_dir)
        _git(["commit", "-m", "docs: expand"], tmp_dir)
        capture = capture_diff(repo=tmp_dir, ref="HEAD")
        if is_likely_pr_review(capture):
            fail(
                f"doc-only diff should NOT be sent to council; "
                f"files: {capture.files_touched}"
            )
        ok(f"doc-only diff (.md files) filtered out (council reviews code)")

    # Step 8: non-git directory
    step("8. NEGATIVE: capture_diff in non-git directory returns error, no crash")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = pathlib.Path(tmp)
        # Don't init git
        capture = capture_diff(repo=tmp_dir, ref="HEAD")
        if capture.error is None:
            fail(f"non-git dir should set error: {capture}")
        ok(f"non-git dir: error captured cleanly")

    # Sanity: a meaningful code diff DOES pass is_likely_pr_review
    step("Bonus: meaningful code diff passes is_likely_pr_review")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = pathlib.Path(tmp)
        _init_repo(tmp_dir)
        _commit_file(tmp_dir, "real.py", "x=1\n", "feat: init")
        (tmp_dir / "real.py").write_text(
            "def calculate(items: list) -> int:\n"
            "    if not items:\n"
            "        return 0\n"
            "    total = sum(items)\n"
            "    if total > 1000:\n"
            "        raise ValueError('overflow')\n"
            "    return total\n"
        )
        _git(["add", "."], tmp_dir)
        _git(["commit", "-m", "feat: add calculate"], tmp_dir)
        capture = capture_diff(repo=tmp_dir, ref="HEAD")
        if not is_likely_pr_review(capture):
            fail(f"meaningful code diff should pass: {capture.files_touched}, {capture.line_count} lines")
        ok(f"meaningful code diff passes filter ({capture.line_count} lines)")

    print(f"\n{BOLD}{GREEN}{'=' * 50}{NC}")
    print(f"{BOLD}{GREEN}  ALL 8 GIT-CAPTURE STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}  (6 negative assertions: 3, 4, 5, 6, 7, 8){NC}")
    print(f"{BOLD}{GREEN}{'=' * 50}{NC}")


if __name__ == "__main__":
    main()
