# RESOURCES: pg inference
"""
Drill: /api/v1/health/prompts surfaces active prompt-registry rows
to the operator dashboard.

Closes the trust-scorecard gap "prompt/model/retrieval registry
visibility" cited in:
  * docs/architecture/production-trust-quality-and-readiness.md §7
  * docs/architecture/mcp-agent-gap-review.md §2.5

The endpoint reads governance.prompts WHERE status='active' and
projects the operator-relevant fields (name, version, model,
temperature, max_tokens, status). Template bodies are intentionally
NOT exposed here.

Negative-assertion §43-style:
 1. Baseline — fetch /health/prompts, capture the count of active
    rows we have NOT inserted.
 2. Insert one active row + one draft row + one archived row +
    one deprecated row, all sharing a unique drill-name prefix.
    Re-fetch /health/prompts. Verify ONLY the active row for our
    prefix appears. NEGATIVE: draft/archived/deprecated rows must
    NOT appear — that's the WHERE filter contract.
 3. Tuning fields (model, temperature, max_tokens) round-trip
    correctly. NEGATIVE: a regression that returned ``model: null``
    when the row HAS a model would mask which model is actually
    live.
 4. ``status`` field is the literal string 'active' for every
    returned row. NEGATIVE: a regression that joined into a
    different table (e.g. evaluation runs) and produced rows
    with status='completed' would still pass step 2 but fail
    here.
 5. ``db_reachable`` is True when the DB is up. The endpoint must
    NOT crash with a 500 even when there are zero rows; it
    returns 200 + empty list.
 6. Multiple active versions of the same name are BOTH returned
    (A/B rollout). NEGATIVE: a regression that DISTINCT'd by
    name and dropped older versions would silently break
    operator visibility into A/B state.

Run:
    PYTHONPATH=/mnt/deepa/rag python mcp/tests/drill_inference_health_prompts.py
"""
from __future__ import annotations

import asyncio
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


async def _delete(pool: asyncpg.Pool, name_prefix: str) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM governance.prompts WHERE name LIKE $1",
            f"{name_prefix}%",
        )


