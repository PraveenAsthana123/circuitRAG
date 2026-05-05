"""Inference HTTP routes."""

from __future__ import annotations

from documind_core.auth import require_roles, required_role_for_tool
from documind_core.exceptions import ValidationError
from documind_core.schemas import HealthResponse
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.schemas import (
    AgentAskRequest,
    AgentAskResponse,
    AskRequest,
    AskResponse,
    BestConfigInfo,
    BreakerState,
    ClientErrorListResponse,
    ClientErrorRecord,
    ClientErrorReport,
    DraftListResponse,
    DraftRejectRequest,
    DraftRejectResponse,
    DraftResolveResponse,
    DraftSummary,
    HealthBestConfigHistoryResponse,
    HealthBestConfigResponse,
    HealthDetailedResponse,
    HealthPromptsResponse,
    HealthTechstackResponse,
    HealthToolsResponse,
    HealthUpstreamsResponse,
    PromptInfo,
    TechstackEntry,
    ToolStats,
    TraceLinkAuditRow,
    TraceLinkDraftRow,
    TraceLinkHitlRow,
    TraceLinkResponse,
    UpstreamHealthRow,
)
from app.services import RagInferenceService
from app.services.agent import AgentService

router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["health"])
async def health() -> HealthResponse:
    return HealthResponse(status="ok", service="inference-svc")


@router.get(
    "/api/v1/health/detailed",
    response_model=HealthDetailedResponse,
    tags=["health"],
    summary="Operator-facing detail: breaker states + readiness flags",
)
async def health_detailed(request: Request) -> HealthDetailedResponse:
    import time
    from datetime import UTC, datetime

    state = request.app.state
    started_at = getattr(state, "started_at_monotonic", None)
    uptime = (time.monotonic() - started_at) if started_at is not None else 0.0

    breakers: list[BreakerState] = []
    # Every registered MCP namespace gets its own breaker row so the
    # dashboard sees them independently. Stable name scheme:
    # ``mcp_<namespace>`` (mcp_hr, mcp_itsm, ...). Matches the
    # Prometheus exporter's label naming so /detailed and /metrics
    # agree on identifiers.
    mcp_clients = getattr(state, "mcp_clients", None) or {}
    for namespace in sorted(mcp_clients):
        client = mcp_clients[namespace]
        # ``failures`` is the public CircuitBreaker property (post-unification).
        # Old code reached into ``_breaker._failures`` — that attribute
        # only existed on the deleted ``_MCPBreaker``. Touch the public
        # surface only so dashboards keep working when the breaker swaps.
        inner = getattr(client, "_breaker", None)
        failures = getattr(inner, "failures", None) if inner is not None else None
        recovery_timeout_s = getattr(inner, "recovery_timeout", None) if inner is not None else None
        breakers.append(
            BreakerState(
                name=f"mcp_{namespace}",
                state=client.cb_state,
                failures=failures,
                recovery_timeout_s=recovery_timeout_s,
            ),
        )
    # Observability CB lives inside the OTel exporter wrapper; exposed
    # on app.state when the lifespan hands us the reference (opt-in so
    # services that don't use setup_observability don't explode here).
    ocb = getattr(state, "obs_breaker", None)
    if ocb is not None:
        breakers.append(BreakerState(name=ocb.name, state=ocb.state.value))

    readiness = {
        "draft_store": ("postgres" if getattr(state, "db_client", None) is not None else "in_memory"),
        "audit_log": "on" if getattr(state, "db_client", None) is not None else "off",
        "auth": "required" if getattr(state, "auth_required", False) else "optional",
        "agent_service": ("on" if getattr(state, "agent_service", None) is not None else "off"),
        "draft_replay_worker": ("on" if getattr(state, "draft_replay_worker", None) is not None else "off"),
    }

    return HealthDetailedResponse(
        service="inference-svc",
        uptime_s=round(uptime, 3),
        observed_at=datetime.now(UTC).isoformat(),
        breakers=breakers,
        readiness=readiness,
    )


@router.get(
    "/api/v1/health/tools",
    response_model=HealthToolsResponse,
    tags=["health"],
    summary="Per-tool aggregate of MCP /metrics — calls, latency, denials",
)
async def health_tools(request: Request) -> HealthToolsResponse:
    """
    Aggregate per-tool stats by scraping every registered MCP server's
    /metrics endpoint. Operators read this to see, per (namespace,
    tool):
      * calls by outcome (ok / error / replay / http_<status>)
      * latency aggregate (count, sum, avg) — p95 stays in Prometheus
      * scope denials by reason (NOT_AUTHENTICATED, INVALID_TOKEN,
        INSUFFICIENT_SCOPE, UNKNOWN)

    The endpoint is best-effort: each namespace is scraped with a
    short timeout, and a failed scrape lands in ``unreachable`` so
    the UI shows '(stale)' rather than '(no data)'.

    Closes Phase-1 #2 of mcp-agent-gap-review.md ("per-tool
    monitoring views"). The metrics primitives shipped in commit
    598ca9a; this endpoint surfaces them.
    """
    from datetime import UTC, datetime

    import httpx
    from prometheus_client.parser import text_string_to_metric_families

    state = request.app.state
    mcp_clients = getattr(state, "mcp_clients", None) or {}

    tools_by_key: dict[tuple[str, str], ToolStats] = {}
    unreachable: list[str] = []

    # Short timeout — this endpoint is poll-driven from the dashboard
    # at ~5s cadence. A slow MCP shouldn't block the operator UI.
    async with httpx.AsyncClient(timeout=2.0) as client:
        for namespace, mcp in sorted(mcp_clients.items()):
            ns_key = f"mcp_{namespace}"
            try:
                # MCPClient stores its base URL on ``_base`` (already
                # rstrip-cleaned). Touch the private attr deliberately —
                # it's a stable contract within this monorepo and the
                # alternative (a public getter just for this scrape) is
                # over-engineering for one consumer.
                base = getattr(mcp, "_base", "") or ""
                if not base:
                    unreachable.append(ns_key)
                    continue
                r = await client.get(f"{base}/metrics")
                if r.status_code != 200:
                    unreachable.append(ns_key)
                    continue
                body = r.text
            except (httpx.RequestError, httpx.TimeoutException):
                unreachable.append(ns_key)
                continue

            # Parse with prometheus_client's tolerant parser — handles
            # HELP/TYPE/buckets/sum/count without us reimplementing
            # exposition format. We only care about three families.
            try:
                families = list(text_string_to_metric_families(body))
            except (ValueError, OSError):
                # Malformed exposition — log via unreachable rather
                # than crashing the dashboard with a 500.
                unreachable.append(ns_key)
                continue

            for fam in families:
                if fam.name == "documind_mcp_tool_calls":
                    for s in fam.samples:
                        labels = s.labels or {}
                        ns = labels.get("namespace", "")
                        tool = labels.get("tool", "")
                        outcome = labels.get("outcome", "")
                        if not ns or not tool or not outcome:
                            continue
                        ts = tools_by_key.setdefault(
                            (ns, tool),
                            ToolStats(namespace=ns, tool=tool),
                        )
                        ts.calls[outcome] = int(s.value)
                elif fam.name == "documind_mcp_tool_call_duration_seconds":
                    # _count and _sum samples drive the aggregate.
                    # Bucket samples (one per `le`) carry no extra
                    # info beyond the histogram count surface, and
                    # we don't expose p95 (deriving it from buckets
                    # is lossy — Prometheus does it correctly).
                    for s in fam.samples:
                        labels = s.labels or {}
                        ns = labels.get("namespace", "")
                        tool = labels.get("tool", "")
                        if not ns or not tool:
                            continue
                        ts = tools_by_key.setdefault(
                            (ns, tool),
                            ToolStats(namespace=ns, tool=tool),
                        )
                        if s.name.endswith("_count"):
                            ts.latency.count = int(s.value)
                        elif s.name.endswith("_sum"):
                            ts.latency.sum_seconds = float(s.value)
                elif fam.name == "documind_mcp_scope_denials":
                    for s in fam.samples:
                        labels = s.labels or {}
                        ns = labels.get("namespace", "")
                        tool = labels.get("tool", "")
                        reason = labels.get("reason", "")
                        if not ns or not tool or not reason:
                            continue
                        ts = tools_by_key.setdefault(
                            (ns, tool),
                            ToolStats(namespace=ns, tool=tool),
                        )
                        ts.denials[reason] = int(s.value)

    # Compute avg_seconds now that count + sum are populated. Done
    # post-loop so partial samples (sum without count, etc.) don't
    # produce divide-by-zero or nonsensical averages.
    tools = []
    for (_ns, _tool), ts in sorted(tools_by_key.items()):
        if ts.latency.count > 0:
            ts.latency.avg_seconds = round(
                ts.latency.sum_seconds / ts.latency.count,
                6,
            )
        tools.append(ts)

    return HealthToolsResponse(
        service="inference-svc",
        observed_at=datetime.now(UTC).isoformat(),
        tools=tools,
        unreachable=sorted(unreachable),
    )


