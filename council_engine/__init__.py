"""council_engine — multi-agent debate + judge with 6-dim scoring.

Phases 1-5 wired:
  Phase 1 — independent answers (run_role × N)
  Phase 2 — judge with 6-dim weighted scoring
  Phase 3 — cross-critique (deep=True)
  Phase 4 — revision (deep=True)
  Phase 5 — evidence check + dissent detection (deep=True)

Q1 (aggregation) / Q2 (evidence) / Q3 (dissent) picks: rounds.py
docstring. All 3 are env-overridable.

Composes with (per CLAUDE.md §49):
  - safety_store.save_history       — every council_run persists with rollback_id
  - approval_agent.decide           — judge verdict can feed approval gate
  - risk_classifier.classify_task   — when_to_council() consults this
  - agent_cli.schemas.CouncilDecision — the locked output contract
  - ops_worker.worker               — high-risk tasks should escalate to council
  - scripts/paperclip_manager.aggregate_council_runs — Stage-1 surface reads here
  - mcp/tests/drill_council_engine.py / drill_council_rounds.py — 20 steps total
"""

from .judge import DIM_WEIGHTS, JudgeResult, judge
from .orchestrator import DEFAULT_ROLES, CouncilRun, run_council, when_to_council
from .rounds import (
    aggregate_confidence,
    check_evidence,
    cross_critique,
    detect_dissent,
    revise_round,
)

__all__ = [
    "CouncilRun",
    "DEFAULT_ROLES",
    "DIM_WEIGHTS",
    "JudgeResult",
    "aggregate_confidence",
    "check_evidence",
    "cross_critique",
    "detect_dissent",
    "judge",
    "revise_round",
    "run_council",
    "when_to_council",
]
