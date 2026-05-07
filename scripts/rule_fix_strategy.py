"""Per-rule fix-strategy table — Tier 1 #1.3 of the autonomous-fix-bot roadmap.

Per CLAUDE.md §50 + §55. Closes the empirical session finding that
council quality varies wildly across rule types because they all
get the SAME prompt:

  F841 (unused var)       → real-bug-vs-dead-code investigation
  UP035 (deprecated import) → mechanical 1-line replacement
  E702 (multi-statement)  → literal split into N lines
  I001 (import sort)      → reorganize block
  no-untyped-def (mypy)   → add type annotation
  B*  / S* (security)     → human review only (per §50.5.3)

Today's local_council.py uses ONE generic AUTHOR prompt for all of
these. Empirical: F841 council proposed `pipeline_v2 = False`
(wrong fix, didn't investigate); E702 reviewer said "add a
semicolon" (reversed the rule). Same prompt, very different
problem shapes.

This module is the dispatch table. Each rule code → strategy with:

  category     - which prompt template to use
  context_lines - how many lines around the issue to include
  needs_grep_refs - whether to run grep -rn for the symbol first
  model_tier   - "small" (llama3.2:1b) / "default" (deepseek-coder)
                 / "tier_b" (Claude/Codex CLI) / "human" (skip)

Drilled by mcp/tests/drill_rule_fix_strategy.py — both directions:
  - known rule → returns the right strategy
  - unknown rule → falls back to default with conservative settings
  - security rule → returns model_tier='human' (never to model)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Category = Literal[
    "investigation",      # F841, F811: maybe-real-bug; investigate references
    "mechanical_rewrite", # UP035, UP041, E702, E711: literal fix per rule msg
    "import_sort",        # I001: reorganize the import block
    "type_fix",           # mypy index, no-untyped-def, assignment errors
    "frontend_jsx",       # eslint react/* + react-hooks/* rules
    "security",           # S*, B*: NEVER to model per §50.5.3
    "default",            # unknown / unmapped: conservative fallback
]
ModelTier = Literal["small", "default", "tier_b", "human"]


@dataclass(frozen=True)
class RuleStrategy:
    """One row of the dispatch table."""

    category: Category
    context_lines: int          # ± lines around issue site
    needs_grep_refs: bool       # run grep -rn for symbol mentioned in rule msg
    model_tier: ModelTier
    prompt_template_key: str    # key into PROMPT_TEMPLATES below


PROMPT_TEMPLATES: dict[str, str] = {
    "investigation": (
        "<role>You investigate maybe-real-bug findings before proposing a fix.</role>\n"
        "<goal>Decide if the flagged symbol is dead code (delete it) OR a real bug "
        "(restore intended use). Output a CouncilProposal JSON.</goal>\n"
        "<rules>\n"
        "1. Read the ±30 lines + grep references provided.\n"
        "2. If the symbol has NO references anywhere in the repo: dead code; "
        "propose delete diff with high confidence.\n"
        "3. If references exist but appear to use a DIFFERENT name: real bug; "
        "propose rename or restore diff with medium confidence + risks list.\n"
        "4. If unclear: propose investigation comment + low confidence + risks.\n"
        "</rules>\n"
    ),
    "mechanical_rewrite": (
        "<role>You produce literal mechanical fixes for trivial style rules.</role>\n"
        "<goal>Apply the rule's exact suggested fix. No interpretation, no "
        "investigation. CouncilProposal JSON.</goal>\n"
        "<rules>\n"
        "1. The rule message describes the exact fix; apply it literally.\n"
        "2. Diff must be MINIMAL — touch only the cited line.\n"
        "3. Confidence ≥ 0.85 since rules in this category are mechanical.\n"
        "4. risks=[] unless the change touches a public API.\n"
        "</rules>\n"
    ),
    "import_sort": (
        "<role>You reorganize Python import blocks per ruff/isort conventions.</role>\n"
        "<goal>Sort imports into groups: stdlib / third-party / first-party / "
        "relative; alphabetize within each group. CouncilProposal JSON.</goal>\n"
        "<rules>\n"
        "1. Detect the import-block boundaries (top of file until first non-import).\n"
        "2. Categorize each import by source.\n"
        "3. Rewrite the entire block; preserve __future__ at the very top.\n"
        "4. Diff covers the whole import block, not individual lines.\n"
        "</rules>\n"
    ),
    "type_fix": (
        "<role>You add type annotations + cast() where mypy demands.</role>\n"
        "<goal>Fix the specific type error in the rule message. "
        "CouncilProposal JSON.</goal>\n"
        "<rules>\n"
        "1. Index errors → cast() the index OR change the dict's key type.\n"
        "2. Missing annotation → add the most-narrow type (Literal > Union > Any).\n"
        "3. Unreachable / no-untyped-def → annotate explicitly.\n"
        "4. Confidence 0.7-0.85 — type fixes can have semantic impact.\n"
        "</rules>\n"
    ),
    "frontend_jsx": (
        "<role>You fix React/JSX lint rules (react/* + react-hooks/*).</role>\n"
        "<goal>Fix the specific eslint rule violation. CouncilProposal JSON.</goal>\n"
        "<rules>\n"
        "1. react/no-unescaped-entities → escape & ' \" < > with HTML entities.\n"
        "2. react-hooks/exhaustive-deps → add the missing dep OR document why it's "
        "intentional via // eslint-disable-next-line.\n"
        "3. Confidence ≥ 0.8 for entity escapes; 0.6-0.7 for deps (intent unclear).\n"
        "</rules>\n"
    ),
    "default": (
        "<role>You propose a minimal fix for an uncategorized lint/check finding.</role>\n"
        "<goal>Read the rule message + ±10 lines context; propose the smallest "
        "change that resolves the rule. Conservative — prefer no-op + comment if "
        "uncertain. CouncilProposal JSON.</goal>\n"
        "<rules>\n"
        "1. If you don't recognize the rule, do NOT guess — return confidence < 0.5.\n"
        "2. Diff MUST be minimal. No drive-by refactors.\n"
        "3. Risks list must be honest about what you don't know.\n"
        "</rules>\n"
    ),
}


# Dispatch table: known rule code → strategy.
# Keys are case-sensitive matches against the issue's `code` field.
RULE_STRATEGIES: dict[str, RuleStrategy] = {
    # Investigation — maybe real bug, needs cross-references
    "F841": RuleStrategy("investigation", 30, True, "default", "investigation"),
    "F811": RuleStrategy("investigation", 30, True, "default", "investigation"),
    "F401": RuleStrategy("mechanical_rewrite", 5, False, "small", "mechanical_rewrite"),  # unused import — usually safe to delete
    # Mechanical rewrite — rule message describes exact fix
    "UP035": RuleStrategy("mechanical_rewrite", 5, False, "default", "mechanical_rewrite"),
    "UP041": RuleStrategy("mechanical_rewrite", 5, False, "small", "mechanical_rewrite"),
    "UP037": RuleStrategy("mechanical_rewrite", 5, False, "small", "mechanical_rewrite"),
    "E702": RuleStrategy("mechanical_rewrite", 5, False, "small", "mechanical_rewrite"),
    "E711": RuleStrategy("mechanical_rewrite", 5, False, "small", "mechanical_rewrite"),
    "E712": RuleStrategy("mechanical_rewrite", 5, False, "small", "mechanical_rewrite"),
    "E501": RuleStrategy("mechanical_rewrite", 10, False, "default", "mechanical_rewrite"),  # line too long — sometimes needs reformat
    # E402 — module-level import not at top. Often needs structural reasoning
    # (where to move imports, whether the offending line belongs above/below
    # imports, # noqa candidate). Empirical: 0/8 council apply rate on E402.
    # Route to human-review queue; operator decides per-file.
    "E402": RuleStrategy("investigation", 30, True, "human", "investigation"),
    # Import sort — full-block rewrite
    "I001": RuleStrategy("import_sort", 50, False, "default", "import_sort"),  # 50 because need full import block
    # Type fixes
    "index": RuleStrategy("type_fix", 15, True, "default", "type_fix"),         # mypy index error
    "no-untyped-def": RuleStrategy("type_fix", 15, False, "default", "type_fix"),
    "no-untyped-call": RuleStrategy("type_fix", 15, False, "default", "type_fix"),
    "assignment": RuleStrategy("type_fix", 15, False, "default", "type_fix"),
    "arg-type": RuleStrategy("type_fix", 15, True, "default", "type_fix"),
    # Frontend / JSX
    "react/no-unescaped-entities": RuleStrategy("frontend_jsx", 5, False, "small", "frontend_jsx"),
    "react-hooks/exhaustive-deps": RuleStrategy("frontend_jsx", 30, True, "default", "frontend_jsx"),
}


# Default fallback for unmapped rules. Conservative: more context,
# default tier, slow + careful.
DEFAULT_STRATEGY: RuleStrategy = RuleStrategy(
    category="default",
    context_lines=10,
    needs_grep_refs=False,
    model_tier="default",
    prompt_template_key="default",
)


# Security: hard-coded skip list. Per §50.5.3, NEVER to model.
SECURITY_PREFIXES: tuple[str, ...] = ("S", "B")  # ruff S* + bandit B*


def get_strategy(rule_code: str) -> RuleStrategy:
    """Look up the strategy for a rule code.

    Returns:
      - SECURITY strategy (model_tier='human') for any rule starting
        with S or B (per §50.5.3 — bandit + ruff security)
      - The exact match from RULE_STRATEGIES if known
      - DEFAULT_STRATEGY for unknown codes (conservative fallback)
    """
    if not rule_code:
        return DEFAULT_STRATEGY
    # Security check FIRST — bandit B* must never reach a model.
    if any(rule_code.startswith(p) for p in SECURITY_PREFIXES):
        return RuleStrategy(
            category="security",
            context_lines=0,
            needs_grep_refs=False,
            model_tier="human",
            prompt_template_key="default",  # not used; tier=human short-circuits
        )
    return RULE_STRATEGIES.get(rule_code, DEFAULT_STRATEGY)


def get_prompt_template(strategy: RuleStrategy) -> str:
    """Return the prompt template for the strategy."""
    return PROMPT_TEMPLATES.get(strategy.prompt_template_key, PROMPT_TEMPLATES["default"])


def is_human_only(rule_code: str) -> bool:
    """True if this rule must be routed to a human (security)."""
    return get_strategy(rule_code).model_tier == "human"


if __name__ == "__main__":
    import sys
    print("scripts/rule_fix_strategy.py — per-rule fix-strategy table (§50 + §55 Tier 1.3)")
    print("Library module — imported by scripts/local_council.py, scripts/agent_lead.py, and 1 drill.")
    print("Exports: get_strategy(rule_code) · is_human_only(rule_code) · STRATEGY_BY_RULE")
    print("This script has no CLI; --help prints this summary. See module docstring for full context.")
    sys.exit(0)
