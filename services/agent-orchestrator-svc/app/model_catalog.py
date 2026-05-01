"""Curated catalog of models per role, with tier mapping for the routing layer.

Tier A = local Ollama (free, fast, deterministic).
Tier B = cloud frontier via local CLI (Claude/Codex; reuses local auth).

The router (app/model_router.py — Phase A3) picks per (role, complexity, novelty).
Frontend reads via GET /api/v1/agentic/models/catalog.

Backward compat: env overrides on AgentOrchestratorSettings still take precedence
when set, so existing deployments keep their hardcoded model choices until they
opt in to the catalog.

Why this layout instead of a config file: routing is correctness-critical (a
misrouted novel task bills 10x). Keeping the catalog as Python code keeps it
within the §43 drill suite — the catalog is itself drilled.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CatalogEntry:
    role_id: str
    role_type: str
    display_name: str
    tier_a_primary: str
    tier_a_backup: str
    tier_a_heavy: str | None = None
    tier_b: str | None = None
    tier_b_backend: str = "claude_cli"
    description: str = ""
    strengths: tuple[str, ...] = ()
    min_ram_gb: int = 8


# Default catalog uses Ollama models known to be installed on the dev host.
# Stronger options (qwen2.5-coder:7b-instruct, mistral-nemo:12b) are noted in
# the strengths field; operators can `ollama pull` them and override via env.
DEFAULT_CATALOG: tuple[CatalogEntry, ...] = (
    CatalogEntry(
        role_id="researcher",
        role_type="researcher",
        display_name="Researcher",
        tier_a_primary="qwen2.5:latest",
        tier_a_backup="llama3.1:8b",
        tier_b="claude-sonnet-4-6",
        description="Searches docs, synthesises sources, suggests approach for novel topics.",
        strengths=("synthesis", "multi-source citation", "novel API discovery"),
    ),
    CatalogEntry(
        role_id="strategist",
        role_type="planner",
        display_name="Strategist",
        tier_a_primary="qwen2.5:latest",
        tier_a_backup="llama3.1:8b",
        tier_b="claude-sonnet-4-6",
        description="Classifies complexity/novelty per step; sets routing tier downstream.",
        strengths=("task decomposition", "tier classification"),
    ),
    CatalogEntry(
        role_id="coder_executor",
        role_type="coder",
        display_name="Coder Executor",
        tier_a_primary="deepseek-coder:6.7b-instruct",
        tier_a_backup="codellama:7b-instruct",
        tier_a_heavy="deepseek-coder:6.7b-instruct",
        tier_b="claude-sonnet-4-6",
        tier_b_backend="codex_cli",
        description="Primary implementation agent. Tier-B for novel APIs / new frameworks.",
        strengths=("code generation", "patch synthesis"),
    ),
    CatalogEntry(
        role_id="reviewer",
        role_type="reviewer",
        display_name="Reviewer",
        tier_a_primary="starcoder2:7b",
        tier_a_backup="codellama:7b-instruct",
        description="Reviews worker output; returns SCORE: 0-10 used by retry-loop.",
        strengths=("code review", "score extraction"),
    ),
    CatalogEntry(
        role_id="advisor",
        role_type="advisor",
        display_name="Advisor",
        tier_a_primary="qwen2.5:latest",
        tier_a_backup="mistral:latest",
        tier_b="claude-sonnet-4-6",
        description="Synthesises execution + review + risks into operator recommendation.",
        strengths=("risk synthesis", "operator framing"),
    ),
    CatalogEntry(
        role_id="security_advisor",
        role_type="advisor",
        display_name="Security Advisor",
        tier_a_primary="codellama:7b-instruct",
        tier_a_backup="codegemma:7b-instruct",
        tier_b="claude-sonnet-4-6",
        description="Security-focused review for risky / write-capable tasks.",
        strengths=("secret/auth/injection detection",),
    ),
    CatalogEntry(
        role_id="tester",
        role_type="tester",
        display_name="Tester",
        tier_a_primary="deepseek-coder:6.7b-instruct",
        tier_a_backup="starcoder2:7b",
        description="Runs pytest/jest/ruff/mypy via mcp_tests; interprets failures.",
        strengths=("test pattern recognition", "failure triage"),
    ),
    CatalogEntry(
        role_id="deployer",
        role_type="deployer",
        display_name="Deployer",
        tier_a_primary="qwen2.5:latest",
        tier_a_backup="llama3.1:8b",
        description="Pre-flight check + diff summary. Actual deploy is human-gated per §42.",
        strengths=("diff summary", "pre-flight check"),
    ),
    CatalogEntry(
        role_id="observer",
        role_type="observer",
        display_name="Observer",
        tier_a_primary="llama3.1:8b",
        tier_a_backup="qwen2.5:latest",
        description="Queries Prom/Loki post-deploy; flags regressions.",
        strengths=("log summarisation", "metric anomaly framing"),
    ),
)


def get_catalog() -> tuple[CatalogEntry, ...]:
    return DEFAULT_CATALOG


def get_entry(role_id: str) -> CatalogEntry | None:
    for entry in DEFAULT_CATALOG:
        if entry.role_id == role_id:
            return entry
    return None


def validate_catalog(entries: tuple[CatalogEntry, ...]) -> list[str]:
    """Return list of validation errors. Empty list = catalog OK.

    Negative-assertion source: every entry MUST have a non-empty tier_a_primary
    AND tier_a_backup. The drill (drill_model_catalog.py) builds a broken entry
    and asserts this returns errors.
    """
    errors: list[str] = []
    seen_ids: set[str] = set()
    for entry in entries:
        if entry.role_id in seen_ids:
            errors.append(f"duplicate role_id: {entry.role_id}")
        seen_ids.add(entry.role_id)
        if not entry.tier_a_primary:
            errors.append(f"{entry.role_id}: tier_a_primary is empty")
        if not entry.tier_a_backup:
            errors.append(f"{entry.role_id}: tier_a_backup is empty")
        if entry.tier_b and entry.tier_b_backend not in ("claude_cli", "codex_cli"):
            errors.append(f"{entry.role_id}: invalid tier_b_backend {entry.tier_b_backend!r}")
    return errors
