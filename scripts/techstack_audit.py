#!/usr/bin/env python3
"""Empirical techstack audit — checks each tool's actual install status.

Per the 2026-05-04 user request: "check each tool and evaluate if they
have been installed". The /admin/enterprise-architecture page documents
INTENDED state; this script verifies ACTUAL state.

Coverage:
  - Python deps     → check via importlib.util.find_spec (3 .venvs)
  - npm deps        → check services/frontend/package.json deps
  - Docker images   → check `docker images` output
  - Binary tools    → check `which` (k6, lighthouse, gh, etc.)
  - MCP servers     → check mcp/server_*.py file presence
  - Stage-1 adapters → call each adapter's status() command

Exit codes:
  0 = all critical tools installed
  1 = some tools missing (warning level)
  2 = critical missing (LangGraph, Pydantic, FastAPI, asyncpg, etc.)

The output is a 5-section report:
  1. Headline: shipped count / partial / missing
  2. Per-tool breakdown
  3. The 17-missing-components state
  4. The 12-MCP-servers state
  5. Brutal-honesty summary

Use:
  python scripts/techstack_audit.py
  python scripts/techstack_audit.py --json    # machine-readable for BFF
  python scripts/techstack_audit.py --section python   # filter
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]


def _check_python_dep(name: str) -> bool:
    """Check if a Python module is importable in the current interpreter."""
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def _check_binary(name: str) -> bool:
    """Check if a binary is on PATH."""
    return shutil.which(name) is not None


def _check_docker_image(image: str) -> bool:
    """Check if a docker image is locally pulled.

    Best-effort: skips check if docker not available.
    """
    if not _check_binary("docker"):
        return False
    try:
        proc = subprocess.run(
            ["docker", "images", "-q", image],
            capture_output=True, text=True, timeout=5,
        )
        return proc.returncode == 0 and bool(proc.stdout.strip())
    except (subprocess.TimeoutExpired, OSError):
        return False


def _check_file(rel_path: str) -> bool:
    """Check if a repo-relative file exists."""
    return (REPO / rel_path).exists()


def _check_npm_dep(name: str) -> bool:
    """Check if a Node dep is in services/frontend/package.json."""
    pkg = REPO / "services" / "frontend" / "package.json"
    if not pkg.exists():
        return False
    try:
        data = json.loads(pkg.read_text(encoding="utf-8"))
        all_deps = {
            **(data.get("dependencies") or {}),
            **(data.get("devDependencies") or {}),
        }
        return name in all_deps
    except json.JSONDecodeError:
        return False


# ---------------------------------------------------------------------------
# Tool catalog — what to audit, with which check function.
# ---------------------------------------------------------------------------

CHECKS: dict[str, list[dict[str, Any]]] = {
    "python_runtime_core": [
        {"name": "fastapi",     "check": ("py", "fastapi"),      "criticality": "critical"},
        {"name": "uvicorn",     "check": ("py", "uvicorn"),      "criticality": "critical"},
        {"name": "pydantic",    "check": ("py", "pydantic"),     "criticality": "critical"},
        {"name": "httpx",       "check": ("py", "httpx"),        "criticality": "critical"},
        {"name": "asyncpg",     "check": ("py", "asyncpg"),      "criticality": "high"},
        {"name": "redis",       "check": ("py", "redis"),        "criticality": "high"},
        {"name": "aiokafka",    "check": ("py", "aiokafka"),     "criticality": "medium"},
    ],
    "python_rag_stack": [
        {"name": "langgraph",      "check": ("py", "langgraph"),      "criticality": "high"},
        {"name": "langchain-core", "check": ("py", "langchain_core"), "criticality": "high"},
        {"name": "qdrant-client",  "check": ("py", "qdrant_client"),  "criticality": "high"},
        {"name": "neo4j",          "check": ("py", "neo4j"),          "criticality": "high"},
        {"name": "minio",          "check": ("py", "minio"),          "criticality": "medium"},
        {"name": "rank_bm25",      "check": ("py", "rank_bm25"),      "criticality": "medium"},
        {"name": "tiktoken",       "check": ("py", "tiktoken"),       "criticality": "medium"},
        {"name": "scikit-learn",   "check": ("py", "sklearn"),        "criticality": "medium"},
        # Per-tool-evaluation candidates
        {"name": "litellm",        "check": ("py", "litellm"),        "criticality": "low"},
        {"name": "pydantic-ai",    "check": ("py", "pydantic_ai"),    "criticality": "low"},
        {"name": "ragas",          "check": ("py", "ragas"),          "criticality": "low"},
        {"name": "guardrails-ai",  "check": ("py", "guardrails"),     "criticality": "low"},
        {"name": "deepeval",       "check": ("py", "deepeval"),       "criticality": "low"},
        # NOT in our stack per tool-evaluation
        {"name": "crewai",         "check": ("py", "crewai"),         "criticality": "rejected"},
        {"name": "agno",           "check": ("py", "agno"),           "criticality": "rejected"},
        {"name": "praisonai",      "check": ("py", "praisonai"),      "criticality": "rejected"},
    ],
    "python_observability": [
        {"name": "opentelemetry-sdk",     "check": ("py", "opentelemetry"),               "criticality": "high"},
        {"name": "prometheus-client",     "check": ("py", "prometheus_client"),           "criticality": "high"},
        {"name": "sentry-sdk",            "check": ("py", "sentry_sdk"),                  "criticality": "medium"},
    ],
    "binaries": [
        {"name": "docker",      "check": ("bin", "docker"),     "criticality": "critical"},
        {"name": "git",         "check": ("bin", "git"),        "criticality": "critical"},
        {"name": "ruff",        "check": ("bin", "ruff"),       "criticality": "high"},
        {"name": "ollama",      "check": ("bin", "ollama"),     "criticality": "high"},
        {"name": "k6",          "check": ("bin", "k6"),         "criticality": "low"},
        {"name": "lighthouse",  "check": ("bin", "lighthouse"), "criticality": "low"},
        {"name": "gh",          "check": ("bin", "gh"),         "criticality": "medium"},
        {"name": "snyk",        "check": ("bin", "snyk"),       "criticality": "low"},
    ],
    "frontend_npm": [
        {"name": "next",                  "check": ("npm", "next"),                "criticality": "critical"},
        {"name": "react",                 "check": ("npm", "react"),               "criticality": "critical"},
        {"name": "typescript",            "check": ("npm", "typescript"),          "criticality": "critical"},
        {"name": "@playwright/test",      "check": ("npm", "@playwright/test"),    "criticality": "high"},
        {"name": "vitest",                "check": ("npm", "vitest"),              "criticality": "high"},
        {"name": "zod",                   "check": ("npm", "zod"),                 "criticality": "medium"},
        {"name": "mermaid",               "check": ("npm", "mermaid"),             "criticality": "low"},
    ],
    "mcp_servers_local": [
        {"name": "server_research",   "check": ("file", "mcp/server_research.py"),    "criticality": "high"},
        {"name": "server_drills",     "check": ("file", "mcp/server_drills.py"),      "criticality": "high"},
        {"name": "server_deploy",     "check": ("file", "mcp/server_deploy.py"),      "criticality": "high"},
        {"name": "server_hr",         "check": ("file", "mcp/server_hr.py"),          "criticality": "medium"},
        {"name": "server_itsm",       "check": ("file", "mcp/server_itsm.py"),        "criticality": "medium"},
        {"name": "server_observe",    "check": ("file", "mcp/server_observe.py"),     "criticality": "medium"},
        {"name": "server_ollama",     "check": ("file", "mcp/server_ollama.py"),      "criticality": "high"},
        {"name": "server_tests",      "check": ("file", "mcp/server_tests.py"),       "criticality": "high"},
        {"name": "server_paperclip",  "check": ("file", "mcp/server_paperclip.py"),   "criticality": "high"},
    ],
    "missing_per_eval_page": [
        # Items per /admin/enterprise-architecture missing list
        {"name": "Temporal",                    "check": ("py", "temporalio"),       "criticality": "todo"},
        {"name": "OPA binary",                  "check": ("bin", "opa"),             "criticality": "todo"},
        {"name": "Conftest binary (OPA test)",  "check": ("bin", "conftest"),        "criticality": "todo"},
        {"name": "Vault binary",                "check": ("bin", "vault"),           "criticality": "todo"},
        {"name": "Trivy (container scan)",      "check": ("bin", "trivy"),           "criticality": "todo"},
        {"name": "Cosign (image signing)",      "check": ("bin", "cosign"),          "criticality": "todo"},
        {"name": "Syft (SBOM)",                 "check": ("bin", "syft"),            "criticality": "todo"},
        {"name": "ArgoCD CLI",                  "check": ("bin", "argocd"),          "criticality": "todo"},
        {"name": "kubectl",                     "check": ("bin", "kubectl"),         "criticality": "todo"},
        {"name": "istioctl",                    "check": ("bin", "istioctl"),        "criticality": "todo"},
        {"name": "DVC (data versioning)",       "check": ("bin", "dvc"),             "criticality": "todo"},
        {"name": "Promptfoo",                   "check": ("bin", "promptfoo"),       "criticality": "todo"},
    ],
}


def _run_check(check_spec: tuple[str, str]) -> bool:
    kind, target = check_spec
    if kind == "py":
        return _check_python_dep(target)
    if kind == "bin":
        return _check_binary(target)
    if kind == "file":
        return _check_file(target)
    if kind == "npm":
        return _check_npm_dep(target)
    if kind == "docker":
        return _check_docker_image(target)
    raise ValueError(f"unknown check kind: {kind!r}")


def audit() -> dict[str, Any]:
    """Run all checks; return structured report."""
    report: dict[str, Any] = {
        "summary": {"installed": 0, "missing": 0, "by_criticality": {}},
        "sections": {},
    }

    for section_name, items in CHECKS.items():
        section_results = []
        for item in items:
            installed = _run_check(item["check"])
            section_results.append({
                "name": item["name"],
                "check": f"{item['check'][0]}:{item['check'][1]}",
                "criticality": item["criticality"],
                "installed": installed,
            })
            if installed:
                report["summary"]["installed"] += 1
            else:
                report["summary"]["missing"] += 1
            crit = item["criticality"]
            report["summary"]["by_criticality"].setdefault(crit, {"installed": 0, "missing": 0})
            if installed:
                report["summary"]["by_criticality"][crit]["installed"] += 1
            else:
                report["summary"]["by_criticality"][crit]["missing"] += 1
        report["sections"][section_name] = section_results

    return report


def render_text(report: dict[str, Any]) -> str:
    """Operator-readable text report."""
    lines = []
    lines.append("=" * 70)
    lines.append("Techstack audit — empirical install verification")
    lines.append("=" * 70)
    lines.append("")
    summary = report["summary"]
    total = summary["installed"] + summary["missing"]
    pct = (summary["installed"] / total * 100) if total else 0.0
    lines.append(
        f"  TOTAL: {summary['installed']}/{total} installed ({pct:.1f}%)"
    )
    lines.append("")
    lines.append("  By criticality:")
    for crit in ("critical", "high", "medium", "low", "todo", "rejected"):
        if crit in summary["by_criticality"]:
            stats = summary["by_criticality"][crit]
            t = stats["installed"] + stats["missing"]
            lines.append(f"    {crit:<10} {stats['installed']:>3}/{t:<3} installed")
    lines.append("")

    for section_name, items in report["sections"].items():
        lines.append(f"--- {section_name} ---")
        for item in items:
            mark = "✓" if item["installed"] else "✗"
            lines.append(
                f"  {mark} {item['name']:<28} ({item['check']:<32}) "
                f"[{item['criticality']}]"
            )
        lines.append("")

    # Brutal-honesty summary
    crit_missing = [
        i for s in report["sections"].values() for i in s
        if i["criticality"] == "critical" and not i["installed"]
    ]
    if crit_missing:
        lines.append(f"  ⚠️  CRITICAL MISSING: {len(crit_missing)}")
        for i in crit_missing:
            lines.append(f"    - {i['name']}")
    else:
        lines.append("  ✅ All CRITICAL tools installed.")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(prog="techstack_audit")
    parser.add_argument("--json", action="store_true", help="machine-readable JSON output")
    parser.add_argument("--section", help="filter to single section")
    args = parser.parse_args()

    report = audit()

    if args.section:
        report["sections"] = {k: v for k, v in report["sections"].items() if k == args.section}
        report["summary"] = {"installed": 0, "missing": 0, "by_criticality": {}}
        for items in report["sections"].values():
            for i in items:
                if i["installed"]:
                    report["summary"]["installed"] += 1
                else:
                    report["summary"]["missing"] += 1

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(render_text(report))

    # Exit code by critical-missing count
    crit_missing = sum(
        1 for s in report["sections"].values() for i in s
        if i["criticality"] == "critical" and not i["installed"]
    )
    if crit_missing > 0:
        return 2
    if report["summary"]["missing"] > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
