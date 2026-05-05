#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: /api/v1/health/best-config operator visibility (per §38 + §43).

Locks the route contract that surfaces what BestConfig is live
RIGHT NOW to operators. Closes the §38 "live state, not what's in
code" gap for the AutoRAG → registry → loader chain.

Eight steps. Six negative.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ROUTES = REPO / "services" / "inference-svc" / "app" / "routers" / "__init__.py"
SCHEMAS = REPO / "services" / "inference-svc" / "app" / "schemas" / "__init__.py"


def main() -> int:
    print("-- 1. POSITIVE: HealthBestConfigResponse + BestConfigInfo schemas exported --")
    if not SCHEMAS.exists():
        print(f"x {SCHEMAS} missing")
        return 1
    schemas_src = SCHEMAS.read_text(encoding="utf-8")
    if "class HealthBestConfigResponse(BaseModel):" not in schemas_src:
        print("x HealthBestConfigResponse must be defined in schemas")
        return 1
    if "class BestConfigInfo(BaseModel):" not in schemas_src:
        print("x BestConfigInfo must be defined in schemas")
        return 1
    print("  ok: both schemas present")

    print("-- 2. NEGATIVE: required fields prevent half-rendered UI --")
    # The UI relies on enabled+loaded to decide what to render.
    # Both must be NON-OPTIONAL booleans on the response.
    tree = ast.parse(schemas_src)
    found = None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "HealthBestConfigResponse":
            found = node
            break
    if found is None:
        print("x HealthBestConfigResponse class not found")
        return 1
    field_names = []
    for stmt in found.body:
        if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            field_names.append(stmt.target.id)
    for required in ("enabled", "loaded", "config_path", "config_exists",
                     "ttl_s", "fallback_defaults", "next_stage"):
        if required not in field_names:
            print(f"x HealthBestConfigResponse must declare {required}")
            return 1
    print("  ok: required visibility fields all declared")

    print("-- 3. POSITIVE: route exists with /api/v1/health/best-config path --")
    if not ROUTES.exists():
        print(f"x {ROUTES} missing")
        return 1
    routes_src = ROUTES.read_text(encoding="utf-8")
    if '"/api/v1/health/best-config"' not in routes_src:
        print("x route /api/v1/health/best-config must be registered")
        return 1
    if "response_model=HealthBestConfigResponse" not in routes_src:
        print("x route must declare response_model=HealthBestConfigResponse")
        return 1
    print("  ok: route registered with response_model")

    print("-- 4. NEGATIVE: route MUST NOT raise — wraps loader call in try/except --")
    # Visibility endpoint that crashes on loader-import error masks
    # the real outage operators are investigating. §47 fail-safe.
    handler_idx = routes_src.find("async def health_best_config()")
    if handler_idx < 0:
        print("x async def health_best_config() must exist")
        return 1
    handler_end = routes_src.find("@router.get(", handler_idx + 100)
    handler_body = routes_src[handler_idx:handler_end]
    if "try:" not in handler_body:
        print("x handler must wrap loader access in try")
        return 1
    if "except Exception" not in handler_body:
        print("x handler must catch generic Exception (visibility never crashes)")
        return 1
    print("  ok: §47 fail-safe — visibility never crashes")

    print("-- 5. NEGATIVE: handler reads via lazy sys.path import (no startup coupling) --")
    # Module-level import would couple inference-svc startup to
    # best_config_loader's environment. Lazy import keeps the
    # dependency optional.
    tree_routes = ast.parse(routes_src)
    for node in tree_routes.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            mod = getattr(node, "module", None) or ""
            names = [a.name for a in getattr(node, "names", [])]
            if mod == "best_config_loader" or "best_config_loader" in names:
                print("x best_config_loader must NOT be imported at module level")
                return 1
    if "from best_config_loader import" not in handler_body:
        print("x handler must lazy-import from best_config_loader")
        return 1
    print("  ok: lazy import inside handler; no startup coupling")

    print("-- 6. NEGATIVE: response always 200; enabled/loaded distinguish state --")
    # The handler must never `raise HTTPException` — visibility=200
    # with descriptive fields is the contract. UI distinguishes
    # disabled/missing/loaded via `enabled` + `loaded` booleans.
    if "raise HTTPException" in handler_body:
        print("x handler must NOT raise HTTPException — always 200")
        return 1
    if "enabled = False" not in handler_body:
        print("x handler must initialize enabled=False (default-deny)")
        return 1
    if "loaded = False" not in handler_body:
        print("x handler must initialize loaded=False (default-deny)")
        return 1
    print("  ok: always-200 contract; default-deny initial state")

    print("-- 7. POSITIVE: BestConfigInfo populated only when loaded=True --")
    # Defense against half-rendered UI: when loaded=False, the
    # config field MUST be None (not a partially-filled BestConfigInfo).
    if "loaded = True" not in handler_body:
        print("x must set loaded=True when load_best_config() returns non-None")
        return 1
    if "config = BestConfigInfo(" not in handler_body:
        print("x must instantiate BestConfigInfo from cfg attributes")
        return 1
    # Ensure config defaults to None at handler entry (initialized
    # before the try-block so failure path leaves it None).
    config_init_idx = handler_body.find("config: BestConfigInfo | None = None")
    if config_init_idx < 0:
        print("x config must initialize to None (covers loader-failure path)")
        return 1
    print("  ok: config is None unless loader succeeded")

    print("-- 8. NEGATIVE: BestConfigInfo MUST surface pass_rate (provenance) --")
    # Without pass_rate, operators can't tell whether the live config
    # was promoted from a thorough eval or a 1-pair smoke test.
    found_info = None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "BestConfigInfo":
            found_info = node
            break
    if found_info is None:
        print("x BestConfigInfo class not found")
        return 1
    info_fields = []
    for stmt in found_info.body:
        if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            info_fields.append(stmt.target.id)
    for required in ("min_score", "top_k", "rerank_enabled",
                     "pass_rate", "eval_set_size", "promoted_at_ts"):
        if required not in info_fields:
            print(f"x BestConfigInfo must surface {required} for provenance")
            return 1
    print("  ok: BestConfigInfo carries provenance fields (pass_rate / eval_set_size / promoted_at_ts)")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
