# RESOURCES: inference mcp_hr pg
"""
Drill: prove the HITL admin HTTP loop end-to-end via the inference-svc.

Flow:
 1. GET /api/v1/drafts?status=pending — establish baseline (count = N)
 2. kill MCP
 3. POST /api/v1/agent/ask with a leave request → must return
    action.degraded=true, action.draft_id=DRAFT-*
 4. GET /api/v1/drafts — the new draft_id MUST appear, status=pending
 5. restart MCP
 6. POST /api/v1/drafts/{draft_id}/resolve → ok=true, result.ticket_id set
 7. GET /api/v1/drafts — list no longer contains the replayed draft_id
    (it's now status=replayed, so the pending filter excludes it)
 8. POST /api/v1/drafts/{draft_id}/resolve AGAIN → 409 DRAFT_NOT_PENDING
 9. POST /api/v1/drafts/DRAFT-ZZZZ/resolve → 404 DRAFT_NOT_FOUND

Prereqs: same as golden-demo.sh (inference :8084, mcp-hr :8090, PG).
Run:
    PYTHONPATH=/mnt/deepa/rag python mcp/tests/drill_admin_api.py
"""
from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parents[2]

INFERENCE = os.getenv("INFERENCE_URL", "http://127.0.0.1:8084")
MCP_BASE = os.getenv("MCP_HR_URL", "http://127.0.0.1:8090")
MCP_PORT = int(os.getenv("MCP_HR_PORT", "8090"))
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


def _kill_mcp_by_port() -> None:
    # `fuser -k` kills owners of a TCP port — avoids `pkill` self-match.
    subprocess.run(["fuser", "-k", f"{MCP_PORT}/tcp"], check=False, capture_output=True)


def _spawn_mcp() -> subprocess.Popen:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO)
    env["MCP_HR_PORT"] = str(MCP_PORT)
    log = open("/tmp/documind-mcp-hr-admin-drill.log", "w")
    return subprocess.Popen(
        [sys.executable, str(REPO / "mcp" / "server_hr.py")],
        env=env, stdout=log, stderr=subprocess.STDOUT,
    )


async def _wait_healthy(client: httpx.AsyncClient, url: str, tries: int = 30) -> bool:
    for _ in range(tries):
        try:
            r = await client.get(f"{url}/health", timeout=2.0)
            if r.status_code == 200:
                return True
        except httpx.HTTPError:
            pass
        await asyncio.sleep(0.5)
    return False


async def _wait_dead(client: httpx.AsyncClient, url: str, tries: int = 15) -> None:
    for _ in range(tries):
        try:
            r = await client.get(f"{url}/health", timeout=1.0)
            if r.status_code != 200:
                return
        except httpx.HTTPError:
            return
        await asyncio.sleep(0.3)