@router.get(
    "/api/v1/health/prompts",
    response_model=HealthPromptsResponse,
    tags=["health"],
    summary="Active prompt registry — name, version, model, tuning",
)
async def health_prompts(request: Request) -> HealthPromptsResponse:
    """
    Operator-facing visibility into the active prompt registry
    (governance.prompts WHERE status='active'). Returns the lifecycle
    + tuning fields without dumping template bodies.

    Closes the trust-scorecard gap from
    docs/architecture/production-trust-quality-and-readiness.md:
    "prompt/model/retrieval registry visibility — operators still
    can't easily answer 'which prompt + model is live right now?'"

    The endpoint stays 200 even when the DB is unreachable —
    db_reachable=false + empty prompts lets the UI surface the
    degradation cleanly. A 500 here would mystify operators
    investigating an unrelated outage.
    """
    from datetime import UTC, datetime

    from app.services.prompt_repo import PromptRepo

    db_client = getattr(request.app.state, "db_client", None)
    prompts: list[PromptInfo] = []
    db_reachable = False

    if db_client is not None:
        try:
            repo = PromptRepo(db_client)
            rows = await repo.list_active()
            db_reachable = True
            for r in rows:
                # Coerce DB types (asyncpg Decimal etc.) to plain
                # Python primitives — Pydantic accepts them but JSON
                # encoding chokes on Decimal without a default.
                prompts.append(
                    PromptInfo(
                        name=str(r["name"]),
                        version=str(r["version"]),
                        model=str(r["model"]) if r.get("model") is not None else None,
                        temperature=(float(r["temperature"]) if r.get("temperature") is not None else None),
                        max_tokens=(int(r["max_tokens"]) if r.get("max_tokens") is not None else None),
                        status=str(r["status"]),
                    )
                )
        except Exception:  # noqa: BLE001 — registry visibility must not
            # crash the dashboard. Surface as db_reachable=false; the
            # operator sees "(registry unavailable)" rather than a 500
            # masking the real outage they're investigating.
            db_reachable = False

    return HealthPromptsResponse(
        service="inference-svc",
        observed_at=datetime.now(UTC).isoformat(),
        db_reachable=db_reachable,
        prompts=prompts,
    )


