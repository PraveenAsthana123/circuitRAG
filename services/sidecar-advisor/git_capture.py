"""Capture git activity into Sidecar Advisor pr_review events.

The Sidecar backend can review pasted content; this module closes
the auto-capture gap so commits flow into the council without an
operator paste-step.

Two capture modes:

  * capture_diff(ref="HEAD") - the diff for the most recent commit
    (HEAD~1..HEAD). Run via the Phase 4B post-commit hook to feed
    the just-committed change into the council.
  * capture_diff(ref="HEAD", staged=True) - the staged-but-uncommitted
    diff. Run pre-commit to get a preview of "what will the council
    say about this change?" before landing it.

Both return a DiffCapture dataclass with the raw diff, files
touched, sha (HEAD), and a likelihood heuristic. The caller
typically:

    capture = capture_diff(repo=Path(repo_root))
    if is_likely_pr_review(capture):
        parsed, raw, model, dur, telemetry = await advisor.review(
            event_type="pr_review",
            content=capture.content,
        )
        memory.record_event(
            event_type="pr_review",
            source="git-diff",
            content=capture.content,
            ...
        )
"""
from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class DiffCapture:
    """One git-diff snapshot."""

    content: str                  # raw diff text (unified format)
    source: str                   # "git-diff-head" | "git-diff-staged" | "git-diff-empty"
    files_touched: list[str]      # paths in the diff
    sha: str                      # HEAD commit sha (12-char), or "" if no commit
    line_count: int               # total lines in the diff (incl. context + headers)
    payload_lines: int = 0        # only +/- content lines (excludes ---/+++ headers)
    has_binary: bool = False
    error: str | None = None      # populated when capture failed

    @property
    def is_empty(self) -> bool:
        return not self.content.strip()


def _count_payload_lines(diff: str) -> int:
    """Count only +/- lines that represent actual content changes.
    Excludes '---' and '+++' file-header lines (which start with
    --- / +++ respectively but represent metadata, not content)."""
    n = 0
    for line in diff.split("\n"):
        if not line:
            continue
        if line.startswith("+") and not line.startswith("+++"):
            n += 1
        elif line.startswith("-") and not line.startswith("---"):
            n += 1
    return n


def _run_git(args: list[str], cwd: Path) -> tuple[bool, str, str]:
    """Returns (success, stdout, stderr_or_error)."""
    try:
        result = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            cwd=str(cwd),
            timeout=30.0,
        )
        if result.returncode == 0:
            return True, result.stdout, result.stderr
        return False, result.stdout, result.stderr or f"exit {result.returncode}"
    except FileNotFoundError:
        return False, "", "git binary not found on PATH"
    except subprocess.TimeoutExpired:
        return False, "", "git command timed out"
    except OSError as exc:
        return False, "", f"OSError: {exc}"


def capture_diff(
    *,
    repo: Path | None = None,
    ref: str = "HEAD",
    staged: bool = False,
) -> DiffCapture:
    """Run git diff and return a DiffCapture.

    Args:
        repo: directory to run git in. Default = cwd.
        ref: the ref whose parent diff we want. Default "HEAD".
            Ignored when staged=True.
        staged: if True, capture the index (staged-but-uncommitted)
            diff via `git diff --cached`. The ref arg is ignored.

    Never raises. On failure, returns a DiffCapture with content="",
    files_touched=[], and error set so the caller can decide whether
    to skip or surface the error.
    """
    repo = repo or Path.cwd()

    # 1. Get HEAD sha (or empty if no commits)
    ok_sha, sha_out, _ = _run_git(["rev-parse", "HEAD"], repo)
    sha = sha_out.strip()[:12] if ok_sha else ""

    # 2. Build the diff command per mode
    if staged:
        diff_cmd = ["diff", "--cached"]
        files_cmd = ["diff", "--cached", "--name-only"]
        source = "git-diff-staged"
    else:
        # HEAD~1..HEAD if HEAD has a parent; otherwise diff against
        # the empty tree (initial-commit case).
        ok_parent, _, _ = _run_git(["rev-parse", f"{ref}^"], repo)
        if ok_parent:
            diff_cmd = ["diff", f"{ref}^..{ref}"]
            files_cmd = ["show", "--name-only", "--format=", ref]
        else:
            # Initial commit: no parent. Diff against empty tree.
            empty_tree = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"  # git's well-known empty-tree hash
            diff_cmd = ["diff", "--binary", empty_tree, ref]
            files_cmd = ["show", "--name-only", "--format=", ref]
        source = "git-diff-head"

    # 3. Run the diff
    ok_diff, diff_out, diff_err = _run_git(diff_cmd, repo)
    if not ok_diff:
        return DiffCapture(
            content="",
            source="git-diff-empty",
            files_touched=[],
            sha=sha,
            line_count=0,
            has_binary=False,
            error=diff_err.strip()[:300] or "git diff failed",
        )

    # 4. Run the files-touched query
    ok_files, files_out, _ = _run_git(files_cmd, repo)
    files_touched = (
        [ln.strip() for ln in files_out.splitlines() if ln.strip()]
        if ok_files else []
    )

    # 5. Detect binary diffs (the diff output contains "Binary files
    # ... differ" or "GIT binary patch" markers)
    has_binary = ("Binary files" in diff_out
                  or "GIT binary patch" in diff_out)

    return DiffCapture(
        content=diff_out,
        source=source,
        files_touched=files_touched,
        sha=sha,
        line_count=diff_out.count("\n"),
        payload_lines=_count_payload_lines(diff_out),
        has_binary=has_binary,
    )


# ── Heuristics ──────────────────────────────────────────────────
# Counted as +/- payload lines (excluding ---/+++ headers + @@ hunks).
# A 1-line code change = 2 payload lines (1 removed, 1 added). This
# threshold filters typo-fix-shaped diffs (3-5 payload lines) but
# keeps real refactors (10+ payload lines).
MIN_PAYLOAD_LINES = 5


def is_likely_pr_review(capture: DiffCapture) -> bool:
    """Heuristic: should this diff be sent to the pr_review council?

    Returns False for:
      * empty / errored captures
      * diffs with fewer than MIN_PAYLOAD_LINES content changes
      * pure-binary diffs (council can't review binary)
      * doc-only diffs (every file ends in .md / .rst / .txt)

    The caller can override - this is advisory. For Phase 2A the
    auto-pipeline only fires the council when this returns True.
    """
    if capture.error or capture.is_empty:
        return False
    if capture.payload_lines < MIN_PAYLOAD_LINES:
        return False
    if capture.has_binary and not any(
        not f.endswith((".png", ".jpg", ".jpeg", ".gif", ".pdf",
                        ".zip", ".tar", ".gz", ".whl"))
        for f in capture.files_touched
    ):
        return False  # all-binary
    if capture.files_touched and all(
        f.endswith(".md") or f.endswith(".rst") or f.endswith(".txt")
        for f in capture.files_touched
    ):
        return False  # doc-only
    return True
