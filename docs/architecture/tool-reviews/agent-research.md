# `ResearchAgent` + `mcp_research` — Brutal Tool Review

**Source:** `services/agent-orchestrator-svc/app/research.py` + `mcp/server_research.py`
**Date:** 2026-05-01

## Triage

| Severity | Count | Top items |
|---|---|---|
| **P0** | 0 | — |
| **P1** | 5 | rows #11 (no slow-fetch detect), #12 (no rate-window), #18 (no integration drill), #21 (no caching), #36 (no breaker around mcp_research) |
| **P2** | 3 | rows #19, #20, #22 |

## Highlights

- ✅ E6 wired real httpx fetch with 5 security guards (file://, data:, ≥6 URLs, etc.)
- ✅ `_validate_url` rejects non-http(s)
- ✅ HTML extractor strips `<script>`/`<style>`
- ✅ 1 MiB body cap

## Notable gaps

| # | Dim | Status | Note |
|---|---|---|---|
| 11 | Slow-fetch detect | ✗ | **P1** — slow upstream (8s response) returns ok with 0 indication |
| 21 | Persistent research cache | ✗ | **P1** — each researcher call hits source from scratch; same topic re-fetched |
| 23 | Cost-of-failures | ⚠ | Fetch is free, but LLM synthesis path (Tier-B in agent) costs — not tracked at MCP boundary |
| 25 | Audit row | ⚠ | Sources flow to /explain via task_runs; retrieval-trail per §48.5 not first-class field |
| 31 | Identity boundary | ⚠ | mcp_research ignores `tenant_id` for filtering — global cache risk |
| 33 | Rate limit on /tools/call | ✗ | **P1** — flooding research.synthesize with 5-URL × 1000-task = DoS the upstream sites |
| 36 | DB/dep CB | ✗ | **P1** — no breaker on mcp_research itself; if one upstream URL is slow, every tenant's research is slow |
| 37 | Idempotency | ⚠ | Same (topic, urls) → would re-fetch identical pages every time |

## Brutal one-liner

> The hardening so far is **at the parser level** (URL validation + HTML extraction);
> what's missing is **operational discipline** — no caching, no rate limit, no breaker.
> 5 P1 gaps. The 100GB RAG goal needs caching urgently; without it, every researcher
> call is full upstream pay.