@router.get(
    "/api/v1/health/upstreams",
    response_model=HealthUpstreamsResponse,
    tags=["health"],
    summary="Cross-service reachability view from inference-svc's perspective",
)
async def health_upstreams(request: Request) -> HealthUpstreamsResponse:
    """
    Probe every upstream dependency this service reaches out to:
    retrieval-svc, ollama, registered MCP namespaces, the governance
    DB. Returns reachability + probe latency + version per row.

    Honest scoping: this endpoint reflects ONE service's upstream
    view, not a global service registry. governance-svc / ingestion-
    svc / etc. own their own equivalents. The frontend renders this
    as a "Service mesh — inference-svc upstreams" panel; the same
    pattern can be added to other services without coupling them.

    Closes the audit-checklist gap "service-level monitoring" and
    the gRPC/microservices reference doc's monitoring scenarios
    around cross-service reachability.

    Probes run in parallel with a tight 2s timeout — a slow upstream
    must NOT block the dashboard refresh on the rest. Each row
    surfaces ``error`` as a short label so operators can pattern-
    match without reading server logs.
    """
    import asyncio
    import os
    import time
    from datetime import UTC, datetime

    import httpx

    state = request.app.state
    settings = getattr(state, "settings", None)

    # Probe specs — (name, kind, url, probe_path). ``probe_path`` is
    # optional; for ollama we hit the root, for HTTP services /health.
    specs: list[tuple[str, str, str, str]] = []

    # retrieval-svc: from settings, fall back to env. The settings object
    # may not be on app.state for older lifespans; getattr defends.
    retrieval_url = getattr(settings, "retrieval_svc_url", None) or os.getenv(
        "DOCUMIND_RETRIEVAL_SVC_URL", "http://localhost:8083"
    )
    specs.append(("retrieval-svc", "http_service", retrieval_url, "/health"))

    # ollama: probes the root which Ollama returns "Ollama is running"
    # on, no auth needed. Skipped if not configured.
    ollama_url = getattr(settings, "ollama_url", None) or os.getenv("DOCUMIND_OLLAMA_URL", "")
    if ollama_url:
        specs.append(("ollama", "llm", ollama_url, "/"))

    # MCP namespaces: probe each registered MCP server's /health.
    mcp_clients = getattr(state, "mcp_clients", None) or {}
    for namespace, mcp in sorted(mcp_clients.items()):
        base = getattr(mcp, "_base", "") or ""
        if base:
            specs.append((f"mcp_{namespace}", "mcp", base, "/health"))

    # governance DB: a connection check, not an HTTP probe.
    db_client = getattr(state, "db_client", None)

    # Kafka broker(s): TCP-level reachability probe. The settings/env
    # carry a comma-separated bootstrap list; we probe the FIRST entry
    # (the broker exposes the cluster via metadata once you connect to
    # any node, so first-bootstrap reachability is a fair proxy).
    kafka_bootstrap = getattr(settings, "kafka_bootstrap_servers", None) or os.getenv(
        "DOCUMIND_KAFKA_BOOTSTRAP_SERVERS", ""
    )

    async def _probe_http(
        client: httpx.AsyncClient,
        name: str,
        kind: str,
        base_url: str,
        path: str,
    ) -> UpstreamHealthRow:
        url = f"{base_url.rstrip('/')}{path}"
        started = time.perf_counter()
        try:
            r = await client.get(url, timeout=2.0)
            latency_ms = round((time.perf_counter() - started) * 1000, 2)
            version: str | None = None
            try:
                body = r.json()
                if isinstance(body, dict):
                    version = body.get("version")
            except (ValueError, TypeError):
                pass
            return UpstreamHealthRow(
                name=name,
                kind=kind,
                url=base_url,
                reachable=200 <= r.status_code < 300,
                latency_ms=latency_ms,
                status=str(r.status_code),
                version=version,
                error=(None if r.status_code < 400 else f"http_{r.status_code}"),
            )
        except httpx.ConnectError:
            return UpstreamHealthRow(
                name=name,
                kind=kind,
                url=base_url,
                reachable=False,
                latency_ms=round((time.perf_counter() - started) * 1000, 2),
                error="connect_refused",
            )
        except httpx.TimeoutException:
            return UpstreamHealthRow(
                name=name,
                kind=kind,
                url=base_url,
                reachable=False,
                latency_ms=round((time.perf_counter() - started) * 1000, 2),
                error="timeout",
            )
        except httpx.RequestError as exc:
            return UpstreamHealthRow(
                name=name,
                kind=kind,
                url=base_url,
                reachable=False,
                latency_ms=round((time.perf_counter() - started) * 1000, 2),
                error=type(exc).__name__,
            )

    async def _probe_kafka() -> UpstreamHealthRow:
        # TCP-level broker reachability — open a connection to the
        # first bootstrap host:port, close immediately. Doesn't
        # exchange the Kafka protocol (which would require aiokafka
        # producer/consumer setup); for a 5s dashboard refresh this
        # would be too heavy and would create + tear down clients
        # constantly. TCP-reachable + nothing-listening-on-port is
        # the strongest signal we get cheaply, and it's what the
        # operator actually needs to know first.
        url = kafka_bootstrap or "(unset)"
        if not kafka_bootstrap:
            return UpstreamHealthRow(
                name="kafka",
                kind="kafka",
                url=url,
                reachable=False,
                error="bootstrap_unset",
            )
        # Take the first bootstrap entry; brokers exchange cluster
        # metadata once we connect to any node.
        first = kafka_bootstrap.split(",")[0].strip()
        if ":" not in first:
            return UpstreamHealthRow(
                name="kafka",
                kind="kafka",
                url=url,
                reachable=False,
                error="bad_bootstrap_format",
            )
        host, port_s = first.rsplit(":", 1)
        try:
            port = int(port_s)
        except ValueError:
            return UpstreamHealthRow(
                name="kafka",
                kind="kafka",
                url=url,
                reachable=False,
                error="bad_bootstrap_port",
            )
        started = time.perf_counter()
        try:
            # 2s timeout same as the HTTP probes — a slow Kafka
            # mustn't drag the dashboard.
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=2.0,
            )
            writer.close()
            try:
                await writer.wait_closed()
            except (ConnectionError, OSError):
                pass
            latency_ms = round((time.perf_counter() - started) * 1000, 2)
            return UpstreamHealthRow(
                name="kafka",
                kind="kafka",
                url=url,
                reachable=True,
                latency_ms=latency_ms,
                status="tcp_open",
            )
        except TimeoutError:
            return UpstreamHealthRow(
                name="kafka",
                kind="kafka",
                url=url,
                reachable=False,
                latency_ms=round((time.perf_counter() - started) * 1000, 2),
                error="timeout",
            )
        except (ConnectionRefusedError, OSError) as exc:
            return UpstreamHealthRow(
                name="kafka",
                kind="kafka",
                url=url,
                reachable=False,
                latency_ms=round((time.perf_counter() - started) * 1000, 2),
                error=type(exc).__name__,
            )

    async def _probe_db() -> UpstreamHealthRow:
        # ``db_client.pool.fetchval('SELECT 1')`` is the canonical
        # liveness probe for asyncpg — exercises pool acquire +
        # query roundtrip without touching schema.
        host = os.getenv("DOCUMIND_PG_HOST", "localhost")
        port = os.getenv("DOCUMIND_PG_PORT", "5432")
        url = f"{host}:{port}"
        if db_client is None:
            return UpstreamHealthRow(
                name="governance-db",
                kind="db",
                url=url,
                reachable=False,
                error="db_client_not_configured",
            )
        started = time.perf_counter()
        try:
            async with db_client.admin_connection() as conn:
                v = await conn.fetchval("SELECT 1")
            latency_ms = round((time.perf_counter() - started) * 1000, 2)
            return UpstreamHealthRow(
                name="governance-db",
                kind="db",
                url=url,
                reachable=(v == 1),
                latency_ms=latency_ms,
                status="connected",
            )
        except Exception as exc:  # noqa: BLE001 — operator probe must not raise
            return UpstreamHealthRow(
                name="governance-db",
                kind="db",
                url=url,
                reachable=False,
                latency_ms=round((time.perf_counter() - started) * 1000, 2),
                error=type(exc).__name__,
            )

    # Run all probes in parallel — slowest probe sets the latency
    # ceiling, not the sum. 2s timeout per probe means the endpoint
    # always returns within ~2.1s even if every upstream is dead.
    async with httpx.AsyncClient() as client:
        http_tasks = [_probe_http(client, name, kind, url, path) for (name, kind, url, path) in specs]
        results: list[UpstreamHealthRow] = list(
            await asyncio.gather(*http_tasks, _probe_db(), _probe_kafka()),
        )

    # Stable sort: kind (db, http_service, kafka, llm, mcp), then
    # name — operators visually expect related rows together.
    results.sort(key=lambda r: (r.kind, r.name))

    return HealthUpstreamsResponse(
        service="inference-svc",
        observed_at=datetime.now(UTC).isoformat(),
        upstreams=results,
    )


# ---------------------------------------------------------------------------
# Client-error ring buffer — module-level so it survives across requests
# but resets on process restart. Bounded; oldest evicted when full. No DB
# persistence: this is for debugging the last few minutes, not historical
# analytics. A real production rollout would forward to Sentry / Faro /
# Datadog RUM; this is the local-dev variant that doesn't need a network
# dependency.
# ---------------------------------------------------------------------------
from collections import deque as _deque  # noqa: E402

_CLIENT_ERROR_BUFFER_CAPACITY = 100
_CLIENT_ERROR_STACK_CAP = 4096  # bytes — cap stack so a runaway error doesn't blow memory
_client_errors: _deque[ClientErrorRecord] = _deque(maxlen=_CLIENT_ERROR_BUFFER_CAPACITY)


