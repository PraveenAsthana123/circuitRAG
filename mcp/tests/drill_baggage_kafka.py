#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: Kafka producer + consumer carry W3C trace context + baggage.

Composes with:
- drill_baggage_propagation (helper API contract)
- drill_baggage_middleware (FastAPI middleware producer)
- drill_baggage_log_formatter (structlog consumer)
This one closes the Kafka leg.

The propagator + helpers ship trace context across HTTP via
HTTPXClientInstrumentor (commit f8f0ba5). Kafka is NOT auto-
instrumented; without explicit inject/extract on producer/consumer,
async event flows lose tenant_id / user_id / request_id at the
boundary. Commit landing alongside this drill wires:
  * EventProducer.publish — appends traceparent + baggage to
    message headers
  * IdempotentConsumer._handle_one — extracts on receive, attaches
    to OTel context for the handler call, detaches in finally

Three exercised steps in this local drill shape:

 1. _inject_kafka_headers + _extract_kafka_context exist + are used by
    EventProducer.publish + IdempotentConsumer._handle_one (source scan).
 2. Inject — set baggage in current OTel context, then call
    _inject_kafka_headers on a fresh list. List MUST contain
    traceparent + baggage entries with the expected baggage value
    encoded as bytes.
 3. Extract round-trip — take the list from step 2, attach via
    _extract_kafka_context. Inside the attached context,
    baggage_get("tenant_id") must return the value.
 4. NEGATIVE: Empty headers (msg.headers = None) returns None token,
    no attach, no crash. Consumer must keep working when a producer
    didn't inject (e.g. legacy publisher OR producer running without
    OTel SDK).
 5. NEGATIVE: A non-UTF-8 header byte sequence MUST NOT crash the
    extract path; it should be skipped + logged. A single bad
    domain header must not poison propagation for the rest.
 6. NEGATIVE: After detach, baggage_get returns the value the parent
    context had (None when no parent baggage) — context isolation
    holds across the Kafka boundary same as it does across HTTP.

Run:
    PYTHONPATH=/tmp/baggage_test_stubs:/mnt/deepa/rag \\
        .venv-tts/bin/python3 mcp/tests/drill_baggage_kafka.py