async def _insert(
    pool: asyncpg.Pool,
    *, name: str, version: str, status: str,
    template: str = "system\n---USER---\nask: {q}",
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO governance.prompts
                (name, version, template, status, model,
                 temperature, max_tokens)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            """,
            name, version, template, status, model, temperature, max_tokens,
        )


async def _fetch(c: httpx.AsyncClient) -> dict:
    r = await c.get(f"{INF_BASE}/api/v1/health/prompts")
    if r.status_code != 200:
        fail(f"/health/prompts returned {r.status_code}: {r.text[:200]}")
    return r.json()


async def main() -> None:
    suffix = uuid.uuid4().hex[:8].upper()
    NAME = f"drill_visibility_{suffix}"

    pool = await asyncpg.create_pool(dsn=PG_DSN, min_size=1, max_size=2)
    try:
        await _delete(pool, "drill_visibility_")

        async with httpx.AsyncClient(timeout=10.0) as c:
            step("0. baseline /api/v1/health/prompts")
            base = await _fetch(c)
            for required in ("service", "observed_at", "db_reachable", "prompts"):
                if required not in base:
                    fail(f"missing top-level key: {required}")
            if not isinstance(base["prompts"], list):
                fail("prompts must be a list")
            if not isinstance(base["db_reachable"], bool):
                fail(
                    f"db_reachable must be bool, got "
                    f"{type(base['db_reachable']).__name__}"
                )
            base_ours = [p for p in base["prompts"] if p["name"] == NAME]
            if base_ours:
                fail(f"unique drill name already present: {base_ours}")
            ok(
                f"baseline: db_reachable={base['db_reachable']} "
                f"total_active={len(base['prompts'])}"
            )

            step("1. insert active + draft + archived + deprecated")
            await _insert(
                pool, name=NAME, version="v1", status="active",
                model="llama3.1:8b", temperature=0.1, max_tokens=1024,
            )
            await _insert(pool, name=NAME, version="v2_draft", status="draft")
            await _insert(pool, name=NAME, version="v3_archived", status="archived")
            await _insert(pool, name=NAME, version="v4_deprecated", status="deprecated")
            r = await _fetch(c)
            ours = [p for p in r["prompts"] if p["name"] == NAME]
            if len(ours) != 1:
                fail(
                    f"expected 1 row (the active one), got {len(ours)}: "
                    f"{[p['version'] for p in ours]}. "
                    f"Either WHERE status='active' is broken, or "
                    f"non-active rows are bleeding into the response."
                )
            if ours[0]["version"] != "v1":
                fail(
                    f"wrong version surfaced: {ours[0]['version']}. "
                    f"Only the v1/active row should appear."
                )
            ok("only the active row v1 surfaced (3 non-active rows filtered)")

            step("2. tuning fields round-trip — model, temperature, max_tokens")
            row = ours[0]
            if row["model"] != "llama3.1:8b":
                fail(f"model field wrong: got {row['model']!r}")
            if row["temperature"] != 0.1:
                fail(f"temperature wrong: got {row['temperature']!r}")
            if row["max_tokens"] != 1024:
                fail(f"max_tokens wrong: got {row['max_tokens']!r}")
            ok(f"model={row['model']} temp={row['temperature']} max_tokens={row['max_tokens']}")

            step("3. status field literal — every returned row says 'active'")
            for p in r["prompts"]:
                if p["status"] != "active":
                    fail(
                        f"non-active row leaked into /health/prompts: "
                        f"{p['name']}/{p['version']} status={p['status']!r}. "
                        f"Either the WHERE filter is wrong or the projection "
                        f"is reading a different table."
                    )
            ok(f"all {len(r['prompts'])} returned rows have status='active'")

            step("4. db_reachable=true and 200 even with zero matches")
            # Delete our row temporarily — the OTHER rows are untouched.
            await _delete(pool, "drill_visibility_")
            r2 = await _fetch(c)
            if not r2["db_reachable"]:
                fail("db_reachable went false despite DB being up")
            ours2 = [p for p in r2["prompts"] if p["name"] == NAME]
            if ours2:
                fail("delete didn't propagate")
            # Re-insert for next step.
            await _insert(
                pool, name=NAME, version="v1", status="active",
                model="llama3.1:8b", temperature=0.1, max_tokens=1024,
            )
            ok("db_reachable holds; endpoint returned 200 with no panic on empty match")

            step("5. multiple active versions of same name BOTH appear (A/B)")
            await _insert(
                pool, name=NAME, version="v2", status="active",
                model="qwen2.5:14b", temperature=0.05, max_tokens=2048,
            )
            r3 = await _fetch(c)
            ours3 = [p for p in r3["prompts"] if p["name"] == NAME]
            versions = {p["version"] for p in ours3}
            if versions != {"v1", "v2"}:
                fail(
                    f"A/B rollout broken — expected {{v1, v2}} "
                    f"both active, got {versions}. A regression that "
                    f"DISTINCT'd by name would drop older versions and "
                    f"hide A/B state from operators."
                )
            models = {p["model"] for p in ours3}
            if models != {"llama3.1:8b", "qwen2.5:14b"}:
                fail(f"per-version model mapping wrong: {models}")
            ok(f"both versions surface with their respective models: {sorted(models)}")

        # Cleanup.
        await _delete(pool, "drill_visibility_")

    finally:
        await pool.close()

    print(f"\n{BOLD}{GREEN}════════════════════════════════════════{NC}")
    print(f"{BOLD}{GREEN}  ALL 6 PROMPT-REGISTRY-VISIBILITY STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}════════════════════════════════════════{NC}")


if __name__ == "__main__":
    asyncio.run(main())