@router.post(
    "/api/v1/admin/client-errors",
    response_model=ClientErrorRecord,
    tags=["admin"],
    status_code=201,
    summary="Frontend-reported client-side error event",
)
async def admin_client_error_report(
    body: ClientErrorReport,
    request: Request,
) -> ClientErrorRecord:
    """
    Frontend posts uncaught JS errors / unhandled promise rejections /
    React error-boundary catches here. The server stores them in a
    bounded in-memory ring buffer; the admin dashboard reads them via
    the GET sibling.

    Stack traces are length-capped at insertion time so a runaway
    error message can't blow memory. No auth on this endpoint —
    in dev, the gateway / network policy gates browser access; in
    prod, this would be replaced by Sentry / Faro / equivalent.

    Server-side tenant capture: TenantContextMiddleware reads
    X-Tenant-ID from the inbound request (the api.ts wrapper sends
    it on every call) and writes it to request.state.tenant_id. We
    stamp it onto the record so the admin /admin/client-errors →
    /admin/forensics deep-link can fully pre-fill cid + tid and the
    auto-fire kicks in. Nullable when not present (e.g. an error
    fires before the tenant is known).
    """
    import uuid as _uuid
    from datetime import UTC, datetime

    stack = body.stack
    if stack is not None and len(stack) > _CLIENT_ERROR_STACK_CAP:
        # Cap from the END — the bottom of the stack (the actual error
        # site) is more useful than the top (which is usually deep
        # framework frames).
        stack = "...[truncated]...\n" + stack[-_CLIENT_ERROR_STACK_CAP:]

    # Pull tenant_id from request.state (TenantContextMiddleware
    # populates this from X-Tenant-ID). Empty string → None so the
    # JSON response carries `null` rather than `""`, matching the
    # nullable shape advertised on ClientErrorRecord.
    tenant = getattr(request.state, "tenant_id", "") or None

    record = ClientErrorRecord(
        id=_uuid.uuid4().hex[:12],
        received_at=datetime.now(UTC).isoformat(),
        kind=body.kind,
        message=body.message[:1024],  # message cap too
        stack=stack,
        route=body.route,
        user_agent=body.user_agent,
        correlation_id=body.correlation_id,
        tenant_id=tenant,
        extra=body.extra or {},
    )
    _client_errors.appendleft(record)  # newest first
    return record


@router.get(
    "/api/v1/admin/client-errors",
    response_model=ClientErrorListResponse,
    tags=["admin"],
    summary="Recent frontend-reported client-side errors (newest first)",
)
async def admin_client_error_list() -> ClientErrorListResponse:
    """
    Read-only view of the in-memory ring buffer. Admin dashboard polls
    this so operators can see what broke in the browser without asking
    the user to F12.
    """
    from datetime import UTC, datetime

    records = list(_client_errors)
    return ClientErrorListResponse(
        service="inference-svc",
        observed_at=datetime.now(UTC).isoformat(),
        capacity=_CLIENT_ERROR_BUFFER_CAPACITY,
        count=len(records),
        records=records,
    )


@router.get(
    "/api/v1/health/techstack",
    response_model=HealthTechstackResponse,
    tags=["health"],
    summary="Curated tech-stack inventory — installed pip/npm packages vs pending",
)
async def health_techstack(request: Request) -> HealthTechstackResponse:
    """
    Read-only tech-stack inventory. Curates a list of "interesting"
    Python and Node packages (RAG frameworks, agent frameworks,
    observability tools, data-tier libs, etc.) and reports each one
    as installed (with version) or pending.

    Hard rules:
      * The catalog is HARDCODED server-side. No dynamic command
        construction; no path for an attacker to probe arbitrary
        binaries via crafted request data.
      * No installs triggered from this endpoint. Operator runs
        `pip install X` themselves if they want a pending tool.
      * Probe-cost is bounded: importlib.metadata for pip lookups
        (no subprocess), file-system read of package.json for npm.

    Closes the request for a 'techstack UI to know what software
    has been installed or pending' from the integration / RAG /
    agent catalog stream.
    """
    import json as _json
    import os as _os
    from datetime import UTC, datetime
    from importlib import metadata as _meta
    from pathlib import Path as _Path

    # ---- Curated catalog --------------------------------------------------
    # source ∈ {pip, npm}. category drives the UI grouping. purpose is a
    # one-line description so operators don't context-switch to look up
    # what 'crewai' or 'ragas' is.
    PIP_CATALOG: list[tuple[str, str, str]] = [  # noqa: N806 — function-scoped constant
        # (pkg_dist_name, category, purpose)
        # core stack
        ("fastapi", "core", "Web framework"),
        ("pydantic", "core", "Schema validation"),
        ("asyncpg", "core", "Postgres async driver"),
        ("redis", "core", "Redis client"),
        ("httpx", "core", "Async HTTP client"),
        ("uvicorn", "core", "ASGI server"),
        # observability
        ("opentelemetry-api", "observability", "OTel API surface"),
        ("opentelemetry-sdk", "observability", "OTel SDK"),
        ("prometheus-client", "observability", "Prometheus metrics"),
        # rag frameworks
        ("langchain", "rag-framework", "RAG/agent framework (heavy)"),
        ("llama-index", "rag-framework", "Indexing + retrieval framework"),
        ("langgraph", "rag-framework", "Stateful agent orchestration"),
        # agent frameworks
        ("autogen", "agent-framework", "Multi-agent communication"),
        ("crewai", "agent-framework", "Lightweight role-based agents"),
        ("semantic-kernel", "agent-framework", "Enterprise agent SDK"),
        # vector + embeddings
        ("qdrant-client", "vector-db", "Qdrant client"),
        ("weaviate-client", "vector-db", "Weaviate client"),
        ("pymilvus", "vector-db", "Milvus client"),
        ("sentence-transformers", "embeddings", "Local embedding models"),
        # llm hosting / inference
        ("ollama", "llm-host", "Ollama Python client"),
        ("vllm", "llm-host", "vLLM inference server"),
        ("openai", "llm-host", "OpenAI / OpenAI-compatible client"),
        ("anthropic", "llm-host", "Anthropic SDK"),
        # voice
        ("openai-whisper", "voice", "Whisper transcription"),
        ("TTS", "voice", "Coqui TTS"),
        # eval / quality
        ("ragas", "eval", "RAG evaluation"),
        ("guardrails-ai", "guardrails", "Guardrails for LLM output"),
        ("promptfoo", "eval", "Prompt regression"),
        # data
        ("pyspark", "data", "Apache Spark"),
        ("clickhouse-driver", "data", "ClickHouse client"),
        ("duckdb", "data", "DuckDB"),
        ("mlflow", "data", "ML experiment tracking"),
        ("pandas", "data", "DataFrames"),
        # autonomous experimental
        ("autogpt", "autonomous-agent", "AutoGPT (experimental)"),
        # workflow
        ("apache-airflow", "data", "Workflow orchestration"),
    ]

    NPM_CATALOG: list[tuple[str, str, str]] = [  # noqa: N806 — function-scoped constant
        # (pkg_name, category, purpose)
        ("next", "frontend", "Next.js framework"),
        ("react", "frontend", "React"),
        ("react-dom", "frontend", "React DOM bindings"),
        ("typescript", "frontend", "TypeScript"),
        ("@opentelemetry/api", "observability", "OTel browser API"),
        ("@playwright/test", "testing", "E2E testing"),
        ("zod", "frontend", "Schema validation"),
        ("eslint", "frontend", "Linting"),
    ]

    entries: list[TechstackEntry] = []

    # ---- Probe pip distributions (pure Python, no subprocess) -------------
    # importlib.metadata.version() raises PackageNotFoundError when the
    # package isn't installed; we catch and mark pending.
    for pkg, category, purpose in PIP_CATALOG:
        try:
            ver = _meta.version(pkg)
            entries.append(
                TechstackEntry(
                    name=pkg,
                    category=category,
                    source="pip",
                    installed=True,
                    version=ver,
                    purpose=purpose,
                )
            )
        except _meta.PackageNotFoundError:
            entries.append(
                TechstackEntry(
                    name=pkg,
                    category=category,
                    source="pip",
                    installed=False,
                    version=None,
                    purpose=purpose,
                )
            )
        except Exception as exc:  # noqa: BLE001 — never crash the dashboard
            entries.append(
                TechstackEntry(
                    name=pkg,
                    category=category,
                    source="pip",
                    installed=False,
                    version=None,
                    purpose=purpose,
                    error=type(exc).__name__,
                )
            )

    # ---- Probe npm via package.json read ----------------------------------
    # Read the frontend's package.json. The repo root is a known path
    # (DOCUMIND_REPO_ROOT) or we walk up from this file. Defensive: if
    # the file is missing, mark every npm entry as pending — don't
    # 500 the endpoint.
    pkg_json_path = _Path(
        _os.getenv("DOCUMIND_FRONTEND_PACKAGE_JSON", "") or "/mnt/deepa/rag/services/frontend/package.json"
    )
    npm_versions: dict[str, str] = {}
    if pkg_json_path.is_file():
        try:
            data = _json.loads(pkg_json_path.read_text())
            for section in ("dependencies", "devDependencies"):
                deps = data.get(section, {}) or {}
                for k, v in deps.items():
                    if isinstance(v, str):
                        # strip leading ^ ~ to get a clean version
                        npm_versions[k] = v.lstrip("^~>=< ")
        except (OSError, ValueError):
            # File unreadable or malformed — leave npm_versions empty;
            # every npm entry below will mark pending.
            pass
    for pkg, category, purpose in NPM_CATALOG:
        if pkg in npm_versions:
            entries.append(
                TechstackEntry(
                    name=pkg,
                    category=category,
                    source="npm",
                    installed=True,
                    version=npm_versions[pkg],
                    purpose=purpose,
                )
            )
        else:
            entries.append(
                TechstackEntry(
                    name=pkg,
                    category=category,
                    source="npm",
                    installed=False,
                    version=None,
                    purpose=purpose,
                )
            )

    # Stable order: category → name. Operators visually expect related
    # rows together (e.g. all rag-framework rows side-by-side).
    entries.sort(key=lambda e: (e.category, e.source, e.name))

    installed_count = sum(1 for e in entries if e.installed)
    pending_count = len(entries) - installed_count

    return HealthTechstackResponse(
        service="inference-svc",
        observed_at=datetime.now(UTC).isoformat(),
        installed_count=installed_count,
        pending_count=pending_count,
        entries=entries,
    )


