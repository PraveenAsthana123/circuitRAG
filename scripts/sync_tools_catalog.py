#!/usr/bin/env python3
"""Sync MCP server TOOLS lists into governance.tools.

Per CLAUDE.md §47.7 migrate-phase. Iter 9 (commit 5189b2e) created
governance.tools as the SQL catalog. This module is the migrate-phase
counterpart: when MCP_TOOLS_SYNC_ENABLED=1, walks the mcp/server_*.py
files, extracts each module's TOOLS list, and upserts into
governance.tools.

Per §38 governance + §43 drill discipline:
  - Server-source-of-truth remains the Python TOOLS literal
  - SQL catalog is a queryable mirror
  - Sync is idempotent (UPSERT on (server, name))
  - Risk derivation is deterministic (side_effects → risk_level)
  - Failure on one tool doesn't block the rest

Drilled by mcp/tests/drill_tools_catalog_sync.py.

Usage:
    # Dry-run (no SQL writes; prints what would change)
    python3 scripts/sync_tools_catalog.py --dry-run

    # Actual sync (requires MCP_TOOLS_SYNC_ENABLED=1 + Postgres)
    MCP_TOOLS_SYNC_ENABLED=1 python3 scripts/sync_tools_catalog.py

    # Sync from a specific module list (used in drills)
    python3 scripts/sync_tools_catalog.py --module mcp.server_paperclip
"""
from __future__ import annotations

import argparse
import importlib
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
MCP_DIR = REPO / "mcp"

log = logging.getLogger(__name__)

# side_effects → risk_level mapping. Drilled in
# drill_tools_catalog_sync.py to ensure operators don't accidentally
# downgrade a destructive tool to low risk.
SIDE_EFFECTS_TO_RISK: dict[str, str] = {
    "read": "low",
    "write": "medium",
    "external": "medium",
    "destructive": "high",
}

# side_effects → approval_required default. Operators can override
# the SQL row directly if a tool's risk profile differs from the
# default (e.g. a "write" tool that's actually low-risk).
SIDE_EFFECTS_TO_APPROVAL: dict[str, bool] = {
    "read": False,
    "write": True,
    "external": False,
    "destructive": True,
}


def _list_server_modules() -> list[str]:
    """Return the dotted module names of all mcp/server_*.py files."""
    modules: list[str] = []
    for p in sorted(MCP_DIR.glob("server_*.py")):
        if p.stem == "server_common":
            continue  # shared helpers; no TOOLS list
        modules.append(f"mcp.{p.stem}")
    return modules


def _server_name_from_module(module_name: str) -> str:
    """Extract the short server name from a module path.

    'mcp.server_paperclip' → 'paperclip'
    'mcp.server_drills'    → 'drills'
    """
    short = module_name.rsplit(".", 1)[-1]
    if short.startswith("server_"):
        return short[len("server_"):]
    return short


def _extract_tools(module_name: str) -> list[dict[str, Any]]:
    """Import module, return its TOOLS list. [] if absent."""
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    try:
        mod = importlib.import_module(module_name)
    except Exception as exc:  # noqa: BLE001
        log.warning("sync_skip_module=%s err=%s", module_name, type(exc).__name__)
        return []
    tools = getattr(mod, "TOOLS", None)
    if not isinstance(tools, list):
        return []
    return tools


def _normalize_record(server: str, tool: dict[str, Any]) -> dict[str, Any] | None:
    """Map a Python TOOLS record to the governance.tools row shape.

    Returns None when the tool is malformed (missing name) — drill
    verifies these are skipped, not crashed.
    """
    name = tool.get("name")
    if not name or not isinstance(name, str):
        return None
    side_effects = str(tool.get("side_effects", "read")).lower()
    if side_effects not in SIDE_EFFECTS_TO_RISK:
        side_effects = "read"  # safe default; drilled

    return {
        "server": server,
        "name": name,
        "description": str(tool.get("description", ""))[:2000],
        "input_schema": tool.get("input_schema") or {},
        "output_schema": tool.get("output_schema") or {},
        "side_effects": side_effects,
        "required_scopes": list(tool.get("required_scopes") or []),
        "idempotent": bool(tool.get("idempotent", False)),
        "risk_level": SIDE_EFFECTS_TO_RISK[side_effects],
        "approval_required": SIDE_EFFECTS_TO_APPROVAL[side_effects],
    }


