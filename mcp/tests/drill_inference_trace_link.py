# RESOURCES: pg inference
"""
Drill: /api/v1/admin/trace/{correlation_id} reconstructs one
request end-to-end — audit rows + draft rows + HITL queue items
linked by correlation_id.

Closes the gap "no easy way to follow trace → draft → replay →
audit" cited across THREE independent reviews:
  * docs/architecture/mcp-agent-gap-review.md §2.3
  * docs/architecture/production-trust-quality-and-readiness.md §2
  * docs/architecture/tech-lead-audit-checklist.md §7

Plus the HITL completion documented at
/admin/explainability/deep#audit-rag-contract-regulation — without
HITL surfaced in forensics, EU AI Act Art. 14 (human oversight)
evidence is incomplete: an operator sees the trace + drafts but
not whether human review intervened.

The endpoint surfaces audit + draft + HITL rows that share the
correlation_id, plus a Jaeger deep-link if DOCUMIND_JAEGER_URL is
configured. Operators paste a correlation_id from the dashboard
and see the full request reconstruction including any human-
review state.

Negative-assertion §43-style:
 1. Bad UUID → 400. NEGATIVE: a string-shaped query that always
    returns zero rows would silently mislead operators
    investigating a typo'd correlation_id.
 2. Unknown UUID → 200 with empty arrays + db_reachable=true.
    NEGATIVE: returning 404 here would conflate "not found
    yet" (operator investigating early) with "endpoint broken".
 3. Insert ONE audit + ONE draft row sharing a known cid. Lookup
    returns BOTH. NEGATIVE: returning only one would hide either
    the audit chain or the draft state from the operator.
 4. Insert ANOTHER audit row with a DIFFERENT cid. Lookup for
    the original cid does NOT return the second audit. NEGATIVE:
    a regression that scanned without a WHERE filter would
    surface every audit row in the system.
 5. Insert a SECOND audit row sharing the original cid. Lookup
    returns BOTH ordered by timestamp ASC. NEGATIVE: chronological
    order matters — out-of-order surfacing would force the
    operator to manually sort to reconstruct what happened.
 6a. Tenant isolation — wrong tenant_id sees ZERO rows for cid_main.
     NEGATIVE: rows for tenant A must NEVER surface to a request
     scoped to tenant B (RLS isolation).
 6. fail_closed_failed projection — insert an audit row with
    details={'fail_closed_failed': true}; lookup surfaces it as
    True; the other (success) row surfaces as False. NEGATIVE: a
    regression that hardcoded fail_closed_failed=False (or always
    True) would mask one of the most operationally significant
    audit attributes.
 7. HITL join — flagged answer surfaces with review_status +
    confidence + flag_reason. POSITIVE: completes the trace →
    draft → audit → HITL loop documented at
    /admin/explainability/deep.
 8. NEGATIVE: HITL row for cid_other does NOT bleed into cid_main
    lookup. A regression that scanned hitl_queue without WHERE
    correlation_id filter would surface every flagged answer.

Run:
    PYTHONPATH=/mnt/deepa/rag python mcp/tests/drill_inference_trace_link.py
"""
from __future__ import annotations

import asyncio
import json
import os
import uuid
from pathlib import Path

import asyncpg
import httpx

REPO = Path(__file__).resolve().parents[2]
INF_BASE = os.getenv("INFERENCE_URL", "http://127.0.0.1:8084")
PG_DSN = (
    f"postgresql://{os.getenv('DOCUMIND_PG_USER', 'documind_app')}:"
    f"{os.getenv('DOCUMIND_PG_PASSWORD', 'documind_app')}@"
    f"{os.getenv('DOCUMIND_PG_HOST', 'localhost')}:"
    f"{os.getenv('DOCUMIND_PG_PORT', '55432')}/"
    f"{os.getenv('DOCUMIND_PG_DB', 'documind')}"
)

GREEN = "\033[32m"; RED = "\033[31m"; BOLD = "\033[1m"; NC = "\033[0m"


def ok(msg: str) -> None:
    print(f"  {GREEN}✓ {msg}{NC}")


def fail(msg: str) -> None:
    print(f"  {RED}✗ {msg}{NC}")
    raise SystemExit(1)


def step(title: str) -> None:
    print(f"\n{BOLD}── {title} ──{NC}")