@router.get(
    "/api/v1/health/best-config",
    response_model=HealthBestConfigResponse,
    tags=["health"],
    summary="Live best_config registry — what BestConfig is in effect RIGHT NOW",
)
async def health_best_config() -> HealthBestConfigResponse:
    """
    Operator-facing visibility into the empirically-best config the
    inference + retrieval services would seed defaults from. Closes
    the §38 governance gap "what's live RIGHT NOW?" for the
    AutoRAG → best_config.json → loader chain.

    Always returns 200. The `enabled` + `loaded` fields tell the UI
    how to render:
      enabled=False, loaded=False → "(loader disabled)"
      enabled=True,  loaded=False → "(file missing/malformed —
                                     using legacy fallback defaults)"
      enabled=True,  loaded=True  → "(loader active — see config block)"

    Per CLAUDE.md §47 fail-safe: this endpoint NEVER raises on loader
    error; the UI sees `enabled=False, loaded=False` if the import
    fails, which is the same as "disabled" — graceful degradation.
    """
    from datetime import UTC, datetime

    observed_at = datetime.now(UTC).isoformat()
    config: BestConfigInfo | None = None
    enabled = False
    loaded = False
    config_path = ".loop/best_config.json"
    config_exists = False
    config_size_bytes = 0
    ttl_s = 300.0
    cache_age_s = 0.0
    fallback_defaults: dict = {}
    next_stage = ""

    try:
        import sys

        sys.path.insert(0, "/mnt/deepa/rag/scripts")
        from best_config_loader import (
            is_available,
            load_best_config,
            status,
        )

        st = status()
        enabled = bool(st.get("enabled_env", False))
        config_path = str(st.get("config_path", config_path))
        config_exists = bool(st.get("config_exists", False))
        config_size_bytes = int(st.get("config_size_bytes", 0))
        ttl_s = float(st.get("ttl_s", 300.0))
        cache_age_s = float(st.get("cache_age_s", 0.0))
        fallback_defaults = dict(st.get("fallback_defaults", {}))
        next_stage = str(st.get("next_stage", ""))

        if is_available():
            cfg = load_best_config()
            if cfg is not None:
                loaded = True
                config = BestConfigInfo(
                    min_score=cfg.min_score,
                    top_k=cfg.top_k,
                    rerank_enabled=cfg.rerank_enabled,
                    rerank_top_k=cfg.rerank_top_k,
                    chunking_strategy=cfg.chunking_strategy,
                    pass_rate=cfg.pass_rate,
                    promoted_at_ts=cfg.promoted_at_ts,
                    eval_set_size=cfg.eval_set_size,
                )
    except Exception:  # noqa: BLE001 — visibility must never crash
        # §47 fail-safe: surface as "(unavailable)" rather than 500
        pass

    return HealthBestConfigResponse(
        service="inference-svc",
        observed_at=observed_at,
        enabled=enabled,
        loaded=loaded,
        config_path=config_path,
        config_exists=config_exists,
        config_size_bytes=config_size_bytes,
        ttl_s=ttl_s,
        cache_age_s=cache_age_s,
        fallback_defaults=fallback_defaults,
        config=config,
        next_stage=next_stage,
    )


