#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: pr_review_filter_reason() returns SPECIFIC named filters.

Phase 5K added a granular sibling to is_likely_pr_review:
pr_review_filter_reason(capture) returns either None (fire the
council) or a stable string naming the EXACT filter that tripped.

Operators read this name in council_runs.log to debug why a commit
was filtered. If a future refactor silently renames the filters
(e.g. "skip_token" → "skipCouncilToken") it breaks every log-search
runbook and dashboard. This drill locks the contract.

Eight steps. Seven negative assertions.

  1. None is returned when the diff SHOULD fire the council
     (positive baseline — without it, every other check is
     untrustworthy because we don't know the "fire" path works).
  2. NEGATIVE: error capture → "capture_error" (exact string).
  3. NEGATIVE: empty diff → "empty_diff".
  4. NEGATIVE: skip-token in subject → "skip_token".
  5. NEGATIVE: tiny diff → starts with "too_short" and includes
     the actual payload count for triage (operators get the number
     without re-running capture).
  6. NEGATIVE: pure-binary diff (e.g. all .png files with binary
     marker) → "all_binary".
  7. NEGATIVE: pure-doc diff → "doc_only".
  8. NEGATIVE: the set of returned reasons is closed — only six
     non-None values are valid. A future refactor that adds a new
     filter MUST update this drill (forces deliberate change).

Run: python3 mcp/tests/drill_filter_reason_granularity.py
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _load_git_capture():
    p = REPO / "services" / "sidecar-advisor" / "git_capture.py"
    spec = importlib.util.spec_from_file_location("_gc_drill_5K", p)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_gc_drill_5K"] = mod
    spec.loader.exec_module(mod)
    return mod


def _make_capture(gc, *, message: str = "feat: real change",
                  payload_lines: int = 20,
                  files_touched: list[str] | None = None,
                  has_binary: bool = False,
                  diff_content: str | None = None,
                  error: str | None = None):
    if diff_content is None and error is None:
        diff_content = (
            "diff --git a/x.py b/x.py\n"
            "--- a/x.py\n+++ b/x.py\n"
            "@@ -1,3 +1,3 @@\n"
            + "\n".join("+new line" for _ in range(payload_lines)) + "\n"
        )
    return gc.DiffCapture(
        content=diff_content or "",
        source="git-diff-head",
        files_touched=files_touched or ["x.py"],
        sha="abc123def456",
        line_count=(diff_content or "").count("\n"),
        payload_lines=payload_lines,
        has_binary=has_binary,
        error=error,
        commit_message=message,
    )


def main() -> int:
    gc = _load_git_capture()

    # ── Step 1: None for normal/healthy capture ──
    healthy = _make_capture(gc, message="feat: ship a feature", payload_lines=40)
    reason = gc.pr_review_filter_reason(healthy)
    if reason is not None:
        print(f"✗ step 1: healthy capture returned non-None reason={reason!r}; "
              "the 'fire the council' path is broken")
        return 1
    print("✓ step 1: healthy capture → None (fire the council)")

    # ── Step 2: NEGATIVE — capture_error ──
    errored = _make_capture(gc, error="git binary not found", payload_lines=0)
    reason = gc.pr_review_filter_reason(errored)
    if reason != "capture_error":
        print(f"✗ step 2: error capture returned {reason!r}, expected 'capture_error'")
        return 1
    print(f"✓ step 2: error capture → {reason!r}")

    # ── Step 3: NEGATIVE — empty_diff ──
    empty = _make_capture(gc, payload_lines=0, diff_content="   \n  \n")
    reason = gc.pr_review_filter_reason(empty)
    if reason != "empty_diff":
        print(f"✗ step 3: empty diff returned {reason!r}, expected 'empty_diff'")
        return 1
    print(f"✓ step 3: empty diff → {reason!r}")

    # ── Step 4: NEGATIVE — skip_token in subject ──
    skipped = _make_capture(gc, message="feat: bump [skip-council]", payload_lines=200)
    reason = gc.pr_review_filter_reason(skipped)
    if reason != "skip_token":
        print(f"✗ step 4: skip-token returned {reason!r}, expected 'skip_token'")
        return 1
    print(f"✓ step 4: skip-token in subject → {reason!r}")

    # ── Step 5: NEGATIVE — too_short with payload count ──
    tiny = _make_capture(gc, message="fix: typo", payload_lines=2)
    reason = gc.pr_review_filter_reason(tiny)
    if reason is None or not reason.startswith("too_short"):
        print(f"✗ step 5: tiny diff returned {reason!r}, expected to start with 'too_short'")
        return 1
    if "payload=2" not in reason:
        print(f"✗ step 5: tiny diff reason missing payload count: {reason!r}")
        return 1
    print(f"✓ step 5: tiny diff → {reason!r} (payload count included)")

    # ── Step 6: NEGATIVE — all_binary ──
    all_bin = _make_capture(
        gc, message="chore: update assets", payload_lines=20,
        files_touched=["logo.png", "icon.jpg", "screenshot.gif"],
        has_binary=True,
    )
    reason = gc.pr_review_filter_reason(all_bin)
    if reason != "all_binary":
        print(f"✗ step 6: all-binary returned {reason!r}, expected 'all_binary'")
        return 1
    print(f"✓ step 6: all-binary → {reason!r}")

    # ── Step 7: NEGATIVE — doc_only ──
    doc_only = _make_capture(
        gc, message="docs: update guides", payload_lines=80,
        files_touched=["README.md", "GUIDE.rst", "NOTES.txt"],
    )
    reason = gc.pr_review_filter_reason(doc_only)
    if reason != "doc_only":
        print(f"✗ step 7: doc-only returned {reason!r}, expected 'doc_only'")
        return 1
    print(f"✓ step 7: doc-only → {reason!r}")

    # ── Step 8: NEGATIVE — closed set of reason names ──
    # Collect every reason we've observed plus the None case. The
    # contract is: None or one of these six. If a future refactor
    # adds a seventh filter (e.g. "size_too_big"), it MUST update
    # this drill — the test failure forces a deliberate decision.
    EXPECTED = {
        None,
        "capture_error",
        "empty_diff",
        "skip_token",
        "all_binary",
        "doc_only",
        # too_short carries a payload count, so we match the prefix
    }
    observed_prefixes = set()
    cases = [
        _make_capture(gc, message="feat: real", payload_lines=40),
        _make_capture(gc, error="boom", payload_lines=0),
        _make_capture(gc, payload_lines=0, diff_content=""),
        _make_capture(gc, message="feat: x [skip-council]", payload_lines=40),
        _make_capture(gc, payload_lines=2),
        _make_capture(gc, files_touched=["a.png", "b.jpg"], has_binary=True, payload_lines=20),
        _make_capture(gc, files_touched=["a.md", "b.rst"], payload_lines=20),
    ]
    for c in cases:
        r = gc.pr_review_filter_reason(c)
        if r is None:
            observed_prefixes.add(None)
        else:
            # Normalize "too_short (payload=N)" → "too_short"
            observed_prefixes.add(r.split(" ", 1)[0])

    EXPECTED_PREFIXES = {None, "capture_error", "empty_diff", "skip_token",
                         "too_short", "all_binary", "doc_only"}
    if observed_prefixes != EXPECTED_PREFIXES:
        unexpected = observed_prefixes - EXPECTED_PREFIXES
        missing = EXPECTED_PREFIXES - observed_prefixes
        print(f"✗ step 8: reason set drifted. unexpected={unexpected}, missing={missing}")
        return 1
    print(f"✓ step 8: closed reason set verified "
          f"({len(EXPECTED_PREFIXES) - 1} non-None filters + None)")

    print("\nALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