async def main() -> None:
    async with httpx.AsyncClient(timeout=30.0) as c:
        # ---- 0. sanity -------------------------------------------
        step("0. sanity — services up")
        if (await c.get(f"{INFERENCE}/health")).status_code != 200:
            fail(f"inference not healthy at {INFERENCE}")
        if not await _wait_healthy(c, MCP_BASE, tries=2):
            fail(f"MCP not healthy at {MCP_BASE} — start it first")
        ok("inference + MCP healthy")

        # ---- 1. baseline list ------------------------------------
        step("1. GET /api/v1/drafts — baseline")
        r = await c.get(f"{INFERENCE}/api/v1/drafts?status=pending", headers=H)
        if r.status_code != 200:
            fail(f"list failed: {r.status_code} {r.text[:200]}")
        baseline = r.json()["drafts"]
        baseline_ids = {d["draft_id"] for d in baseline}
        ok(f"baseline drafts (pending) = {len(baseline)}")

        # ---- 2. kill MCP -----------------------------------------
        step("2. kill MCP")
        _kill_mcp_by_port()
        await _wait_dead(c, MCP_BASE)
        ok("MCP down")

        # ---- 3. agent call → degraded ----------------------------
        step("3. agent/ask with leave request → degraded draft")
        r = await c.post(
            f"{INFERENCE}/api/v1/agent/ask",
            headers=H,
            json={
                "query": "Please submit a 4-day leave request for a drill",
                "employee_id": "E42",
            },
        )
        if r.status_code != 200:
            fail(f"agent/ask returned {r.status_code}: {r.text[:300]}")
        action = r.json().get("action") or {}
        if not action.get("degraded") or not action.get("draft_id"):
            fail(f"expected degraded+draft_id, got: {action}")
        new_draft_id = action["draft_id"]
        ok(f"degraded=true new_draft_id={new_draft_id}")

        # ---- 4. list contains the new draft ----------------------
        step("4. GET /api/v1/drafts — new draft is listed")
        r = await c.get(f"{INFERENCE}/api/v1/drafts?status=pending", headers=H)
        if r.status_code != 200:
            fail(f"list failed: {r.status_code}")
        now_list = r.json()["drafts"]
        now_ids = {d["draft_id"] for d in now_list}
        if new_draft_id not in now_ids:
            fail(f"new draft {new_draft_id} not in pending list (got {len(now_list)} rows)")
        row = next(d for d in now_list if d["draft_id"] == new_draft_id)
        if row["tool"] != "hr.leave_request":
            fail(f"wrong tool: {row['tool']}")
        if row["status"] != "pending":
            fail(f"wrong status: {row['status']}")
        if row["tenant_id"] != TENANT:
            fail(f"wrong tenant: {row['tenant_id']}")
        ok(f"draft found: tool={row['tool']} reason={row['reason']} args={row['arguments']}")

        # ---- 5. restart MCP --------------------------------------
        step("5. restart MCP")
        mcp_proc = _spawn_mcp()
        if not await _wait_healthy(c, MCP_BASE):
            fail("MCP did not come back")
        ok("MCP back up")

        # ---- 6. resolve the draft --------------------------------
        step("6. POST /api/v1/drafts/{id}/resolve")
        # CB on inference-svc side may still be OPEN from step-3 failures
        # — we need to wait out recovery_timeout (30s default) before the
        # client will probe again. In a real ops flow the operator knows
        # when MCP came back, and resolve_draft is their explicit retry.
        # Here, the 30s wait is unavoidable given the current CB config.
        print("    waiting 32s for CB recovery_timeout...")
        await asyncio.sleep(32)
        r = await c.post(
            f"{INFERENCE}/api/v1/drafts/{new_draft_id}/resolve", headers=H, timeout=60.0,
        )
        if r.status_code != 200:
            fail(f"resolve returned {r.status_code}: {r.text[:300]}")
        body = r.json()
        if not body.get("ok"):
            fail(f"resolve not ok: {body}")
        tid = (body.get("result") or {}).get("ticket_id")
        if not tid:
            fail(f"no ticket_id on resolve: {body}")
        ok(f"replay ok ticket_id={tid}")

        # ---- 7. list no longer contains it -----------------------
        step("7. GET /api/v1/drafts — replayed draft no longer pending")
        r = await c.get(f"{INFERENCE}/api/v1/drafts?status=pending", headers=H)
        after = r.json()["drafts"]
        if new_draft_id in {d["draft_id"] for d in after}:
            fail(f"{new_draft_id} still in pending list")
        ok(f"replayed draft removed from pending (current pending count={len(after)})")

        # ---- 8. second resolve → 409 -----------------------------
        step("8. second resolve_draft → 409 DRAFT_NOT_PENDING")
        r = await c.post(
            f"{INFERENCE}/api/v1/drafts/{new_draft_id}/resolve", headers=H,
        )
        if r.status_code != 409:
            fail(f"expected 409, got {r.status_code}: {r.text[:200]}")
        detail = r.json().get("detail") or {}
        if detail.get("code") != "DRAFT_NOT_PENDING":
            fail(f"expected DRAFT_NOT_PENDING, got: {detail}")
        ok(f"409 DRAFT_NOT_PENDING (status={detail.get('status')})")

        # ---- 9. unknown draft → 404 ------------------------------
        step("9. unknown draft_id → 404 DRAFT_NOT_FOUND")
        r = await c.post(
            f"{INFERENCE}/api/v1/drafts/DRAFT-NOSUCHID/resolve", headers=H,
        )
        if r.status_code != 404:
            fail(f"expected 404, got {r.status_code}: {r.text[:200]}")
        ok(f"404 DRAFT_NOT_FOUND")

    print(f"\n{BOLD}{GREEN}════════════════════════════════════════{NC}")
    print(f"{BOLD}{GREEN}  ALL 9 ADMIN-API STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}════════════════════════════════════════{NC}")


if __name__ == "__main__":
    asyncio.run(main())
