"""agent_cli — terminal-based always-on Ollama Agent Council.

Composition:
  safety_store    → history + rollback substrate
  approval_agent  → blocked / human / auto rules
  agent_cli       → planner / researcher / advisor / critic / presenter
                  → orchestrator (with safety gates)
                  → REPL (main.py)

Composes with (per CLAUDE.md §49):
  - safety_store.save_history     — every session writes 'agent_cli_session'
  - approval_agent.decide         — gate before Presenter
  - risk_classifier.classify      — _infer_risk delegates here
  - council_engine                — high-risk sessions could escalate
  - schemas.CouncilDecision       — locked output contract
  - mcp/tests/drill_safety_approval_council.py — 16-step composition drill
"""