async def _upsert_one(conn: Any, rec: dict[str, Any]) -> None:
    await conn.execute(
        "INSERT INTO governance.tools "
        "(server, name, description, input_schema, output_schema, "
        " side_effects, required_scopes, idempotent, risk_level, "
        " approval_required, owner_team) "
        "VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, $6, $7, $8, $9, $10, "
        " 'mcp-sync') "
        "ON CONFLICT (server, name) DO UPDATE SET "
        "  description = EXCLUDED.description, "
        "  input_schema = EXCLUDED.input_schema, "
        "  output_schema = EXCLUDED.output_schema, "
        "  side_effects = EXCLUDED.side_effects, "
        "  required_scopes = EXCLUDED.required_scopes, "
        "  idempotent = EXCLUDED.idempotent, "
        "  risk_level = EXCLUDED.risk_level, "
        "  approval_required = EXCLUDED.approval_required, "
        "  updated_at = NOW()",
        rec["server"], rec["name"], rec["description"],
        json.dumps(rec["input_schema"]),
        json.dumps(rec["output_schema"]),
        rec["side_effects"],
        rec["required_scopes"],
        rec["idempotent"],
        rec["risk_level"],
        rec["approval_required"],
    )


def sync_tools(
    *,
    dry_run: bool = False,
    only_module: str | None = None,
) -> dict[str, Any]:
    """Walk MCP server modules, extract TOOLS, upsert into governance.tools.

    Returns a summary dict. Per §47.7 migrate-phase, this NEVER changes
    the Python TOOLS literals — those remain authoritative. The SQL
    catalog is the queryable mirror.
    """
    summary: dict[str, Any] = {
        "modules_scanned": 0,
        "tools_total": 0,
        "tools_synced": 0,
        "tools_skipped_malformed": 0,
        "errors": [],
        "by_server": {},
        "dry_run": dry_run,
    }

    modules = [only_module] if only_module else _list_server_modules()
    summary["modules_scanned"] = len(modules)

    records: list[dict[str, Any]] = []
    for module_name in modules:
        server = _server_name_from_module(module_name)
        tools = _extract_tools(module_name)
        for raw in tools:
            summary["tools_total"] += 1
            rec = _normalize_record(server, raw)
            if rec is None:
                summary["tools_skipped_malformed"] += 1
                continue
            records.append(rec)
            summary["by_server"][server] = summary["by_server"].get(server, 0) + 1

    if dry_run:
        summary["tools_synced"] = len(records)
        return summary

    # Real sync — async asyncpg upsert with tenant context
    try:
        import asyncio

        import asyncpg
    except ImportError:
        summary["errors"].append("asyncpg not installed")
        return summary

    pg_host = os.getenv("DOCUMIND_PG_HOST", "localhost")
    pg_port = int(os.getenv("DOCUMIND_PG_PORT", "55432"))
    pg_user = os.getenv("DOCUMIND_PG_USER", "documind_app")
    pg_password = os.getenv("DOCUMIND_PG_PASSWORD", "documind_app")
    pg_db = os.getenv("DOCUMIND_PG_DB", "documind")

    async def _run() -> None:
        conn = await asyncpg.connect(
            host=pg_host, port=pg_port, user=pg_user,
            password=pg_password, database=pg_db, timeout=3.0,
        )
        try:
            for rec in records:
                try:
                    await _upsert_one(conn, rec)
                    summary["tools_synced"] += 1
                except Exception as exc:  # noqa: BLE001 - per-tool tolerance
                    summary["errors"].append(
                        f"{rec['server']}.{rec['name']}: {type(exc).__name__}"
                    )
                    log.warning("tool_sync_failed server=%s name=%s err=%s",
                                rec["server"], rec["name"], exc)
        finally:
            await conn.close()

    try:
        asyncio.run(_run())
    except Exception as exc:  # noqa: BLE001
        summary["errors"].append(f"connection_failed: {type(exc).__name__}")
        log.warning("sync_tools_failed err=%s", exc)

    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="Report what would be synced; no SQL writes")
    parser.add_argument("--module", type=str, default=None,
                        help="Sync only this module (e.g. 'mcp.server_paperclip')")
    parser.add_argument("--require-flag", action="store_true", default=True,
                        help="Require MCP_TOOLS_SYNC_ENABLED=1 (default)")
    args = parser.parse_args()

    if (
        not args.dry_run
        and args.require_flag
        and os.getenv("MCP_TOOLS_SYNC_ENABLED", "").strip() != "1"
    ):
        print(
            "MCP_TOOLS_SYNC_ENABLED is unset; refusing actual sync. "
            "Use --dry-run to preview, OR export MCP_TOOLS_SYNC_ENABLED=1.",
            file=sys.stderr,
        )
        return 2

    summary = sync_tools(dry_run=args.dry_run, only_module=args.module)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if not summary["errors"] else 1


if __name__ == "__main__":
    sys.exit(main())
