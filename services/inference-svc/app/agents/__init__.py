"""
Agent orchestration (Design Area 11 — Agent State, + Extra — CCB).

This package holds multi-step agent loops for DocuMind's advanced-RAG use
cases (multi-hop QA, corrective RAG, plan-then-retrieve). Every agent run
is guarded by :class:`~documind_core.breakers.AgentLoopCircuitBreaker`.

Right now this is a thin skeleton showing the pattern — the production
planner/synthesizer/critic live in spec Areas 11 + 25 and will be filled
in a future session.
"""

from .multi_hop_agent import MultiHopRagAgent

__all__ = ["MultiHopRagAgent"]