@router.get(
    "/api/v1/health/best-config-history",
    response_model=HealthBestConfigHistoryResponse,
    tags=["health"],
    summary="Promotion-gate audit trail summary (window-bounded)",
)
async def health_best_config_history(
    days: int = Query(
        7,
        ge=-1,
        le=365,
        description="Window in days; -1 means 'all rows'",
    ),
) -> HealthBestConfigHistoryResponse:
    """
    Operator visibility into the .loop/best_config_history.jsonl
    audit trail. Composes scripts/best_config_history.py:summarize()
    + status() over an HTTP surface so the dashboard can render
    'last N days: X promoted / Y rejected / Z skipped' without
    operator shell access.

    Always returns 200. enabled+history_exists distinguish state.
    Per CLAUDE.md §47: visibility never crashes; lazy import +
    try/except + descriptive empty-state fields on any failure.
    """
    from datetime import UTC, datetime

    observed_at = datetime.now(UTC).isoformat()
    enabled = False
    history_path = ".loop/best_config_history.jsonl"
    history_exists = False
    history_size_bytes = 0
    total = 0
    promoted = 0
    rejected = 0
    skipped = 0
    gates_failed_counts: dict[str, int] = {}
    latest_decision: dict[str, Any] | None = None
    earliest_ts = 0.0
    latest_ts = 0.0

    try:
        import sys

        sys.path.insert(0, "/mnt/deepa/rag/scripts")
        from best_config_history import (
            is_available,
            load_history,
            status,
            summarize,
        )

        st = status()
        enabled = bool(st.get("enabled_env", False))
        history_path = str(st.get("history_path", history_path))
        history_exists = bool(st.get("history_exists", False))
        history_size_bytes = int(st.get("history_size_bytes", 0))

        if is_available():
            rows = load_history()
            summary = summarize(rows, days=days)
            total = summary.total_attempts
            promoted = summary.promoted
            rejected = summary.rejected
            skipped = summary.skipped
            gates_failed_counts = dict(summary.gates_failed_counts)
            latest_decision = summary.latest_decision
            earliest_ts = summary.earliest_ts
            latest_ts = summary.latest_ts
    except Exception:  # noqa: BLE001 — visibility never crashes
        pass

    return HealthBestConfigHistoryResponse(
        service="inference-svc",
        observed_at=observed_at,
        enabled=enabled,
        history_path=history_path,
        history_exists=history_exists,
        history_size_bytes=history_size_bytes,
        window_days=days,
        total_attempts=total,
        promoted=promoted,
        rejected=rejected,
        skipped=skipped,
        gates_failed_counts=gates_failed_counts,
        latest_decision=latest_decision,
        earliest_ts=earliest_ts,
        latest_ts=latest_ts,
    )


@router.get(
    "/api/v1/admin/trace/{correlation_id}",
    response_model=TraceLinkResponse,
    tags=["admin"],
    summary="Trace → draft → audit linkage by correlation_id",
)
async def admin_trace_link(
    correlation_id: str,
    request: Request,
    tenant_id: str = Query(
        ...,
        description=(
            "Tenant UUID — required because audit_log has FORCE-enabled "
            "RLS and the documind_app role is non-BYPASSRLS. The lookup "
            "scopes to (correlation_id, tenant_id) — operators investigate "
            "with both pieces in hand from the dashboard."
        ),
    ),
) -> TraceLinkResponse:
    """
    Operator-facing trace reconstruction. Given a correlation_id
    (propagated by ``X-Correlation-ID`` through every request) and
    the tenant_id it belongs to, returns the audit rows + draft
    rows that share that correlation_id — and a Jaeger deep-link
    if configured.

    Closes the gap "no easy way to follow trace → draft → replay →
    audit" cited in:
      * mcp-agent-gap-review.md §2.3
      * production-trust-quality-and-readiness.md §2
      * tech-lead-audit-checklist.md §7

    Tenant scoping: ``tenant_id`` is required (not derived from
    cross-tenant admin context) because audit_log RLS is FORCE-
    enabled and documind_app is non-BYPASSRLS. This is the honest
    security shape — a future privileged-role + admin endpoint
    can offer cross-tenant aggregation, but until that role exists,
    the safer surface is per-tenant lookup.

    Stays 200 even with zero matches: an unknown (correlation_id,
    tenant_id) is a normal "I'm investigating, nothing happened
    yet" state, not a 404. The UI distinguishes empty-result from
    db_reachable=false.
    """
    import os
    import uuid as _uuid
    from datetime import UTC, datetime

    # Validate both path/query UUIDs upfront — reject 400 with a
    # specific code so the UI surfaces "(invalid X)" rather than
    # running a query that returns zero rows for the wrong reason.
    try:
        cid = str(_uuid.UUID(correlation_id))
    except (ValueError, AttributeError) as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "INVALID_CORRELATION_ID",
                "message": "correlation_id must be a UUID",
            },
        ) from exc
    try:
        tid = str(_uuid.UUID(tenant_id))
    except (ValueError, AttributeError) as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "INVALID_TENANT_ID",
                "message": "tenant_id must be a UUID",
            },
        ) from exc

    db_client = getattr(request.app.state, "db_client", None)
    audit_rows: list[TraceLinkAuditRow] = []
    draft_rows: list[TraceLinkDraftRow] = []
    hitl_rows: list[TraceLinkHitlRow] = []
    db_reachable = False

    if db_client is not None:
        try:
            async with db_client.tenant_connection(tid) as conn:
                a_rows = await conn.fetch(
                    """
                    SELECT id, timestamp, tenant_id, actor_id, actor_type,
                           action, resource_type, resource_id, details
                    FROM governance.audit_log
                    WHERE correlation_id = $1::uuid
                    ORDER BY timestamp ASC
                    """,
                    cid,
                )
                d_rows = await conn.fetch(
                    """
                    SELECT draft_id, tenant_id, tool, status, reason,
                           created_at, replayed_at
                    FROM governance.action_drafts
                    WHERE correlation_id = $1::uuid
                    ORDER BY created_at ASC
                    """,
                    cid,
                )
                # HITL queue projection — completes the trace → draft →
                # audit → HITL loop. Empty result is normal (most answers
                # are NOT flagged); non-empty means human-in-the-loop
                # intervened, which is critical evidence for EU AI Act
                # Art. 14 (human oversight) audits.
                # ORDER BY created_at ASC matches the audit + draft
                # contracts so all three timelines line up for the
                # operator.
                h_rows = await conn.fetch(
                    """
                    SELECT id, tenant_id, question, confidence, flag_reason,
                           review_status, reviewer_id, review_notes,
                           created_at, reviewed_at
                    FROM governance.hitl_queue
                    WHERE correlation_id = $1::uuid
                    ORDER BY created_at ASC
                    """,
                    cid,
                )
            db_reachable = True

            for r in a_rows:
                details = r["details"] or {}
                # ``details`` arrives as either dict or json-string
                # depending on asyncpg codec settings; normalize.
                if isinstance(details, str):
                    import json as _json

                    try:
                        details = _json.loads(details)
                    except _json.JSONDecodeError:
                        details = {}
                audit_rows.append(
                    TraceLinkAuditRow(
                        id=str(r["id"]),
                        timestamp=r["timestamp"].isoformat() if r["timestamp"] else "",
                        tenant_id=str(r["tenant_id"]) if r["tenant_id"] else None,
                        actor_id=r["actor_id"],
                        actor_type=r["actor_type"],
                        action=r["action"],
                        resource_type=r["resource_type"],
                        resource_id=str(r["resource_id"]) if r["resource_id"] else None,
                        fail_closed_failed=bool(isinstance(details, dict) and details.get("fail_closed_failed", False)),
                    )
                )
            for r in d_rows:
                draft_rows.append(
                    TraceLinkDraftRow(
                        draft_id=r["draft_id"],
                        tenant_id=str(r["tenant_id"]) if r["tenant_id"] else None,
                        tool=r["tool"],
                        status=r["status"],
                        reason=r["reason"],
                        created_at=r["created_at"].isoformat() if r["created_at"] else "",
                        replayed_at=(r["replayed_at"].isoformat() if r["replayed_at"] else None),
                    )
                )
            for r in h_rows:
                hitl_rows.append(
                    TraceLinkHitlRow(
                        id=str(r["id"]),
                        tenant_id=str(r["tenant_id"]) if r["tenant_id"] else None,
                        question=r["question"],
                        confidence=(float(r["confidence"]) if r["confidence"] is not None else None),
                        flag_reason=r["flag_reason"],
                        review_status=r["review_status"],
                        reviewer_id=str(r["reviewer_id"]) if r["reviewer_id"] else None,
                        review_notes=r["review_notes"],
                        created_at=r["created_at"].isoformat() if r["created_at"] else "",
                        reviewed_at=(r["reviewed_at"].isoformat() if r["reviewed_at"] else None),
                    )
                )
        except Exception:  # noqa: BLE001 — operator visibility must
            # not crash. Surface as db_reachable=false; UI shows
            # "(governance unreachable)" rather than 500.
            db_reachable = False

    # Jaeger deep-link, only if configured. Constructs the canonical
    # search URL — Jaeger UI parses ?service=inference-svc&tags=...
    # and surfaces the trace. The operator clicks through; we don't
    # try to render spans here.
    jaeger_url: str | None = None
    base = os.getenv("DOCUMIND_JAEGER_URL", "").rstrip("/")
    if base:
        # ``correlation.id`` is the OTel attribute name we set in
        # mcp.server_common.handle_tool_call (sp.set_attribute
        # documind.correlation_id). Jaeger searches by tag.
        from urllib.parse import quote as _quote

        tag_filter = _quote(f'documind.correlation_id="{cid}"')
        jaeger_url = f"{base}/search?service=inference-svc&tags=%7B" f"%22documind.correlation_id%22%3A%22{cid}%22%7D"
        # Suppress F841 — tag_filter computed for clarity; not used
        # because Jaeger's tag-search format differs.
        _ = tag_filter

    return TraceLinkResponse(
        correlation_id=cid,
        observed_at=datetime.now(UTC).isoformat(),
        db_reachable=db_reachable,
        audit_rows=audit_rows,
        draft_rows=draft_rows,
        hitl_rows=hitl_rows,
        jaeger_url=jaeger_url,
    )


