#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: /api/v1/health/best-config-history (per §38 + §43 + §51).

Locks the route that surfaces the .loop/best_config_history.jsonl
audit trail summary to the operator dashboard. Composes the
best_config_history reader (commit b6a6fcf) over HTTP.

Eight steps. Six negative.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ROUTES = REPO / "services" / "inference-svc" / "app" / "routers" / "__init__.py"
SCHEMAS = REPO / "services" / "inference-svc" / "app" / "schemas" / "__init__.py"


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
    print("-- 1. POSITIVE: HealthBestConfigHistoryResponse schema declared --")
    src = SCHEMAS.read_text(encoding="utf-8")
    if "class HealthBestConfigHistoryResponse(BaseModel):" not in src:
        print("x HealthBestConfigHistoryResponse must be declared")
        return 1
    print("  ok: schema declared")

    print("-- 2. NEGATIVE: required visibility fields prevent half-rendered UI --")
    fields = _class_fields(src, "HealthBestConfigHistoryResponse")
    for required in ("enabled", "history_path", "history_exists",
                     "window_days", "total_attempts", "promoted",
                     "rejected", "skipped", "gates_failed_counts",
                     "latest_decision"):
        if required not in fields:
            print(f"x HealthBestConfigHistoryResponse missing field: {required}")
            return 1
    print(f"  ok: {len(fields)} fields declared; all required present")

    print("-- 3. POSITIVE: route registered with correct path + response_model --")
    routes_src = ROUTES.read_text(encoding="utf-8")
    if '"/api/v1/health/best-config-history"' not in routes_src:
        print("x route must register /api/v1/health/best-config-history")
        return 1
    if "response_model=HealthBestConfigHistoryResponse" not in routes_src:
        print("x route must declare response_model=HealthBestConfigHistoryResponse")
        return 1
    print("  ok: route registered")

    print("-- 4. NEGATIVE: handler accepts `days` query param with safe bounds --")
    handler_idx = routes_src.find("async def health_best_config_history(")
    if handler_idx < 0:
        print("x async def health_best_config_history must exist")
        return 1
    handler_end = routes_src.find("@router.get(", handler_idx + 100)
    handler_body = routes_src[handler_idx:handler_end]
    if "days: int = Query(" not in handler_body:
        print("x handler must accept days as Query param")
        return 1
    if "ge=-1" not in handler_body:
        print("x days param must allow -1 (all rows)")
        return 1
    if "le=365" not in handler_body:
        print("x days param must cap at 365 (DoS guard)")
        return 1
    print("  ok: days param bounded [-1, 365]")

    print("-- 5. NEGATIVE: handler MUST NOT raise (visibility never crashes) --")
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

    print("-- 6. NEGATIVE: lazy import (no module-level coupling) --")
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
    print("  ok: lazy import inside handler")

    print("-- 7. NEGATIVE: handler resolves summary fields from summarize() return --")
    # The handler must threading summarize().total_attempts / promoted /
    # rejected / skipped into the response. If it just returned zeros,
    # the dashboard would show empty.
    for getter in ("summary.total_attempts", "summary.promoted",
                   "summary.rejected", "summary.skipped",
                   "summary.gates_failed_counts", "summary.latest_decision"):
        if getter not in handler_body:
            print(f"x handler must read {getter} from summarize() return")
            return 1
    print("  ok: handler threads summarize() output into response")

    print("-- 8. POSITIVE: schema is additive — does NOT break HealthBestConfigResponse --")
    # Adding the new schema must not have removed/renamed the existing
    # HealthBestConfigResponse fields (regression guard).
    bc_fields = _class_fields(src, "HealthBestConfigResponse")
    for required in ("enabled", "loaded", "config_path", "fallback_defaults",
                     "config", "next_stage"):
        if required not in bc_fields:
            print(f"x HealthBestConfigResponse REGRESSION: lost field {required}")
            return 1
    print(f"  ok: HealthBestConfigResponse intact ({len(bc_fields)} fields)")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
