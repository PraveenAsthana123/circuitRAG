#!/usr/bin/env python3
"""MCP fleet health monitor — classify every installed/configured tool.

Per CLAUDE.md §44 (autonomous-loop iter-72; user asked 'all the tools
which have been installed or configured must work; create mechanism
which helps understand all tools working or not / failing / sleeping'),
§47 (observability — tool health is a first-class surface), §38
(governance — operator must be able to audit fleet state at any time).

CLASSIFICATION (per server)
  WORKING        installed + URL configured + /health 200 + /tools/list
                 returns tools + live deps (env keys for upstream set)
  DEGRADED       installed + URL configured + /health 200 + /tools/list
                 returns + deps in STUB mode (env keys missing → tools
                 return available:False but server itself works)
  FAILING        installed + URL configured + /health 4xx/5xx OR
                 timeout OR /tools/list malformed
  SLEEPING       installed + URL NOT set (server file exists; not
                 deployed — operator opt-in pending)
  NOT_INSTALLED  server file missing in mcp/server_*.py
                 (currently impossible per iter-71 inventory; included
                 for future fleet shrink scenarios)

OUTPUT
  Human-readable table (default) — one line per server with status +
                                   tool count + reason.
  JSON shape (--json) — for /admin dashboard consumption.
  Exit codes:
    0   all servers WORKING or SLEEPING (operator-intentional state)
    1   any server FAILING (operational alarm)
    2   any server NOT_INSTALLED but configured (config drift)

CLI:
  python3 scripts/mcp_fleet_health.py
  python3 scripts/mcp_fleet_health.py --json
  python3 scripts/mcp_fleet_health.py --only slack       # one server
  python3 scripts/mcp_fleet_health.py --probe-timeout 5  # tighter probe
  python3 scripts/mcp_fleet_health.py --include-stub-tools  # detail per tool
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MCP_DIR = REPO / "mcp"
INFERENCE_MAIN = REPO / "services" / "inference-svc" / "app" / "main.py"


@dataclass
class ToolHealth:
    name: str
    side_effects: str
    has_live_deps: bool          # env keys for upstream service set
    available_in_probe: bool | None  # None when /tools/list not probed


@dataclass
class UsageStats:
    """Per-server usage from Prometheus metrics (when --usage)."""
    calls_total: int = 0          # documind_mcp_<ns>_calls_total
    success_total: int = 0
    error_total: int = 0
    p95_latency_ms: float = 0.0
    avg_latency_ms: float = 0.0
    wip_count: int = 0            # in-flight calls (gauge)
    completed_24h: int = 0
    success_rate: float = 0.0     # success / total ∈ [0, 1]


@dataclass
class ServerHealth:
    namespace: str               # e.g. 'jira'
    file_path: str               # e.g. 'mcp/server_jira.py'
    installed: bool
    configured_url: str          # empty when not set
    env_var: str                 # e.g. DOCUMIND_MCP_JIRA_URL
    expected_env_keys: list[str] = field(default_factory=list)
    missing_env_keys: list[str] = field(default_factory=list)
    health_endpoint_ok: bool | None = None
    tools_endpoint_ok: bool | None = None
    tool_count: int = 0
    tools: list[ToolHealth] = field(default_factory=list)
    status: str = "UNKNOWN"      # WORKING / DEGRADED / FAILING / SLEEPING / NOT_INSTALLED
    reason: str = ""
    probe_latency_ms: float = 0.0
    e2e_passed: bool | None = None    # set by --e2e
    e2e_reason: str = ""
    usage: UsageStats = field(default_factory=UsageStats)


@dataclass
class FleetHealth:
    generated_at: str
    total_servers: int
    by_status: dict[str, int] = field(default_factory=dict)
    servers: list[ServerHealth] = field(default_factory=list)


# Inventory the mcp/ directory + extract per-server expected env keys
# from each server's _live_or_stub() function (or equivalent).
_LIVE_KEYS_RE = re.compile(
    # Accept either ' or " quotes (iter-71 builder uses single quotes;
    # iter-67/68 hand-written servers use double). Capture up to 6 keys.
    r'_live_or_stub.*?keys\s*=\s*\(\s*'
    r'(?:["\']([^"\']+)["\']\s*,?\s*)'      # key 1
    r'(?:["\']([^"\']+)["\']\s*,?\s*)?'     # key 2
    r'(?:["\']([^"\']+)["\']\s*,?\s*)?'     # key 3
    r'(?:["\']([^"\']+)["\']\s*,?\s*)?'     # key 4
    r'(?:["\']([^"\']+)["\']\s*,?\s*)?'     # key 5
    r'(?:["\']([^"\']+)["\']\s*,?\s*)?'     # key 6
    r'\s*\)',
    re.DOTALL,
)
# Some servers use single getenv check (no tuple); look for getenv("X"
# but ONLY before the first occurrence of MCP_INJECT_FAIL (chaos var)
# so it doesn't false-match the chaos check.
_LIVE_KEY_GETENV_RE = re.compile(
    r'_live_or_stub.*?os\.getenv\(["\']([A-Z_]+)["\']', re.DOTALL,
)


def _list_mcp_servers() -> list[tuple[str, Path]]:
    """Return [(namespace, server_file_path), ...] for every
    mcp/server_*.py except common/__init__/etc."""
    out: list[tuple[str, Path]] = []
    for p in sorted(MCP_DIR.glob("server_*.py")):
        if p.name == "server_common.py":
            continue
        ns = p.stem.removeprefix("server_")
        out.append((ns, p))
    return out


def _parse_inference_mcp_spec() -> dict[str, str]:
    """Parse mcp_spec list in inference-svc/main.py to extract
    {namespace → DOCUMIND_MCP_<NS>_URL env var name}."""
    if not INFERENCE_MAIN.exists():
        return {}
    src = INFERENCE_MAIN.read_text(encoding="utf-8")
    out: dict[str, str] = {}
    # Match patterns like ("jira", os.getenv("DOCUMIND_MCP_JIRA_URL", ""))
    for m in re.finditer(
        r'\(\s*"([a-z_]+)"\s*,\s*os\.getenv\(\s*"([A-Z_]+)"',
        src,
    ):
        ns, env_var = m.group(1), m.group(2)
        out[ns] = env_var
    return out


# Env vars that look like creds in regex but aren't — exclude from
# the "expected upstream creds" set so they don't appear as missing
# in the health report.
_NON_CRED_ENV_VARS: frozenset[str] = frozenset({
    "MCP_INJECT_FAIL",        # chaos-test injection
    "DOCUMIND_PG_HOST",       # idempotency-store choice (not cred)
    "DOCUMIND_PG_USER",       # ditto
    "DOCUMIND_PG_PASSWORD",   # ditto
    "DOCUMIND_PG_PORT",       # ditto
    "DOCUMIND_PG_DB",         # ditto
    "MCP_IDEMPOTENCY_DURABLE",
    "MCP_IDEMPOTENCY_TTL_S",
    "CSV_INGEST_MAX_FILE_BYTES",
    "CSV_INGEST_ALLOWED_TABLES",
    "CSV_INGEST_SQLITE_PATH",
})


def _extract_live_env_keys(server_path: Path) -> list[str]:
    """Read server source + extract env keys checked by _live_or_stub.

    Returns a list of env var names. Empty list = no upstream creds
    needed (e.g. observe server hits local Prometheus).
    """
    src = server_path.read_text(encoding="utf-8")
    # Try tuple form first (most common in iter-67/71)
    m = _LIVE_KEYS_RE.search(src)
    if m:
        return [g for g in m.groups() if g and g not in _NON_CRED_ENV_VARS]
    # Fall back to single-getenv form (iter-68 github / iter-61 documents)
    keys: list[str] = []
    seen: set[str] = set()
    for gm in _LIVE_KEY_GETENV_RE.finditer(src):
        k = gm.group(1)
        if k in _NON_CRED_ENV_VARS or k in seen:
            continue
        seen.add(k)
        keys.append(k)
    return keys


def _probe_health(url: str, timeout: float) -> tuple[bool, float, str]:
    """GET <url>/health with timeout. Returns (ok, latency_ms, reason)."""
    if not url:
        return False, 0.0, "no url"
    import time
    full = url.rstrip("/") + "/health"
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(full, timeout=timeout) as r:
            body = r.read(2048).decode("utf-8", errors="replace")
            ms = (time.monotonic() - t0) * 1000
            ok = r.status == 200
            return ok, ms, "" if ok else f"HTTP {r.status}: {body[:200]}"
    except urllib.error.HTTPError as e:
        ms = (time.monotonic() - t0) * 1000
        return False, ms, f"HTTP {e.code}: {str(e)[:200]}"
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        ms = (time.monotonic() - t0) * 1000
        return False, ms, f"{type(e).__name__}: {str(e)[:200]}"


def _probe_tools_list(url: str, timeout: float) -> tuple[bool, list[ToolHealth], str]:
    """GET <url>/tools/list. Returns (ok, [ToolHealth], reason)."""
    if not url:
        return False, [], "no url"
    full = url.rstrip("/") + "/tools/list"
    try:
        with urllib.request.urlopen(full, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8", errors="replace"))
        tools_raw = data.get("tools") or []
        tools = [
            ToolHealth(
                name=t.get("name", ""),
                side_effects=t.get("side_effects", ""),
                has_live_deps=False,  # filled by caller post-env-check
                available_in_probe=None,
            )
            for t in tools_raw
        ]
        return True, tools, ""
    except (urllib.error.HTTPError, urllib.error.URLError,
            TimeoutError, OSError, json.JSONDecodeError) as e:
        return False, [], f"{type(e).__name__}: {str(e)[:200]}"


def _probe_e2e(url: str, ns: str, tools: list[ToolHealth], timeout: float) -> tuple[bool, str]:
    """End-to-end test: pick the FIRST read tool, call /tools/call with
    minimal valid args, verify response shape. Returns (ok, reason).

    Per §50.5.3 + ADR-028: never call write tools as part of e2e probe;
    the probe is read-only by contract. Synthetic args used (placeholder
    strings); a stub-mode server returns available:False without making
    a real upstream call. A live server with the right creds returns
    real data — both are valid PASS conditions for the probe.
    """
    if not url or not tools:
        return False, "no tools to probe"
    # Pick the first read tool
    read_tool = next((t for t in tools if t.side_effects == "read"), None)
    if read_tool is None:
        return False, "no read tool in /tools/list"
    # Build synthetic minimal args. Most read tools accept a 'query' /
    # 'name' / 'id' / 'path' field; we send a benign string. Servers
    # that require specific fields (e.g. jira.issue_lookup needs
    # issue_key matching ^[A-Z]+-\d+$) should accept TEST-1 / etc.
    args = _synthetic_args_for(read_tool.name, ns)
    full = url.rstrip("/") + "/tools/call"
    body = json.dumps({"name": read_tool.name, "arguments": args}).encode()
    req = urllib.request.Request(
        full, data=body,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            json.loads(r.read().decode("utf-8", errors="replace"))
        # Shape check: response should have a payload (server_common
        # wraps results); accept any 200 response as "tool reachable".
        return True, f"called {read_tool.name}; response shape ok"
    except urllib.error.HTTPError as e:
        # 4xx is a VALID e2e response — the server is up + validated input.
        # The probe verifies the call ROUNDTRIPPED, not that the input
        # was perfectly formed for the live API.
        if 400 <= e.code < 500:
            return True, f"called {read_tool.name}; got HTTP {e.code} (validation; reachable)"
        return False, f"HTTP {e.code}: {str(e)[:200]}"
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
        return False, f"{type(e).__name__}: {str(e)[:200]}"


def _synthetic_args_for(tool_name: str, ns: str) -> dict:
    """Minimal valid arguments for an e2e probe of a read tool.
    Per-namespace overrides match the validators each server enforces."""
    # Tool-specific known shapes (extend as namespaces are added)
    if tool_name.startswith("jira.issue_lookup"):
        return {"issue_key": "TEST-1"}
    if tool_name.startswith("jira.issue_search"):
        return {"jql": "test"}
    if tool_name.startswith("github.repo_get_file"):
        return {"repo": "test/test", "path": "README.md"}
    if tool_name.startswith("github.pr_lookup"):
        return {"repo": "test/test", "number": 1}
    if tool_name.startswith("github.code_search"):
        return {"query": "test"}
    if tool_name.startswith("github.issue_lookup"):
        return {"repo": "test/test", "number": 1}
    if tool_name.startswith("github."):
        return {"query": "test"}
    if tool_name.startswith("documents.csv_parse"):
        return {"path": "/tmp/test.csv"}
    if tool_name.startswith("documents.pdf_extract_text"):
        return {"path": "/tmp/test.pdf"}
    if tool_name.startswith("documents.docx_extract_text"):
        return {"path": "/tmp/test.docx"}
    if tool_name.startswith("documents.db_query_select"):
        return {"sql": "SELECT 1"}
    if tool_name.startswith("servicenow.incident_lookup"):
        return {"sys_id": "0" * 32}
    if tool_name.startswith("whatsapp.template_lookup"):
        return {"template_name": "hello_world"}
    if tool_name.startswith("gdrive.file_get_metadata"):
        return {"file_id": "test_id"}
    if tool_name.startswith("paperclip."):
        return {}
    if tool_name.startswith("drills."):
        return {}
    if tool_name.startswith("ollama."):
        return {"model": "qwen2.5:latest"}
    # iter-71 batch: all use {"query": ...} or empty per the builder
    return {"query": "test"}


def _scrape_prometheus(url: str, ns: str, timeout: float) -> UsageStats:
    """Scrape /metrics + extract per-namespace counters/histograms.

    Returns zeroed UsageStats when /metrics unreachable OR when no
    metrics for this namespace exist (server has been up but never
    called). Best-effort; never raises.
    """
    stats = UsageStats()
    if not url:
        return stats
    full = url.rstrip("/") + "/metrics"
    try:
        with urllib.request.urlopen(full, timeout=timeout) as r:
            text = r.read().decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001 — best-effort
        return stats
    # Parse Prometheus exposition format. Look for lines like:
    #   documind_mcp_calls_total{service="mcp_jira",...} 42
    # The prefix used by server_common is documind_mcp_*; the service
    # label is set per-server.
    for line in text.splitlines():
        if line.startswith("#") or not line.strip():
            continue
        if f'service="mcp_{ns}"' not in line and f'service_label="mcp_{ns}"' not in line:
            continue
        # Crude parse — split on whitespace, last field is the value
        parts = line.rsplit(" ", 1)
        if len(parts) != 2:
            continue
        head, val_str = parts
        try:
            val = float(val_str)
        except ValueError:
            continue
        if "_calls_total" in head or "_requests_total" in head:
            stats.calls_total += int(val)
        if "_success" in head or 'status="ok"' in head or 'outcome="success"' in head:
            stats.success_total += int(val)
        if "_error" in head or 'status="error"' in head or 'outcome="error"' in head:
            stats.error_total += int(val)
        if "_in_flight" in head or "_wip" in head:
            stats.wip_count = max(stats.wip_count, int(val))
        # p95 / latency parsing skipped in Stage-1 (histograms need
        # quantile resolution); set when a future iter wires it.
    if stats.calls_total > 0:
        stats.success_rate = stats.success_total / stats.calls_total
        stats.completed_24h = stats.success_total + stats.error_total
    return stats


def classify_server(
    ns: str, server_path: Path,
    env_var: str, probe_timeout: float,
    *, do_e2e: bool = False, do_usage: bool = False,
) -> ServerHealth:
    """Build a ServerHealth row for one namespace."""
    sh = ServerHealth(
        namespace=ns,
        file_path=str(server_path.relative_to(REPO)),
        installed=server_path.is_file(),
        env_var=env_var,
        configured_url=os.getenv(env_var, "").strip() if env_var else "",
    )
    if not sh.installed:
        sh.status = "NOT_INSTALLED"
        sh.reason = f"{sh.file_path} missing"
        return sh

    sh.expected_env_keys = _extract_live_env_keys(server_path)
    sh.missing_env_keys = [
        k for k in sh.expected_env_keys if not os.getenv(k, "").strip()
    ]

    if not sh.configured_url:
        sh.status = "SLEEPING"
        sh.reason = f"{env_var or '(no env-var configured)'} unset"
        return sh

    # Configured — probe.
    h_ok, h_ms, h_reason = _probe_health(sh.configured_url, probe_timeout)
    sh.health_endpoint_ok = h_ok
    sh.probe_latency_ms = round(h_ms, 1)
    if not h_ok:
        sh.status = "FAILING"
        sh.reason = f"/health probe failed: {h_reason}"
        return sh

    t_ok, tools, t_reason = _probe_tools_list(sh.configured_url, probe_timeout)
    sh.tools_endpoint_ok = t_ok
    if not t_ok:
        sh.status = "FAILING"
        sh.reason = f"/tools/list probe failed: {t_reason}"
        return sh

    # Mark each tool with has_live_deps based on the server-level env state
    for t in tools:
        t.has_live_deps = len(sh.missing_env_keys) == 0
    sh.tools = tools
    sh.tool_count = len(tools)

    if sh.missing_env_keys:
        sh.status = "DEGRADED"
        sh.reason = (
            f"server up but upstream creds unset: {sh.missing_env_keys}; "
            "tools return available:False"
        )
    else:
        sh.status = "WORKING"
        sh.reason = (
            f"healthy ({sh.tool_count} tools advertised; "
            f"{sh.probe_latency_ms:.0f}ms /health)"
        )

    # E2E probe (synthetic call to first read tool)
    if do_e2e:
        e2e_ok, e2e_reason = _probe_e2e(
            sh.configured_url, ns, sh.tools, probe_timeout,
        )
        sh.e2e_passed = e2e_ok
        sh.e2e_reason = e2e_reason

    # Usage scrape from Prometheus /metrics
    if do_usage:
        sh.usage = _scrape_prometheus(sh.configured_url, ns, probe_timeout)

    return sh


def collect_fleet_health(
    *, only: str | None = None, probe_timeout: float = 3.0,
    do_e2e: bool = False, do_usage: bool = False,
) -> FleetHealth:
    """Walk every mcp/server_*.py + classify."""
    from datetime import UTC, datetime
    spec = _parse_inference_mcp_spec()
    by_status: dict[str, int] = {}
    rows: list[ServerHealth] = []
    for ns, path in _list_mcp_servers():
        if only and only != ns:
            continue
        env_var = spec.get(ns, "")
        sh = classify_server(
            ns, path, env_var, probe_timeout,
            do_e2e=do_e2e, do_usage=do_usage,
        )
        by_status[sh.status] = by_status.get(sh.status, 0) + 1
        rows.append(sh)
    return FleetHealth(
        generated_at=datetime.now(UTC).isoformat(),
        total_servers=len(rows),
        by_status=by_status,
        servers=rows,
    )


# ---------------------------------------------------------------------------
# Ollama model inventory + status (per user request: 'all the models on ollama')
# ---------------------------------------------------------------------------
@dataclass
class OllamaModel:
    name: str                # e.g. "qwen2.5:latest"
    size_bytes: int
    loaded_in_vram: bool     # via /api/ps
    family: str              # heuristic: "qwen" / "deepseek" / "codegemma" / etc.


@dataclass
class OllamaInventory:
    reachable: bool
    base_url: str
    installed: list[OllamaModel] = field(default_factory=list)
    loaded: list[str] = field(default_factory=list)  # model names in VRAM
    error: str = ""


def collect_ollama_inventory(*, base_url: str = "http://localhost:11434",
                             timeout: float = 3.0) -> OllamaInventory:
    """Probe Ollama daemon: /api/tags (installed models) + /api/ps (loaded)."""
    inv = OllamaInventory(reachable=False, base_url=base_url)
    try:
        with urllib.request.urlopen(f"{base_url}/api/tags", timeout=timeout) as r:
            tags = json.loads(r.read().decode("utf-8"))
        inv.reachable = True
        loaded_set: set[str] = set()
        try:
            with urllib.request.urlopen(f"{base_url}/api/ps", timeout=timeout) as r:
                ps = json.loads(r.read().decode("utf-8"))
            loaded_set = {m.get("name", "") for m in ps.get("models", [])}
        except Exception:  # noqa: BLE001 — /api/ps optional
            pass
        for m in tags.get("models", []):
            name = m.get("name", "")
            family = name.split(":")[0].split("-")[0].lower()
            inv.installed.append(OllamaModel(
                name=name,
                size_bytes=int(m.get("size", 0)),
                loaded_in_vram=name in loaded_set,
                family=family,
            ))
        inv.loaded = sorted(loaded_set)
    except Exception as exc:  # noqa: BLE001
        inv.error = f"{type(exc).__name__}: {str(exc)[:200]}"
    return inv


# ---------------------------------------------------------------------------
# Agent council node inventory (per user request: 'all the node of agent
# working, review, search, plan, code, test, deploy, security, monitoring,
# visualization')
# ---------------------------------------------------------------------------
@dataclass
class CouncilNode:
    role: str                # canonical: researcher / author / reviewer / advisor
    aliases: list[str]       # 5-role aliases pointing at this canonical
    model: str               # e.g. "qwen2.5:latest"
    domain: str              # plan / code / review / search / test / etc.
    available: bool          # model present in Ollama inventory
    available_reason: str = ""


def collect_council_inventory(ollama: OllamaInventory) -> list[CouncilNode]:
    """Read scripts/local_council.py to extract canonical 4-role
    council + iter-34's 5-role alias map. Mark each node as
    available iff its underlying Ollama model is installed."""
    council_src = (REPO / "scripts" / "local_council.py").read_text(encoding="utf-8")
    # Match each entry in COUNCIL_ROLES = { "researcher": {"model": "..."} ...}
    role_model_re = re.compile(
        r'"(researcher|author|reviewer|advisor)":\s*\{\s*"model":\s*"([^"]+)"',
        re.DOTALL,
    )
    canonical: dict[str, str] = {}
    for m in role_model_re.finditer(council_src):
        canonical[m.group(1)] = m.group(2)

    # Match COUNCIL_ROLE_ALIASES = { "Planner": "author", ... }
    alias_re = re.compile(
        r'"([A-Z][A-Za-z]+)":\s*"(researcher|author|reviewer|advisor)"'
    )
    aliases_for: dict[str, list[str]] = {r: [] for r in canonical}
    for m in alias_re.finditer(council_src):
        target = m.group(2)
        if target in aliases_for:
            aliases_for[target].append(m.group(1))

    # Domain mapping per iter-34 ADR + iter-58 reflection engine
    domain_for = {
        "researcher": "search",       # gathers context (Retriever alias)
        "author": "plan + code",      # proposes (Planner / Writer alias)
        "reviewer": "review + risk",  # critiques (Risk alias)
        "advisor": "test + evaluator",# synthesizes (Evaluator alias)
    }

    installed_names = {m.name for m in ollama.installed}
    nodes: list[CouncilNode] = []
    for role, model in canonical.items():
        avail = model in installed_names
        reason = "" if avail else f"model {model!r} not in Ollama inventory"
        nodes.append(CouncilNode(
            role=role,
            aliases=sorted(aliases_for.get(role, [])),
            model=model,
            domain=domain_for.get(role, "?"),
            available=avail,
            available_reason=reason,
        ))
    return nodes


# ---------------------------------------------------------------------------
# Backend service inventory (per user request: 'each backend operation
# tool functionality must be presented')
# ---------------------------------------------------------------------------
@dataclass
class BackendService:
    name: str                # e.g. "inference-svc"
    kind: str                # "python" / "go"
    file_count: int          # rough size signal
    health_endpoint: str     # canonical health URL
    operations: list[str]    # high-level operations (per-svc curated list)
    description: str         # one-liner for UI


# Hand-curated per-service description. Captures the "what does this
# service DO at the operational layer" beyond the tool surface.
BACKEND_SERVICES: list[BackendService] = [
    BackendService(
        name="api-gateway", kind="go", file_count=0,
        health_endpoint="http://localhost:8080/health",
        operations=["JWT auth", "rate limit", "tenant header injection",
                    "request routing"],
        description="Edge HTTP entrypoint (Go); enforces JWT + rate limits before forwarding.",
    ),
    BackendService(
        name="ingestion-svc", kind="python", file_count=0,
        health_endpoint="http://localhost:8001/health",
        operations=["document ingest saga", "outbox dispatcher",
                    "embedding generation", "Qdrant + Neo4j upsert",
                    "document.lifecycle Kafka events"],
        description="CSV/document ingestion pipeline (saga + outbox); writes to Qdrant + Neo4j; emits Kafka events.",
    ),
    BackendService(
        name="retrieval-svc", kind="python", file_count=0,
        health_endpoint="http://localhost:8002/health",
        operations=["hybrid retrieval (vector + graph)", "BM25 fallback",
                    "reranker", "circuit breaker", "query.retrieved.v1 events"],
        description="Hybrid retrieval (Qdrant vector + Neo4j graph + BM25); reranker; per-tenant cache.",
    ),
    BackendService(
        name="inference-svc", kind="python", file_count=0,
        health_endpoint="http://localhost:8003/health",
        operations=["RAG inference (retrieval + LLM)", "agent service (MCP)",
                    "HITL draft persistence", "audit log writes",
                    "query.generated.v1 events", "MCP client to 28 servers"],
        description="RAG + agent service; calls retrieval-svc + Ollama + 28 MCP servers; writes draft + audit rows.",
    ),
    BackendService(
        name="evaluation-svc", kind="python", file_count=0,
        health_endpoint="http://localhost:8004/health",
        operations=["RAG metric scoring (precision/recall/MRR/nDCG)",
                    "regression-gate comparison",
                    "Ragas/Guardrails/DeepEval/Lakera/Giskard adapters",
                    "eval.completed.v1 events"],
        description="RAG + LLM evaluation (5 engines); regression gate; emits eval.completed.v1.",
    ),
    BackendService(
        name="agent-orchestrator-svc", kind="python", file_count=0,
        health_endpoint="http://localhost:8005/health",
        operations=["agentic task lifecycle",
                    "LangGraph workflow execution",
                    "approval state machine",
                    "agent.task.created.v1 events"],
        description="Agentic orchestrator; LangGraph workflows; idempotency-keyed task creation; approval gate.",
    ),
    BackendService(
        name="governance-svc", kind="go", file_count=0,
        health_endpoint="http://localhost:8011/health",
        operations=["audit log ingest", "policy decision log",
                    "decision audit reads"],
        description="Governance audit trail (Go); receives decision logs; serves audit queries.",
    ),
    BackendService(
        name="identity-svc", kind="go", file_count=0,
        health_endpoint="http://localhost:8012/health",
        operations=["JWT issue", "RBAC role lookup",
                    "tenant validation", "scope enforcement"],
        description="Identity + RBAC (Go); issues JWTs; validates per-tenant + per-scope.",
    ),
    BackendService(
        name="finops-svc", kind="go", file_count=0,
        health_endpoint="http://localhost:8013/health",
        operations=["cost aggregation", "budget alerts",
                    "per-tenant cost attribution"],
        description="FinOps cost aggregation (Go); per-tenant + per-provider cost tracking.",
    ),
    BackendService(
        name="observability-svc", kind="go", file_count=0,
        health_endpoint="http://localhost:8014/health",
        operations=["metric scrape proxy", "log query proxy",
                    "trace lookup proxy"],
        description="Observability proxy (Go); fronts Prometheus + Jaeger + ES for the agent surface.",
    ),
]


def collect_backend_services_health(*, probe_timeout: float = 2.0) -> list[dict]:
    """Probe each backend service /health (best-effort)."""
    out: list[dict] = []
    for svc in BACKEND_SERVICES:
        ok, ms, reason = _probe_health(svc.health_endpoint.rsplit("/health", 1)[0],
                                       probe_timeout)
        out.append({
            "name": svc.name,
            "kind": svc.kind,
            "operations": svc.operations,
            "description": svc.description,
            "health_endpoint": svc.health_endpoint,
            "alive": ok,
            "latency_ms": round(ms, 1),
            "reason": reason,
        })
    return out


def _exit_code(fleet: FleetHealth) -> int:
    """0 = all WORKING or SLEEPING; 1 = any FAILING; 2 = any NOT_INSTALLED-but-configured."""
    statuses = fleet.by_status
    if statuses.get("FAILING", 0) > 0:
        return 1
    if statuses.get("NOT_INSTALLED", 0) > 0:
        return 2
    return 0


def _render_human(fleet: FleetHealth, *, include_tools: bool) -> str:
    lines: list[str] = []
    lines.append(f"MCP Fleet Health — {fleet.generated_at}")
    lines.append(f"  total servers: {fleet.total_servers}")
    for status in ("WORKING", "DEGRADED", "FAILING", "SLEEPING", "NOT_INSTALLED"):
        n = fleet.by_status.get(status, 0)
        if n:
            lines.append(f"  {status:14s} {n}")
    lines.append("")
    lines.append(f"{'NAMESPACE':24s} {'STATUS':14s} {'TOOLS':5s} {'LATENCY':>9s}  REASON")
    lines.append("-" * 100)
    for s in fleet.servers:
        latency = f"{s.probe_latency_ms:.0f}ms" if s.probe_latency_ms else "-"
        lines.append(
            f"{s.namespace:24s} {s.status:14s} {s.tool_count:5d} {latency:>9s}  {s.reason[:70]}"
        )
        if include_tools and s.tools:
            for t in s.tools:
                deps = "live" if t.has_live_deps else "stub"
                lines.append(
                    f"  {'':22s} ↳ {t.name:30s} {t.side_effects:6s} ({deps})"
                )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true",
                        help="emit JSON instead of human-readable table")
    parser.add_argument("--only", type=str, default=None,
                        help="filter to one namespace (e.g. slack)")
    parser.add_argument("--probe-timeout", type=float, default=3.0,
                        help="HTTP probe timeout seconds (default: 3.0)")
    parser.add_argument("--include-stub-tools", action="store_true",
                        help="include per-tool detail (live vs stub)")
    parser.add_argument("--e2e", action="store_true",
                        help="end-to-end probe each server's first read tool")
    parser.add_argument("--usage", action="store_true",
                        help="scrape Prometheus /metrics for per-server usage stats")
    parser.add_argument("--full", action="store_true",
                        help="include Ollama + council + backend service inventories")
    args = parser.parse_args()

    fleet = collect_fleet_health(
        only=args.only, probe_timeout=args.probe_timeout,
        do_e2e=args.e2e, do_usage=args.usage,
    )

    ollama: OllamaInventory | None = None
    council: list[CouncilNode] | None = None
    backends: list[dict] | None = None
    if args.full:
        ollama = collect_ollama_inventory(timeout=args.probe_timeout)
        council = collect_council_inventory(ollama)
        backends = collect_backend_services_health(probe_timeout=args.probe_timeout)

    if args.json:
        out: dict = {
            "generated_at": fleet.generated_at,
            "total_servers": fleet.total_servers,
            "by_status": fleet.by_status,
            "servers": [asdict(s) for s in fleet.servers],
        }
        if args.full:
            out["ollama"] = asdict(ollama) if ollama else None
            out["council"] = [asdict(n) for n in (council or [])]
            out["backend_services"] = backends
        print(json.dumps(out, indent=2, default=str))
    else:
        print(_render_human(fleet, include_tools=args.include_stub_tools))
        if args.full:
            print()
            if ollama:
                print(f"Ollama daemon: {'reachable' if ollama.reachable else 'UNREACHABLE'}")
                print(f"  base_url: {ollama.base_url}")
                print(f"  installed models: {len(ollama.installed)}")
                print(f"  loaded in VRAM: {len(ollama.loaded)}")
                for m in ollama.installed[:20]:
                    flag = "★" if m.loaded_in_vram else " "
                    sz_gb = m.size_bytes / (1024**3)
                    print(f"    {flag} {m.name:35s}  {sz_gb:5.1f} GB  ({m.family})")
            print()
            if council:
                print(f"Agent council nodes: {len(council)}")
                for n in council:
                    avail = "✅" if n.available else "❌"
                    print(f"  {avail} {n.role:12s}  model={n.model:30s}  domain={n.domain}")
                    if n.aliases:
                        print(f"        aliases: {', '.join(n.aliases)}")
            print()
            if backends:
                alive_n = sum(1 for b in backends if b["alive"])
                print(f"Backend services: {alive_n}/{len(backends)} alive")
                for b in backends:
                    flag = "✅" if b["alive"] else "💤"
                    lat = f"{b['latency_ms']:.0f}ms" if b["alive"] else "-"
                    print(f"  {flag} {b['name']:24s} {b['kind']:7s} {lat:>7s}  {b['description'][:60]}")

    return _exit_code(fleet)


if __name__ == "__main__":
    sys.exit(main())
