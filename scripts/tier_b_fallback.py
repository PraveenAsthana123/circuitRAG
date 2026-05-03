"""Confidence-gated Tier-B fallback — Tier 2 #2.7.

Per CLAUDE.md §50 + §55. When local-Ollama council exhausts its 2
AUTHOR attempts (Tier 2 #2.1) AND no validated proposal emerged,
the daemon today writes outcome='author_schema_rejected_after_retry'
and gives up. Empirically: those issues frequently DO have valid
fixes — they just need a higher-quality model.

This module is the escalation path. It:

  1. Decides when to escalate (should_escalate_to_tier_b)
  2. Invokes the Tier-B model (Claude CLI by default; Codex CLI fallback)
  3. Validates the Tier-B output through the SAME CouncilProposal
     schema (Tier 1 #1.1) — no schema bypass; same gate as local
  4. Returns the validated proposal OR None (graceful degradation
     when Tier-B unavailable; daemon escalates to human)

USAGE FROM local_council.py
============================

  after both local AUTHOR attempts fail:
    if should_escalate_to_tier_b(audit_chain):
      tier_b_proposal = try_tier_b(issue, context)
      if tier_b_proposal:
        return tier_b_proposal
    # else: escalate to human-review queue

§42 / §50.5.3 BOUNDARIES
========================

  - Tier-B never escalates security rules (B*/S*) — those are
    blocked at agent_lead routing layer BEFORE this function fires
  - Tier-B output goes through the SAME schema validator as local —
    schema-failed Tier-B output is also rejected
  - Tier-B subprocess timeout bounded (240s default) so a hung
    Claude CLI can't block the daemon indefinitely

DEFAULT TIER-B MODELS
=====================

In priority order, the first available wins:
  1. claude-cli   (Anthropic Claude CLI — apt-installed system binary)
  2. codex-cli    (OpenAI Codex CLI)
  3. None         → return None; daemon escalates to human

Drilled by mcp/tests/drill_tier_b_fallback.py.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(REPO / "scripts"))
from council_schemas import (  # noqa: E402
    PROMPT_ADDENDUM,
    CouncilProposal,
    validate_council_proposal,
)

# Default confidence threshold below which we treat the local council
# result as "low confidence; would benefit from Tier-B."
DEFAULT_CONFIDENCE_THRESHOLD = 0.6

# Tier-B candidate binaries in priority order.
TIER_B_CANDIDATES: tuple[str, ...] = ("claude", "codex")

TIER_B_TIMEOUT_S: float = 240.0


def should_escalate_to_tier_b(
    audit_chain: dict,
    *,
    threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
) -> bool:
    """Decide if a council outcome should escalate to Tier-B.

    Three trigger conditions (any one fires):
      1. Both local AUTHOR attempts schema-rejected
         (audit_chain[author_attempt_2] failed validation OR absent)
      2. Last validated proposal had confidence < threshold
      3. Council ran but advisor produced an alternative
         flagging high risk

    Returns False (no escalation needed) when local council
    produced a confident validated proposal.
    """
    a1 = audit_chain.get("author_attempt_1", {})
    a2 = audit_chain.get("author_attempt_2", {})
    final_author = audit_chain.get("author", {})

    # Trigger 1: both local attempts rejected at validator
    if a1.get("validation") == "rejected" and a2.get("validation") == "rejected":
        return True

    # Trigger 2: low confidence on the validated proposal
    proposal = final_author.get("proposal")
    if proposal is not None:
        confidence = proposal.get("confidence", 0.0)
        if isinstance(confidence, (int, float)) and confidence < threshold:
            return True

    # Trigger 3: high-risk alternative from advisor (heuristic — flagged
    # via 'risks' length or specific words). Conservative: any non-empty
    # risks list with >= 3 entries OR contains 'breaking change'.
    advisor = audit_chain.get("advisor", {})
    alt = advisor.get("alternative_proposal")
    if alt is not None:
        risks = alt.get("risks", [])
        if isinstance(risks, list) and (
            len(risks) >= 3
            or any("breaking" in str(r).lower() for r in risks)
        ):
            return True

    return False


def find_available_tier_b() -> str | None:
    """Return the first Tier-B binary on PATH, or None."""
    for candidate in TIER_B_CANDIDATES:
        if shutil.which(candidate):
            return candidate
    return None


def try_tier_b(
    issue: dict,
    context: str,
    *,
    research_brief: str = "",
    timeout: float = TIER_B_TIMEOUT_S,
) -> CouncilProposal | None:
    """Invoke the highest-priority available Tier-B CLI; validate output.

    Returns CouncilProposal on success; None when:
      - no Tier-B binary on PATH
      - Tier-B subprocess exits non-zero or times out
      - Tier-B output fails CouncilProposal schema validation

    Same schema gate as local council (Tier 1 #1.1) — Tier-B does NOT
    get a free pass; bad output is still rejected.
    """
    binary = find_available_tier_b()
    if binary is None:
        return None

    prompt = (
        f"Fix this issue. Output ONLY a CouncilProposal JSON.\n\n"
        f"Issue: {issue.get('id', '?')}\n"
        f"Rule: {issue.get('code', '?')}\n"
        f"File: {issue.get('file', '?')}:{issue.get('line', '?')}\n"
        f"Message: {issue.get('message', '')}\n\n"
        f"Context:\n```\n{context[:4000]}\n```\n"
    )
    if research_brief:
        prompt += f"\nResearch brief:\n```\n{research_brief}\n```\n"
    prompt += PROMPT_ADDENDUM

    try:
        proc = subprocess.run(
            [binary, "--print", prompt],
            capture_output=True, text=True,
            timeout=timeout,
            cwd=str(REPO),
        )
    except subprocess.TimeoutExpired:
        return None
    except (FileNotFoundError, PermissionError):
        return None

    if proc.returncode != 0:
        return None
    return validate_council_proposal(proc.stdout, repo=REPO)


def main() -> int:
    """CLI helper: --help / --check (test if Tier-B is available)."""
    import argparse
    parser = argparse.ArgumentParser(prog="tier_b_fallback.py", description=__doc__)
    parser.add_argument("--check", action="store_true", help="Print which Tier-B binary is available")
    parser.add_argument("--threshold", type=float, default=DEFAULT_CONFIDENCE_THRESHOLD,
                        help="Confidence threshold for escalation (default: 0.6)")
    args = parser.parse_args()

    if args.check:
        binary = find_available_tier_b()
        if binary:
            print(f"✓ Tier-B available: {binary} (in PATH)")
            return 0
        print(f"✗ no Tier-B binary on PATH (looked for: {', '.join(TIER_B_CANDIDATES)})")
        return 1
    print(f"Tier-B fallback module ready. Threshold={args.threshold}")
    print(f"Available: {find_available_tier_b() or '(none)'}")
    print("Run --check to verify; --help for usage.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