async def _insert_audit(
    pool: asyncpg.Pool,
    *, correlation_id: str | None, action: str,
    actor_id: str, actor_type: str = "service",
    tenant_id: str | None = None,
    fail_closed_failed: bool = False,
) -> str:
    details = {"fail_closed_failed": fail_closed_failed} if fail_closed_failed else {}
    async with pool.acquire() as conn:
        async with conn.transaction():
            # RLS is forced on audit_log — must set the session
            # tenant before insert. We use the tenant we're inserting
            # for; the policy allows tenant_id=NULL or tenant_id=current.
            if tenant_id is not None:
                await conn.execute(
                    "SELECT set_config('app.current_tenant', $1, true)",
                    tenant_id,
                )
            row = await conn.fetchrow(
                """
                INSERT INTO governance.audit_log
                    (tenant_id, actor_id, actor_type, action,
                     details, correlation_id)
                VALUES ($1::uuid, $2, $3, $4, $5::jsonb, $6::uuid)
                RETURNING id
                """,
                tenant_id, actor_id, actor_type, action,
                json.dumps(details), correlation_id,
            )
    return str(row["id"])


async def _insert_draft(
    pool: asyncpg.Pool,
    *, correlation_id: str | None, draft_id: str,
    tool: str, reason: str = "drill", tenant_id: str | None = None,
) -> None:
    async with pool.acquire() as conn:
        async with conn.transaction():
            if tenant_id is not None:
                await conn.execute(
                    "SELECT set_config('app.current_tenant', $1, true)",
                    tenant_id,
                )
            await conn.execute(
                """
                INSERT INTO governance.action_drafts
                    (draft_id, tenant_id, tool, arguments, correlation_id,
                     reason, status)
                VALUES ($1, $2::uuid, $3, $4::jsonb, $5::uuid, $6, 'pending')
                """,
                draft_id, tenant_id, tool, json.dumps({"q": "drill"}),
                correlation_id, reason,
            )


async def _insert_hitl(
    pool: asyncpg.Pool,
    *, correlation_id: str, tenant_id: str,
    question: str, generated_answer: str = "stub",
    confidence: float = 0.42,
    flag_reason: str = "low_confidence",
    review_status: str = "pending",
) -> str:
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "SELECT set_config('app.current_tenant', $1, true)",
                tenant_id,
            )
            row = await conn.fetchrow(
                """
                INSERT INTO governance.hitl_queue
                    (tenant_id, correlation_id, question, retrieved_chunks,
                     generated_answer, confidence, flag_reason, review_status)
                VALUES ($1::uuid, $2::uuid, $3, $4::jsonb, $5, $6, $7, $8)
                RETURNING id
                """,
                tenant_id, correlation_id, question,
                json.dumps([]), generated_answer, confidence,
                flag_reason, review_status,
            )
    return str(row["id"])


async def _cleanup(pool: asyncpg.Pool, correlation_ids: list[str]) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM governance.audit_log WHERE correlation_id = ANY($1::uuid[])",
            correlation_ids,
        )
        await conn.execute(
            "DELETE FROM governance.action_drafts WHERE correlation_id = ANY($1::uuid[])",
            correlation_ids,
        )
        await conn.execute(
            "DELETE FROM governance.hitl_queue WHERE correlation_id = ANY($1::uuid[])",
            correlation_ids,
        )


async def _lookup(
    c: httpx.AsyncClient, cid: str, tenant: str,
) -> tuple[int, dict]:
    r = await c.get(
        f"{INF_BASE}/api/v1/admin/trace/{cid}",
        params={"tenant_id": tenant},
    )
    body = {}
    try:
        body = r.json()
    except json.JSONDecodeError:
        pass
    return r.status_code, body


