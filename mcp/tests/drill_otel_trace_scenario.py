#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: telemetry scenario verifies OTLP trace export into Jaeger.

Locks the telemetry scenario in scripts/scenario_batch_and_inference.py so
it proves end-to-end trace flow, not just that the OTel collector port
returns HTTP 405 to an unsupported GET.

NEGATIVE: an HTTP 405 health probe must not masquerade as trace export.
"""
from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCENARIO = REPO / "scripts" / "scenario_batch_and_inference.py"


def require(src: str, needle: str, label: str) -> None:
    if needle not in src:
        raise AssertionError(f"missing {label}: {needle!r}")


def main() -> int:
    print("-- 1. POSITIVE: scenario runner exists + parses --")
    src = SCENARIO.read_text(encoding="utf-8")
    ast.parse(src)
    print("  ok: scenario runner exists and is Python-valid")

    print("-- 2. POSITIVE: telemetry scenario emits OTLP HTTP span --")
    require(src, "OTLPSpanExporter", "OTLP HTTP exporter")
    require(src, "http://localhost:4318/v1/traces", "OTLP HTTP traces endpoint")
    require(src, "scenario-otel-smoke", "smoke service name")
    require(src, "scenario.otel_smoke", "smoke operation name")
    print("  ok: telemetry scenario exports a real smoke span")

    print("-- 3. POSITIVE: telemetry scenario verifies Jaeger readback --")
    require(src, "http://localhost:16686", "Jaeger API URL")
    require(src, "/api/traces?", "Jaeger trace query")
    require(src, "trace_found_in_jaeger", "Jaeger readback evidence")
    require(src, "documind.correlation_id", "unique correlation tag")
    require(src, "_jaeger_trace_has_correlation", "correlation matcher")
    print("  ok: telemetry scenario checks the exact exported span in Jaeger")

    print("-- 4. NEGATIVE: OTel collector GET 405 is not a pass condition --")
    if "otel_collector_v1_traces" in src:
        raise AssertionError("telemetry scenario still has collector GET reachability probe")
    if "accept 405 for GET" in src:
        raise AssertionError("telemetry scenario still documents 405 as success")
    require(src, '"reachable": trace_found', "strict trace-found reachability")
    print("  ok: telemetry PASS requires Jaeger trace readback")

    print("\nALL 4 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
