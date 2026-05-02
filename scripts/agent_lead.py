"""Agent-lead-first routing — Tier 1 #1.2 of the autonomous-fix-bot roadmap.

Per CLAUDE.md §50 + §55. Closes the gap that today every issue
goes through the full 4-role council (RESEARCHER + AUTHOR +
REVIEWER + ADVISOR) regardless of difficulty. F401 (unused import,
trivial) gets the same 3+ minute treatment as F841 (real-bug
investigation). That's wasteful: trivial fixes don't need council
deliberation, and complex fixes need a tier-B human-grade model.

The agent-lead reads the issue + strategy and decides:

  ROUTE_COUNCIL_FULL    — strategy.model_tier='default' or 'large';
                          use full 4-role council
  ROUTE_SMALL_DIRECT    — strategy.model_tier='small'; single
                          fast model call (llama3.2:1b or
                          codegemma:7b) bypassing council overhead
  ROUTE_TIER_B          — strategy.model_tier='tier_b'; escalate
                          to Claude/Codex CLI (not Ollama)
  ROUTE_HUMAN           — strategy.model_tier='human'; skip; queue
                          to .loop/human_review_queue.md
  ROUTE_SKIP            — already-attempted OR out-of-safe-path;
                          no model invocation

The routing decision is the supervisor pattern (CrewAI / LangGraph
supervisor / lead-and-delegate). It's the "lead first" shape — a
manager agent picks the right tier before any worker fires.

Drilled by mcp/tests/drill_agent_lead_routing.py — verifies each
of the 5 routes for representative inputs + that the decision is
auditable (RouteDecision returned + reason + estimated_cost).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, Literal


REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
from rule_fix_strategy import RuleStrategy, get_strategy, is_human_only  # noqa: E402


Route = Literal[
    "council_full",
    "small_direct",
    "tier_b",
    "human",
    "skip",
]


@dataclass(frozen=True)
class RouteDecision:
    """Structured output of the agent-lead routing call.

    Auditable: every fix-attempt logs which route fired + why +
    estimated cost so post-incident analysis can answer
    'what should we have routed differently?'
    """

    route: Route
    reason: str
    model: str | None
    estimated_tokens: int
    estimated_cost_cents: float

    model_config: ClassVar[dict] = {"frozen": True}


# Cost estimates per model. Local Ollama models are GPU/electricity
# cost only; we approximate as $0.001/1K tokens to keep parity with
# how the rest of the audit row tracks cost. Tier-B (Claude/Codex)
# uses real API rates.
COST_PER_1K_TOKENS_CENTS: dict[str, float] = {
    "llama3.2:1b":                0.05,   # very cheap; small model
    "codegemma:7b-instruct":      0.10,
    "deepseek-coder:6.7b-instruct": 0.10,
    "codellama:7b-instruct":      0.10,
    "qwen2.5:latest":             0.10,
    "claude-cli":                 5.0,    # Tier-B real cost
    "codex-cli":                  4.0,
}


# Tokens roughly consumed per route (full pipeline tally).
EXPECTED_TOKENS_PER_ROUTE: dict[Route, int] = {
    "council_full":  3500,   # researcher 300 + author 700 + reviewer 200 + advisor 300, with prompts
    "small_direct":   400,   # single model call with minimal prompt
    "tier_b":        1500,   # tier-B model with concise prompt
    "human":            0,   # no model invocation
    "skip":             0,
}


def _estimate_cost(route: Route, model: str | None) -> tuple[int, float]:
    tokens = EXPECTED_TOKENS_PER_ROUTE.get(route, 0)
    if model is None or tokens == 0:
        return tokens, 0.0
    rate = COST_PER_1K_TOKENS_CENTS.get(model, 0.10)
    return tokens, round(tokens / 1000.0 * rate, 4)


def decide_route(issue: dict, *, already_attempted: bool = False, in_safe_path: bool = True) -> RouteDecision:
    """The lead-first decision.

    Inputs:
      issue            — checklist row {id, code, file, line, ...}
      already_attempted - if true, route='skip' to avoid retry loop
                         (unless operator explicitly clears the audit)
      in_safe_path     — false if path outside services/+libs/+mcp/+scripts/

    Output: RouteDecision with route + reason + model + cost estimate.

    The decision is deterministic given the inputs — the strategy
    table (Tier 1 #1.3) does the categorization; this function
    just maps strategy.model_tier to the right route + estimates cost.
    """
    rule_code = issue.get("code", "")

    # Filter 1 — already-attempted skip (prevents retry-loop).
    if already_attempted:
        return RouteDecision(
            route="skip",
            reason=f"issue {issue.get('id')} already in apply audit; skip per daemon retry policy",
            model=None,
            estimated_tokens=0,
            estimated_cost_cents=0.0,
        )

    # Filter 2 — out-of-safe-path skip.
    if not in_safe_path:
        return RouteDecision(
            route="skip",
            reason=f"path {issue.get('file')!r} outside safe boundary (services/ libs/py/ mcp/ scripts/)",
            model=None,
            estimated_tokens=0,
            estimated_cost_cents=0.0,
        )

    # Filter 3 — security rules NEVER to model (per §50.5.3).
    if is_human_only(rule_code):
        return RouteDecision(
            route="human",
            reason=f"rule {rule_code!r} is security-tier; routes to .loop/human_review_queue.md per §50.5.3",
            model=None,
            estimated_tokens=0,
            estimated_cost_cents=0.0,
        )

    strategy = get_strategy(rule_code)

    # Map strategy.model_tier to a route + concrete model.
    if strategy.model_tier == "human":
        return RouteDecision(
            route="human",
            reason=f"strategy explicitly routes {rule_code!r} to human",
            model=None,
            estimated_tokens=0,
            estimated_cost_cents=0.0,
        )

    if strategy.model_tier == "small":
        # Small-direct path: bypass council overhead for trivial rules.
        # Picks llama3.2:1b for the fastest single-model fix.
        model = "llama3.2:1b"
        tokens, cost = _estimate_cost("small_direct", model)
        return RouteDecision(
            route="small_direct",
            reason=(
                f"strategy.model_tier='small' for {rule_code!r}; "
                f"single {model} call ~7x faster than 4-role council"
            ),
            model=model,
            estimated_tokens=tokens,
            estimated_cost_cents=cost,
        )

    if strategy.model_tier == "tier_b":
        # Tier-B escalation: Claude or Codex CLI; far higher cost
        # but needed for high-complexity / high-novelty fixes.
        model = "claude-cli"
        tokens, cost = _estimate_cost("tier_b", model)
        return RouteDecision(
            route="tier_b",
            reason=(
                f"strategy.model_tier='tier_b' for {rule_code!r}; "
                f"escalating to {model} (real-API cost)"
            ),
            model=model,
            estimated_tokens=tokens,
            estimated_cost_cents=cost,
        )

    # Default: full 4-role council (researcher + author + reviewer + advisor).
    # AUTHOR is the cost driver (longest output); use deepseek-coder for cost.
    model = "deepseek-coder:6.7b-instruct"
    tokens, cost = _estimate_cost("council_full", model)
    return RouteDecision(
        route="council_full",
        reason=(
            f"strategy.model_tier='default' for {rule_code!r}; full 4-role "
            f"council (RESEARCHER+AUTHOR+REVIEWER+ADVISOR) with schema gate"
        ),
        model=model,
        estimated_tokens=tokens,
        estimated_cost_cents=cost,
    )


def main() -> int:
    """CLI: decide route for one issue id.

    Usage: agent_lead.py decide --id <issue_id>
    """
    import argparse
    import json

    parser = argparse.ArgumentParser(prog="agent_lead.py")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_dec = sub.add_parser("decide", help="emit route decision for one issue id")
    p_dec.add_argument("--id", required=True)
    args = parser.parse_args()

    if args.cmd == "decide":
        checklist_path = REPO / ".loop" / "issue_checklist.jsonl"
        if not checklist_path.exists():
            print("x .loop/issue_checklist.jsonl missing; run scanner first")
            return 1
        issues = [json.loads(l) for l in checklist_path.read_text().splitlines() if l.strip()]
        issue = next((i for i in issues if i["id"] == args.id), None)
        if issue is None:
            print(f"x issue not found: {args.id}")
            return 1
        decision = decide_route(issue)
        print(json.dumps({
            "route": decision.route,
            "model": decision.model,
            "estimated_tokens": decision.estimated_tokens,
            "estimated_cost_cents": decision.estimated_cost_cents,
            "reason": decision.reason,
        }, indent=2))
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
