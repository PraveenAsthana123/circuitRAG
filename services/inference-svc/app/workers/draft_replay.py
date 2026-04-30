"""
Draft replay worker — periodically resolves pending MCP drafts.

Design
------
This is the autonomous counterpart to the admin API. Operators can still
hit ``POST /api/v1/drafts/{id}/resolve`` manually; the worker just
automates the common case ("MCP was down, it's back, go through the
backlog and try again").

The worker runs as an ``asyncio.Task`` attached to the inference-svc
lifespan. Every ``interval_s`` seconds it walks the configured tenant
list, asks the :class:`MCPClient` for that tenant's pending drafts,
and replays one at a time. If the first replay comes back ``degraded``
(MCP still unreachable), the worker bails out for this cycle — no
point hammering further rows when the downstream is visibly down.

Per-draft backoff
~~~~~~~~~~~~~~~~~
A small in-memory ``{draft_id: last_attempt_monotonic}`` map prevents
the worker from retrying the same draft every tick. If MCP is flapping,
a draft that failed 5s ago would otherwise be tried on every cycle —
``per_draft_backoff_s`` enforces a minimum gap.

Why not push this into the client or the store?
  * The client should stay synchronous-on-request — adding a scheduler
    there would couple tool calls to retry state.
  * The store is passive.
  * The worker is the *policy* layer; client + store are mechanism.

Tenant enumeration
~~~~~~~~~~~~~~~~~~
We require the tenant list via config rather than discovering it
(``documind_app`` is NOBYPASSRLS; listing tenants means crossing the
isolation boundary, which is a governance decision). In production a
separate "tenants to sweep" feed — identity-svc, a feature flag — fills
it in. Today, a comma-separated env var is enough.

Env config (read by the lifespan, not by this module):
  DOCUMIND_REPLAY_WORKER_ENABLED  -- "true" to start the loop
  DOCUMIND_REPLAY_WORKER_TENANTS  -- CSV of UUIDs
  DOCUMIND_REPLAY_WORKER_INTERVAL_S (default 20)
  DOCUMIND_REPLAY_WORKER_BACKOFF_S  (default 60)
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from contextlib import nullcontext
from typing import Any

log = logging.getLogger(__name__)


# OTel — guarded import so the worker still runs when the SDK is
# unavailable. ``_TRACER`` is None in that case and the wrappers
# below collapse to a nullcontext, so the sweep never sprouts a
# branch like "did we instrument this?" in business code.
try:
    from opentelemetry import trace as _otel_trace

    _TRACER = _otel_trace.get_tracer(__name__)
    _OTEL_AVAILABLE = True
except ImportError:  # pragma: no cover
    _TRACER = None
    _OTEL_AVAILABLE = False


def _sweep_span(correlation_id: str, tenant_count: int) -> Any:
    """
    Open a span around the worker sweep cycle, or a nullcontext
    when OTel is unavailable. Span carries:

      documind.correlation_id  — uuid per sweep, links log lines
      worker.tenant_count      — how many tenants this sweep covered
      worker.kind              — ``"draft_replay"``

    Per-namespace and per-draft details land on log lines + the
    existing Prometheus counters; the span is the trace seam that
    makes those signals queryable as a unit in Jaeger.
    """
    if _TRACER is None:
        return nullcontext()
    span_cm = _TRACER.start_as_current_span("draft_replay.sweep")

    class _SpanWrap:
        def __enter__(self):
            self._sp = span_cm.__enter__()
            try:
                self._sp.set_attribute("documind.correlation_id", correlation_id)
                self._sp.set_attribute("worker.tenant_count", int(tenant_count))
                self._sp.set_attribute("worker.kind", "draft_replay")
            except Exception:  # noqa: BLE001, S110 — never let span attributes break the sweep
                pass
            return self._sp

        def __exit__(self, exc_type, exc, tb):
            return span_cm.__exit__(exc_type, exc, tb)

    return _SpanWrap()


# Prometheus metric for the autonomous worker. The pre-existing
# ``self.stats`` dict gave per-instance introspection, but production
# operators needed a graphable signal. One counter with two labels
# keeps cardinality bounded (finite namespace × finite outcome set)
# and lets a single PromQL query answer the operational questions:
#   * How many drafts is the worker actually completing?
#     sum(rate(documind_draft_replay_total{outcome="replayed"}[5m]))
#   * Is a namespace's CB stuck open (worker tries blocked)?
#     rate(...{outcome="cb_wait", namespace="hr"}[5m])
#   * Is the worker running into systematic errors?
#     rate(...{outcome="error"}[5m])
try:
    from prometheus_client import Counter as _PromCounter
    from prometheus_client import Gauge as _PromGauge

    _draft_replay_total = _PromCounter(
        "documind_draft_replay_total",
        "Draft replay attempts by the autonomous worker, labelled by "
        "MCP namespace and outcome.",
        labelnames=["namespace", "outcome"],
    )
    # Backlog-age gauge — surfaces the slow-leak case the auto-reject
    # threshold doesn't catch. A draft hitting cb_wait or
    # skipped_backoff repeatedly never increments the consecutive-
    # failure counter, so it never auto-rejects, but it also never
    # gets replayed. Without this metric an operator wouldn't notice
    # the queue ageing.
    #
    # PromQL recipes:
    #   max by(namespace) (documind_draft_pending_age_seconds)
    #     → "what's the oldest draft I have, per namespace?"
    #   max(documind_draft_pending_age_seconds) > 3600
    #     → alert: any draft older than an hour
    #
    # Cardinality bound: namespace count is finite + small (one per
    # MCP server). Tenant is intentionally NOT a label — a future
    # multi-tenant deployment can add a second gauge with quantized
    # tenant buckets if cross-tenant breakdown is needed; for now
    # the per-namespace dimension is enough to trigger an alert.
    _draft_pending_age_seconds = _PromGauge(
        "documind_draft_pending_age_seconds",
        "Age of the oldest pending draft per MCP namespace, in seconds. "
        "Updated each sweep cycle.",
        labelnames=["namespace"],
    )
except ImportError:  # pragma: no cover — prometheus_client is optional
    _draft_replay_total = None
    _draft_pending_age_seconds = None


def _bump(namespace: str, outcome: str) -> None:
    """Increment the worker counter; no-op if prometheus_client missing."""
    if _draft_replay_total is not None:
        _draft_replay_total.labels(namespace=namespace, outcome=outcome).inc()


def _set_pending_age(namespace: str, age_seconds: float) -> None:
    """Set the per-namespace oldest-pending-draft gauge."""
    if _draft_pending_age_seconds is not None:
        _draft_pending_age_seconds.labels(namespace=namespace).set(age_seconds)


def _cb_state(client: Any) -> str | None:
    """Read the MCP client's breaker state if exposed, else None."""
    state = getattr(client, "cb_state", None)
    if state is None:
        return None
    # Support both string and Enum-like state objects.
    value = getattr(state, "value", None)
    return value if value is not None else str(state)


