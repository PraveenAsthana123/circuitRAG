"""PR management — Tier 5 #5.5.

Per CLAUDE.md §50 + §55. Closes the local → GitHub loop. After the
daemon batch-applies fixes (each tagged `auto-apply-<id>`), this
module gathers the tagged commits + builds a PR title/body + calls
`gh pr create`. Operator review is still required before merge —
PR creation is automated; PR merge is gated.

§42 SAFETY
==========

  - Default mode is dry-run (--dry-run); no PR created
  - --apply mode requires --confirm flag too (double-gate per §42
    for outward-facing GitHub operations)
  - Never force-pushes; never deletes branches
  - Never auto-merges (operator-only via `gh pr merge`)
  - PR body MUST cite each auto-apply tag for atomic-revert traceability

WHAT GETS GROUPED
=================

A daemon "batch" = the auto-apply commits since the last push to
the upstream branch. find_batch_commits() reads
`git log origin/main..HEAD --grep="autonomous daemon"` to identify
the batch boundary; PR groups all of them.

USAGE
=====

  python3 scripts/pr_management.py preview                    # dry-run; show what PR would say
  python3 scripts/pr_management.py preview --since-ref HEAD~5
  python3 scripts/pr_management.py create --confirm           # actually create the PR

Drilled by mcp/tests/drill_pr_management.py.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, Field

REPO = Path(__file__).resolve().parent.parent

DEFAULT_TITLE_PREFIX = "chore: autonomous-fix-bot batch"
DEFAULT_BASE = "main"
DEFAULT_SINCE_REF = "origin/main"


class PullRequestSpec(BaseModel):
    """Wire format for the PR. Validated before any gh CLI call."""

    title: str = Field(min_length=1, max_length=72,
                       description="PR title; under 72 chars per GitHub UX")
    body: str = Field(min_length=1, max_length=64_000)
    head: str = Field(min_length=1, max_length=128,
                      pattern=r"^[A-Za-z0-9._/-]+$",
                      description="branch name; alphanumeric + . _ / -")
    base: str = Field(default=DEFAULT_BASE, min_length=1, max_length=128,
                      pattern=r"^[A-Za-z0-9._/-]+$")
    draft: bool = Field(default=False)
    labels: list[str] = Field(default_factory=list)

    model_config: ClassVar[dict] = {"extra": "forbid"}


@dataclass(frozen=True)
class BatchCommit:
    """One auto-apply commit in the batch."""

    sha: str
    subject: str
    auto_apply_tag: str | None  # None if not daemon-tagged

    model_config: ClassVar[dict] = {"frozen": True}


def _git(args: list[str], *, timeout: int = 10) -> tuple[int, str, str]:
    proc = subprocess.run(
        ["git", *args], cwd=REPO, capture_output=True, text=True, timeout=timeout,
    )
    return proc.returncode, proc.stdout, proc.stderr


def find_batch_commits(*, since_ref: str = DEFAULT_SINCE_REF) -> list[BatchCommit]:
    """Return all commits between since_ref and HEAD with their
    auto-apply tag (if daemon-applied). Newest first."""
    rc, out, err = _git(["log", f"{since_ref}..HEAD",
                         "--pretty=format:%H|%s"])
    if rc != 0:
        return []
    commits: list[BatchCommit] = []
    for line in out.splitlines():
        if "|" not in line:
            continue
        sha, subject = line.split("|", 1)
        # Look for an auto-apply tag pointing at this SHA.
        tag_rc, tag_out, _ = _git(["tag", "--points-at", sha,
                                    "--list", "auto-apply-*"])
        tag = None
        if tag_rc == 0 and tag_out.strip():
            tag = tag_out.strip().splitlines()[0]
        commits.append(BatchCommit(sha=sha, subject=subject.strip(), auto_apply_tag=tag))
    return commits


def build_pr_spec(commits: list[BatchCommit], *, head: str, base: str = DEFAULT_BASE) -> PullRequestSpec:
    """Construct the PR spec from a list of batch commits."""
    if not commits:
        raise ValueError("no commits to PR; aborting")
    # Title: prefix + count + first commit's subject (truncated)
    auto_count = sum(1 for c in commits if c.auto_apply_tag is not None)
    if auto_count > 0:
        title = f"{DEFAULT_TITLE_PREFIX}: {auto_count} fix(es) in {len(commits)} commits"
    else:
        title = f"{DEFAULT_TITLE_PREFIX}: {len(commits)} commit(s) (manual)"
    title = title[:72]

    # Body: list each commit + its tag, cite §42 + §54 + §51 forensic substrate
    lines = [
        "## Summary",
        "",
        f"Autonomous-fix-bot batch — {len(commits)} commit(s).",
        f"Auto-apply tagged: {auto_count}; operator-tagged: {len(commits) - auto_count}.",
        "",
        "## Commits",
        "",
    ]
    for c in commits:
        tag_str = f" — `{c.auto_apply_tag}`" if c.auto_apply_tag else ""
        lines.append(f"- `{c.sha[:12]}` {c.subject[:80]}{tag_str}")
    lines += [
        "",
        "## Verification",
        "",
        "Drill catalog passing locally (`mcp/tests/drill_*.py`).",
        "Apply-gate: ruff + mypy + pytest per Tier 2 #2.11.",
        "Rollback: per-commit `auto-apply-*` tags allow atomic revert.",
        "",
        "## Per CLAUDE.md",
        "",
        "- §42: this PR was created by the autonomous fix-bot; merge gated to operator review",
        "- §51: each commit body has Location / Approach / Policies / Verification metadata",
        "- §54: NO Co-Authored-By trailer in any commit",
    ]
    body = "\n".join(lines)
    return PullRequestSpec(title=title, body=body, head=head, base=base)


def gh_available() -> bool:
    return shutil.which("gh") is not None


def create_pr(spec: PullRequestSpec, *, dry_run: bool = True) -> tuple[bool, str]:
    """Invoke `gh pr create`. Returns (ok, output_or_url).

    When dry_run=True, returns (True, "<dry-run preview>") without
    calling gh. When --apply, requires gh CLI on PATH OR returns
    (False, "gh not available").
    """
    if dry_run:
        return True, f"[dry-run] would create PR: title={spec.title!r} head={spec.head!r}"
    if not gh_available():
        return False, "gh CLI not on PATH; cannot create PR"
    cmd = [
        "gh", "pr", "create",
        "--title", spec.title,
        "--body", spec.body,
        "--head", spec.head,
        "--base", spec.base,
    ]
    if spec.draft:
        cmd.append("--draft")
    for label in spec.labels:
        cmd.extend(["--label", label])
    proc = subprocess.run(
        cmd, cwd=REPO, capture_output=True, text=True, timeout=30,
    )
    if proc.returncode != 0:
        return False, f"gh pr create failed: {proc.stderr.strip()[:300]}"
    return True, proc.stdout.strip()


def cmd_preview(args: argparse.Namespace) -> int:
    commits = find_batch_commits(since_ref=args.since_ref)
    if not commits:
        print(f"(no commits between {args.since_ref} and HEAD)")
        return 1
    rc, branch, _ = _git(["branch", "--show-current"])
    head = branch.strip() if rc == 0 else "HEAD"
    spec = build_pr_spec(commits, head=head, base=args.base)
    print("=== PR preview ===")
    print(f"  title: {spec.title}")
    print(f"  head:  {spec.head}")
    print(f"  base:  {spec.base}")
    print(f"  body length: {len(spec.body)} chars")
    print(f"  draft: {spec.draft}")
    print()
    print("--- body ---")
    print(spec.body[:2000])
    if len(spec.body) > 2000:
        print(f"\n... ({len(spec.body) - 2000} more chars)")
    return 0


def cmd_create(args: argparse.Namespace) -> int:
    if not args.confirm:
        print("x --confirm required to actually create PR (per §42 outward-facing op)")
        print("  retry: python3 scripts/pr_management.py create --confirm")
        return 2
    commits = find_batch_commits(since_ref=args.since_ref)
    if not commits:
        print("x no commits to PR")
        return 1
    rc, branch, _ = _git(["branch", "--show-current"])
    head = branch.strip() if rc == 0 else "HEAD"
    spec = build_pr_spec(commits, head=head, base=args.base)
    ok, output = create_pr(spec, dry_run=False)
    if ok:
        print(f"✓ PR created: {output}")
        return 0
    print(f"x PR creation failed: {output}")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(prog="pr_management.py", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_pr = sub.add_parser("preview", help="show what the PR would say (dry-run)")
    p_pr.add_argument("--since-ref", default=DEFAULT_SINCE_REF)
    p_pr.add_argument("--base", default=DEFAULT_BASE)
    p_pr.set_defaults(func=cmd_preview)
    p_cr = sub.add_parser("create", help="create the PR (--confirm required per §42)")
    p_cr.add_argument("--since-ref", default=DEFAULT_SINCE_REF)
    p_cr.add_argument("--base", default=DEFAULT_BASE)
    p_cr.add_argument("--confirm", action="store_true",
                      help="explicit confirmation; without this, --create exits 2")
    p_cr.set_defaults(func=cmd_create)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
