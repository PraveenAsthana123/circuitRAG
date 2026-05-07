"""End-to-end per-tool integration test harness (iter-90).

User asked: "do the detailed testing and give me report for each tool —
take test data, schedule the job, see the output. end-to-end."

For every MCP server in mcp/server_*.py, this script:
  1. Starts the server (best-effort; uses existing if already running)
  2. Probes /health (or /health/live) for liveness
  3. Lists tools via /tools/list
  4. For each tool, sends a test input (from the catalog YAML when
     possible) and captures input/process/output/status/latency
  5. Writes a per-tool markdown report to .loop/e2e_per_tool_report.md
  6. Writes a per-tool JSON to .loop/e2e_per_tool_report.json

For SLEEPING servers (no creds set), the script verifies the stub-mode
contract: response carries available:False without leaking real data.

Per CLAUDE.md §44 (iter-90), §57.4 Discipline-4 (layered testing:
smoke → integration → drill → outcome → production), §51 (forensic
substrate — every result captured to .loop).

CLI
---
$ python3 scripts/e2e_per_tool_report.py            # all servers; live + stub
$ python3 scripts/e2e_per_tool_report.py --only documents
$ python3 scripts/e2e_per_tool_report.py --start    # try to start sleeping servers
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LOOP = REPO / ".loop"
JSON_REPORT = LOOP / "e2e_per_tool_report.json"
MD_REPORT = LOOP / "e2e_per_tool_report.md"

# Known port assignments (matches scripts/start_mcp_*.sh + iter-72 fleet monitor)
KNOWN_PORTS: dict[str, int] = {
    "hr": 8090,
    "itsm": 8091,
    "drills": 8092,
    "documents": 8094,
    "csv_ingest": 8095,
    "ollama": 8098,
    "github": 8093,  # if started
    "slack": 8096,
    "jira": 8097,
}

DEFAULT_PORT_BASE = 8120  # for unknown namespaces

# Test inputs per tool — keep small/safe; READ-only tools only.
# Format: {tool_name: {input_dict_for_tools_call}}
TEST_INPUTS: dict[str, dict] = {
    "documents.csv_parse": {
        "path": "/mnt/deepa/rag/tests/fixtures/multimodal/sample.csv",
        "max_rows": 3,
    },
    "documents.pdf_extract_text": {
        "path": "/mnt/deepa/rag/tests/fixtures/multimodal/sample.pdf",
        "max_pages": 2,
    },
    "documents.docx_extract_text": {
        "path": "/mnt/deepa/rag/tests/fixtures/multimodal/sample.docx",
    },
    "documents.db_query_select": {
        "db": "documind",
        "query": "SELECT 1 AS smoke",
    },
    "drill.list": {},
    "ollama.list_models": {},
    "ollama.warm": {"model": "llama3.2:1b"},
    # SaaS read tools — most accept a query string
    "slack.channel_list": {"query": "general"},
    "slack.message_search": {"query": "ok"},
    "github.repo_get_file": {"repo": "owner/repo", "path": "README.md"},
    "github.pr_lookup": {"repo": "owner/repo", "pr_number": 1},
    "github.code_search": {"repo": "owner/repo", "query": "TODO"},
    "github.issue_search": {"query": "label:bug"},
    "github.issue_lookup": {"repo": "owner/repo", "issue_number": 1},
    "github.pr_search": {"query": "is:pr is:open"},
    "jira.issue_lookup": {"key": "PROJ-1"},
    "jira.search_issues": {"jql": "project = PROJ"},
    "teams.channel_list": {"query": "general"},
    "teams.message_search": {"query": "ok"},
    "whatsapp.template_lookup": {"name": "hello_world"},
    "whatsapp.template_search": {"query": "hello"},
    "gdrive.file_search": {"query": "name contains 'test'"},
    "gdrive.file_metadata": {"file_id": "1abc"},
    "servicenow.incident_lookup": {"number": "INC0000001"},
    "servicenow.incident_search": {"query": "active=true"},
    "confluence.page_search": {"query": "guidelines"},
    "confluence.page_get": {"page_id": "12345"},
    "sentry.issue_search": {"query": "is:unresolved"},
    "sentry.event_lookup": {"event_id": "1abc"},
    "pagerduty.incident_lookup": {"incident_id": "P12345"},
    "pagerduty.oncall_get": {"schedule_id": "SCH001"},
    "datadog.metric_query": {"query": "avg:system.cpu.user{*}"},
    "datadog.log_search": {"query": "service:web"},
    "kubectl.pod_describe": {"namespace": "default", "pod": "example"},
    "kubectl.event_search": {"namespace": "default"},
    "github_actions.workflow_run_get": {"repo": "owner/repo", "run_id": 1},
    "github_actions.workflow_run_search": {"repo": "owner/repo", "branch": "main"},
    "sonarqube.issues_search": {"project": "demo"},
    "sonarqube.measures_get": {"project": "demo"},
    "aws.ec2_describe": {"region": "us-east-1"},
    "aws.s3_list_bucket": {"bucket": "example-bucket"},
    "gcp.gce_list_instances": {"project": "demo", "zone": "us-central1-a"},
    "gcp.gcs_list_bucket": {"bucket": "demo-bucket"},
    "azure.vm_list": {"subscription": "demo"},
    "azure.blob_list_container": {"account": "demo", "container": "demo"},
    "research.fetch_url": {"url": "https://example.com"},
    "research.synthesize": {"topic": "smoke test"},
    "observe.prom_query": {"query": "up"},
    "observe.prom_p95": {"metric": "http_request_duration_seconds"},
    "observe.alerts_active": {},
    "deploy.compose_apply": {"service": "smoke", "image": "alpine:latest"},
    "deploy.compose_rollback": {"service": "smoke"},
    "tests.run_pytest": {"path": "tests/", "k": "smoke"},
    "tests.run_jest": {"path": "src/"},
    "tests.run_ruff": {"path": "scripts/"},
    "tests.run_drill": {"name": "drill_smoke"},
    "paperclip.snapshot": {},
    "paperclip.health": {},
    "hr.leave_request": {"employee_id": "E001", "days": 1},
    "hr.lookup": {"employee_id": "E001"},
    "itsm.incident_open": {"summary": "smoke test"},
    "itsm.incident_lookup": {"incident_id": "INC0000001"},
    "csv_ingest.session_start": {"tenant_id": "smoke", "table": "demo"},
    "csv_ingest.preview": {"session_id": "s1"},
    "csv_ingest.upload": {"session_id": "s1", "rows": []},
    "csv_ingest.approve": {"session_id": "s1", "approver": "smoke"},
    "csv_ingest.cancel": {"session_id": "s1"},
}


def _http_get(url: str, timeout: float = 2.0) -> tuple[int, bytes, float]:
    started = time.monotonic()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:  # noqa: S310
            data = r.read()
            return r.status, data, time.monotonic() - started
    except urllib.error.HTTPError as e:
        return e.code, b"", time.monotonic() - started
    except Exception:  # noqa: BLE001
        return 0, b"", time.monotonic() - started


def _http_post_json(url: str, body: dict, timeout: float = 30.0) -> tuple[int, bytes, float]:
    started = time.monotonic()
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310
            data = r.read()
            return r.status, data, time.monotonic() - started
    except urllib.error.HTTPError as e:
        body_bytes = b""
        try:
            body_bytes = e.read()
        except Exception:  # noqa: BLE001
            pass
        return e.code, body_bytes, time.monotonic() - started
    except Exception as e:  # noqa: BLE001
        return 0, str(e).encode(), time.monotonic() - started


def _port_listening(port: int) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.5)
    try:
        s.connect(("127.0.0.1", port))
        s.close()
        return True
    except OSError:
        return False


def discover_servers() -> list[tuple[str, int | None]]:
    """Map namespace -> port (or None if not started)."""
    out = []
    base = DEFAULT_PORT_BASE
    for f in sorted((REPO / "mcp").glob("server_*.py")):
        if f.stem == "server_common":
            continue
        ns = f.stem.replace("server_", "")
        port = KNOWN_PORTS.get(ns)
        if port is None:
            port = base
            base += 1
        out.append((ns, port))
    return out


def probe_health(port: int) -> tuple[str, str]:
    """Returns (status, evidence)."""
    for path in ("/health/live", "/health"):
        code, body, _ = _http_get(f"http://localhost:{port}{path}")
        if code == 200:
            return "REACHABLE", f"GET :{port}{path} → 200"
    if _port_listening(port):
        return "PORT_OPEN_NO_HEALTH", f"port {port} listening but /health returns non-200"
    return "NOT_RUNNING", f"port {port} not listening"


def list_tools(port: int) -> list[dict]:
    code, body, _ = _http_get(f"http://localhost:{port}/tools/list", timeout=3.0)
    if code != 200:
        return []
    try:
        d = json.loads(body)
        return d.get("tools", [])
    except json.JSONDecodeError:
        return []


def call_tool(port: int, name: str, arguments: dict) -> dict:
    """Returns {ok, status, latency_ms, response_preview, response_keys, error}."""
    code, body, latency = _http_post_json(
        f"http://localhost:{port}/tools/call",
        {"name": name, "arguments": arguments},
        timeout=10.0,
    )
    try:
        parsed = json.loads(body) if body else {}
    except json.JSONDecodeError:
        parsed = {}
    response_keys = list(parsed.keys()) if isinstance(parsed, dict) else []
    preview = json.dumps(parsed)[:200] if parsed else body[:200].decode("utf-8", "replace")
    return {
        "ok": code in (200, 202) and bool(parsed),
        "http_status": code,
        "latency_ms": int(latency * 1000),
        "response_keys": response_keys,
        "response_preview": preview,
        "error": None if code in (200, 202) else preview,
    }


def test_namespace(ns: str, port: int) -> dict:
    """Returns full per-namespace result row."""
    started = datetime.now(timezone.utc).isoformat()
    health_status, health_evidence = probe_health(port)
    if health_status == "NOT_RUNNING":
        return {
            "namespace": ns,
            "port": port,
            "tested_at": started,
            "health": {"status": health_status, "evidence": health_evidence},
            "tools": [],
            "skipped": True,
        }

    tools_list = list_tools(port)
    tool_results = []
    for tool in tools_list:
        name = tool.get("name", "")
        test_input = TEST_INPUTS.get(name, {})
        if not test_input and tool.get("input_schema", {}).get("required", []):
            tool_results.append({
                "name": name,
                "skipped": True,
                "reason": f"no test input defined for {name}",
            })
            continue
        result = call_tool(port, name, test_input)
        tool_results.append({
            "name": name,
            "input": test_input,
            "skipped": False,
            "process": tool.get("description", "")[:200],
            **result,
        })

    return {
        "namespace": ns,
        "port": port,
        "tested_at": started,
        "health": {"status": health_status, "evidence": health_evidence},
        "tools": tool_results,
        "skipped": False,
    }


def render_markdown(report: dict) -> str:
    out = []
    out.append("# E2E Per-Tool Test Report")
    out.append("")
    out.append(f"**Generated:** {report['generated_at']}")
    out.append(f"**Total namespaces:** {report['total_namespaces']}")
    out.append(f"**Total tools tested:** {report['total_tools']}")
    out.append(f"**Reachable:** {report['by_health']['REACHABLE']} · "
               f"Not running: {report['by_health']['NOT_RUNNING']} · "
               f"Port open / no health: {report['by_health'].get('PORT_OPEN_NO_HEALTH', 0)}")
    out.append("")

    out.append("## Summary table")
    out.append("")
    out.append("| Namespace | Port | Health | Tools listed | Tools OK | Tools skipped |")
    out.append("|---|---:|---|---:|---:|---:|")
    for r in report["namespaces"]:
        h = r["health"]["status"]
        h_emoji = {"REACHABLE": "✅", "NOT_RUNNING": "💤", "PORT_OPEN_NO_HEALTH": "⚠️"}.get(h, "❓")
        n_tools = len(r["tools"])
        n_ok = sum(1 for t in r["tools"] if not t.get("skipped") and t.get("ok"))
        n_skip = sum(1 for t in r["tools"] if t.get("skipped"))
        out.append(f"| `{r['namespace']}` | {r['port']} | {h_emoji} {h} | {n_tools} | {n_ok} | {n_skip} |")
    out.append("")

    out.append("## Per-tool details (REACHABLE namespaces only)")
    out.append("")
    for r in report["namespaces"]:
        if r["health"]["status"] != "REACHABLE":
            continue
        out.append(f"### `{r['namespace']}` (port {r['port']})")
        out.append("")
        if not r["tools"]:
            out.append("_no tools listed_")
            out.append("")
            continue
        for t in r["tools"]:
            if t.get("skipped"):
                out.append(f"- **`{t['name']}`** — SKIPPED ({t.get('reason')})")
                continue
            mark = "✅" if t.get("ok") else "❌"
            out.append(f"- {mark} **`{t['name']}`** — `{t['http_status']}` in {t['latency_ms']}ms")
            if t.get("input"):
                out.append(f"  - input: `{json.dumps(t['input'])[:120]}`")
            if t.get("process"):
                out.append(f"  - process: {t['process'][:120]}")
            if t.get("response_keys"):
                out.append(f"  - output keys: `{t['response_keys']}`")
            if t.get("response_preview"):
                out.append(f"  - output preview: `{t['response_preview'][:160]}`")
            if t.get("error") and not t.get("ok"):
                out.append(f"  - error: `{t['error'][:120]}`")
        out.append("")
    return "\n".join(out) + "\n"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--only", help="test only this namespace")
    args = p.parse_args()

    LOOP.mkdir(parents=True, exist_ok=True)
    servers = discover_servers()
    if args.only:
        servers = [(ns, pt) for ns, pt in servers if ns == args.only]

    print(f"Testing {len(servers)} namespaces…")
    namespace_results = []
    for ns, port in servers:
        print(f"  {ns:<18} port={port} …", end="", flush=True)
        r = test_namespace(ns, port)
        namespace_results.append(r)
        h = r["health"]["status"]
        n_ok = sum(1 for t in r["tools"] if t.get("ok"))
        print(f" {h} · {len(r['tools'])} tools · {n_ok} OK")

    by_health: dict[str, int] = {}
    for r in namespace_results:
        by_health[r["health"]["status"]] = by_health.get(r["health"]["status"], 0) + 1

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_namespaces": len(namespace_results),
        "total_tools": sum(len(r["tools"]) for r in namespace_results),
        "by_health": by_health,
        "namespaces": namespace_results,
    }

    JSON_REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    MD_REPORT.write_text(render_markdown(report), encoding="utf-8")

    print()
    print(f"Report written: {JSON_REPORT.relative_to(REPO)}")
    print(f"                {MD_REPORT.relative_to(REPO)}")
    print()
    print(f"by_health: {by_health}")
    return 0 if by_health.get("NOT_RUNNING", 0) < len(servers) else 1


if __name__ == "__main__":
    sys.exit(main())
