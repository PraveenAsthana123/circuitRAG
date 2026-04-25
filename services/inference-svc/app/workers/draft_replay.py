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
from typing import Any

log = logging.getLogger(__name__)


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

    _draft_replay_total = _PromCounter(
        "documind_draft_replay_total",
        "Draft replay attempts by the autonomous worker, labelled by "
        "MCP namespace and outcome.",
        labelnames=["namespace", "outcome"],
    )
except ImportError:  # pragma: no cover — prometheus_client is optional
    _draft_replay_total = None


def _bump(namespace: str, outcome: str) -> None:
    """Increment the worker counter; no-op if prometheus_client missing."""
    if _draft_replay_total is not None:
        _draft_replay_total.labels(namespace=namespace, outcome=outcome).inc()


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
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._last_attempt: dict[str, float] = {}
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
        except asyncio.TimeoutError:
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
            except asyncio.TimeoutError:
                pass  # interval elapsed → next cycle

    async def _sweep(self) -> None:
        self.stats["cycles"] += 1
        now = time.monotonic()
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
                    # 4xx-shaped failure that didn't degrade. Surfaces
                    # NOT_AUTHENTICATED, INSUFFICIENT_SCOPE, etc.
                    _bump(namespace, "failed")
                    log.warning(
                        "draft_replay_failed draft_id=%s namespace=%s err=%s",
                        draft.draft_id, namespace, result.error,
                    )
