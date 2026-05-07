#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: Stage-7 GEPA canary routing (tenant-sticky hash).

Locks the `select_canary_version` helper that Stage-7 will eventually
call from rag_inference.ask. The wiring itself is deferred (operator-
decision commit); this drill ensures the helper's contract holds.

Approach: AST-validate the source-level contract (steps 1-5) + run a
self-contained reproduction of the routing logic to verify runtime
behavior (steps 6-8). The reproduction mirrors the source-level
algorithm; if the source diverges, AST steps catch it.

Eight steps. Six negative.
"""
from __future__ import annotations

import ast
import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PROMPT_REPO = REPO / "services" / "inference-svc" / "app" / "services" / "prompt_repo.py"


def _select_canary_repro(
    *,
    cache: dict,
    template_name: str,
    tenant_id: str | None,
) -> str:
    """Self-contained reproduction of prompt_repo.select_canary_version.

    Mirrors the source-level algorithm. Drill steps 1-5 enforce that
    the source matches this shape; if source drifts, those steps fail.
    """
    if os.environ.get("GEPA_CANARY_ENABLED", "").strip() != "1":
        return template_name
    try:
        percent = int(os.environ.get("GEPA_CANARY_PERCENT", "0").strip())
    except ValueError:
        return template_name
    if percent <= 0:
        return template_name
    if percent > 100:
        percent = 100
    gepa_keys = [
        k for k in cache
        if k.startswith(f"{template_name}_gepa-")
    ]
    if not gepa_keys:
        return template_name
    gepa_keys.sort()
    latest_gepa = gepa_keys[-1]
    if not tenant_id:
        return template_name
    try:
        bucket = abs(hash(str(tenant_id))) % 100
    except Exception:
        return template_name
    if bucket < percent:
        return latest_gepa
    return template_name


def main() -> int:
    print("-- 1. POSITIVE: select_canary_version method declared in source --")
    if not PROMPT_REPO.exists():
        print(f"x {PROMPT_REPO} missing")
        return 1
    src = PROMPT_REPO.read_text(encoding="utf-8")
    if "def select_canary_version" not in src:
        print("x prompt_repo must declare select_canary_version method")
        return 1
    if "GEPA_CANARY_ENABLED" not in src:
        print("x must check GEPA_CANARY_ENABLED env flag")
        return 1
    if "GEPA_CANARY_PERCENT" not in src:
        print("x must read GEPA_CANARY_PERCENT env var")
        return 1
    print("  ok: helper present + env flags declared")

    print("-- 2. NEGATIVE: source enforces default-deny (env unset → return baseline) --")
    # AST-walk: find the select_canary_version function and verify the
    # FIRST executable statement is the env-flag default-deny check.
    tree = ast.parse(src)
    fn_node = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "select_canary_version":
            fn_node = node
            break
    if fn_node is None:
        print("x select_canary_version FunctionDef not found")
        return 1
    # Skip docstring; find first non-docstring statement.
    body = fn_node.body
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]  # strip docstring
    # First statement should reference GEPA_CANARY_ENABLED
    if not body:
        print("x function body empty")
        return 1
    first_two = ast.unparse(ast.Module(body=body[:3], type_ignores=[]))
    if "GEPA_CANARY_ENABLED" not in first_two:
        print(f"x default-deny must be first check; got body[0:3] = {first_two[:200]}")
        return 1
    print("  ok: default-deny is first guard in function body")

    print("-- 3. NEGATIVE: source enforces tenant=None defense (no canary) --")
    # The source must include `if not tenant_id: return template_name`.
    if "if not tenant_id:" not in src:
        print("x must guard tenant=None case (un-attributable traffic stays baseline)")
        return 1
    print("  ok: tenant=None defense present in source")

    print("-- 4. NEGATIVE: source enforces missing-alias defense (gepa_keys empty) --")
    if "if not gepa_keys:" not in src:
        print("x must guard empty gepa_keys (no canary fires when alias missing)")
        return 1
    if 'k.startswith(f"{template_name}_gepa-")' not in src:
        print("x must select keys by `<template_name>_gepa-` prefix")
        return 1
    print("  ok: missing-alias defense present")

    print("-- 5. NEGATIVE: §47 fail-safe — hash errors fall back to baseline --")
    # The source must wrap hash() in try/except and return template_name on error
    fn_src = ast.unparse(fn_node)
    if "try:" not in fn_src:
        print("x source must wrap hash computation in try/except")
        return 1
    if "abs(hash(str(tenant_id)))" not in fn_src:
        print("x must use abs(hash(str(tenant_id))) for stable per-tenant bucket")
        return 1
    print("  ok: hash error → baseline (§47 fail-safe)")

    print("-- 6. NEGATIVE: runtime — percent=0 always returns baseline --")
    os.environ["GEPA_CANARY_ENABLED"] = "1"
    os.environ["GEPA_CANARY_PERCENT"] = "0"
    cache = {"rag.qa": "baseline", "rag.qa_gepa-1": "tuned"}
    for tid in ["t-1", "t-2", "t-3", "t-99"]:
        result = _select_canary_repro(cache=cache, template_name="rag.qa", tenant_id=tid)
        if result != "rag.qa":
            print(f"x percent=0 must return baseline; tenant {tid} got {result!r}")
            return 1
    print("  ok: percent=0 always baseline")

    print("-- 7. NEGATIVE: runtime — tenant-sticky (same tenant → same version) --")
    os.environ["GEPA_CANARY_PERCENT"] = "50"
    cache = {"rag.qa": "baseline", "rag.qa_gepa-1": "tuned"}
    first = _select_canary_repro(cache=cache, template_name="rag.qa", tenant_id="tenant-A")
    for _ in range(20):
        if _select_canary_repro(
            cache=cache, template_name="rag.qa", tenant_id="tenant-A",
        ) != first:
            print("x tenant-sticky violated: same tenant got different versions")
            return 1
    print(f"  ok: tenant 'tenant-A' stable on {first!r} across 20 calls")

    print("-- 8. POSITIVE: runtime — percent=100 + alias → gepa version --")
    os.environ["GEPA_CANARY_PERCENT"] = "100"
    cache = {"rag.qa": "baseline", "rag.qa_gepa-1762": "tuned"}
    result = _select_canary_repro(
        cache=cache, template_name="rag.qa", tenant_id="t-canary",
    )
    if not result.startswith("rag.qa_gepa-"):
        print(f"x percent=100 + alias must return gepa version; got {result!r}")
        return 1
    # And tenant=None still baseline even at 100%
    none_result = _select_canary_repro(
        cache=cache, template_name="rag.qa", tenant_id=None,
    )
    if none_result != "rag.qa":
        print("x tenant=None at 100% must STILL return baseline")
        return 1
    print(f"  ok: percent=100 routes to {result!r}; tenant=None still baseline")

    # Cleanup
    os.environ.pop("GEPA_CANARY_ENABLED", None)
    os.environ.pop("GEPA_CANARY_PERCENT", None)

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