def _service(request: Request) -> RagInferenceService:
    svc = getattr(request.app.state, "rag_service", None)
    if svc is None:
        raise RuntimeError("rag_service not initialized")
    return svc


@router.post("/api/v1/ask", response_model=AskResponse, tags=["inference"])
async def ask(
    body: AskRequest,
    request: Request,
    debug: bool = Query(False, description="Include debug info in the response"),
    svc: RagInferenceService = Depends(_service),
) -> AskResponse:
    tenant_id = getattr(request.state, "tenant_id", "") or ""
    correlation_id = getattr(request.state, "correlation_id", "") or ""
    if not tenant_id:
        raise ValidationError("X-Tenant-ID header is required")
    return await svc.ask(
        tenant_id=tenant_id,
        correlation_id=correlation_id,
        request=body,
        include_debug=debug,
    )


def _agent_service(request: Request) -> AgentService:
    svc = getattr(request.app.state, "agent_service", None)
    if svc is None:
        raise RuntimeError("agent_service disabled — set DOCUMIND_MCP_HR_URL to enable the agent path")
    return svc


@router.post("/api/v1/agent/ask", response_model=AgentAskResponse, tags=["agent"])
async def agent_ask(
    body: AgentAskRequest,
    request: Request,
    svc: AgentService = Depends(_agent_service),
) -> AgentAskResponse:
    tenant_id = getattr(request.state, "tenant_id", "") or ""
    correlation_id = getattr(request.state, "correlation_id", "") or ""
    if not tenant_id:
        raise ValidationError("X-Tenant-ID header is required")
    # Forward the caller's verified JWT to MCP so the server can
    # enforce per-tool scopes defence-in-depth. Also pass through
    # roles + auth_required so the agent can pre-check scope before
    # spending MCP bandwidth on requests it knows will 403.
    auth_token = getattr(request.state, "raw_token", "") or None
    roles = list(getattr(request.state, "roles", []) or [])
    auth_required = bool(getattr(request.app.state, "auth_required", False))
    # Idempotency-Key — when a client retries (network hiccups mid-flight)
    # the same key lets MCP replay its cached response instead of
    # executing a second tool call. Case-insensitive lookup because HTTP.
    idempotency_key = request.headers.get("Idempotency-Key") or request.headers.get("X-Idempotency-Key")
    return await svc.ask(
        tenant_id=tenant_id,
        correlation_id=correlation_id,
        request=body,
        auth_token=auth_token,
        roles=roles,
        auth_required=auth_required,
        idempotency_key=idempotency_key,
    )


# ---------------------------------------------------------------------------
# HITL admin — list + resolve persisted drafts from governance.action_drafts
# ---------------------------------------------------------------------------
def _mcp_client(request: Request):
    """Dep: the MCPClient attached in the lifespan. 503 if agent disabled."""
    client = getattr(request.app.state, "mcp_client", None)
    if client is None:
        raise HTTPException(
            status_code=503,
            detail="agent_service disabled — set DOCUMIND_MCP_HR_URL to enable the HITL path",
        )
    return client


def _record_to_summary(record) -> DraftSummary:
    return DraftSummary(
        draft_id=record.draft_id,
        tool=record.tool,
        arguments=record.arguments,
        tenant_id=record.tenant_id,
        correlation_id=record.correlation_id,
        reason=record.reason,
        status=record.status,
        created_at=record.created_at,
        replayed_at=record.replayed_at,
        replay_result=record.replay_result,
    )


@router.get(
    "/api/v1/drafts",
    response_model=DraftListResponse,
    tags=["hitl"],
    summary="List pending MCP action drafts for the current tenant",
)
async def list_drafts(
    request: Request,
    status: str = Query(
        "pending",
        description="Only 'pending' is supported today; exposed for forward-compat.",
    ),
    client=Depends(_mcp_client),
) -> DraftListResponse:
    tenant_id = getattr(request.state, "tenant_id", "") or ""
    if not tenant_id:
        raise ValidationError("X-Tenant-ID header is required")
    if status != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"unsupported status filter: {status!r} (only 'pending' today)",
        )
    records = await client.list_pending_drafts(tenant_id)
    return DraftListResponse(
        drafts=[_record_to_summary(r) for r in records],
        tenant_id=tenant_id,
        status_filter=status,
    )


