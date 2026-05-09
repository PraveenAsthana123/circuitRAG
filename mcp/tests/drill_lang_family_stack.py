#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: LangChain/LangGraph/LangSmith/Langfuse package compatibility.

Locks the local "Lang family" stack against the failure mode where
LangChain integrations are upgraded but langchain-core remains on the
old 0.x line. This is an import-only/offline drill: LangSmith and
Langfuse clients are not allowed to call external services here.

NEGATIVE: Lang-family package versions must not drift into incompatible core lines.
"""
from __future__ import annotations

import importlib
from importlib.metadata import PackageNotFoundError, requires, version


def _major(pkg: str) -> int:
    return int(version(pkg).split(".", 1)[0])


def _require_pkg(pkg: str, module: str | None = None) -> None:
    module = module or pkg.replace("-", "_")
    try:
        importlib.import_module(module)
        print(f"  ok: {module} importable ({pkg} {version(pkg)})")
    except (ImportError, PackageNotFoundError) as exc:
        raise AssertionError(f"{pkg}/{module} must be importable: {exc}") from exc


def _requires_core_1x(pkg: str) -> None:
    reqs = requires(pkg) or []
    core_reqs = [req for req in reqs if req.lower().startswith("langchain-core")]
    if not core_reqs:
        raise AssertionError(f"{pkg} does not declare a langchain-core dependency")
    if not any(">=1" in req or ">= 1" in req for req in core_reqs):
        raise AssertionError(f"{pkg} must require langchain-core >=1.x; saw {core_reqs}")
    print(f"  ok: {pkg} declares {core_reqs[0]}")


def main() -> int:
    print("-- 1. POSITIVE: core Lang packages import offline --")
    for pkg, module in [
        ("langchain", "langchain"),
        ("langchain-core", "langchain_core"),
        ("langchain-community", "langchain_community"),
        ("langchain-text-splitters", "langchain_text_splitters"),
        ("langgraph", "langgraph"),
        ("langsmith", "langsmith"),
        ("langfuse", "langfuse"),
    ]:
        _require_pkg(pkg, module)

    print("-- 2. POSITIVE: LangChain integrations import offline --")
    _require_pkg("langchain-ollama", "langchain_ollama")
    _require_pkg("langchain-xai", "langchain_xai")

    print("-- 3. NEGATIVE: langchain-core must be on 1.x line --")
    if _major("langchain-core") < 1:
        raise AssertionError(
            f"langchain-core {version('langchain-core')} is too old for "
            "langchain-ollama/langchain-xai/langgraph 1.x",
        )
    print(f"  ok: langchain-core {version('langchain-core')} is compatible")

    print("-- 4. POSITIVE: integrations declare langchain-core >=1.x --")
    for pkg in (
        "langchain-community",
        "langchain-text-splitters",
        "langchain-ollama",
        "langchain-xai",
        "langgraph",
    ):
        _requires_core_1x(pkg)

    print("\nALL 4 LANG-FAMILY STACK STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