class DraftReplayWorker:
    def __init__(
        self,
        *,
        mcp_client: Any = None,
        mcp_clients: dict[str, Any] | None = None,
        tenant_ids: list[str],
        interval_s: int = 20,
        per_draft_backoff_s: int = 60,
        skip_when_cb_open: bool = True,
        service_auth_token: str | None = None,
        service_actor_id: str | None = None,
        auto_reject_threshold: int = 5,
    ) -> None:
        # mcp_clients (preferred) is a namespace→client dict so the
        # worker can route each draft to the server that owns its
        # tool. mcp_client (single) is kept for back-compat and
        # auto-wrapped as {"hr": client}.
        if mcp_clients is None:
            mcp_clients = {"hr": mcp_client} if mcp_client is not None else {}
        self._clients: dict[str, Any] = {k: v for k, v in mcp_clients.items() if v is not None}
        if not self._clients:
            raise ValueError(
                "DraftReplayWorker needs at least one MCPClient; "
                "pass mcp_clients={namespace: client} or mcp_client=single."
            )
        self._tenants = list(tenant_ids)
        self._interval = max(1, interval_s)
        self._backoff = max(1, per_draft_backoff_s)
        # When True, a draft's sweep-attempt is skipped if its target
        # client's CB is OPEN — per-namespace gate. Without this, a
        # cycle with both hr (closed) and itsm (open) would sleep the
        # whole cycle instead of making progress on hr drafts.
        self._skip_when_cb_open = skip_when_cb_open
        # Service-account JWT to forward to MCP. The autonomous worker
        # has no human caller to inherit a token from, so a deployment
        # with MCP_AUTH_REQUIRED=true MUST inject one (env var picked up
        # in the lifespan). Without it every replay 401s and the audit
        # log fills with NOT_AUTHENTICATED while drafts pile up — a
        # silent operational failure mode that the previous version had.
        self._service_auth_token = service_auth_token
        # ``service_actor_id`` is the ``sub`` claim of the service token,
        # decoded once in the lifespan. We forward it as actor_id on the
        # audit row so governance can answer "WHICH service account
        # replayed this draft?" — a different worker per environment
        # (staging vs prod replay sweeper) shows up as a different
        # actor_id under the same actor_type="worker".
        self._service_actor_id = service_actor_id
        # Permanent-failure detection. The worker tracks consecutive
        # 4xx/business-rejection failures per draft; once the count
        # reaches ``auto_reject_threshold``, the draft is auto-rejected
        # with a ``worker``-actored audit row instead of cycling
        # forever. This closes the "MCP returns internal_error
        # because the draft has malformed arguments → worker retries
        # every backoff window for eternity" failure mode.
        #
        # Threshold is heuristic — a transient 4xx-shaped error
        # (e.g. tool returning ok=false because of an external
        # service hiccup) gets a few retries before being marked
        # terminal. Set to 0 to disable (worker keeps retrying).
        self._auto_reject_threshold = max(0, int(auto_reject_threshold))
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._last_attempt: dict[str, float] = {}
        # Per-draft consecutive-failure counter. Only carries entries
        # for drafts that have failed at least once; a successful
        # replay transitions the draft out of pending so we never see
        # it again — bounded growth.
        self._consecutive_failures: dict[str, int] = {}
        # Observable counters — useful in tests + metrics later.
        self.stats = {
            "cycles": 0,
            "replayed": 0,
            "skipped_backoff": 0,
            "cb_wait_skips": 0,       # per-draft, not per-cycle anymore
            "degraded_bailouts": 0,   # per-namespace, not per-cycle
            "no_server_skips": 0,     # draft has no client for its namespace
            "errors": 0,
        }

    def _client_for(self, tool: str) -> Any:
        namespace = tool.split(".", 1)[0] if "." in tool else tool
        return self._clients.get(namespace)

    async def start(self) -> None:
        if self._task is not None:
            return
        log.info(
            "draft_replay_worker_start tenants=%d interval=%ds backoff=%ds",
            len(self._tenants), self._interval, self._backoff,
        )
        self._stop.clear()
        self._task = asyncio.create_task(self._loop(), name="draft_replay_worker")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stop.set()
        try:
            await asyncio.wait_for(self._task, timeout=self._interval + 5)
        except TimeoutError:
            self._task.cancel()
        self._task = None
        log.info("draft_replay_worker_stopped stats=%s", self.stats)

    async def sweep_once(self) -> None:
        """Run a single cycle — exposed for tests that want deterministic ticks."""
        await self._sweep()

    async def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                await self._sweep()
            except Exception as exc:  # noqa: BLE001
                self.stats["errors"] += 1
                # Cycle-level failure (sweep itself blew up before
                # reaching any namespace). ``__cycle__`` label keeps
                # this distinct from per-namespace error counts so
                # dashboards can alert on "worker is fundamentally
                # broken" vs "one namespace flaking."
                _bump("__cycle__", "error")
                log.error("draft_replay_worker_cycle_failed err=%s", exc)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._interval)
            except TimeoutError:
                pass  # interval elapsed → next cycle

    async def _sweep(self) -> None:
        # Per-sweep correlation_id stamps the span + every log line
        # in this cycle, so a Jaeger trace and the structured logs
        # can be cross-joined. Same convention as the rest of the
        # codebase — see ADR-007 (identity-driven attribution) for
        # how correlation flows downstream.
        sweep_correlation_id = uuid.uuid4().hex
        with _sweep_span(sweep_correlation_id, len(self._tenants)):
            await self._sweep_inner(sweep_correlation_id)

    async def _sweep_inner(self, sweep_correlation_id: str) -> None:
        self.stats["cycles"] += 1
        now = time.monotonic()
        # Wall-clock for draft-age computation. ``time.monotonic()``
        # above is for elapsed-since-last-attempt (immune to clock
        # drift); ``wall_now`` is for "how old is this draft" against
        # the row's ``created_at`` epoch.
        wall_now = time.time()
        # Per-namespace max age, computed across ALL tenants in this
        # sweep. The gauge is set once per namespace at sweep end so
        # an empty queue resets the gauge to 0 (otherwise a stale
        # value from a previous cycle lingers forever and triggers
        # phantom alerts).
        oldest_age_per_namespace: dict[str, float] = {}
        # list_pending_drafts works through any client because the
        # PostgresDraftStore is shared across clients. Use the first
        # one arbitrarily as the reader; routing happens per-draft.
        reader = next(iter(self._clients.values()))
        # Track per-namespace bailout: if one namespace's client is
        # degraded, stop processing THAT namespace's drafts this cycle
        # but keep processing others. A global bail-out across all
        # namespaces would lose independence on MCP outages.
        bailed: set[str] = set()

        for tenant in self._tenants:
            try:
                drafts = await reader.list_pending_drafts(tenant)
            except Exception as exc:  # noqa: BLE001
                self.stats["errors"] += 1
                # Tenant enumeration failure isn't tied to a specific
                # namespace; label it ``__list__`` so dashboards
                # distinguish "the worker can't even read drafts" from
                # per-namespace replay failures.
                _bump("__list__", "error")
                log.error("draft_replay_list_failed tenant=%s err=%s", tenant, exc)
                continue
            if not drafts:
                continue
            log.info(
                "draft_replay_sweep tenant=%s pending=%d", tenant, len(drafts),
            )
            # Pre-scan: compute oldest age per namespace BEFORE the
            # per-draft loop. The loop short-circuits on ``bailed``,
            # so doing this inline would miss drafts in degraded
            # namespaces — exactly the namespaces an operator most
            # wants to watch ageing.
            for draft in drafts:
                ns = (
                    draft.tool.split(".", 1)[0] if "." in draft.tool else draft.tool
                )
                age = max(0.0, wall_now - float(draft.created_at))
                if age > oldest_age_per_namespace.get(ns, 0.0):
                    oldest_age_per_namespace[ns] = age
            for draft in drafts:
                namespace = (
                    draft.tool.split(".", 1)[0] if "." in draft.tool else draft.tool
                )
                if namespace in bailed:
                    # Already decided to skip this namespace this cycle
                    continue

                client = self._client_for(draft.tool)
                if client is None:
                    self.stats["no_server_skips"] += 1
                    _bump(namespace, "no_server")
                    log.info(
                        "draft_replay_no_server draft_id=%s namespace=%s — leaving pending",
                        draft.draft_id, namespace,
                    )
                    continue

                # Per-draft CB fast-path keyed by THIS draft's target
                # client. A draft targeting a closed-CB namespace runs
                # even when another namespace's CB is open.
                if self._skip_when_cb_open and _cb_state(client) == "open":
                    self.stats["cb_wait_skips"] += 1
                    _bump(namespace, "cb_wait")
                    log.info(
                        "draft_replay_cb_wait draft_id=%s namespace=%s cb=open",
                        draft.draft_id, namespace,
                    )
                    continue

                last = self._last_attempt.get(draft.draft_id, 0.0)
                if now - last < self._backoff:
                    self.stats["skipped_backoff"] += 1
                    _bump(namespace, "skipped_backoff")
                    continue
                self._last_attempt[draft.draft_id] = now
                try:
                    result = await client.resolve_draft(
                        draft.draft_id, tenant_id=tenant,
                        actor_type="worker",  # governance-visible; not "service"
                        actor_id=self._service_actor_id,
                        auth_token=self._service_auth_token,
                    )
                except Exception as exc:  # noqa: BLE001
                    self.stats["errors"] += 1
                    _bump(namespace, "error")
                    log.error(
                        "draft_replay_call_failed draft_id=%s namespace=%s err=%s",
                        draft.draft_id, namespace, exc,
                    )
                    continue
                if result.ok:
                    self.stats["replayed"] += 1
                    _bump(namespace, "replayed")
                    ticket = (result.data or {}).get("ticket_id") or (
                        result.data or {}
                    ).get("incident_id")
                    log.info(
                        "draft_replayed_by_worker draft_id=%s tenant=%s namespace=%s ticket=%s",
                        draft.draft_id, tenant, namespace, ticket,
                    )
                elif result.degraded:
                    # Namespace-scoped bailout: skip remaining drafts
                    # for THIS namespace this cycle. Other namespaces
                    # keep being processed in the outer loop.
                    self.stats["degraded_bailouts"] += 1
                    _bump(namespace, "degraded")
                    bailed.add(namespace)
                    log.info(
                        "draft_replay_namespace_down draft_id=%s namespace=%s "
                        "— skipping rest of this namespace's drafts this cycle",
                        draft.draft_id, namespace,
                    )
                else:
                    # 4xx-shaped failure or business rejection that
                    # didn't degrade. Surfaces NOT_AUTHENTICATED,
                    # INSUFFICIENT_SCOPE, internal_error from a
                    # KeyError-y tool handler, etc. Track per-draft
                    # consecutive count; auto-reject past threshold so
                    # permanent failures don't loop forever.
                    _bump(namespace, "failed")
                    log.warning(
                        "draft_replay_failed draft_id=%s namespace=%s err=%s",
                        draft.draft_id, namespace, result.error,
                    )
                    if self._auto_reject_threshold > 0:
                        prev = self._consecutive_failures.get(draft.draft_id, 0)
                        new_count = prev + 1
                        self._consecutive_failures[draft.draft_id] = new_count
                        if new_count >= self._auto_reject_threshold:
                            await self._auto_reject(
                                client, draft, tenant, namespace, result.error,
                            )

        # Set the backlog-age gauge for EVERY known namespace — not
        # just the ones with pending drafts this cycle. A namespace
        # whose queue drained should drop to 0; otherwise the gauge
        # stays at the last-seen value and triggers phantom alerts
        # forever.
        for ns in self._clients:
            _set_pending_age(ns, oldest_age_per_namespace.get(ns, 0.0))

    async def _auto_reject(
        self,
        client: Any,
        draft: Any,
        tenant: str,
        namespace: str,
        last_error: dict[str, Any] | None,
    ) -> None:
        """
        Terminal auto-rejection of a draft after ``auto_reject_threshold``
        consecutive failures. Marks the row 'rejected' with a system-
        generated reason, so:
          * The worker stops attempting it (list_pending filters
            status='pending').
          * Operators reviewing audit see WHY it stopped — a permanent
            failure that needs human attention, not a silent abandon.
          * The metric ``outcome="auto_rejected"`` makes the spike
            graphable so a flood of auto-rejections triggers an
            on-call alert (often the symptom of an upstream regression
            that's poisoning every retry).

        Uses ``actor_type="worker"`` and the worker's service-account
        actor_id — same attribution as a successful worker replay,
        but with the rejection action.

        ``audit_fail_closed=False`` (default): if audit is unreachable,
        the metric still moves and a structured log emits, but we
        don't crash the sweep. The draft DB transition is the
        load-bearing thing; the audit row is best-effort here.
        """
        reason = (
            f"auto-rejected by worker after {self._consecutive_failures.get(draft.draft_id, 0)} "
            f"consecutive failures; last error: {last_error}"
        )
        try:
            result = await client.reject_draft(
                draft.draft_id,
                reason=reason,
                tenant_id=tenant,
                actor_type="worker",
                actor_id=self._service_actor_id,
            )
        except Exception as exc:  # noqa: BLE001 — auto-reject must never wedge sweep
            log.error(
                "draft_auto_reject_call_failed draft_id=%s namespace=%s err=%s",
                draft.draft_id, namespace, exc,
            )
            return

        if result.ok:
            _bump(namespace, "auto_rejected")
            log.warning(
                "draft_auto_rejected draft_id=%s namespace=%s threshold=%d reason=%r",
                draft.draft_id, namespace, self._auto_reject_threshold, reason,
            )
            # Cleanup the per-draft counter so an operator manually
            # reopening this draft id (rare, requires DB intervention)
            # would start fresh. Bounded growth is the main goal —
            # the dict only carries failed-count for currently-pending
            # drafts.
            self._consecutive_failures.pop(draft.draft_id, None)
        else:
            # CAS lost — another actor moved this draft between our
            # read and reject (an operator clicking reject, or a
            # parallel worker). Log + carry on; we'll see the next
            # cycle whether the draft is gone.
            log.info(
                "draft_auto_reject_lost_race draft_id=%s namespace=%s err=%s",
                draft.draft_id, namespace, result.error,
            )
