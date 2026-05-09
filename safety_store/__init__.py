"""safety_store — History + Rollback substrate for autonomous-agent platforms.

Hard rule: every change/delete writes to ``history_events`` BEFORE the
mutation. Direct DB writes bypass the rule — drill catches.

Composes with (per CLAUDE.md §49):
  - approval_agent.decide  — every decision lands here as a history row
  - ops_worker.worker      — pre-state captured before status transitions
  - council_engine         — every council run persists as entity_type='council_run'
  - agent_cli.orchestrator — every CLI session persists as 'agent_cli_session'
  - scripts/paperclip_manager.aggregate_safety_history — Stage-1 dashboard reads here
  - mcp/tests/drill_safety_approval_council.py — locks the contract
"""

from .history import (
    DEFAULT_ROLLBACK_DAYS,
    HistoryRecord,
    RollbackError,
    ensure_schema,
    get_by_rollback_id,
    list_history,
    rollback,
    save_history,
    with_history,
)

__all__ = [
    "DEFAULT_ROLLBACK_DAYS",
    "HistoryRecord",
    "RollbackError",
    "ensure_schema",
    "get_by_rollback_id",
    "list_history",
    "rollback",
    "save_history",
    "with_history",
]
