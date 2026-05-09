"""risk_classifier — pure-function classification over (action, type, text).

Closed set: low / medium / high / critical. Uses MAX of action floor +
type floor + keyword scan.

Composes with (per CLAUDE.md §49):
  - approval_agent.decide          — risk is the gate parameter
  - ops_worker.worker              — server-classifies before approval
  - agent_cli.orchestrator         — _infer_risk delegates here
  - council_engine.when_to_council — selects high/critical for full council
  - mcp/tests/drill_risk_classifier.py — 10-step contract drill
"""

from .classifier import (
    ACTION_FLOORS,
    TYPE_FLOORS,
    RiskAssessment,
    RiskLevel,
    classify,
    classify_task,
)

__all__ = [
    "ACTION_FLOORS",
    "RiskAssessment",
    "RiskLevel",
    "TYPE_FLOORS",
    "classify",
    "classify_task",
]
