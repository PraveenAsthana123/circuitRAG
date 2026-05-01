"""MCP observe server (E3: real Prometheus backing).

E3 wires observe.prom_query + observe.compute_p95_delta to the live
Prometheus HTTP API at PROMETHEUS_URL (default http://localhost:9090).
observe.check_alerts_fired stays stubbed (Alertmanager API is similar
shape; replace in a follow-up with real AM query).

Security: read-only HTTP queries; no PromQL injection risk because
queries are passed as URL-encoded params to /api/v1/query — Prometheus
itself parses & sandboxes them.

Run:
    MCP_OBSERVE_PORT=8097 \
    PROMETHEUS_URL=http://localhost:9090 \
    python mcp/server_observe.py
"""
from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from fastapi import FastAPI
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("mcp.server_observe")

app = FastAPI(title="DocuMind MCP — Observe server (E3)")

PROMETHEUS_URL = os.environ.get("PROMETHEUS_URL", "http://localhost:9090").rstrip("/")
PROM_TIMEOUT_SEC = float(os.environ.get("PROMETHEUS_TIMEOUT_SEC", "10"))


TOOLS: list[dict[str, Any]] = [
    {
        "name": "observe.prom_query",
        "description": "Query Prometheus /api/v1/query (instant). REAL backing.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
        "required_scopes": ["observe:read"],
    },
    {
        "name": "observe.compute_p95_delta",
        "description": "Compute p95 latency delta vs baseline. REAL backing.",
        "input_schema": {
            "type": "object",
            "properties": {
                "service": {"type": "string"},
                "metric": {
                    "type": "string",
                    "default": "http_request_duration_seconds_bucket",
                },
                "baseline_window_seconds": {"type": "integer", "default": 3600},
                "compare_window_seconds": {"type": "integer", "default": 300},
            },
            "required": ["service"],
        },
        "required_scopes": ["observe:read"],
    },
    {
        "name": "observe.check_alerts_fired",
        "description": "Count alertmanager alerts in window. STUBBED (real AM in follow-up).",
        "input_schema": {
            "type": "object",
            "properties": {"window_seconds": {"type": "integer", "default": 300}},
        },
        "required_scopes": ["observe:read"],
    },
]


