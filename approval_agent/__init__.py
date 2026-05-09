"""approval_agent — pure-function decide() with blocked/human/auto rules.

Default engine: OPA (rego at policy.rego). Inline JSON rules.json is
the fallback when policy.rego is missing OR operator overrides via
DOCUMIND_APPROVAL_ENGINE=inline.

Composes with (per CLAUDE.md §49):
  - safety_store.save_history       — every decision writes a history row
  - risk_classifier.classify_task   — feeds the risk input into decide()
  - ops_worker.worker               — gates the COMPLETED transition
  - agent_cli.orchestrator          — gates the council session approval
  - council_engine.orchestrator     — judges before recommended_action
  - mcp/tests/drill_opa_approval_parity.py — 12-input parity gate
"""

from .agent import ApprovalDecision, decide, to_dict

__all__ = ["ApprovalDecision", "decide", "to_dict"]
