"""Minimal graph API compatible with import-only LangGraph probes."""
from __future__ import annotations

END = "__end__"


class _CompiledGraph:
    def __init__(self, nodes: dict[str, object], entry_point: str | None) -> None:
        self.nodes = dict(nodes)
        self.entry_point = entry_point

    def invoke(self, state):
        return state


class StateGraph:
    def __init__(self, state_schema=None) -> None:
        self.state_schema = state_schema
        self._nodes: dict[str, object] = {}
        self._entry_point: str | None = None

    def add_node(self, name: str, node) -> None:
        self._nodes[name] = node

    def add_edge(self, start: str, end: str) -> None:
        return None

    def set_entry_point(self, name: str) -> None:
        self._entry_point = name

    def compile(self) -> _CompiledGraph:
        return _CompiledGraph(self._nodes, self._entry_point)


__all__ = ["END", "StateGraph"]
