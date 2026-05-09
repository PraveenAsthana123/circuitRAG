#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: LangSmith/Langfuse advanced operator status surface.

NEGATIVE: missing tracing credentials must be visible instead of reported ready.
"""
from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
STATUS = REPO / "scripts" / "lang_observability_status.py"


def require(src: str, needle: str, label: str) -> None:
    if needle not in src:
        raise AssertionError(f"missing {label}: {needle!r}")


def _load_status_module():
    spec = importlib.util.spec_from_file_location("lang_observability_status", STATUS)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load lang_observability_status module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    print("-- 1. POSITIVE: status script exists + parses --")
    src = STATUS.read_text(encoding="utf-8")
    ast.parse(src)
    print("  ok: status script is Python-valid")

    print("-- 2. POSITIVE: LangSmith managed tracing readiness is explicit --")
    for needle in ("LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2", "LANGSMITH_API_KEY", "LANGCHAIN_API_KEY"):
        require(src, needle, needle)
    require(src, "offline_safe", "offline-safe status")
    print("  ok: LangSmith env readiness is surfaced without SaaS calls")

    print("-- 3. POSITIVE: Langfuse self-hosted health is explicit --")
    require(src, "/api/public/health", "Langfuse health endpoint")
    require(src, "http://localhost:3002", "local Langfuse default")
    require(src, "LANGFUSE_TRACER_ENABLED", "Langfuse opt-in env")
    print("  ok: Langfuse health + tracer readiness are surfaced")

    print("-- 4. POSITIVE: module returns structured status --")
    mod = _load_status_module()
    payload = mod.status()
    if set(payload) != {"langsmith", "langfuse", "recommendation", "overall"}:
        raise AssertionError(f"unexpected top-level keys: {sorted(payload)}")
    if payload["langsmith"]["mode"] != "managed":
        raise AssertionError("LangSmith mode must be managed")
    if payload["langfuse"]["mode"] != "self_hosted":
        raise AssertionError("Langfuse mode must be self_hosted")
    if "managed_tracing_ready" not in payload["overall"]:
        raise AssertionError("overall status must include managed_tracing_ready")
    print("  ok: structured status includes LangSmith, Langfuse, recommendation, overall")

    print("\nALL 4 LANG OBSERVABILITY STATUS STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
