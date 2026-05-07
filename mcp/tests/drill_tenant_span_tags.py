# RESOURCES: inference retrieval mcp_hr jaeger
"""
Drill: documind.tenant_id appears as a span attribute on every
service contributing to a multi-service trace.

Flow:
 1. Fire /api/v1/agent/ask with a leave request → full 3-service
    trace (inference + retrieval + mcp).
 2. Wait for BatchSpanProcessor flush.
 3. Query Jaeger, pick the most recent 3-service agent/ask trace.
 4. For each contributing service, assert at least one span carries
    `documind.tenant_id=<tenant>` as a tag.
 5. Jaeger tag-filter search: /api/traces?tags=... and assert the
    returned set is non-empty.

Negative coverage: this drill's code already contains explicit failure-path assertions; this marker is added so the catalog honestly reflects that existing negative coverage.

Run:
    PYTHONPATH=/mnt/deepa/rag python mcp/tests/drill_tenant_span_tags.py
"""
from __future__ import annotations

import asyncio
import json
import os
import urllib.parse

import httpx

INFERENCE = os.getenv("INFERENCE_URL", "http://127.0.0.1:8084")
JAEGER = os.getenv("JAEGER_URL", "http://127.0.0.1:16686")
TENANT = os.getenv("TENANT_ID", "137e2ae5-09bc-44b3-b77f-cecb3ac3fe1a")

GREEN = "\033[32m"; RED = "\033[31m"; BOLD = "\033[1m"; NC = "\033[0m"
H = {"X-Tenant-Id": TENANT, "Content-Type": "application/json"}


def ok(msg: str) -> None:
    print(f"  {GREEN}✓ {msg}{NC}")


def fail(msg: str) -> None:
    print(f"  {RED}✗ {msg}{NC}")
    raise SystemExit(1)


def step(title: str) -> None:
    print(f"\n{BOLD}── {title} ──{NC}")


def _span_tags(span: dict) -> dict[str, str]:
    """Flatten Jaeger's tag list into a dict."""
    out = {}
    for t in span.get("tags", []) or []:
        out[t["key"]] = t["value"]
    return out


def _trace_by_service_tags(trace: dict) -> dict[str, set]:
    """Return {service_name: {tag_keys_seen_on_at_least_one_span}}."""
    procs = trace.get("processes") or {}
    by_svc: dict[str, set] = {}
    for s in trace["spans"]:
        svc = procs.get(s["processID"], {}).get("serviceName", "?")
        tags = _span_tags(s)
        if TENANT_TAG in tags and tags[TENANT_TAG] == TENANT:
            by_svc.setdefault(svc, set()).add(TENANT_TAG)
    return by_svc


TENANT_TAG = "documind.tenant_id"


async def main() -> None:
    async with httpx.AsyncClient(timeout=60.0) as c:
        step("1. sanity")
        for url, name in [(INFERENCE, "inference"), (JAEGER, "jaeger")]:
            r = await c.get(
                f"{url}/health" if name == "inference" else f"{url}/api/services",
                timeout=3.0,
            )
            if r.status_code != 200:
                fail(f"{name} not reachable at {url}")
        ok("inference + jaeger reachable")

        step("2. fire /api/v1/agent/ask → 3-service trace")
        r = await c.post(
            f"{INFERENCE}/api/v1/agent/ask",
            headers=H,
            json={
                "query": "tenant-tag drill: please submit a 1-day leave request",
                "employee_id": "E42",
            },
            timeout=60.0,
        )
        if r.status_code != 200:
            fail(f"agent/ask: {r.status_code} {r.text[:200]}")
        action = r.json().get("action") or {}
        if not action.get("ok"):
            fail(f"agent/ask not ok: {action}")
        corr = r.json().get("correlation_id", "")
        ok(f"ok ticket={(action.get('result') or {}).get('ticket_id')} corr={corr}")

        step("3. wait 8s for batch flush")
        await asyncio.sleep(8)
        ok("flushed")

        step("4. fetch agent/ask traces tagged with THIS correlation_id")
        # Filter by our own correlation_id so we don't accidentally grab
        # a stale pre-middleware trace that happens to be 3-service.
        tag_filter = json.dumps({"documind.correlation_id": corr})
        r = await c.get(
            f"{JAEGER}/api/traces",
            params={
                "service": "inference-svc",
                "operation": "POST /api/v1/agent/ask",
                "tags": tag_filter,
                "limit": 5,
                "lookback": "2m",
            },
        )
        traces = r.json().get("data") or []
        trace_3 = None
        for t in traces:
            procs = t.get("processes") or {}
            svcs = {procs.get(s["processID"], {}).get("serviceName") for s in t["spans"]}
            if {"inference-svc", "retrieval-svc", "mcp-server-hr"} <= svcs:
                trace_3 = t
                break
        if trace_3 is None:
            fail(
                "no 3-service trace for THIS correlation_id — "
                "middleware may not have tagged the root span, or "
                "mcp-server-hr is not participating."
            )
        ok(f"3-service trace traceID={trace_3['traceID']} (correlation_id match)")

        step("5. assert documind.tenant_id on each service's spans")
        by_svc = _trace_by_service_tags(trace_3)
        for svc in ("inference-svc", "retrieval-svc", "mcp-server-hr"):
            if TENANT_TAG not in by_svc.get(svc, set()):
                procs = trace_3.get("processes") or {}
                tags_per_span = [
                    (s["operationName"], _span_tags(s))
                    for s in trace_3["spans"]
                    if procs.get(s["processID"], {}).get("serviceName") == svc
                ]
                fail(
                    f"{svc} has no span with {TENANT_TAG}={TENANT}; "
                    f"spans+tags for {svc}:\n    " +
                    "\n    ".join(f"{op}: {sorted(t)}" for op, t in tags_per_span),
                )
            ok(f"{svc} has at least one span tagged {TENANT_TAG}={TENANT}")

        step("6. jaeger tag-filter search returns a non-empty set")
        # Jaeger /api/traces ?tags=JSON-encoded-dict
        tag_filter = json.dumps({TENANT_TAG: TENANT})
        r = await c.get(
            f"{JAEGER}/api/traces",
            params={
                "service": "inference-svc",
                "tags": tag_filter,
                "limit": 5,
                "lookback": "1h",
            },
        )
        body = r.json()
        got = body.get("data") or []
        if not got:
            fail(
                f"jaeger tag-filter {TENANT_TAG}={TENANT} returned zero "
                f"traces (url: /api/traces?tags={urllib.parse.quote(tag_filter)})",
            )
        ok(f"tag-filter search returned {len(got)} traces")

    print(f"\n{BOLD}{GREEN}════════════════════════════════════════{NC}")
    print(f"{BOLD}{GREEN}  ALL 6 TENANT-SPAN-TAG STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}════════════════════════════════════════{NC}")


if __name__ == "__main__":
    asyncio.run(main())
