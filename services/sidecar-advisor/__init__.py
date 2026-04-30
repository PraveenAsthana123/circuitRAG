"""Sidecar Advisor — personal AI auditor for prompt + code activity.

Phase 1 (current): manual paste → classify → advise (local Ollama) →
SQLite memory → user rating.

Phase 2 (next): Next.js UI in services/frontend/, git-diff capture,
Claude/Codex routes, LangGraph agent council, RAG-monitoring board.
"""
from .advisor import Advisor, AdvisorOutput  # noqa: F401
from .classifier import EventType, classify_input  # noqa: F401
from .memory import AdvisorMemory  # noqa: F401
