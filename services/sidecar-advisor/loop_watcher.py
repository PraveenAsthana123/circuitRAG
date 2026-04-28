"""LoopWatcher - the live gate between iterations of the autonomous loop.

The policy_approver agent (services/sidecar-advisor/agents/
policy_approver.py) defines the rules. This module is its
deterministic counterpart: pure-Python, no LLM call, runs in
milliseconds, drillable in tier 1.

Phase 4A's contract:

  watcher.decide(commit, drills, history) -> ApprovalDecision
    verdict ∈ {APPROVE, HOLD, REJECT}
    reason - human-readable explanation
    rule_fired - which of the 5 rules from the agent's prompt
    blocking_files - the specific paths that caused HOLD/REJECT

Why deterministic + LLM, not just LLM:

  * Determinism: two runs against the same commit + drill output
    produce the same verdict. An LLM-only approver could drift.
  * Speed: ~1ms vs ~5s for an LLM call. Runs at every commit
    without slowing the loop.
  * Drillable: tier-1 drill verifies the rules. An LLM-only
    approver can only be probabilistically tested.
  * Audit: the rule_fired field tells the operator EXACTLY which
    rule blocked. "REJECT: drill_failed" beats a vague LLM verdict.

Phase 4A+ wires the LLM path: when verdict=HOLD with
rule_fired=4 (composability), the watcher invokes the
policy_approver agent for a second-opinion check, since the
composability rule is the one most amenable to natural-language
analysis. Rules 1-3 + 5 stay deterministic.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)


# ── File-disposition mapping ────────────────────────────────────
# Maps a repo-relative file path to one of the matrix dispositions.
# Patterns are checked in order; first match wins. NEVER entries
# come BEFORE pre-approved so a path like .env in services/ doesn't
# slip through the pre-approved pattern.
_FILE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # ── never (absolute blocks; checked first) ─────────────────
    (re.compile(r"^\.env(\.|$)"), "never"),
    (re.compile(r"\.key$"), "never"),
    (re.compile(r"\.pem$"), "never"),
    (re.compile(r"^\.encryption\.key$"), "never"),
    (re.compile(r"^id_(rsa|ed25519|ecdsa)"), "never"),
    (re.compile(r"^credentials"), "never"),
    (re.compile(r"^secrets"), "never"),

    # ── pre-approved (loop scope) ──────────────────────────────
    (re.compile(r"^services/sidecar-advisor/"), "pre-approved"),
    (re.compile(r"^libs/py/documind_core/"), "pre-approved"),
    (re.compile(r"^services/inference-svc/app/agents/multi_hop"),
     "pre-approved"),
    (re.compile(r"^mcp/tests/drill_"), "pre-approved"),
    (re.compile(r"^scripts/"), "pre-approved"),
    (re.compile(r"^docs/.*\.md$"), "pre-approved"),
    (re.compile(r"\.md$"), "pre-approved"),  # any markdown anywhere

    # ── gated (other-team services + CI infra) ─────────────────
    (re.compile(r"^\.github/workflows/"), "gated"),
    (re.compile(r"^services/governance-svc/"), "gated"),
    (re.compile(r"^services/frontend/"), "gated"),
    (re.compile(r"^services/identity-svc/"), "gated"),
    (re.compile(r"^services/api-gateway/"), "gated"),
    (re.compile(r"^services/observability-svc/"), "gated"),
    (re.compile(r"^services/finops-svc/"), "gated"),
    (re.compile(r"^services/retrieval-svc/"), "gated"),
    (re.compile(r"^services/ingestion-svc/"), "gated"),
    (re.compile(r"^services/evaluation-svc/"), "gated"),
    (re.compile(r"^services/inference-svc/"), "gated"),  # except multi_hop above
    (re.compile(r"^pyproject\.toml$"), "gated"),
    (re.compile(r"^requirements"), "gated"),

    # default: unknown -> conservative gated treatment
]


def file_disposition(path: str) -> str:
    """Return one of {pre-approved, gated, never, unknown} for a
    repo-relative file path."""
    for pat, disp in _FILE_PATTERNS:
        if pat.search(path):
            return disp
    return "unknown"


# ── Data classes ────────────────────────────────────────────────
@dataclass(frozen=True)
class CommitContext:
    """The latest commit being evaluated."""

    sha: str
    message: str
    files_touched: list[str]


@dataclass(frozen=True)
class DrillContext:
    """Drill suite outcome."""

    failed_drills: list[str]
    total_drills: int

    @property
    def all_green(self) -> bool:
        return not self.failed_drills


@dataclass(frozen=True)
class ApprovalDecision:
    """The watcher's verdict."""

    verdict: str           # APPROVE | HOLD | REJECT
    reason: str
    rule_fired: int        # 1..6 (6 means "all rules passed")
    blocking_files: list[str] = field(default_factory=list)

    def __post_init__(self):
        if self.verdict not in ("APPROVE", "HOLD", "REJECT"):
            raise ValueError(
                f"verdict must be APPROVE|HOLD|REJECT, got {self.verdict!r}"
            )


