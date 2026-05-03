#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: PR management subsystem (Tier 5 #5.5).

Per CLAUDE.md §43 + §42 + §54 + §55. Locks the contract: PR spec
validates; gh-CLI invocation requires --confirm; PR body cites the
auto-apply tags; no force-push or destructive ops.

Eight steps. Six negative assertions.
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "pr_management.py"


def _load():
    sys.path.insert(0, str(REPO / "scripts"))
    spec = importlib.util.spec_from_file_location("pr_management", SCRIPT)
    if spec is None or spec.loader is None:
        raise SystemExit(f"could not load {SCRIPT}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["pr_management"] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    print("-- 1. POSITIVE: pr_management imports + 6 exports --")
    pr = _load()
    for name in ("PullRequestSpec", "BatchCommit", "find_batch_commits",
                 "build_pr_spec", "create_pr", "gh_available"):
        if not hasattr(pr, name):
            print(f"x step 1: missing export {name}")
            return 1
    print("  ok: 6 exports present")

    print("-- 2. POSITIVE: well-formed PullRequestSpec parses --")
    spec = pr.PullRequestSpec(
        title="chore: test PR",
        body="## Summary\n\nTest PR body.",
        head="feature/test",
        base="main",
    )
    if spec.draft is not False:
        print(f"x step 2: draft default should be False; got {spec.draft}")
        return 1
    print(f"  ok: spec parsed; head={spec.head} base={spec.base} draft={spec.draft}")

    print("-- 3. NEGATIVE: title > 72 chars rejected --")
    try:
        pr.PullRequestSpec(
            title="x" * 100,  # too long
            body="ok", head="feat/test",
        )
    except Exception:
        print("  ok: 100-char title rejected (GitHub UX bound)")
    else:
        print("x step 3: 100-char title accepted")
        return 1

    print("-- 4. NEGATIVE: head with forbidden chars (spaces) rejected --")
    try:
        pr.PullRequestSpec(
            title="ok", body="ok",
            head="branch with spaces",  # spaces forbidden
        )
    except Exception:
        print("  ok: head 'branch with spaces' rejected by pattern")
    else:
        print("x step 4: branch with spaces accepted")
        return 1

    print("-- 5. NEGATIVE: extra hallucinated field rejected (extra='forbid') --")
    try:
        pr.PullRequestSpec.model_validate({
            "title": "ok", "body": "ok", "head": "feat/x",
            "operator_pii_email": "praveen@example.com",  # extra
        })
    except Exception:
        print("  ok: extra 'operator_pii_email' rejected (extra='forbid')")
    else:
        print("x step 5: extra field accepted")
        return 1

    print("-- 6. NEGATIVE: build_pr_spec on empty commit list raises --")
    try:
        pr.build_pr_spec([], head="feat/test")
    except ValueError as e:
        if "no commits" not in str(e):
            print(f"x step 6: error msg should mention 'no commits'; got {e}")
            return 1
        print("  ok: empty commit list raises ValueError")
    else:
        print("x step 6: build_pr_spec accepted empty commit list")
        return 1

    print("-- 7. POSITIVE: build_pr_spec body cites auto-apply tags + §42/§51/§54 --")
    commits = [
        pr.BatchCommit(sha="abc123def", subject="fix: UP035", auto_apply_tag="auto-apply-ruff-UP035-foo"),
        pr.BatchCommit(sha="456789xyz", subject="fix: E702", auto_apply_tag="auto-apply-ruff-E702-bar"),
        pr.BatchCommit(sha="0deadbeef", subject="docs: roadmap", auto_apply_tag=None),
    ]
    spec = pr.build_pr_spec(commits, head="feat/test")
    body = spec.body
    if "auto-apply-ruff-UP035-foo" not in body:
        print("x step 7: body missing first auto-apply tag")
        return 1
    if "auto-apply-ruff-E702-bar" not in body:
        print("x step 7: body missing second auto-apply tag")
        return 1
    for marker in ("§42", "§51", "§54"):
        if marker not in body:
            print(f"x step 7: body missing policy reference {marker}")
            return 1
    if "Co-Authored-By: Claude" in body:
        print("x step 7: body emits §54-violating Co-Authored-By trailer")
        return 1
    print("  ok: body cites both auto-apply tags + §42/§51/§54; no Co-Authored-By")

    print("-- 8. NEGATIVE: create_pr without --confirm exits 2 (drilled by source-grep) --")
    src = SCRIPT.read_text(encoding="utf-8")
    if "if not args.confirm:" not in src:
        print("x step 8: cmd_create missing --confirm gate")
        return 1
    if "per §42" not in src:
        print("x step 8: cmd_create missing §42 citation")
        return 1
    # Also verify no `git push --force` or `gh ... --force` anywhere
    if re.search(r"git\s+push\s+--force", src):
        print("x step 8: pr_management contains force-push (§42 violation)")
        return 1
    if "force" in src.lower() and "no force-push" not in src.lower():
        # Allow comments but reject actual --force flags
        for line in src.splitlines():
            if line.strip().startswith("#"):
                continue
            if "--force" in line:
                print(f"x step 8: --force flag in non-comment line: {line.strip()}")
                return 1
    print("  ok: --confirm gate present + §42 citation + no force-push anywhere")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
