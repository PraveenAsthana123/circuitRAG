#!/usr/bin/env python3
"""Build 11 MCP server stubs (P1+P2+P3 SDLC batch) from one config map.

Per CLAUDE.md §44 (autonomous-loop iter-71; user asked to set up
slack/github_actions/sonarqube/sentry/pagerduty/kubectl/confluence/
datadog/aws/gcp/azure), §47 (each server owns ONE namespace), §47.6
(read-only Stage-1; write surfaces deferred to per-server ADRs).

This script is the iter-67/iter-68 pattern compressed into a single
config-driven builder. Each server gets:
  - 2 read-only tools (the most-common queries for that namespace)
  - _live_or_stub pattern (env-driven; available:False shape on missing creds)
  - Standard /health + /tools/list + /tools/call routes
  - Same input validators (regex + length cap on query strings)
  - Drilled by mcp/tests/drill_mcp_sdlc_servers.py (unified)

Idempotent. Writes only when target file missing OR --force.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# Config map — per-server tool definitions + env keys.
# Each entry produces one mcp/server_<ns>.py file with 2 read tools.
SERVERS: dict[str, dict] = {
    # P1 — SDLC critical
    "slack": {
        "title": "Slack",
        "log_name": "slack",
        "scope": "slack:read",
        "env_keys": ("SLACK_BOT_TOKEN",),
        "tools": (
            ("channel_list", "List channels in the configured workspace."),
            ("message_search", "Search Slack messages by query (read-only)."),
        ),
        "note": "Sending Slack messages is externally-visible and consent-regulated; needs separate ADR.",
    },
    "github_actions": {
        "title": "GitHub Actions",
        "log_name": "github_actions",
        "scope": "github_actions:read",
        "env_keys": ("GITHUB_TOKEN",),
        "tools": (
            ("workflow_run_get", "Get a single workflow run by id."),
            ("workflow_run_search", "Search workflow runs by status/branch/event."),
        ),
        "note": "Re-running workflows is a write operation; deferred to a write-surface ADR.",
    },
    "sonarqube": {
        "title": "SonarQube",
        "log_name": "sonarqube",
        "scope": "sonarqube:read",
        "env_keys": ("SONAR_HOST_URL", "SONAR_TOKEN"),
        "tools": (
            ("issues_search", "Search code-quality issues by project/severity/type."),
            ("measures_get", "Get project measures (coverage, duplications, debt)."),
        ),
        "note": "Quality-gate writes (mark issue resolved/false-positive) are write surface.",
    },
    # P2 — ops + knowledge
    "sentry": {
        "title": "Sentry",
        "log_name": "sentry",
        "scope": "sentry:read",
        "env_keys": ("SENTRY_AUTH_TOKEN", "SENTRY_ORG"),
        "tools": (
            ("issue_search", "Search Sentry issues by project/level/status."),
            ("event_lookup", "Look up a single event by event_id."),
        ),
        "note": "Resolving/ignoring issues is write surface; deferred.",
    },
    "pagerduty": {
        "title": "PagerDuty",
        "log_name": "pagerduty",
        "scope": "pagerduty:read",
        "env_keys": ("PAGERDUTY_API_KEY",),
        "tools": (
            ("incident_lookup", "Look up an incident by id."),
            ("oncall_get", "Get current on-call schedule for a team."),
        ),
        "note": "Acknowledging/triggering incidents is write surface; deferred.",
    },
    "kubectl": {
        "title": "Kubernetes",
        "log_name": "kubectl",
        "scope": "kubectl:read",
        "env_keys": ("KUBECONFIG",),
        "tools": (
            ("pod_describe", "Describe a pod by namespace/name."),
            ("event_search", "Search recent k8s events by namespace/type."),
        ),
        "note": "kubectl apply / delete are destructive; need separate ADR + approval gate.",
    },
    "confluence": {
        "title": "Confluence",
        "log_name": "confluence",
        "scope": "confluence:read",
        "env_keys": ("CONFLUENCE_BASE_URL", "CONFLUENCE_EMAIL", "CONFLUENCE_API_TOKEN"),
        "tools": (
            ("page_search", "Search Confluence pages by query."),
            ("page_get", "Get a single page by id."),
        ),
        "note": "Page create/edit is write surface; deferred.",
    },
    # P3 — cloud
    "datadog": {
        "title": "Datadog",
        "log_name": "datadog",
        "scope": "datadog:read",
        "env_keys": ("DATADOG_API_KEY", "DATADOG_APP_KEY"),
        "tools": (
            ("metric_query", "Query a metric over a time range."),
            ("log_search", "Search Datadog logs by query."),
        ),
        "note": "Datadog has no destructive APIs at the agent boundary in Stage-1.",
    },
    "aws": {
        "title": "AWS",
        "log_name": "aws",
        "scope": "aws:read",
        "env_keys": ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"),
        "tools": (
            ("ec2_describe", "Describe EC2 instances filtered by tags/state."),
            ("s3_list_bucket", "List objects in an S3 bucket (paginated)."),
        ),
        "note": "Mutating AWS calls (terminate, delete, iam:*) need a separate ADR per service.",
    },
    "gcp": {
        "title": "Google Cloud Platform",
        "log_name": "gcp",
        "scope": "gcp:read",
        "env_keys": ("GOOGLE_APPLICATION_CREDENTIALS",),
        "tools": (
            ("gce_list_instances", "List Compute Engine instances in a project/zone."),
            ("gcs_list_bucket", "List objects in a GCS bucket."),
        ),
        "note": "Mutating GCP calls need separate ADR per service.",
    },
    "azure": {
        "title": "Azure",
        "log_name": "azure",
        "scope": "azure:read",
        "env_keys": ("AZURE_TENANT_ID", "AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET"),
        "tools": (
            ("vm_list", "List Azure VMs in a subscription/resource group."),
            ("blob_list_container", "List blobs in an Azure Storage container."),
        ),
        "note": "Mutating Azure calls need separate ADR per service.",
    },
}


SERVER_TEMPLATE = '''"""
{title} MCP server — read-only Stage-1 (iter-71 SDLC batch).