async def main() -> None:
    cid_main = str(uuid.uuid4())
    cid_other = str(uuid.uuid4())
    tenant = "137e2ae5-09bc-44b3-b77f-cecb3ac3fe1a"
    # Per-run unique draft_id — avoids unique-constraint collisions
    # from prior partial runs (DELETE under RLS would need tenant
    # context we don't have at top of run).
    suffix = uuid.uuid4().hex[:8].upper()
    DRAFT_ID = f"DRAFT-DRILL-{suffix}"

    pool = await asyncpg.create_pool(dsn=PG_DSN, min_size=1, max_size=2)

    try:
        async with httpx.AsyncClient(timeout=10.0) as c:
            step("1. bad UUID → 400")
            status, body = await _lookup(c, "not-a-uuid", tenant)
            if status != 400:
                fail(f"expected 400, got {status}: {body}")
            code = (body.get("detail") or {}).get("code") if isinstance(body.get("detail"), dict) else None
            if code != "INVALID_CORRELATION_ID":
                fail(f"expected detail.code=INVALID_CORRELATION_ID, got {body}")
            ok(f"400 INVALID_CORRELATION_ID returned for malformed UUID")

            step("2. unknown UUID → 200 with empty arrays")
            status, body = await _lookup(c, str(uuid.uuid4()), tenant)
            if status != 200:
                fail(f"expected 200, got {status}: {body}")
            if not body.get("db_reachable"):
                fail("db_reachable should be True with DB up")
            if body.get("audit_rows") != []:
                fail(f"expected empty audit_rows, got {body['audit_rows']}")
            if body.get("draft_rows") != []:
                fail(f"expected empty draft_rows, got {body['draft_rows']}")
            ok(f"200 with empty arrays for unknown correlation_id (no spurious 404)")

            step("3. insert audit + draft sharing cid → both surface")
            audit1_id = await _insert_audit(
                pool, correlation_id=cid_main, action="agent.ask",
                actor_id="alice@tenant-a.local", actor_type="user",
                tenant_id=tenant,
            )
            await _insert_draft(
                pool, correlation_id=cid_main, draft_id=DRAFT_ID,
                tool="hr.leave_request", tenant_id=tenant,
            )
            await asyncio.sleep(0.05)
            status, body = await _lookup(c, cid_main, tenant)
            if status != 200:
                fail(f"expected 200, got {status}: {body}")
            audits = body["audit_rows"]
            drafts = body["draft_rows"]
            if len(audits) != 1:
                fail(f"expected 1 audit row, got {len(audits)}: {audits}")
            if len(drafts) != 1:
                fail(f"expected 1 draft row, got {len(drafts)}: {drafts}")
            if audits[0]["id"] != audit1_id:
                fail(f"wrong audit row surfaced: {audits[0]}")
            if drafts[0]["draft_id"] != DRAFT_ID:
                fail(f"wrong draft row surfaced: {drafts[0]}")
            if drafts[0]["status"] != "pending":
                fail(f"draft status wrong: {drafts[0]['status']}")
            ok(f"audit + draft both surface (action={audits[0]['action']} draft={drafts[0]['draft_id']})")

            step("4. unrelated cid does NOT bleed in")
            audit_other_id = await _insert_audit(
                pool, correlation_id=cid_other, action="agent.unrelated",
                actor_id="bob@tenant-b.local", actor_type="user",
                tenant_id=tenant,
            )
            await asyncio.sleep(0.05)
            status, body = await _lookup(c, cid_main, tenant)
            audits = body["audit_rows"]
            ids = {a["id"] for a in audits}
            if audit_other_id in ids:
                fail(
                    f"unrelated audit ({audit_other_id}) leaked into "
                    f"the lookup for cid_main. WHERE filter is broken — "
                    f"a regression here would surface every audit row "
                    f"in the system to any operator."
                )
            if len(audits) != 1:
                fail(f"expected still 1 audit, got {len(audits)}")
            ok(f"WHERE correlation_id filter holds (unrelated cid filtered out)")

            step("5. multiple audits same cid → ordered by timestamp ASC")
            await asyncio.sleep(0.05)
            audit2_id = await _insert_audit(
                pool, correlation_id=cid_main, action="agent.tool_call",
                actor_id="alice@tenant-a.local", actor_type="user",
                tenant_id=tenant,
            )
            await asyncio.sleep(0.05)
            status, body = await _lookup(c, cid_main, tenant)
            audits = body["audit_rows"]
            if len(audits) != 2:
                fail(f"expected 2 audit rows, got {len(audits)}: "
                     f"{[a['action'] for a in audits]}")
            # ASC ordering: audit1 was inserted first, audit2 second.
            ts0 = audits[0]["timestamp"]
            ts1 = audits[1]["timestamp"]
            if ts0 > ts1:
                fail(f"audit rows not ordered ASC by timestamp: {ts0} > {ts1}")
            if audits[0]["id"] != audit1_id or audits[1]["id"] != audit2_id:
                fail(
                    f"audit rows out of order — got {[a['id'] for a in audits]}, "
                    f"expected {[audit1_id, audit2_id]}"
                )
            ok(f"2 audits returned in ASC order (action: {audits[0]['action']} → {audits[1]['action']})")

            step("6a. tenant isolation — wrong tenant_id sees ZERO rows")
            wrong_tenant = "00000000-0000-0000-0000-000000000099"
            status, body = await _lookup(c, cid_main, wrong_tenant)
            if status != 200:
                fail(f"expected 200 with wrong tenant, got {status}")
            if body.get("audit_rows") or body.get("draft_rows"):
                fail(
                    f"WRONG tenant_id surfaced rows for cid_main — "
                    f"RLS isolation broken. audit_rows={body['audit_rows']} "
                    f"draft_rows={body['draft_rows']}. This is the "
                    f"strongest negative: rows for tenant A must NEVER "
                    f"surface to a request scoped to tenant B."
                )
            ok(f"wrong tenant returns empty arrays (RLS per-tenant scoping holds)")

            step("6. fail_closed_failed projection — surfaces correctly per row")
            await _insert_audit(
                pool, correlation_id=cid_main, action="audit.write_failed",
                actor_id="system", actor_type="service",
                tenant_id=tenant, fail_closed_failed=True,
            )
            await asyncio.sleep(0.05)
            status, body = await _lookup(c, cid_main, tenant)
            audits = body["audit_rows"]
            failed_rows = [a for a in audits if a["fail_closed_failed"]]
            ok_rows = [a for a in audits if not a["fail_closed_failed"]]
            if len(failed_rows) != 1:
                fail(
                    f"expected exactly 1 fail_closed_failed=True row, "
                    f"got {len(failed_rows)}. A regression that "
                    f"hardcoded the field would fail this."
                )
            if failed_rows[0]["action"] != "audit.write_failed":
                fail(f"wrong row marked fail_closed_failed: {failed_rows[0]}")
            if len(ok_rows) != 2:
                fail(
                    f"expected 2 fail_closed_failed=False rows, got "
                    f"{len(ok_rows)} — projection should distinguish "
                    f"per-row, not bulk-flag."
                )
            ok(f"fail_closed_failed projection: 1 true / 2 false (correctly per-row)")

            step("7. HITL join — flagged answer surfaces with review_status")
            # Insert a HITL row sharing cid_main with review_status=pending.
            hitl_id = await _insert_hitl(
                pool, correlation_id=cid_main, tenant_id=tenant,
                question="What is the refund policy?",
                generated_answer="(low confidence)",
                confidence=0.42, flag_reason="low_confidence",
                review_status="pending",
            )
            await asyncio.sleep(0.05)
            status, body = await _lookup(c, cid_main, tenant)
            if status != 200:
                fail(f"expected 200 after HITL insert, got {status}")
            hitls = body.get("hitl_rows", [])
            if len(hitls) != 1:
                fail(
                    f"expected exactly 1 hitl row for cid_main, got "
                    f"{len(hitls)}: {hitls}. The HITL projection completes "
                    f"the trace → draft → audit → HITL loop required for "
                    f"EU AI Act Art. 14 (human oversight) evidence."
                )
            h0 = hitls[0]
            if h0["id"] != hitl_id:
                fail(f"wrong HITL row returned: {h0['id']!r} vs expected {hitl_id!r}")
            if h0["review_status"] != "pending":
                fail(
                    f"review_status not surfaced: got {h0['review_status']!r} "
                    f"vs expected 'pending'. Operator forensics REQUIRES "
                    f"the resolution state."
                )
            if h0["confidence"] is None or abs(h0["confidence"] - 0.42) > 1e-3:
                fail(
                    f"confidence not surfaced or wrong: got {h0['confidence']!r} "
                    f"vs expected 0.42. Confidence is the WHY behind the flag."
                )
            ok(
                f"HITL row surfaced: id={h0['id'][:8]}... "
                f"review_status={h0['review_status']} "
                f"confidence={h0['confidence']}"
            )

            step("8. NEGATIVE: HITL for unrelated cid does NOT bleed into this lookup")
            # Insert a HITL row for cid_other; lookup on cid_main must NOT see it.
            hitl_other = await _insert_hitl(
                pool, correlation_id=cid_other, tenant_id=tenant,
                question="(should not appear in cid_main lookup)",
                review_status="rejected",
            )
            await asyncio.sleep(0.05)
            status, body = await _lookup(c, cid_main, tenant)
            hitls = body.get("hitl_rows", [])
            ids = [h["id"] for h in hitls]
            if hitl_other in ids:
                fail(
                    f"NEGATIVE FAILED: HITL row for cid_other ({hitl_other}) "
                    f"leaked into cid_main lookup. A regression that scanned "
                    f"hitl_queue without WHERE correlation_id filter would "
                    f"surface every flagged answer in the system. Got ids: "
                    f"{ids}"
                )
            if len(hitls) != 1:
                fail(
                    f"expected only the cid_main HITL row (1), got {len(hitls)}: "
                    f"{ids}. Filter must be cid-scoped."
                )
            ok(
                f"only cid_main's HITL row surfaces ({hitls[0]['id'][:8]}...); "
                f"cid_other's row correctly filtered out — WHERE clause holds"
            )

        # Cleanup.
        await _cleanup(pool, [cid_main, cid_other])

    finally:
        await pool.close()

    print(f"\n{BOLD}{GREEN}════════════════════════════════════════{NC}")
    print(f"{BOLD}{GREEN}  ALL 9 TRACE-LINK STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}════════════════════════════════════════{NC}")


if __name__ == "__main__":
    asyncio.run(main())
