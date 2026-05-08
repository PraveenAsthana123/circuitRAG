"""hybrid_architect — Hub-and-Spoke + Council composition (CLAUDE.md §47).

The Hub (agent_cli.orchestrator.run_council) handles execution.
The Council (council_engine.orchestrator.run_council) handles review.
This module composes them, gated by risk_classifier.

Risk → lane routing:
  low      → hub_only
  medium   → hub_council          (deep=False)
  high     → hub_council_deep     (deep=True)
  critical → hub_council_deep_hitl (deep=True + requires_hitl)

Composes with (per §49):
  - agent_cli.orchestrator      — the hub pipeline
  - council_engine.orchestrator — the parallel council
  - risk_classifier             — the lane gate
  - approval_agent              — already-integrated by the hub
  - safety_store.save_history   — every hybrid run persists for replay
  - scripts.langfuse_tracer     — offline-safe spans for day-1 audit
  - mcp/tests/drill_hybrid_architect.py — 8-step contract drill
"""

from .architect import HybridDecision, process
from .architect import _pick_lane  # exported for drill use

__all__ = ["HybridDecision", "process", "_pick_lane"]
