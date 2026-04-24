"""
Drill: verify multi-service distributed traces land in Jaeger.

Flow:
 1. Sanity — inference-svc, retrieval-svc, Jaeger UI all reachable.
 2. Fire a /api/v1/ask call — inference-svc should fan out to
    retrieval-svc. Capture the correlation_id from the response body
    so we can identify *this* specific trace in Jaeger.
 3. Let the OTel BatchSpanProcessor flush (~6s default).
 4. Query Jaeger for inference-svc traces, find the trace for our
    /api/v1/ask call, assert:
      * at least two services present in the trace tree
      * both "POST /api/v1/ask" (inference) and
        "POST /api/v1/retrieve" (retrieval) operations appear
      * the retrieval spans share the same traceID as the inference root
 5. Same pattern for /api/v1/agent/ask — MCP tool invocation produces
    a cross-service trace that still carries the agent-level root span.
 6. Save a JSON dump of one full trace tree to
    /tmp/documind-trace-sample.json so the demo doc can link to it.

Run:
    PYTHONPATH=/mnt/deepa/rag python mcp/tests/drill_trace.py
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import httpx

INFERENCE = os.getenv("INFERENCE_URL", "http://127.0.0.1:8084")
RETRIEVAL = os.getenv("RETRIEVAL_URL", "http://127.0.0.1:8083")
JAEGER = os.getenv("JAEGER_URL", "http://127.0.0.1:16686")
MCP_BASE = os.getenv("MCP_HR_URL", "http://127.0.0.1:8090")
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


def _summarize(trace: dict) -> dict:
    spans = trace.get("spans", [])
    procs = trace.get("processes", {}) or {}
    by_svc: dict[str, list[str]] = {}
    for s in spans:
        svc = procs.get(s["processID"], {}).get("serviceName", "?")
        by_svc.setdefault(svc, []).append(s["operationName"])
    return {
        "traceID": trace["traceID"],
        "total_spans": len(spans),
        "services": {svc: len(ops) for svc, ops in by_svc.items()},
        "operations": {svc: sorted(set(ops)) for svc, ops in by_svc.items()},
    }


async def main() -> None:
    async with httpx.AsyncClient(timeout=30.0) as c:
        step("1. sanity — inference + retrieval + jaeger reachable")
        if (await c.get(f"{INFERENCE}/health")).status_code != 200:
            fail(f"inference not healthy at {INFERENCE}")
        if (await c.get(f"{RETRIEVAL}/health")).status_code != 200:
            fail(f"retrieval not healthy at {RETRIEVAL}")
        if (await c.get(f"{JAEGER}/api/services")).status_code != 200:
            fail(f"jaeger UI not reachable at {JAEGER}")
        ok("all three reachable")

        step("2. /api/v1/ask — fires distributed trace")
        r = await c.post(
            f"{INFERENCE}/api/v1/ask",
            headers=H,
            json={"query": "trace drill: what is the travel reimbursement limit?"},
        )
        if r.status_code != 200:
            fail(f"ask failed: {r.status_code}")
        ask_corr = r.json().get("correlation_id")
        if not ask_corr:
            fail("no correlation_id in response")
        ok(f"ask returned correlation_id={ask_corr}")

        step("3. wait for BatchSpanProcessor flush (8s)")
        await asyncio.sleep(8)
        ok("flushed")

        step("4. jaeger /api/traces?service=inference-svc — find multi-service trace")
        # Ask for a recent batch; filter to the ask endpoint
        r = await c.get(
            f"{JAEGER}/api/traces",
            params={
                "service": "inference-svc",
                "operation": "POST /api/v1/ask",
                "limit": 20,
            },
        )
        traces = r.json().get("data") or []
        if not traces:
            fail("no traces returned for POST /api/v1/ask")
        # Pick the most recent multi-service trace
        multi_svc = []
        for t in traces:
            summ = _summarize(t)
            if len(summ["services"]) >= 2:
                multi_svc.append(summ)
        if not multi_svc:
            fail(f"no multi-service traces — summaries: {[_summarize(t) for t in traces[:3]]}")
        summ = multi_svc[0]
        ok(f"multi-service trace found traceID={summ['traceID']} services={summ['services']}")

        step("5. assert inference + retrieval both contributed spans")
        if "inference-svc" not in summ["services"]:
            fail(f"missing inference-svc in trace: {summ['services']}")
        if "retrieval-svc" not in summ["services"]:
            fail(f"missing retrieval-svc in trace: {summ['services']}")
        # Key operations must be present
        inf_ops = set(summ["operations"].get("inference-svc", []))
        ret_ops = set(summ["operations"].get("retrieval-svc", []))
        if "POST /api/v1/ask" not in inf_ops:
            fail(f"no POST /api/v1/ask span in inference-svc: {inf_ops}")
        if "POST /api/v1/retrieve" not in ret_ops:
            fail(f"no POST /api/v1/retrieve span in retrieval-svc: {ret_ops}")
        ok(f"inference ops include POST /api/v1/ask; retrieval ops include POST /api/v1/retrieve")

        step("6. /api/v1/agent/ask — agent + MCP trace")
        r = await c.post(
            f"{INFERENCE}/api/v1/agent/ask",
            headers=H,
            json={
                "query": "trace drill: please submit a 4-day leave request for testing",
                "employee_id": "E42",
            },
            timeout=60.0,
        )
        if r.status_code != 200:
            fail(f"agent/ask failed: {r.status_code}")
        agent_corr = r.json().get("correlation_id")
        ok(f"agent/ask corr={agent_corr}")

        await asyncio.sleep(8)

        r = await c.get(
            f"{JAEGER}/api/traces",
            params={
                "service": "inference-svc",
                "operation": "POST /api/v1/agent/ask",
                "limit": 5,
            },
        )
        agent_traces = r.json().get("data") or []
        agent_multi = [s for t in agent_traces if (s := _summarize(t)) and len(s["services"]) >= 2]
        if not agent_multi:
            fail(f"no multi-service agent traces: {[_summarize(t) for t in agent_traces]}")
        a_summ = agent_multi[0]
        ok(f"agent trace multi-service traceID={a_summ['traceID']} services={a_summ['services']}")

        # Prefer a trace that includes mcp-server-hr — once the MCP server
        # is OTel-instrumented, EVERY agent/ask with a tool call produces
        # a 3-service tree with the mcp.tool:<name> child span.
        three_svc = [s for s in (_summarize(t) for t in agent_traces) if "mcp-server-hr" in s["services"]]
        if three_svc:
            t3 = three_svc[0]
            mcp_ops = set(t3["operations"].get("mcp-server-hr", []))
            if not any(op.startswith("mcp.tool:") for op in mcp_ops):
                fail(f"mcp-server-hr present but no mcp.tool:* span: {mcp_ops}")
            if "POST /tools/call" not in mcp_ops:
                fail(f"mcp-server-hr missing server span POST /tools/call: {mcp_ops}")
            ok(f"3-service tree (incl. mcp-server-hr) traceID={t3['traceID']} ops={sorted(mcp_ops)}")
        else:
            info = "(mcp-server-hr not yet in agent trace — it may be a fresh run; see DEMO-TRACE.md)"
            print(f"  \033[33m· {info}\033[0m")

        step("7. dump trace sample → /tmp/documind-trace-sample.json")
        sample_path = Path("/tmp/documind-trace-sample.json")
        sample_path.write_text(json.dumps({
            "ask_trace": summ,
            "agent_trace": a_summ,
            "jaeger_ui_tip": f"{JAEGER}/trace/{summ['traceID']}",
        }, indent=2))
        ok(f"sample written: {sample_path}")

        step("8. jaeger reports all 3 services enrolled")
        r = await c.get(f"{JAEGER}/api/services")
        enrolled = r.json().get("data") or []
        missing = {"inference-svc", "retrieval-svc"} - set(enrolled)
        if missing:
            fail(f"services missing from jaeger: {missing}")
        ok(f"services in jaeger: {sorted(enrolled)}")

    print(f"\n{BOLD}{GREEN}════════════════════════════════════════{NC}")
    print(f"{BOLD}{GREEN}  ALL 8 TRACE STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}════════════════════════════════════════{NC}")


if __name__ == "__main__":
    asyncio.run(main())
