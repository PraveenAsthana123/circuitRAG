"""
Structured logging (Design Area 62 — Observability by Design).

Every log line emitted by a DocuMind Python service should:

1. Be **JSON** (one object per line) so Loki / CloudWatch / whatever can
   parse it without regex gymnastics.
2. Carry a ``correlation_id`` so a single user request can be traced across
   services, Kafka events, and database queries.
3. Include ``tenant_id`` whenever a request is in scope — so support can
   filter a tenant's logs without grepping for their UUID.
4. Include ``service_name`` so logs from multiple services in one log stream
   are distinguishable.
5. Include the span + trace IDs from OpenTelemetry so logs link to traces
   in Jaeger with one click.

Never call ``print()`` or ``logging.basicConfig()`` in a DocuMind service —
both bypass this infrastructure.

Usage::

    from documind_core.logging_config import setup_logging, get_logger

    setup_logging(service_name="ingestion-svc", level="INFO", json_format=True)
    log = get_logger(__name__)
    log.info("document_uploaded", document_id=str(doc_id), size_bytes=len(body))
"""

from __future__ import annotations

import logging
import sys
from contextvars import ContextVar
from typing import Any

import structlog
from structlog.stdlib import BoundLogger
from structlog.types import EventDict, Processor

# ContextVar so correlation + tenant propagate across async boundaries.
# Middleware sets these; all log calls pick them up automatically.
correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")
tenant_id_var: ContextVar[str] = ContextVar("tenant_id", default="")
user_id_var: ContextVar[str] = ContextVar("user_id", default="")


def _inject_context(_logger: Any, _name: str, event_dict: EventDict) -> EventDict:
    """structlog processor: stamp every event with request-scoped context."""
    if (cid := correlation_id_var.get()) and "correlation_id" not in event_dict:
        event_dict["correlation_id"] = cid
    if (tid := tenant_id_var.get()) and "tenant_id" not in event_dict:
        event_dict["tenant_id"] = tid
    if (uid := user_id_var.get()) and "user_id" not in event_dict:
        event_dict["user_id"] = uid
    return event_dict


def _inject_otel_trace(_logger: Any, _name: str, event_dict: EventDict) -> EventDict:
    """Link logs to traces: add ``trace_id`` + ``span_id`` from the current span."""
    try:
        from opentelemetry import trace  # local import: no hard dependency
    except ImportError:  # pragma: no cover — optional
        return event_dict

    span = trace.get_current_span()
    ctx = span.get_span_context() if span else None
    if ctx and ctx.is_valid:
        event_dict["trace_id"] = format(ctx.trace_id, "032x")
        event_dict["span_id"] = format(ctx.span_id, "016x")
    return event_dict


def _inject_baggage(_logger: Any, _name: str, event_dict: EventDict) -> EventDict:
    """structlog processor: add ALL W3C baggage entries to every event.

    Composes with :func:`_inject_context` (which uses contextvars set by
    :func:`bind_request_context` in middleware). Handles paths where
    ``bind_request_context`` isn't called:

    * Kafka consumers waking on a message that came with baggage headers
      (after manual ``extract_propagation_context`` per
      ``mcp/server_common``).
    * ``asyncio.create_task(... context=context.copy())`` spawned from
      a request scope — baggage flows; bind_request_context typically
      doesn't follow.
    * Background workers receiving baggage from outbound httpx calls
      auto-instrumented by :class:`HTTPXClientInstrumentor`.

    Why this is separate from ``_inject_context``: contextvars are a
    Python primitive (set by our middleware); baggage is an OTel
    primitive (set by the propagator + middleware OR by upstream
    services via the ``baggage`` HTTP header). Both should land in
    the log; collision policy = explicit log fields win, then
    contextvars, then baggage. Order matters.

    No-op when OTel SDK isn't installed.
    """
    try:
        from opentelemetry import baggage as _otel_baggage
    except ImportError:  # pragma: no cover — optional
        return event_dict

    # _inject_context runs BEFORE this in the processor chain (see
    # setup_logging shared list). Anything it set wins; baggage fills
    # in the gaps. Explicit log fields (passed by the caller) also win
    # because they're already in event_dict before processors run.
    for key, value in _otel_baggage.get_all().items():
        if key not in event_dict:
            event_dict[key] = str(value)
    return event_dict


def _rename_event_to_message(_logger: Any, _name: str, event_dict: EventDict) -> EventDict:
    """structlog uses 'event' as the main field; JSON consumers expect 'message'."""
    if "event" in event_dict:
        event_dict["message"] = event_dict.pop("event")
    return event_dict


def setup_logging(
    *,
    service_name: str,
    level: str = "INFO",
    json_format: bool = True,
) -> None:
    """
    Configure the root logger and structlog.

    Call this ONCE at service startup (typically in ``app/main.py`` before
    any other module is imported). Calling multiple times is safe
    (idempotent) but pointless.
    """
    # Quiet noisy third-party libraries — their DEBUG output floods the logs
    # without being useful for DocuMind-specific work.
    for noisy in ("httpx", "httpcore", "uvicorn.access", "asyncio", "kafka"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    shared: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        _inject_context,
        _inject_otel_trace,
        _inject_baggage,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _rename_event_to_message,
    ]

    renderer: Processor
    if json_format:
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=shared + [renderer],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Pipe the stdlib logging root into structlog so libraries that use
    # ``logging.getLogger()`` also produce structured JSON.
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))  # structlog already renders JSON
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())

    # Stamp service_name on every event — via structlog's initial context.
    structlog.contextvars.bind_contextvars(service_name=service_name)


def get_logger(name: str) -> BoundLogger:
    """Return a structlog BoundLogger for the given module name."""
    return structlog.stdlib.get_logger(name)


# ---------------------------------------------------------------------------
# Context helpers — called by middleware on request entry / exit
# ---------------------------------------------------------------------------
def bind_request_context(
    *,
    correlation_id: str,
    tenant_id: str = "",
    user_id: str = "",
) -> None:
    """Set the per-request context vars — propagates to every log line."""
    correlation_id_var.set(correlation_id)
    if tenant_id:
        tenant_id_var.set(tenant_id)
    if user_id:
        user_id_var.set(user_id)


def clear_request_context() -> None:
    """Reset context vars. Call at the end of a request."""
    correlation_id_var.set("")
    tenant_id_var.set("")
    user_id_var.set("")
