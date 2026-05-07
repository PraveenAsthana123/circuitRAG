"""Generate config/tool_catalog/<ns>.yaml for every MCP server (iter-80).

Per CLAUDE.md §44 (iter-80), §52 (brutal tool review), §57.4
(self-healing as data not code), §47.6 (default-deny).

For every `mcp/server_<ns>.py` that lacks a catalog entry, generate a
best-effort 9-axis YAML by:

1. Importing/parsing the source for `TOOLS = [...]` to enumerate tools
2. Reading first-line + module docstring for the description
3. Filling in fallback / monitoring / observability / policy / runbook
   from canonical templates parameterised by namespace
4. Validating the entry against `scripts/tool_catalog.validate_entry`
   before writing — never ship invalid YAML

The script is idempotent: re-runs skip namespaces that already have a
hand-written or generated entry. Use `--force` to overwrite.

CLI
---
$ python3 scripts/generate_tool_catalog_entries.py            # generate missing
$ python3 scripts/generate_tool_catalog_entries.py --dry-run  # show what would change
$ python3 scripts/generate_tool_catalog_entries.py --only aws # one namespace
$ python3 scripts/generate_tool_catalog_entries.py --force    # overwrite existing
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
MCP_DIR = REPO / "mcp"
CATALOG_DIR = REPO / "config" / "tool_catalog"

sys.path.insert(0, str(REPO / "scripts"))
import tool_catalog as tc  # type: ignore[import-not-found]

# Manual classification — what each server's status_target + owner is.
# Defaults applied for namespaces not listed.
NS_PROFILES: dict[str, dict[str, Any]] = {
    # SDLC stack
    "github": {"status_target": "WORKING", "owner": "platform-sdlc"},
    "github_actions": {"status_target": "OPTIONAL", "owner": "platform-sdlc"},
    "gitlab": {"status_target": "OPTIONAL", "owner": "platform-sdlc"},
    "sonarqube": {"status_target": "OPTIONAL", "owner": "platform-sdlc"},
    "kubectl": {"status_target": "OPTIONAL", "owner": "platform-infra"},
    # Observability
    "datadog": {"status_target": "OPTIONAL", "owner": "platform-observability"},
    "sentry": {"status_target": "OPTIONAL", "owner": "platform-observability"},
    "pagerduty": {"status_target": "OPTIONAL", "owner": "platform-observability"},
    "observe": {"status_target": "WORKING", "owner": "platform-observability"},
    # Cloud
    "aws": {"status_target": "OPTIONAL", "owner": "platform-cloud"},
    "gcp": {"status_target": "OPTIONAL", "owner": "platform-cloud"},
    "azure": {"status_target": "OPTIONAL", "owner": "platform-cloud"},
    # Comms
    "slack": {"status_target": "OPTIONAL", "owner": "platform-comms"},
    "teams": {"status_target": "OPTIONAL", "owner": "platform-comms"},
    "whatsapp": {"status_target": "OPTIONAL", "owner": "platform-comms"},
    # Knowledge / docs
    "confluence": {"status_target": "OPTIONAL", "owner": "platform-knowledge"},
    "gdrive": {"status_target": "OPTIONAL", "owner": "platform-knowledge"},
    # ITSM
    "jira": {"status_target": "OPTIONAL", "owner": "platform-itsm"},
    "servicenow": {"status_target": "OPTIONAL", "owner": "platform-itsm"},
    "itsm": {"status_target": "WORKING", "owner": "platform-itsm"},
    # HR
    "hr": {"status_target": "WORKING", "owner": "platform-hr"},
    # Data / docs / ingest
    "documents": {"status_target": "WORKING", "owner": "platform-data"},
    "csv_ingest": {"status_target": "WORKING", "owner": "platform-data"},
    # Engine
    "deploy": {"status_target": "WORKING", "owner": "platform-deploy"},
    "tests": {"status_target": "WORKING", "owner": "platform-qa"},
    "drills": {"status_target": "WORKING", "owner": "platform-qa"},
    "research": {"status_target": "WORKING", "owner": "platform-research"},
    "ollama": {"status_target": "WORKING", "owner": "platform-ai"},
    "paperclip": {"status_target": "WORKING", "owner": "platform-ai"},
}

DEFAULT_PROFILE = {"status_target": "OPTIONAL", "owner": "platform-misc"}


def parse_tools_from_source(src: str, ns: str) -> list[dict[str, Any]]:
    """Best-effort regex extraction of TOOLS list — name + side_effects."""
    tools: list[dict[str, Any]] = []
    # Capture each {"name": "<ns>.<x>", ..., "side_effects": "<read|write>", ...}
    pattern = re.compile(
        r'\{\s*"name":\s*"(' + re.escape(ns) + r'\.[a-z0-9_]+)"'
        r'(?:[^{}]|\{[^{}]*\})*?'
        r'"side_effects":\s*"(read|write)"',
        re.DOTALL,
    )
    for m in pattern.finditer(src):
        tools.append({
            "tool": m.group(1),
            "side_effects": m.group(2),
        })

    # Fallback: just match name keys; default side_effects to read
    if not tools:
        for m in re.finditer(
            r'"name":\s*"(' + re.escape(ns) + r'\.[a-z0-9_]+)"', src
        ):
            tools.append({"tool": m.group(1), "side_effects": "read"})

    # Dedupe preserving order
    seen = set()
    out = []
    for t in tools:
        if t["tool"] not in seen:
            seen.add(t["tool"])
            out.append(t)
    return out


def render_entry(ns: str, server_path: Path) -> dict[str, Any]:
    src = server_path.read_text(encoding="utf-8")
    profile = NS_PROFILES.get(ns, DEFAULT_PROFILE)
    tools = parse_tools_from_source(src, ns)

    if not tools:
        # Surface the issue rather than emit invalid YAML
        raise ValueError(
            f"no tools found in {server_path} for namespace {ns!r} — "
            f"check TOOLS list shape"
        )

    # Pick the project's drill matching the namespace if it exists
    drill_candidates = [
        f"mcp/tests/drill_mcp_server_{ns}.py",
        f"mcp/tests/drill_mcp_{ns}_server.py",
        f"mcp/tests/drill_mcp_{ns}.py",
        # SDLC and SaaS batch drills cover multiple namespaces
        "mcp/tests/drill_mcp_sdlc_servers.py",
        "mcp/tests/drill_mcp_saas_servers.py",
    ]
    drill_path = next(
        (p for p in drill_candidates if (REPO / p).exists()),
        "mcp/tests/drill_mcp_sdlc_servers.py",  # default
    )

    io_entries = []
    for t in tools:
        io_entries.append({
            "tool": t["tool"],
            "input_schema_ref": f"{t['tool'].replace('.', '_').title().replace('_', '')}Input",
            "process": (
                f"1. Validate input via _validate_query (regex + length cap).\n"
                f"2. _live_or_stub guard: return available:False if creds missing.\n"
                f"3. Issue upstream call via _live_or_stub HTTP path.\n"
                f"4. Map response to canonical output schema.\n"
                f"5. Emit OTel span mcp.{ns}.{t['tool'].split('.', 1)[1]} + Prom counter."
            ),
            "output_schema_ref": f"{t['tool'].replace('.', '_').title().replace('_', '')}Output",
            "side_effects": t["side_effects"],
            "avg_latency_ms": 300,
            "p95_latency_ms": 1200,
            "cost_per_call_usd": 0.0,
        })

    has_writes = any(t["side_effects"] == "write" for t in tools)

    entry: dict[str, Any] = {
        "namespace": ns,
        "status_target": profile["status_target"],
        "owner": profile["owner"],
        "fallback": {
            "on_unreachable": (
                f"skip {ns} lookups; agent uses cached context if any; "
                f"council notes '{ns} unavailable'"
            ),
            "on_failing": (
                f"circuit-break 60s after 3 consecutive failures; "
                f"emit {ns}_circuit_open metric; alert P{2 if has_writes else 3}"
            ),
            "on_not_installed": (
                f"feature flag off (DOCUMIND_MCP_{ns.upper()}_URL unset); "
                f"UI hides {ns} namespace"
            ),
        },
        "io": io_entries,
        "integration": {
            "upstream": ["inference-svc", "agent-orchestrator-svc"],
            "downstream": [],
            "contracts": [
                {"producer": "inference-svc", "consumer": ns, "schema": "McpToolCallRequest"},
            ],
        },
        "testing": {
            "drill": drill_path,
            "smoke_cmd": f"curl -s $DOCUMIND_MCP_{ns.upper()}_URL/health",
            "cadence": "iter",
            "scheduled_via": "scripts/run_drills.py",
        },
        "monitoring": {
            "metrics": [
                {
                    "name": f"mcp_{ns}_requests_total",
                    "type": "counter",
                    "alert_at": "informational",
                },
                {
                    "name": f"mcp_{ns}_request_duration_seconds",
                    "type": "histogram",
                    "alert_at": "p95 > 2s for 5m",
                },
                {
                    "name": f"mcp_{ns}_circuit_open",
                    "type": "gauge",
                    "alert_at": "value == 1 for 5m",
                },
            ],
            "alerts": [
                {
                    "name": f"{ns.title().replace('_', '')}CircuitOpen",
                    "severity": "P2" if has_writes else "P3",
                    "route": f"#oncall-{profile['owner']}",
                },
            ],
        },
        "visualization": {
            "ui_page": "/admin/mcp-fleet-health",
            "embed_in": ["/admin/dashboard", "/admin/mcp-fleet-health"],
            "panels": ["status", "latency_p95", "error_rate", "qps"],
        },
        "policy": {
            "opa_bundle": "config/policies/agent_dispatch.rego",
            "rules": [f"council-{ns}-{t['side_effects']}" for t in tools],
            "default": "deny",
        },
        "observability": {
            "otel": {
                "span_name": f"mcp.{ns}.tools_call",
                "attrs": ["tenant_id", "request_id", "scopes_granted", "tool_name"],
            },
            "jaeger": {
                "query_template": f"service=mcp-{ns}&operation=mcp.{ns}.tools_call",
            },
            "kibana": {
                "index": "filebeat-mcp-*",
                "query_template": (
                    f"kubernetes.labels.app:mcp-{ns} AND request_id:{{request_id}}"
                ),
            },
            "log_fields": [
                "request_id", "tenant_id", "actor", "tool",
                "latency_ms", "outcome",
            ],
        },
        "runbook": f"ops/runbook/{ns}.md",
    }
    return entry


def emit_yaml(entry: dict[str, Any]) -> str:
    """Hand-rolled YAML emitter matching the existing entries' style."""
    import yaml  # type: ignore[import-not-found]
    return yaml.safe_dump(entry, sort_keys=False, default_flow_style=False, width=120)


