#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: /api/v1/health/best-config on retrieval-svc (per §38 + §43).

Mirrors drill_health_best_config_route.py — both services expose the
same shape so the operator dashboard can render the inference-svc
view + the retrieval-svc view side by side. They MUST agree on the
schema; that's what this drill enforces.

Eight steps. Six negative.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ROUTES = REPO / "services" / "retrieval-svc" / "app" / "routers" / "__init__.py"
SCHEMAS = REPO / "services" / "retrieval-svc" / "app" / "schemas" / "__init__.py"
INF_SCHEMAS = REPO / "services" / "inference-svc" / "app" / "schemas" / "__init__.py"


def _class_fields(src: str, class_name: str) -> set[str]:
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            fields = set()
            for stmt in node.body:
                if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                    fields.add(stmt.target.id)
            return fields
    return set()


def main() -> int:
    print("-- 1. POSITIVE: retrieval-svc schemas declare HealthBestConfigResponse + BestConfigInfo --")
    if not SCHEMAS.exists():
        print(f"x {SCHEMAS} missing")
        return 1
    src = SCHEMAS.read_text(encoding="utf-8")
    if "class HealthBestConfigResponse(BaseModel):" not in src:
        print("x retrieval-svc must declare HealthBestConfigResponse")
        return 1
    if "class BestConfigInfo(BaseModel):" not in src:
        print("x retrieval-svc must declare BestConfigInfo")
        return 1
    print("  ok: both schemas declared")

    print("-- 2. NEGATIVE: retrieval-svc HealthBestConfigResponse SHAPE matches inference-svc --")
    # The dashboard calls both. If the shapes diverge, operator sees
    # broken UI on one side. Drill enforces field parity (defaults
    # may differ but the contract names must match).
    inf_src = INF_SCHEMAS.read_text(encoding="utf-8")
    inf_fields = _class_fields(inf_src, "HealthBestConfigResponse")
    ret_fields = _class_fields(src, "HealthBestConfigResponse")
    missing = inf_fields - ret_fields
    if missing:
        print(f"x retrieval-svc HealthBestConfigResponse missing fields: {sorted(missing)}")
        return 1
    print(f"  ok: shape parity (both have {len(inf_fields)} fields)")

    print("-- 3. POSITIVE: BestConfigInfo provenance fields present in retrieval-svc --")
    info_fields = _class_fields(src, "BestConfigInfo")
    for required in ("min_score", "top_k", "rerank_enabled",
                     "pass_rate", "eval_set_size", "promoted_at_ts"):
        if required not in info_fields:
            print(f"x BestConfigInfo missing {required}")
            return 1
    print("  ok: provenance surface complete")

    print("-- 4. POSITIVE: route exists with correct path + response_model --")
    routes_src = ROUTES.read_text(encoding="utf-8")
    if '"/api/v1/health/best-config"' not in routes_src:
        print("x retrieval-svc must register /api/v1/health/best-config")
        return 1
    if "response_model=HealthBestConfigResponse" not in routes_src:
        print("x route must declare response_model=HealthBestConfigResponse")
        return 1
    print("  ok: route registered")

    print("-- 5. NEGATIVE: handler MUST NOT raise (visibility never crashes) --")
    handler_idx = routes_src.find("async def health_best_config()")
    if handler_idx < 0:
        print("x async def health_best_config() must exist")
        return 1
    handler_end = routes_src.find("def _retriever", handler_idx)
    handler_body = routes_src[handler_idx:handler_end]
    if "try:" not in handler_body:
        print("x handler must wrap loader access in try")
        return 1
    if "except Exception" not in handler_body:
        print("x handler must catch generic Exception")
        return 1
    if "raise" in handler_body and "raise " in handler_body:
        # Only acceptable raise is in 'raise' standalone in a comment.
        # Walk the actual handler ast to be sure.
        # Simpler: forbid raise statements outright.
        for line in handler_body.splitlines():
            stripped = line.strip()
            if stripped.startswith("raise "):
                print(f"x handler must NOT raise: {stripped!r}")
                return 1
    print("  ok: §47 fail-safe — visibility never crashes")

    print("-- 6. NEGATIVE: lazy import (no module-level coupling to best_config_loader) --")
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
    print("  ok: lazy import; no startup coupling")

    print("-- 7. NEGATIVE: service field correctly identifies retrieval-svc --")
    # Cross-service mix-ups happen — the dashboard distinguishes which
    # row is which by the `service` field. If retrieval-svc returns
    # service="inference-svc", operators investigate the wrong service
    # during incidents.
    if 'service="retrieval-svc"' not in handler_body:
        print('x handler must return service="retrieval-svc" (not inference-svc)')
        return 1
    if 'service="inference-svc"' in handler_body:
        print('x handler must NOT return service="inference-svc"')
        return 1
    print("  ok: service identifier correct")

    print("-- 8. NEGATIVE: fallback_defaults match legacy un-tuned behavior --")
    # If the fallback_defaults don't reflect what the retriever ACTUALLY
    # uses without the loader (min_score=0.0, top_k=10, rerank=False),
    # operators investigating "why no chunks?" see misleading data.
    # We assert the loader's surface gives the right defaults; the
    # route just relays them. Verify by importing the loader.
    sys.path.insert(0, str(REPO / "scripts"))
    import importlib  # noqa: PLC0415
    import os as _os  # noqa: PLC0415
    _os.environ["BEST_CONFIG_LOADER_ENABLED"] = "1"
    if "best_config_loader" in sys.modules:
        del sys.modules["best_config_loader"]
    bcl = importlib.import_module("best_config_loader")
    st = bcl.status()
    fb = st["fallback_defaults"]
    if fb["min_score"] != 0.0 or fb["top_k"] != 10 or fb["rerank_enabled"] is not False:
        print(f"x fallback_defaults must be legacy un-tuned; got {fb}")
        return 1
    print(f"  ok: legacy fallbacks min_score=0.0 top_k=10 rerank=False")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