class ToolCallRequest(BaseModel):
    name: str
    arguments: dict[str, Any] = {}
    tenant_id: str | None = None
    correlation_id: str | None = None


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe. Reports whether Prometheus is reachable so
    operators can see at a glance whether real backing is degraded."""
    prom_alive = "false"
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get(f"{PROMETHEUS_URL}/-/healthy")
            if r.status_code == 200:
                prom_alive = "true"
    except (httpx.HTTPError, httpx.TimeoutException):
        pass
    return {
        "status": "ok",
        "service": "mcp-server-observe",
        "stub": "partial",
        "prometheus_url": PROMETHEUS_URL,
        "prometheus_reachable": prom_alive,
    }


@app.get("/tools/list")
async def list_tools() -> dict[str, Any]:
    return {"tools": TOOLS}


async def _prom_query(query: str) -> dict[str, Any]:
    """Call Prometheus /api/v1/query. Returns the structured envelope."""
    try:
        async with httpx.AsyncClient(timeout=PROM_TIMEOUT_SEC) as client:
            r = await client.get(
                f"{PROMETHEUS_URL}/api/v1/query",
                params={"query": query},
            )
            if r.status_code != 200:
                return {
                    "ok": False,
                    "error": {
                        "code": "prometheus_http_error",
                        "status": r.status_code,
                        "body": r.text[:500],
                    },
                }
            payload = r.json()
            if payload.get("status") != "success":
                return {
                    "ok": False,
                    "error": {
                        "code": "prometheus_query_failed",
                        "details": payload,
                    },
                }
            return {
                "ok": True,
                "data": {
                    "query": query,
                    "result_type": payload["data"].get("resultType"),
                    "samples": payload["data"].get("result") or [],
                    "stub": False,
                    "real_backing": "prometheus",
                },
            }
    except (httpx.HTTPError, httpx.TimeoutException) as exc:
        return {
            "ok": False,
            "error": {
                "code": "prometheus_unreachable",
                "url": PROMETHEUS_URL,
                "message": str(exc),
            },
        }


async def _compute_p95_delta(args: dict[str, Any]) -> dict[str, Any]:
    """Compute p95 latency for baseline window vs compare window using
    histogram_quantile over a service-scoped *_bucket metric.

    The PromQL pattern:
      histogram_quantile(0.95, sum by (le) (rate(<metric>{service="x"}[5m])))
    is constructed server-side; the caller supplies service + metric
    name only (no PromQL injection vector).
    """
    service = str(args.get("service") or "").strip()
    metric = str(args.get("metric") or "http_request_duration_seconds_bucket").strip()
    baseline_s = int(args.get("baseline_window_seconds") or 3600)
    compare_s = int(args.get("compare_window_seconds") or 300)

    if not service:
        return {
            "ok": False,
            "error": {"code": "invalid_input", "message": "service is required"},
        }

    # Sanitize service + metric names: allow only [A-Za-z0-9_:-]+ to
    # prevent injection. Anything else returns invalid_input.
    import re as _re
    safe_re = _re.compile(r"^[A-Za-z0-9_:.-]+$")
    if not safe_re.match(service) or not safe_re.match(metric):
        return {
            "ok": False,
            "error": {
                "code": "invalid_input",
                "message": "service/metric must match [A-Za-z0-9_:.-]+",
            },
        }

    # Build the two PromQL queries.
    baseline_q = (
        f'histogram_quantile(0.95, sum by (le) '
        f'(rate({metric}{{service="{service}"}}[{baseline_s}s])))'
    )
    compare_q = (
        f'histogram_quantile(0.95, sum by (le) '
        f'(rate({metric}{{service="{service}"}}[{compare_s}s])))'
    )

    baseline = await _prom_query(baseline_q)
    compare = await _prom_query(compare_q)
    if not baseline.get("ok") or not compare.get("ok"):
        return {
            "ok": False,
            "error": {
                "code": "prom_query_failed",
                "baseline_error": baseline.get("error"),
                "compare_error": compare.get("error"),
            },
        }

    def _extract_value(result: dict) -> float | None:
        samples = result["data"]["samples"]
        if not samples:
            return None
        # /api/v1/query result shape: [{metric:{}, value:[ts, "X"]}]
        try:
            return float(samples[0]["value"][1])
        except (KeyError, IndexError, ValueError, TypeError):
            return None

    baseline_v = _extract_value(baseline)
    compare_v = _extract_value(compare)
    delta_pct = None
    if baseline_v is not None and compare_v is not None and baseline_v > 0:
        delta_pct = round(((compare_v - baseline_v) / baseline_v) * 100, 2)

    # Convert to milliseconds (Prometheus histogram_quantile returns
    # seconds for *_seconds_bucket metrics).
    baseline_ms = int(baseline_v * 1000) if baseline_v is not None else None
    compare_ms = int(compare_v * 1000) if compare_v is not None else None

    return {
        "ok": True,
        "data": {
            "service": service,
            "metric": metric,
            "p95_baseline_ms": baseline_ms,
            "p95_observed_ms": compare_ms,
            "delta_pct": delta_pct,
            "stub": baseline_v is None and compare_v is None,
            "real_backing": "prometheus",
        },
    }


@app.post("/tools/call")
async def call_tool(req: ToolCallRequest) -> dict[str, Any]:
    if req.name == "observe.prom_query":
        q = str(req.arguments.get("query") or "").strip()
        if not q:
            return {
                "ok": False,
                "error": {"code": "invalid_input", "message": "query is required"},
            }
        return await _prom_query(q)

    if req.name == "observe.compute_p95_delta":
        return await _compute_p95_delta(req.arguments)

    if req.name == "observe.check_alerts_fired":
        # STUB — Alertmanager integration is the next E-track commit.
        return {
            "ok": True,
            "data": {
                "alerts_fired": 0,
                "alerts": [],
                "window_seconds": int(req.arguments.get("window_seconds") or 300),
                "stub": True,
            },
        }

    return {
        "ok": False,
        "error": {"code": "tool_not_found", "name": req.name},
    }


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    port = int(os.environ.get("MCP_OBSERVE_PORT", "8097"))
    uvicorn.run(app, host="0.0.0.0", port=port)