def list_servers() -> list[tuple[str, Path]]:
    out = []
    for f in sorted(MCP_DIR.glob("server_*.py")):
        if f.stem in ("server_common",):
            continue
        ns = f.stem.replace("server_", "")
        out.append((ns, f))
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true", help="show changes only")
    p.add_argument("--force", action="store_true", help="overwrite existing entries")
    p.add_argument("--only", help="generate only this namespace")
    args = p.parse_args()

    servers = list_servers()
    if args.only:
        servers = [(ns, p) for ns, p in servers if ns == args.only]
        if not servers:
            print(f"no server matches --only={args.only!r}", file=sys.stderr)
            return 2

    CATALOG_DIR.mkdir(parents=True, exist_ok=True)
    written = 0
    skipped = 0
    failed: list[tuple[str, str]] = []

    for ns, path in servers:
        out_path = CATALOG_DIR / f"{ns}.yaml"
        if out_path.exists() and not args.force:
            skipped += 1
            continue
        try:
            entry = render_entry(ns, path)
        except Exception as e:  # noqa: BLE001
            failed.append((ns, str(e)))
            print(f"  ✗ {ns:<24} render failed: {e}", file=sys.stderr)
            continue

        # Validate before writing
        errors = tc.validate_entry(entry)
        if errors:
            failed.append((ns, f"validation errors: {errors}"))
            print(f"  ✗ {ns:<24} validation failed: {errors[:2]}", file=sys.stderr)
            continue

        if args.dry_run:
            print(f"  [dry-run] would write {out_path.relative_to(REPO)}")
        else:
            out_path.write_text(emit_yaml(entry), encoding="utf-8")
            print(f"  ✓ wrote {out_path.relative_to(REPO)} ({len(entry['io'])} tools)")
        written += 1

    print(
        f"\nResult: {written} written / {skipped} skipped / "
        f"{len(failed)} failed across {len(servers)} servers"
    )
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
