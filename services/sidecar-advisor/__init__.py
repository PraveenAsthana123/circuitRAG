"""Sidecar Advisor — personal AI auditor for prompt + code activity.

Phase 1 (current): manual paste → classify → advise (local Ollama) →
SQLite memory → user rating.

Phase 2 (next): Streamlit UI, git-diff capture, Claude/Codex routes,
LangGraph agent council, RAG-monitoring board.
"""
from .classifier import classify_input, EventType  # noqa: F401
from .memory import AdvisorMemory  # noqa: F401
from .advisor import Advisor, AdvisorOutput  # noqa: F401