@router.post(
    "/api/v1/drafts/{draft_id}/resolve",
    response_model=DraftResolveResponse,
    tags=["hitl"],
    summary="Replay a pending MCP draft — uses draft_id as the idempotency key",
)
async def resolve_draft(
    draft_id: str,
    request: Request,
) -> DraftResolveResponse:
    tenant_id = getattr(request.state, "tenant_id", "") or ""
    if not tenant_id:
        raise ValidationError("X-Tenant-ID header is required")

    # Multi-namespace: pick the MCP client by the draft's tool prefix,
    # not by a hardcoded default. A pending itsm.incident_open draft
    # must be replayed against the ITSM server, not HR.
    clients: dict = getattr(request.app.state, "mcp_clients", None) or {}
    if not clients:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "AGENT_DISABLED",
                "message": "no MCP clients configured",
            },
        )

    # Two-phase scope check to avoid info leaks:
    #   (a) authenticate first — so an unauthenticated caller can't
    #       enumerate draft_ids by observing 404 vs 401 responses;
    #   (b) load the draft, derive the required role from the tool
    #       namespace, enforce *that* specific role.
    auth_required = getattr(request.app.state, "auth_required", False)
    if auth_required:
        # (a) must be authenticated — 401 before any draft lookup.
        require_roles()(request)

    # Fetch the draft via ANY client — the PostgresDraftStore is
    # shared, so any client's get_draft sees every tenant's row.
    lookup_client = next(iter(clients.values()))
    record = await lookup_client.get_draft(draft_id, tenant_id=tenant_id)
    if record is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "DRAFT_NOT_FOUND", "draft_id": draft_id},
        )

    if auth_required:
        # (b) now we know the tool, check its required role.
        role = required_role_for_tool(record.tool)
        require_roles(role)(request)

    # Route to the client for this draft's namespace. Without this,
    # an itsm.* draft resolves against hr's client and gets 404 for a
    # non-existent tool — the bug this commit closes.
    namespace = record.tool.split(".", 1)[0] if "." in record.tool else record.tool
    target = clients.get(namespace)
    if target is None:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "NO_SERVER_FOR_NAMESPACE",
                "namespace": namespace,
                "tool": record.tool,
                "message": (
                    "No MCP server configured for this namespace in this "
                    "deployment. The draft remains pending and can be "
                    "resolved once DOCUMIND_MCP_<NS>_URL is set."
                ),
            },
        )

    auth_token = getattr(request.state, "raw_token", "") or None
    # Identity-driven actor_type — NEVER infer "operator" from route shape.
    # The mapping (governance contract):
    #   verified human JWT (auth_user_id present)  -> "operator"
    #   no verified token (dev / auth_required=False) -> "system"
    # A future federated worker hitting this admin route with a service
    # token would still hit "system" here unless its sub maps to a
    # known worker — which is correct: the worker path is the loop in
    # draft_replay.py, not this handler. "Came through admin API" is
    # not the same as "performed by a human operator."
    auth_user = getattr(request.state, "auth_user_id", "") or None
    if auth_user:
        actor_type = "operator"
        actor_id = auth_user
    else:
        actor_type = "system"
        actor_id = None
    # Operator-driven replays are governance-critical. fail_closed=True
    # guarantees that if audit is unreachable, the replay surfaces a
    # 5xx instead of silently succeeding — an operator clicking
    # "Replay" deserves a visible error if the action wouldn't be
    # recorded. The autonomous worker path keeps fail_closed=False
    # so transient audit hiccups don't wedge background retries.
    audit_fail_closed = actor_type == "operator"
    result = await target.resolve_draft(
        draft_id,
        tenant_id=tenant_id,
        auth_token=auth_token,
        actor_type=actor_type,
        actor_id=actor_id,
        audit_fail_closed=audit_fail_closed,
    )
    # Error envelope from DraftStore: DRAFT_NOT_FOUND | DRAFT_NOT_PENDING
    if not result.ok and result.error and result.error.get("code") == "DRAFT_NOT_FOUND":
        raise HTTPException(status_code=404, detail=result.error)
    if not result.ok and result.error and result.error.get("code") == "DRAFT_NOT_PENDING":
        raise HTTPException(status_code=409, detail=result.error)
    return DraftResolveResponse(
        draft_id=draft_id,
        ok=result.ok,
        result=result.data,
        error=result.error,
        degraded=result.degraded,
        new_draft_id=result.draft_id if result.degraded else None,
        idempotent_replay=result.idempotent_replay,
    )


@router.post(
    "/api/v1/drafts/{draft_id}/reject",
    response_model=DraftRejectResponse,
    tags=["hitl"],
    summary="Operator-driven terminal rejection of a pending draft",
)
async def reject_draft(
    draft_id: str,
    body: DraftRejectRequest,
    request: Request,
) -> DraftRejectResponse:
    """
    Reject a pending draft. After this, the autonomous worker will skip
    the row (``list_pending`` filters on ``status='pending'``).

    Posture mirrors /resolve: operator-only when auth_required, the
    rejection audit row is fail_closed because a missing audit record
    on a governance-terminal action is exactly the gap operators need
    to see immediately.

    Returns 200 + ``status='rejected'`` on success, 404 if the draft
    doesn't exist, 409 if it's already moved (replayed by a worker, or
    rejected by another operator).
    """
    tenant_id = getattr(request.state, "tenant_id", "") or ""
    if not tenant_id:
        raise ValidationError("X-Tenant-ID header is required")

    clients: dict = getattr(request.app.state, "mcp_clients", None) or {}
    if not clients:
        raise HTTPException(
            status_code=503,
            detail={"code": "AGENT_DISABLED", "message": "no MCP clients configured"},
        )

    # Two-phase scope check — same shape as /resolve.
    auth_required = getattr(request.app.state, "auth_required", False)
    if auth_required:
        require_roles()(request)

    lookup_client = next(iter(clients.values()))
    record = await lookup_client.get_draft(draft_id, tenant_id=tenant_id)
    if record is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "DRAFT_NOT_FOUND", "draft_id": draft_id},
        )

    if auth_required:
        # Same role mapping — rejecting an hr.* draft requires hr:write.
        # A rejection is a write-side governance action, not a read.
        role = required_role_for_tool(record.tool)
        require_roles(role)(request)

    namespace = record.tool.split(".", 1)[0] if "." in record.tool else record.tool
    target = clients.get(namespace)
    if target is None:
        # Reject is intentionally MORE permissive than resolve here —
        # we don't need an MCP server to be reachable to record a
        # terminal "don't retry this" decision. But routing through
        # the namespace's client keeps the audit + DB connection paths
        # consistent. If a deployment lost its NS server, fall back to
        # any client (the DraftStore is shared).
        target = lookup_client

    auth_user = getattr(request.state, "auth_user_id", "") or None
    if auth_user:
        actor_type = "operator"
        actor_id = auth_user
    else:
        actor_type = "system"
        actor_id = None
    audit_fail_closed = actor_type == "operator"

    result = await target.reject_draft(
        draft_id,
        reason=body.reason,
        tenant_id=tenant_id,
        actor_type=actor_type,
        actor_id=actor_id,
        audit_fail_closed=audit_fail_closed,
    )

    if not result.ok and result.error and result.error.get("code") == "DRAFT_NOT_FOUND":
        raise HTTPException(status_code=404, detail=result.error)
    if not result.ok and result.error and result.error.get("code") == "DRAFT_NOT_PENDING":
        raise HTTPException(status_code=409, detail=result.error)
    return DraftRejectResponse(
        draft_id=draft_id,
        ok=result.ok,
        status=(result.data or {}).get("status"),
        reason=(result.data or {}).get("reason"),
        error=result.error,
    )
