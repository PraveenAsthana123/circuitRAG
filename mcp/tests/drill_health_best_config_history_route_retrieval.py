#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: /api/v1/health/best-config-history on retrieval-svc (per §38 + §43).

Mirrors drill_health_best_config_history_route.py — both services
surface the SAME audit trail. Shape parity locked.

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
    print("-- 1. POSITIVE: retrieval-svc declares HealthBestConfigHistoryResponse --")
    src = SCHEMAS.read_text(encoding="utf-8")
    if "class HealthBestConfigHistoryResponse(BaseModel):" not in src:
        print("x retrieval-svc must declare HealthBestConfigHistoryResponse")
        return 1
    print("  ok: schema declared")

    print("-- 2. NEGATIVE: shape parity with inference-svc HealthBestConfigHistoryResponse --")
    inf_src = INF_SCHEMAS.read_text(encoding="utf-8")
    inf_fields = _class_fields(inf_src, "HealthBestConfigHistoryResponse")
    ret_fields = _class_fields(src, "HealthBestConfigHistoryResponse")
    missing = inf_fields - ret_fields
    if missing:
        print(f"x retrieval-svc HealthBestConfigHistoryResponse missing: {sorted(missing)}")
        return 1
    print(f"  ok: shape parity ({len(inf_fields)} fields)")

    print("-- 3. POSITIVE: route exists on retrieval-svc --")
    routes_src = ROUTES.read_text(encoding="utf-8")
    if '"/api/v1/health/best-config-history"' not in routes_src:
        print("x retrieval-svc must register /api/v1/health/best-config-history")
        return 1
    if "response_model=HealthBestConfigHistoryResponse" not in routes_src:
        print("x route must declare response_model=HealthBestConfigHistoryResponse")
        return 1
    print("  ok: route registered")

    print("-- 4. NEGATIVE: handler MUST NOT raise (visibility never crashes) --")
    handler_idx = routes_src.find("async def health_best_config_history(")
    if handler_idx < 0:
        print("x async def health_best_config_history must exist")
        return 1
    handler_end = routes_src.find("def _retriever", handler_idx)
    handler_body = routes_src[handler_idx:handler_end]
    if "try:" not in handler_body:
        print("x handler must wrap reader call in try/except")
        return 1
    if "except Exception" not in handler_body:
        print("x handler must catch generic Exception")
        return 1
    for line in handler_body.splitlines():
        stripped = line.strip()
        if stripped.startswith("raise "):
            print(f"x handler must NOT raise: {stripped!r}")
            return 1
    print("  ok: §47 fail-safe — visibility never crashes")

    print("-- 5. NEGATIVE: lazy import of best_config_history (no startup coupling) --")
    tree_routes = ast.parse(routes_src)
    for node in tree_routes.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            mod = getattr(node, "module", None) or ""
            names = [a.name for a in getattr(node, "names", [])]
            if mod == "best_config_history" or "best_config_history" in names:
                print("x best_config_history must NOT be imported at module level")
                return 1
    if "from best_config_history import" not in handler_body:
        print("x handler must lazy-import from best_config_history")
        return 1
    print("  ok: lazy import")

    print("-- 6. NEGATIVE: service field correctly identifies retrieval-svc --")
    if 'service="retrieval-svc"' not in handler_body:
        print('x handler must return service="retrieval-svc"')
        return 1
    if 'service="inference-svc"' in handler_body:
        print('x handler must NOT return service="inference-svc"')
        return 1
    print("  ok: service identifier correct")

    print("-- 7. NEGATIVE: days param bounded [-1, 365] (DoS guard) --")
    if "ge=-1" not in handler_body:
        print("x days param must allow -1 (all rows)")
        return 1
    if "le=365" not in handler_body:
        print("x days param must cap at 365")
        return 1
    print("  ok: days bounded")

    print("-- 8. POSITIVE: handler threads summarize() output into response --")
    for getter in ("summary.total_attempts", "summary.promoted",
                   "summary.rejected", "summary.skipped",
                   "summary.gates_failed_counts", "summary.latest_decision"):
        if getter not in handler_body:
            print(f"x handler must read {getter}")
            return 1
    print("  ok: summarize() output threaded")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
