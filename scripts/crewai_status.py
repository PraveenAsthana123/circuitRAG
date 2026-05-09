#!/usr/bin/env python3
"""CrewAI status gate.

CrewAI is intentionally not the primary DocuMind agent framework. ADR-027
keeps LangGraph + the custom council as the accepted orchestration layer.
This script reports accidental install/import drift without turning CrewAI
into a production dependency.
"""
from __future__ import annotations

import argparse
import importlib
import json
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parent.parent
ADR = REPO / "docs" / "architecture" / "adr" / "027-agent-framework-langgraph-not-crewai-agno.md"
CATALOG = REPO / "config" / "agentic_observability" / "oss_tooling_catalog.yaml"


def _pkg_status() -> dict[str, Any]:
    try:
        ver = version("crewai")
    except PackageNotFoundError:
        ver = None
    try:
        importlib.import_module("crewai")
        return {"installed": ver is not None, "importable": True, "version": ver, "error": ""}
    except Exception as exc:  # noqa: BLE001
        return {
            "installed": ver is not None,
            "importable": False,
            "version": ver,
            "error": f"{type(exc).__name__}: {str(exc)[:240]}",
        }


def _catalog_row() -> dict[str, Any]:
    doc = yaml.safe_load(CATALOG.read_text(encoding="utf-8"))
    for tool in doc.get("tools", []):
        if tool.get("name") == "crewai":
            return tool
    return {}


def status() -> dict[str, Any]:
    row = _catalog_row()
    adr_text = ADR.read_text(encoding="utf-8") if ADR.exists() else ""
    pkg = _pkg_status()
    return {
        "crewai": {
            **pkg,
            "catalog_status": row.get("status"),
            "accepted_primary_framework": False,
            "primary_framework": "langgraph_custom_council",
            "adr": str(ADR.relative_to(REPO)),
            "adr_rejects_crewai": "Reject CrewAI" in adr_text or "CrewAI" in adr_text and "Rejected" in adr_text,
            "ready_for_primary_use": False,
        },
        "recommendation": (
            "Do not promote CrewAI into the request hot path unless ADR-027 is superseded. "
            "Use LangGraph + the custom council for production workflows."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-if-primary-ready", action="store_true")
    args = parser.parse_args()
    payload = status()
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        c = payload["crewai"]
        print(f"CrewAI catalog_status={c['catalog_status']} importable={c['importable']}")
        if c["error"]:
            print(f"CrewAI import error: {c['error']}")
        print(f"Primary framework={c['primary_framework']}")
    return 1 if args.fail_if_primary_ready and payload["crewai"]["ready_for_primary_use"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