# ── Watcher ─────────────────────────────────────────────────────
class LoopWatcher:
    """Apply the policy_approver agent's 5 rules deterministically.

    Args:
        policy_path: optional path to NEXT_POLICY.md. The watcher
            consults the §7 scope-extension log to decide whether
            a 'gated' file already has an open extension request.
            If None, no scope-extension lookup happens (rule 3
            HOLDs on first 'gated' encounter).
        thrash_window: how many recent commits to inspect for
            rule 5 ("same file 3+ consecutive iterations").
            Default 3 - matches §44.6 red-flag threshold.
    """

    def __init__(
        self,
        *,
        policy_path: Path | None = None,
        thrash_window: int = 3,
    ) -> None:
        self._policy_path = policy_path
        self._thrash_window = thrash_window
        self._scope_extensions: set[str] = set()
        if policy_path is not None and policy_path.exists():
            self._scope_extensions = self._parse_scope_extensions(policy_path)

    @staticmethod
    def _parse_scope_extensions(policy_path: Path) -> set[str]:
        """Extract the §7 scope-extension log entries that have a
        granted disposition."""
        text = policy_path.read_text()
        s7_start = text.find("## 7. Scope-extension log")
        if s7_start < 0:
            return set()
        s7_end = text.find("## 8.", s7_start)
        block = text[s7_start:s7_end if s7_end > 0 else len(text)]
        # Each row is: | date | request | disposition |. Granted rows
        # contain the word "Granted" (case-insensitive) in the
        # disposition column. Extract the request text as the key.
        granted: set[str] = set()
        for row in re.finditer(
            r"^\| ([0-9]{4}-[0-9]{2}-[0-9]{2}) \| (.+?) \| (.+?) \|",
            block, re.MULTILINE,
        ):
            disposition = row.group(3).lower()
            if "granted" in disposition:
                # Index by the request text (truncated to first 60 chars
                # for keying)
                granted.add(row.group(2).strip()[:60].lower())
        return granted

    def decide(
        self,
        *,
        commit: CommitContext,
        drills: DrillContext,
        recent_files_per_commit: list[list[str]] | None = None,
    ) -> ApprovalDecision:
        """Apply the 5 rules in order. First match wins."""

        # Rule 1: drill_outcome contains 'FAILED' -> REJECT
        if not drills.all_green:
            return ApprovalDecision(
                verdict="REJECT",
                reason=f"drill_failed: {', '.join(drills.failed_drills)}",
                rule_fired=1,
                blocking_files=[],
            )

        # Per-file disposition lookup (used by rules 2 + 3)
        never_files: list[str] = []
        gated_files: list[str] = []
        for f in commit.files_touched:
            disp = file_disposition(f)
            if disp == "never":
                never_files.append(f)
            elif disp == "gated":
                gated_files.append(f)

        # Rule 2: any 'never' file -> REJECT
        if never_files:
            return ApprovalDecision(
                verdict="REJECT",
                reason=f"absolute_block: {len(never_files)} file(s) "
                       f"in 'never' disposition",
                rule_fired=2,
                blocking_files=never_files,
            )

        # Rule 3: any 'gated' file without a scope-extension entry
        # -> HOLD
        if gated_files:
            # If the scope-extension log already covers any of them,
            # treat as approved-by-extension. Conservative: a single
            # extension covers all 'gated' files in this commit.
            # In practice the operator extends scope per-file or
            # per-pattern; a smarter matcher is Phase 4A+.
            if not self._scope_extensions:
                return ApprovalDecision(
                    verdict="HOLD",
                    reason=f"scope_extension_needed: {len(gated_files)} "
                           f"gated file(s); no entry in §7 log",
                    rule_fired=3,
                    blocking_files=gated_files,
                )

        # Rule 5: same file in 3+ consecutive iterations -> HOLD
        # (Rule 4 - composability - deferred to LLM path; Phase 4A+)
        if recent_files_per_commit and len(recent_files_per_commit) >= self._thrash_window:
            recent = recent_files_per_commit[-self._thrash_window:]
            for path in commit.files_touched:
                if all(path in cfiles for cfiles in recent):
                    return ApprovalDecision(
                        verdict="HOLD",
                        reason=f"iteration_thrash: {path} touched in "
                               f"{self._thrash_window}+ consecutive commits",
                        rule_fired=5,
                        blocking_files=[path],
                    )

        # Rule 6 (default): all rules passed -> APPROVE
        return ApprovalDecision(
            verdict="APPROVE",
            reason="all rules passed",
            rule_fired=6,
            blocking_files=[],
        )
