# Golden Demo — End-to-End Walkthrough

**Status:** 🟢 Green. 10 steps, 13 assertions, 0 failures.
**Script:** [scripts/golden-demo.sh](../scripts/golden-demo.sh)
**Date:** 2026-04-24

This is the single executable proof that DocuMind's end-to-end behaviour
works: health → RAG → document saga → agent action → CB fallback →
Qdrant chaos → recovery. Run it; if any assertion fails, exit code is
non-zero.

---

## What the script proves

| # | Step | What it proves |
| - | --- | --- |
| 1 | Health check all 4 services | ingestion/retrieval/inference/mcp-hr all reachable |
| 2 | Baseline RAG ask | existing corpus retrievable, cited answer from LLM |
| 3 | Upload a new document | ingestion saga accepts multipart upload |
| 4 | Poll document until `active` | saga runs: parse → embed → index end-to-end |
| 5 | Ask about the NEW doc | new corpus is immediately queryable and cited |
| 6 | Agent submits 3-day leave | MCP tool fires, real ticket returned |
| 7 | Kill MCP → agent degrades | CB persists a draft, `degraded=true`, no 5xx |
| 8 | Restart MCP → action recovers | CB probes after recovery_timeout, next call green |
| 9 | Kill Qdrant → structured 502 | retrieval refuses to cache-poison on degraded |
| 10 | Restart Qdrant → retrieval recovers | cache skip on failure means first call after returns real data |

---

## How to run it

Prerequisites (docker-compose stack + three HTTP services):

```bash
# infra: postgres(55432), qdrant(6333), redis(56379),
#        neo4j(7687), ollama(11434), minio(59000), kafka(9094)
docker compose up -d postgres qdrant redis neo4j ollama minio kafka

# services (each in its own shell)
source /tmp/start-ingestion-env.sh && uvicorn app.main:app --host 127.0.0.1 --port 8082
source /tmp/start-retrieval-env.sh && uvicorn app.main:app --host 127.0.0.1 --port 8083
source /tmp/start-inference-env.sh && uvicorn app.main:app --host 127.0.0.1 --port 8084

# MCP HR server
PYTHONPATH=. MCP_HR_PORT=8090 python mcp/server_hr.py

# run the demo
scripts/golden-demo.sh
```

Exit code 0 only if every step passes.

---

## Captured run output

```
── Step 1 — health check — all 4 services ──
  ✓ ingestion /health 200
  ✓ retrieval /health 200
  ✓ inference /health 200
  ✓ mcp-hr /health 200

── Step 2 — baseline RAG ask (existing corpus) ──
  ✓ grounded answer with 3 citation(s)
  · $500 per day [Source: ae303815-1c97-49a4-9441-754226a97c7c, Page 1]

── Step 3 — upload a NEW document ──
  ✓ uploaded → document_id=3a4dc8b9-f9fc-416b-8bff-2a5708204bdb

── Step 4 — poll document status until active ──
  · state=parsed (attempt 1/5)
  ✓ state=active (attempt 2)

── Step 5 — ask about the NEW document ──
  ✓ cited answer retrieved from new document
  · According to [Source: 3a4dc8b9-f9fc-416b-8bff-2a5708204bdb, Page 1] ...
    the parental-leave policy grants employees 12 weeks of paid leave for
    the birth or adoption of a child. Leave must be used within 12 months
    of the event and extensions require HR approval and a written request.

── Step 6 — agent action: submit 3-day leave → MCP → real ticket ──
  ✓ real ticket created: ticket_id=HR-40F3494A

── Step 7 — chaos: kill MCP server → agent falls back to draft ──
  · MCP health post-kill: 000 (expecting 000/refused)
  ✓ degraded=True draft_id=DRAFT-5B796A9D43 (no 5xx)

── Step 8 — restart MCP server → action path recovers ──
  · waiting recovery_timeout for CB to probe...
  ✓ recovered — new ticket_id=HR-267580EE

── Step 9 — chaos: kill Qdrant → user sees structured 502, no cache poison ──
  ✓ structured 502 with error_code (not a crash)

── Step 10 — restart Qdrant → retrieval recovers without FLUSHDB ──
  ✓ recovery green — 3 citation(s)

═══════════════════════════════════════════════════
   PASSED: 13     FAILED: 0
═══════════════════════════════════════════════════
```

---

## What each step actually hits on the wire

| Step | Endpoint | Chaos action |
| --- | --- | --- |
| 1 | `GET /health` × 4 | — |
| 2 | `POST /api/v1/ask` on :8084 | — |
| 3 | `POST /api/v1/documents/upload` on :8082 | — |
| 4 | `GET /api/v1/documents/{id}` on :8082 | — |
| 5 | `POST /api/v1/ask` on :8084 (after FLUSHDB) | — |
| 6 | `POST /api/v1/agent/ask` on :8084 | — |
| 7 | same endpoint | `pkill -f 'mcp/server_hr.py'` |
| 8 | same endpoint | restart MCP + wait for CB recovery_timeout |
| 9 | `POST /api/v1/ask` (after FLUSHDB) | `docker compose kill qdrant` |
| 10 | same endpoint | `docker compose up -d qdrant` |

---

## Why step 7 is the keystone assertion

Everything in steps 1–6 is what "it works" looks like. Step 7 is what
"it fails correctly" looks like: MCP dead, agent still answers, action
converted to a durable draft (`DRAFT-*`), HTTP 200 with a structured
`action.degraded=true` field.

That is the production-ready shape: **the user gets a coherent answer
even when a downstream tool is down**. The draft id is the audit trail
for later replay (to be persisted in `governance.hitl_queue` — tracked
as a follow-up in [DEMO-DAY-3-MCP.md](DEMO-DAY-3-MCP.md)).

Similarly, step 9 is the keystone for retrieval: Qdrant dead → no
cached fake result → HTTP 502 with `error_code=EXTERNAL_SERVICE_ERROR`
(structured, not a stack trace). Step 10 proves the cache skip is
correct: no `FLUSHDB` needed after recovery, the next call returns
real data.

---

## Follow-ups (tracked; out of scope for this demo)

- Persist drafts to `governance.hitl_queue` table (currently in-memory dict).
- Hit the HR MCP tools through a proper scope check (derive from JWT role).
- LLM-based intent detection replacing the regex matcher in `agent.py`.
- OTel trace capture across the full 10-step run (separate demo).
