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
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

# Operator opt-out tokens. Either bracketed form bypasses the council
# (case-insensitive). Token must appear in the COMMIT MESSAGE — not the
# diff body — so a code change that mentions the token in a comment
# doesn't accidentally suppress review.
_SKIP_COUNCIL_RE = re.compile(r"\[(?:skip|no)[-_ ]council\]", re.IGNORECASE)

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
    commit_message: str = ""      # full HEAD commit message (empty for staged mode)

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
        if (
            (line.startswith("+") and not line.startswith("+++"))
            or (line.startswith("-") and not line.startswith("---"))
        ):
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

    # 6. Capture the commit message (empty for staged mode — no commit yet).
    # Used by is_likely_pr_review to honor [skip-council] / [no-council]
    # tokens. Best-effort; absent message doesn't fail the capture.
    commit_message = ""
    if not staged:
        ok_msg, msg_out, _ = _run_git(["log", "-1", "--format=%B", ref], repo)
        if ok_msg:
            commit_message = msg_out

    return DiffCapture(
        content=diff_out,
        source=source,
        files_touched=files_touched,
        sha=sha,
        line_count=diff_out.count("\n"),
        payload_lines=_count_payload_lines(diff_out),
        has_binary=has_binary,
        commit_message=commit_message,
    )


# ── Heuristics ──────────────────────────────────────────────────
# Counted as +/- payload lines (excluding ---/+++ headers + @@ hunks).
# A 1-line code change = 2 payload lines (1 removed, 1 added). This
# threshold filters typo-fix-shaped diffs (3-5 payload lines) but
# keeps real refactors (10+ payload lines).
MIN_PAYLOAD_LINES = 5


_BINARY_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".pdf",
                ".zip", ".tar", ".gz", ".whl")
_DOC_EXTS = (".md", ".rst", ".txt")


def _commit_subject(msg: str) -> str:
    """First line of a commit message (git's subject-line convention).

    Empty string for empty messages. We deliberately do NOT trim leading
    whitespace — a malformed message with leading blank lines has no
    subject and shouldn't accidentally match a token on later lines."""
    return msg.split("\n", 1)[0] if msg else ""


def pr_review_filter_reason(capture: DiffCapture) -> str | None:
    """Return None if the diff should fire the council, else a short
    string naming the SPECIFIC filter that tripped.

    This is the granular sibling of is_likely_pr_review. Operators
    inspecting council_runs.log can read the filter name directly
    instead of guessing from a dump of all signals.

    Filter names (stable contract — drill_filter_reason_granularity locks
    them so future refactors can't silently rename):

      capture_error  — git operation failed
      empty_diff     — diff body is empty / whitespace-only
      skip_token     — operator put [skip-council] / [no-council] in
                       the commit MESSAGE SUBJECT LINE (line 1 only)
      too_short      — payload_lines < MIN_PAYLOAD_LINES (typo-shaped)
      all_binary     — every touched file is a binary extension
      doc_only       — every touched file is .md / .rst / .txt
    """
    if capture.error:
        return "capture_error"
    if capture.is_empty:
        return "empty_diff"
    # Subject-line-only match. A commit message that DESCRIBES the
    # skip-token feature (e.g. "feat: ship [skip-council] opt-out") puts
    # the literal token in its subject — that's the rare case where the
    # author MUST quote-escape or rephrase. By matching ONLY line 1, body
    # paragraphs that explain the token (changelog, release notes pasted
    # into the message) don't accidentally suppress review. Mirrors the
    # GitHub Actions [skip ci] contract.
    subject = _commit_subject(capture.commit_message)
    if subject and _SKIP_COUNCIL_RE.search(subject):
        return "skip_token"
    if capture.payload_lines < MIN_PAYLOAD_LINES:
        return f"too_short (payload={capture.payload_lines})"
    if capture.has_binary and not any(
        not f.endswith(_BINARY_EXTS)
        for f in capture.files_touched
    ):
        return "all_binary"
    if capture.files_touched and all(
        f.endswith(_DOC_EXTS) for f in capture.files_touched
    ):
        return "doc_only"
    return None


def is_likely_pr_review(capture: DiffCapture) -> bool:
    """Heuristic: should this diff be sent to the pr_review council?

    Thin wrapper over pr_review_filter_reason for backward compatibility.
    New code preferring a specific reason should call the sibling
    function directly.
    """
    return pr_review_filter_reason(capture) is None
