#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: [skip-council] / [no-council] commit-message opt-out.

Phase 5J ships an operator opt-out token: putting `[skip-council]`
(or `[no-council]`) in a commit message bypasses the LLM review
council. This drill locks the contract so a future refactor of
`is_likely_pr_review` can't silently drop the opt-out.

Eight steps. Six negative assertions.

  1. capture_diff populates DiffCapture.commit_message from
     `git log -1 --format=%B HEAD` for HEAD-mode capture.
  2. NEGATIVE: with [skip-council] in the message, is_likely_pr_review
     returns False even when payload_lines is large enough on its own
     to pass.
  3. NEGATIVE: token match is case-insensitive — [SKIP-COUNCIL],
     [Skip-Council], [skip_council] all suppress.
  4. NEGATIVE: alternative spelling [no-council] also suppresses.
  5. NEGATIVE: a token in the DIFF BODY (e.g. inside an added
     comment) does NOT suppress. Only the commit message counts —
     so a code change that mentions the literal string can't
     accidentally turn off review.
  6. NEGATIVE: empty commit_message is safe — no crash, no false
     suppression. Staged-mode captures (no commit yet) hit this path.
  7. NEGATIVE: existing filters still fire when token absent. Tiny
     diffs (< MIN_PAYLOAD_LINES) still get filtered as noise even
     when commit_message says nothing about councils.
  8. POSITIVE: a normal commit message + a real diff still routes to
     the council (returns True). Sanity check that we didn't break
     the happy path.

Run: python3 mcp/tests/drill_skip_council_token.py
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _load_git_capture():
    """Load services/sidecar-advisor/git_capture.py without importing
    the whole package. Drill stays standalone."""
    p = REPO / "services" / "sidecar-advisor" / "git_capture.py"
    spec = importlib.util.spec_from_file_location("_gc_drill_5J", p)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_gc_drill_5J"] = mod
    spec.loader.exec_module(mod)
    return mod


def _make_capture(gc, *, message: str, payload_lines: int = 20,
                  diff_content: str | None = None,
                  files_touched: list[str] | None = None):
    """Build a synthetic DiffCapture with the field combinations the
    drill needs. We use the dataclass directly — capture_diff itself
    is exercised in step 1 against the real repo."""
    if diff_content is None:
        diff_content = (
            "diff --git a/x.py b/x.py\n"
            "--- a/x.py\n+++ b/x.py\n"
            "@@ -1,3 +1,3 @@\n"
            + "\n".join("+new line" for _ in range(payload_lines)) + "\n"
        )
    return gc.DiffCapture(
        content=diff_content,
        source="git-diff-head",
        files_touched=files_touched or ["x.py"],
        sha="abc123def456",
        line_count=diff_content.count("\n"),
        payload_lines=payload_lines,
        has_binary=False,
        error=None,
        commit_message=message,
    )


