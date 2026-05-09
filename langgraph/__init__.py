"""Repo-local LangGraph compatibility shim for offline drills.

Runtime services should install the real `langgraph` package. This shim is
limited to the small graph symbols used by import-only checks.
"""
from __future__ import annotations

from .graph import END, StateGraph

__version__ = "compat-local"

__all__ = ["END", "StateGraph"]