"""
from __future__ import annotations

import sys
from pathlib import Path


def green(msg: str) -> None:
    print(f"\033[32m✓\033[0m {msg}")


def red(msg: str) -> None:
    print(f"\033[31m✗\033[0m {msg}")


def yellow(msg: str) -> None:
    print(f"\033[33m⚠\033[0m {msg}")


def main() -> int:
    failed = 0
    total = 6
    repo = Path("/mnt/deepa/rag")

    # ── Step 1 ───────────────────────────────────────────────────
    print("\n[1/6] Helpers exist + are wired into EventProducer + IdempotentConsumer")
    try:
        src = (repo / "libs/py/documind_core/kafka_client.py").read_text()
        for name in ("_inject_kafka_headers", "_extract_kafka_context"):
            assert f"def {name}" in src, f"helper {name} missing"
        # Producer wires inject
        assert "_inject_kafka_headers(headers)" in src, (
            "EventProducer.publish does NOT call _inject_kafka_headers — "
            "without it, every published message LOSES baggage"
        )
        # Consumer wires extract + detach
        assert "_extract_kafka_context(msg.headers)" in src, (
            "IdempotentConsumer._handle_one does NOT call _extract_kafka_context — "
            "without it, every consumed message HANDLER runs in a context that "
            "lost tenant_id + correlation_id"
        )
        assert "_otel_context.detach(token)" in src, (
            "consumer does not detach the attached OTel context — leaks across "
            "messages within the consumer's poll loop"
        )
        # Graceful OTel-missing degradation
        assert "_OTEL_AVAILABLE" in src, "no OTel-missing fallback path"
        green("helpers defined + producer + consumer wired + degradation flag present")
    except Exception as exc:  # noqa: BLE001
        red(f"step 1 failed: {exc}")
        failed += 1

    # ── OTel availability gate ───────────────────────────────────
    try:
        from opentelemetry import baggage as _bag  # noqa: F401
        otel_present = True
    except ImportError:
        otel_present = False

    if not otel_present:
        yellow("opentelemetry SDK not installed locally; remaining steps "
               "require it. CI containers run the full drill.")
        return 0 if failed == 0 else 1

    sys.path.insert(0, str(repo / "libs/py"))

    # ── Step 2 ───────────────────────────────────────────────────
    print("\n[2/6] Inject — baggage in current context appears in Kafka headers")
    try:
        from opentelemetry import baggage as _ot_baggage
        from opentelemetry import context as _ot_context

        # Need the CompositePropagator (TraceContext + Baggage) globally
        # set, or the inject path won't emit a baggage header. Wire it
        # explicitly — same call mcp.server_common.setup_server_otel makes.
        from opentelemetry.baggage.propagation import W3CBaggagePropagator
        from opentelemetry.propagate import set_global_textmap
        from opentelemetry.propagators.composite import CompositePropagator
        from opentelemetry.trace.propagation.tracecontext import (
            TraceContextTextMapPropagator,
        )
        set_global_textmap(CompositePropagator([
            TraceContextTextMapPropagator(),
            W3CBaggagePropagator(),
        ]))

        # Try to import _inject_kafka_headers; this triggers the docu-
        # mind_core.kafka_client module which in turn imports aiokafka.
        # If aiokafka is not installed, we source-scan instead so the
        # drill still validates wiring without needing the full env.
        try:
            from documind_core.kafka_client import _inject_kafka_headers
            inject_callable = _inject_kafka_headers
        except ImportError as exc:
            yellow(f"aiokafka not installed locally ({exc}); "
                   "step 2-6 source-scan only")
            return 0 if failed == 0 else 1

        # Need an active span for the W3C TraceContext propagator to
        # emit a `traceparent` header — propagators read the current
        # span context, and a NoOpSpan emits nothing. Set up a real
        # tracer + span for the inject test. Baggage propagator emits
        # independent of trace state, but a complete drill verifies
        # BOTH legs of the CompositePropagator.
        from opentelemetry import trace as _ot_trace
        from opentelemetry.sdk.trace import TracerProvider
        _ot_trace.set_tracer_provider(TracerProvider())
        tracer = _ot_trace.get_tracer("drill")

        ctx = _ot_baggage.set_baggage("tenant_id", "acme-prod")
        ctx = _ot_baggage.set_baggage("request_id", "req-kafka-1", context=ctx)
        token = _ot_context.attach(ctx)
        try:
            with tracer.start_as_current_span("kafka-publish"):
                headers: list[tuple[str, bytes]] = [
                    ("id", b"some-uuid"),
                    ("tenantid", b"acme-prod"),
                ]
                inject_callable(headers)
                keys = {k for k, _ in headers}
                assert "traceparent" in keys, (
                    f"traceparent MISSING from Kafka headers after inject "
                    f"(inside an active span): {headers}. CompositePropagator "
                    f"with TraceContext should emit traceparent for any "
                    f"valid current span."
                )
                assert "baggage" in keys, (
                    f"baggage MISSING from Kafka headers after inject: {headers}"
                )
                bag_val = next(v for k, v in headers if k == "baggage")
                assert b"tenant_id=acme-prod" in bag_val, (
                    f"tenant_id missing from baggage value: {bag_val!r}"
                )
                assert b"request_id=req-kafka-1" in bag_val, (
                    f"request_id missing from baggage value: {bag_val!r}"
                )
        finally:
            _ot_context.detach(token)
        green(f"both traceparent + baggage encoded into Kafka headers: "
              f"baggage={bag_val!r}")
    except AssertionError as exc:
        red(str(exc))
        failed += 1
    except Exception as exc:  # noqa: BLE001
        red(f"step 2 failed: {exc!r}")
        failed += 1

    # ── Step 3 ───────────────────────────────────────────────────
    print("\n[3/6] Round-trip — extract from Kafka headers restores baggage in handler")
    try:
        from documind_core.kafka_client import (
            _extract_kafka_context,
            _inject_kafka_headers,
        )
        from opentelemetry import baggage as _ot_baggage
        from opentelemetry import context as _ot_context

        # Producer side: set baggage + inject into a fresh headers list
        ctx = _ot_baggage.set_baggage("tenant_id", "acme-prod")
        ctx = _ot_baggage.set_baggage("user_id", "u-7", context=ctx)
        token_a = _ot_context.attach(ctx)
        producer_headers: list[tuple[str, bytes]] = [
            ("id", b"some-uuid"),
            ("type", b"document.uploaded"),
        ]
        _inject_kafka_headers(producer_headers)
        _ot_context.detach(token_a)

        # Consumer side: simulate IdempotentConsumer._handle_one — extract
        # from msg.headers, then run the handler in the new context.
        # Outside the attached context, baggage MUST NOT have these
        # entries (we just detached the producer's context).
        assert _ot_baggage.get_baggage("tenant_id") is None, (
            "test setup wrong — parent context already has tenant_id baggage"
        )

        token_b = _extract_kafka_context(producer_headers)
        try:
            assert _ot_baggage.get_baggage("tenant_id") == "acme-prod", (
                f"tenant_id NOT restored on consumer side: "
                f"got {_ot_baggage.get_baggage('tenant_id')!r}"
            )
            assert _ot_baggage.get_baggage("user_id") == "u-7", (
                f"user_id NOT restored: got {_ot_baggage.get_baggage('user_id')!r}"
            )
        finally:
            if token_b is not None:
                _ot_context.detach(token_b)
        green("Kafka round-trip — baggage tenant_id + user_id restored on consumer side")
    except AssertionError as exc:
        red(str(exc))
        failed += 1
    except Exception as exc:  # noqa: BLE001
        red(f"step 3 failed: {exc!r}")
        failed += 1

    # ── Step 4: NEGATIVE — None headers handled ──────────────────
    print("\n[4/6] NEGATIVE: msg.headers=None or [] returns None token, no crash")
    try:
        from documind_core.kafka_client import _extract_kafka_context

        for empty in (None, []):
            token = _extract_kafka_context(empty)  # type: ignore[arg-type]
            assert token is None, (
                f"NEGATIVE FAILED: extract with headers={empty!r} returned "
                f"token {token!r} — expected None. Legacy publishers (no inject) "
                f"or messages from clients without OTel must not crash the "
                f"consumer or attach a bogus context."
            )
        green("None / empty headers → None token (no attach, no crash)")
    except AssertionError as exc:
        red(str(exc))
        failed += 1
    except Exception as exc:  # noqa: BLE001
        red(f"step 4 failed: {exc!r}")
        failed += 1

    # ── Step 5: NEGATIVE — non-UTF-8 byte sequence skipped ───────
    print("\n[5/6] NEGATIVE: non-UTF-8 header bytes skipped, propagation continues")
    try:
        from documind_core.kafka_client import (
            _extract_kafka_context,
            _inject_kafka_headers,
        )
        from opentelemetry import baggage as _ot_baggage
        from opentelemetry import context as _ot_context

        # Build headers with a valid baggage entry + a non-UTF-8 garbage
        # header. The garbage MUST be skipped without poisoning the
        # baggage extract.
        ctx = _ot_baggage.set_baggage("tenant_id", "acme-prod")
        token_a = _ot_context.attach(ctx)
        headers: list[tuple[str, bytes]] = [
            ("id", b"some-uuid"),
        ]
        _inject_kafka_headers(headers)
        # Append a header with non-UTF-8 bytes (0xFF is invalid UTF-8 start).
        headers.append(("garbage", b"\xff\xfe\xfd"))
        _ot_context.detach(token_a)

        token_b = _extract_kafka_context(headers)
        try:
            assert _ot_baggage.get_baggage("tenant_id") == "acme-prod", (
                f"NEGATIVE FAILED: baggage extract was poisoned by a "
                f"non-UTF-8 garbage header. tenant_id={_ot_baggage.get_baggage('tenant_id')!r}. "
                f"Per the helper docstring, one bad domain header must NOT "
                f"break propagation for the rest."
            )
        finally:
            if token_b is not None:
                _ot_context.detach(token_b)
        green("non-UTF-8 header skipped; baggage propagation still succeeded")
    except AssertionError as exc:
        red(str(exc))
        failed += 1
    except Exception as exc:  # noqa: BLE001
        red(f"step 5 failed: {exc!r}")
        failed += 1

    # ── Step 6: NEGATIVE — context isolation across Kafka boundary
    print("\n[6/6] NEGATIVE: after detach, parent context unaffected")
    try:
        from documind_core.kafka_client import (
            _extract_kafka_context,
            _inject_kafka_headers,
        )
        from opentelemetry import baggage as _ot_baggage
        from opentelemetry import context as _ot_context

        # Parent context starts clean — no baggage.
        assert _ot_baggage.get_baggage("tenant_id") is None, (
            "test setup wrong — parent already has tenant_id"
        )

        # Build a "consumed" message with baggage.
        producer_ctx = _ot_baggage.set_baggage("tenant_id", "acme-prod")
        producer_ctx = _ot_baggage.set_baggage(
            "ephemeral_key", "should-not-leak", context=producer_ctx,
        )
        producer_token = _ot_context.attach(producer_ctx)
        headers: list[tuple[str, bytes]] = [("id", b"x")]
        _inject_kafka_headers(headers)
        _ot_context.detach(producer_token)

        # Simulate consumer _handle_one — attach + handler + detach
        token = _extract_kafka_context(headers)
        # Inside the handler context: baggage exists.
        assert _ot_baggage.get_baggage("tenant_id") == "acme-prod"
        assert _ot_baggage.get_baggage("ephemeral_key") == "should-not-leak"
        # Detach — back to the parent (clean) context.
        if token is not None:
            _ot_context.detach(token)

        # CRITICAL: after detach, the parent context must NOT see the
        # baggage we attached. A regression that forgot to detach
        # would leak tenant_id into the next poll iteration's handler.
        assert _ot_baggage.get_baggage("tenant_id") is None, (
            f"NEGATIVE FAILED: tenant_id leaked across Kafka boundary "
            f"after detach. Got {_ot_baggage.get_baggage('tenant_id')!r}. "
            f"This means the consumer's poll loop processes message N+1 "
            f"with message N's baggage — a tenant cross-contamination "
            f"bug class."
        )
        assert _ot_baggage.get_baggage("ephemeral_key") is None
        green("post-detach parent context clean — no baggage leak across "
              "Kafka boundary; consumer poll loop tenant-isolated")
    except AssertionError as exc:
        red(str(exc))
        failed += 1
    except Exception as exc:  # noqa: BLE001
        red(f"step 6 failed: {exc!r}")
        failed += 1

    print()
    if failed == 0:
        green(f"ALL {total} STEPS PASSED")
        return 0
    red(f"{failed}/{total} STEPS FAILED")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