def main() -> int:
    gc = _load_git_capture()

    # ── Step 1: capture_diff populates commit_message on real repo ──
    # We run it against the actual project. If HEAD has any commit
    # at all, commit_message must be non-empty.
    cap = gc.capture_diff(repo=REPO, staged=False)
    if cap.error:
        print(f"✗ step 1: capture_diff returned error={cap.error}")
        return 1
    if not cap.commit_message:
        print("✗ step 1: commit_message empty after HEAD capture; "
              "the new git log step in capture_diff didn't populate")
        return 1
    if not isinstance(cap.commit_message, str):
        print(f"✗ step 1: commit_message wrong type: {type(cap.commit_message)}")
        return 1
    print(f"✓ step 1: commit_message populated "
          f"({len(cap.commit_message)} chars, sha={cap.sha})")

    # ── Step 2: NEGATIVE — [skip-council] suppresses even large diffs ──
    big_diff_skip = _make_capture(
        gc, message="feat: big refactor [skip-council]\n\nlots of changes",
        payload_lines=200,
    )
    if gc.is_likely_pr_review(big_diff_skip):
        print("✗ step 2: [skip-council] in 200-line commit STILL "
              "routed to council; opt-out broken")
        return 1
    print("✓ step 2: [skip-council] suppresses 200-line diff "
          "(opt-out wins over payload_lines)")

    # ── Step 3: NEGATIVE — case-insensitive ──
    variants = [
        "[SKIP-COUNCIL]",
        "[Skip-Council]",
        "[skip_council]",
        "[skip council]",
        "[SKIP COUNCIL]",
    ]
    for v in variants:
        c = _make_capture(gc, message=f"chore: bump {v}", payload_lines=50)
        if gc.is_likely_pr_review(c):
            print(f"✗ step 3: variant {v!r} did NOT suppress; "
                  "regex isn't case-insensitive enough")
            return 1
    print(f"✓ step 3: {len(variants)} case/separator variants all suppress")

    # ── Step 4: NEGATIVE — [no-council] alternative ──
    alt_forms = ["[no-council]", "[NO-COUNCIL]", "[No-Council]",
                 "[no_council]", "[no council]"]
    for v in alt_forms:
        c = _make_capture(gc, message=f"refactor: cleanup {v}", payload_lines=80)
        if gc.is_likely_pr_review(c):
            print(f"✗ step 4: {v!r} did NOT suppress")
            return 1
    print(f"✓ step 4: {len(alt_forms)} [no-council] variants all suppress")

    # ── Step 5: NEGATIVE — token in DIFF body doesn't suppress ──
    # An added comment that contains the literal "[skip-council]"
    # must NOT silently disable review of unrelated code. Only the
    # commit message counts.
    diff_with_token = (
        "diff --git a/x.py b/x.py\n"
        "--- a/x.py\n+++ b/x.py\n"
        "@@ -1,3 +1,3 @@\n"
        "+# example: write [skip-council] in your commit to bypass review\n"
        + "\n".join("+code" for _ in range(20)) + "\n"
    )
    c = _make_capture(
        gc, message="docs: explain how to skip the council",
        payload_lines=21, diff_content=diff_with_token,
    )
    if not gc.is_likely_pr_review(c):
        print("✗ step 5: token in diff BODY suppressed review; "
              "the regex is matching the wrong field")
        return 1
    print("✓ step 5: [skip-council] inside diff body does NOT "
          "suppress (only commit message counts)")

    # ── Step 6: NEGATIVE — empty commit_message is safe ──
    # Staged-mode captures (no commit yet) have commit_message="".
    # The skip-token check must short-circuit cleanly without crash.
    c_empty = _make_capture(gc, message="", payload_lines=20)
    try:
        result = gc.is_likely_pr_review(c_empty)
    except Exception as exc:
        print(f"✗ step 6: empty commit_message crashed: "
              f"{type(exc).__name__}: {exc}")
        return 1
    if not result:
        print("✗ step 6: empty commit_message wrongly suppressed "
              "(should fall through to existing filters)")
        return 1
    print("✓ step 6: empty commit_message is safe (staged-mode path)")

    # ── Step 7: NEGATIVE — existing filters still fire ──
    # Tiny diff with no skip token must still be filtered as noise.
    # Confirms we didn't accidentally short-circuit the OTHER way
    # (always-True when token absent).
    tiny = _make_capture(
        gc, message="fix: typo in comment",
        payload_lines=2,  # below MIN_PAYLOAD_LINES (5)
    )
    if gc.is_likely_pr_review(tiny):
        print("✗ step 7: tiny diff (2 payload lines) routed to council; "
              "MIN_PAYLOAD_LINES filter broken")
        return 1
    print("✓ step 7: existing payload_lines filter still fires "
          "when token absent (tiny diffs filtered as noise)")

    # ── Step 8: POSITIVE — normal commit + real diff routes to council ──
    normal = _make_capture(
        gc, message="feat: add new agent for code review\n\n"
                    "Implements the AgentBoard fanout pattern.",
        payload_lines=40,
    )
    if not gc.is_likely_pr_review(normal):
        print("✗ step 8: normal commit + 40 payload lines did NOT "
              "route to council; happy path broken")
        return 1
    print("✓ step 8: normal commit routes to council (happy path intact)")

    print("\nALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