Per CLAUDE.md §44 (iter-71; SDLC fleet expansion), §47 (each MCP
server owns ONE namespace; {ns}.* is the {title} boundary), §47.6
(read-only Stage-1; write surfaces deferred — {note}).

TOOLS (read only)
{tools_doc}

CONFIG
{config_doc}
  When unset → tools return available:False stub (no live calls).
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any

from fastapi import FastAPI, Header, HTTPException

from mcp.server_common import (
    ToolCallRequest,
    build_auth,
    enforce_scope as _enforce_scope_common,
    handle_tool_call,
    mount_metrics_endpoint,
    setup_server_otel,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("mcp.server_{log_name}")

app = FastAPI(title="DocuMind MCP — {title} server")
setup_server_otel(app, service_name="mcp-server-{log_name_dashed}")
mount_metrics_endpoint(app)

_AUTH_REQUIRED, _VERIFIER = build_auth()


def _enforce_scope(authorization: str | None, tool: dict[str, Any]) -> dict[str, Any]:
    return _enforce_scope_common(_VERIFIER, authorization, tool)


_QUERY_FORBIDDEN_RE = re.compile(
    r"\\b(DROP|DELETE|INSERT|UPDATE|TRUNCATE|EXECUTE|UNION)\\b",
    re.IGNORECASE,
)


def _validate_query(q: str) -> str:
    if not isinstance(q, str) or len(q) > 500:
        raise HTTPException(
            status_code=400,
            detail={{"code": "query_too_long_or_invalid", "max": 500}},
        )
    if _QUERY_FORBIDDEN_RE.search(q):
        raise HTTPException(
            status_code=400,
            detail={{"code": "query_forbidden_keyword",
                    "message": "query contains DDL/DML-shaped keyword"}},
        )
    return q


TOOLS: list[dict[str, Any]] = [
{tools_block}
]

_IDEMPOTENCY: dict[str, Any] = {{}}


def _live_or_stub() -> tuple[bool, str]:
    keys = {env_keys_tuple}
    if all(os.getenv(k, "").strip() for k in keys):
        return True, ""
    missing = [k for k in keys if not os.getenv(k, "").strip()]
    return False, f"unset env: {{missing}}"


{impls}


@app.get("/health")
async def health() -> dict[str, str]:
    return {{"status": "ok", "service": "mcp-server-{log_name_dashed}"}}


@app.get("/tools/list")
async def tools_list() -> dict[str, Any]:
    return {{"tools": TOOLS}}


@app.post("/tools/call")
async def tools_call(
    req: ToolCallRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    return await handle_tool_call(
        req=req, tools=TOOLS, idempotency_key=idempotency_key,
        authorization=authorization, auth_required=_AUTH_REQUIRED,
        verifier=_VERIFIER, idempotency_store=_IDEMPOTENCY,
        dispatch=_dispatch, tracer_module=__name__, logger=log,
        service_label="mcp_{log_name}",
    )


async def _dispatch(req: ToolCallRequest, idempotency_key: str | None, cid: str) -> dict[str, Any]:
    tool = next((t for t in TOOLS if t["name"] == req.name), None)
    if tool is None:
        raise HTTPException(status_code=404, detail={{"code": "tool_not_found", "name": req.name}})
    if os.getenv("MCP_INJECT_FAIL") == "1":
        raise HTTPException(status_code=502, detail={{"code": "upstream_error"}})
    try:
{dispatch_block}
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        log.exception("dispatch_failed tool=%s", req.name)
        raise HTTPException(status_code=500,
                            detail={{"code": "tool_dispatch_error", "message": str(exc)[:500]}}) from exc
    raise HTTPException(status_code=500, detail={{"code": "no_dispatch_for_tool", "name": req.name}})
'''


TOOL_BLOCK_TEMPLATE = '''    {{
        "name": "{ns}.{tool}",
        "description": {desc!r},
        "input_schema": {{
            "type": "object",
            "properties": {{
                "query": {{"type": "string", "maxLength": 500}},
            }},
        }},
        "output_schema": {{
            "type": "object",
            "properties": {{
                "results": {{"type": "array"}},
                "available": {{"type": "boolean"}},
            }},
        }},
        "side_effects": "read",
        "required_scopes": [{scope!r}],
        "idempotent": True,
    }},'''


IMPL_TEMPLATE = '''def _{tool}_impl(args: dict[str, Any]) -> dict[str, Any]:
    if "query" in args:
        _validate_query(str(args.get("query", "")))
    live, reason = _live_or_stub()
    if not live:
        return {{"results": [], "available": False, "reason": reason}}
    return {{"results": [], "available": True, "stub": "live_wiring_pending"}}'''


DISPATCH_TEMPLATE = '''        if req.name == "{ns}.{tool}":
            return _{tool}_impl(req.arguments)'''


def _render_server(ns: str, cfg: dict) -> str:
    log_name_dashed = cfg["log_name"].replace("_", "-")
    tools_doc = "\n".join(f"  {ns}.{t}    {desc}" for t, desc in cfg["tools"])
    config_doc = "\n".join(f"  {k}" for k in cfg["env_keys"])
    tools_block = "\n".join(
        TOOL_BLOCK_TEMPLATE.format(ns=ns, tool=t, desc=desc, scope=cfg["scope"])
        for t, desc in cfg["tools"]
    )
    impls = "\n\n\n".join(
        IMPL_TEMPLATE.format(tool=t) for t, _ in cfg["tools"]
    )
    dispatch_block = "\n".join(
        DISPATCH_TEMPLATE.format(ns=ns, tool=t) for t, _ in cfg["tools"]
    )
    return SERVER_TEMPLATE.format(
        title=cfg["title"],
        log_name=cfg["log_name"],
        log_name_dashed=log_name_dashed,
        ns=ns,
        scope=cfg["scope"],
        note=cfg["note"],
        env_keys_tuple=repr(cfg["env_keys"]),
        tools_doc=tools_doc,
        config_doc=config_doc,
        tools_block=tools_block,
        impls=impls,
        dispatch_block=dispatch_block,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    counts = {"created": 0, "skipped_exists": 0, "overwritten": 0,
              "dry_create": 0, "dry_overwrite": 0}
    for ns, cfg in SERVERS.items():
        path = REPO / "mcp" / f"server_{ns}.py"
        content = _render_server(ns, cfg)
        if args.dry_run:
            status = "dry_create" if not path.exists() else "dry_overwrite"
        elif path.exists() and not args.force:
            status = "skipped_exists"
        else:
            existed = path.exists()
            path.write_text(content, encoding="utf-8")
            status = "overwritten" if existed else "created"
        counts[status] = counts.get(status, 0) + 1
        print(f"  {ns:20s} {status}")

    print()
    print("Summary:")
    for k, v in sorted(counts.items()):
        if v:
            print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
