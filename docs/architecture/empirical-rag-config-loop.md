# Empirical RAG-config Promotion Loop — End-to-End

**Closed:** 2026-05-04 → 2026-05-05 (10 commits, 72 drill-steps green)
**Status:** Live. End-to-end verified on the BBC News corpus.

## Why this loop exists

Before this work, retrieval defaults (`top_k=5`, `min_score=0.0`, `rerank=False`)
were hard-coded constants in the request schemas. The empirical RAG test
on 2026-05-04 (`docs/architecture/rag-deep-test-2026-05-04.md`) showed:

- `min_score=0.0` → 0% pass-rate (chunks unrelated to query slip through)
- `min_score=0.5` → 100% pass-rate (5-pair eval set)

But there was no chain to **propagate that empirical winner into the
request defaults**, and no **safety gate** to refuse promotion when the
eval set was too small or the margin too narrow. So:

1. Operators tweaking config in code = reproducibility gap (§38).
2. Blind "highest pass-rate wins" = silently promotes degraded eval runs.
3. No audit trail = can't reconstruct *why* the live config is what it is.

## The closed chain

```
.loop/eval_set.jsonl                     (operator content, generated/curated)
  │
  │   scripts/run_autorag_empirical.py    (orchestrator)
  ▼
scripts/autorag_optimizer.py             (search engine — env-only gate after a33ff27)
  │
  │   8 configs × 5 questions = 40 evals
  │   substring scoring (Stage-2 fast path; Stage-3 swaps in RAGAS judge)
  ▼
.loop/autorag_search_report.json         (ranked configs + per-metric means)
  │
  │   scripts/promote_best_config.py     (3 thresholds + Occam tie-break)
  │   PROMOTION_MIN_PASS_RATE=0.5
  │   PROMOTION_MIN_MARGIN=0.0
  │   PROMOTION_MIN_EVAL_SET=5
  ▼
.loop/best_config.json                   (winner + provenance)
.loop/best_config_history.jsonl          (append-only audit trail; success OR rejection)
  │
  │   scripts/best_config_loader.py      (5min TTL cache, fail-safe defaults)
  ▼
services/inference-svc/.../rag_inference.py    (ask() Stage-2: top_k default)
services/retrieval-svc/.../hybrid_retriever.py (retrieve() Stage-2: min_score default)

Operator visibility:
  GET /api/v1/health/best-config         (both inference-svc + retrieval-svc, shape-parity drilled)
  scripts/best_config_history.py         (CLI audit-trail summary)
```

## The four discipline rules (non-negotiable)

### 1. `model_fields_set` is the ONLY way to layer registry defaults on Pydantic args

```python
# CORRECT — caller intent preserved
if "top_k" not in request.model_fields_set:
    effective_top_k = best_config.top_k

# WRONG — explicit min_score=0.0 (caller disabling floor) gets silently
# overridden to 0.5 from best_config
if request.top_k == 5:  # default value
    effective_top_k = best_config.top_k
```

`model_fields_set` distinguishes "caller omitted the field" from "caller
passed the default value." Without this guard, registry overrides destroy
caller intent. Drilled at `mcp/tests/drill_best_config_in_inference_stage2.py`
step 4 + retriever step 4.

### 2. Cache fingerprint reads the request literal, NOT the effective override

`hybrid_retriever.py:120` — `min_score=str(req.min_score)`. If we
fingerprinted on `effective_min_score`, two callers with different intent
(one explicit `0.0`, one omitting → best_config `0.5`) would COLLIDE on
the same cache row. Drilled at `drill_best_config_in_retriever_stage2.py`
step 7.

### 3. Visibility endpoints NEVER raise

`/api/v1/health/best-config` is the surface operators read DURING incidents.
A 500 here masks the real outage they're investigating. Lazy import +
try/except + always-200 + descriptive `enabled+loaded` fields are the
contract. Drilled at `drill_health_best_config_route.py` step 4 + step 6.

### 4. The promotion gate logs EVERY decision, success or rejection

`.loop/best_config_history.jsonl` is append-only. A gate that *rejects*
without *logging the rejection with reason* is just a noisy filter —
operators can't tell whether the gate is working or fighting them. Three-
tier classification: `promoted` / `rejected` / `skipped` map to the three
states an audit needs. Drilled at `drill_promote_best_config_stage1.py`
step 7 + `drill_best_config_history_stage1.py` step 8.

## Env flags (default-deny per §56)

| Flag | Default | Purpose |
|------|---------|---------|
| `AUTORAG_OPTIMIZER_ENABLED=1` | off | gates the search loop |
| `PROMOTION_GATE_ENABLED=1` | off | gates promotion (else legacy blind-write) |
| `BEST_CONFIG_LOADER_ENABLED=1` | off | gates consumer-side defaults |
| `BEST_CONFIG_HISTORY_ENABLED=1` | off | gates the history-reader CLI |
| `PROMOTION_MIN_PASS_RATE` | 0.5 | gate threshold |
| `PROMOTION_MIN_MARGIN` | 0.0 | gate threshold |
| `PROMOTION_MIN_EVAL_SET` | 5 | gate threshold |

When ALL flags are off, the legacy un-tuned defaults run unchanged. Stage-3
default-flip is **not yet earned** per §56.3 (requires 10+ empirical
cycles; we have 1).

## Operator runbook

```bash
# 1. Generate / refresh the eval set (one-shot)
EVAL_SET_GENERATOR_ENABLED=1 \
  python3 scripts/eval_set_generator.py \
    --corpus docs/sample-corpus/bbc-news-data.csv \
    --max-pairs 50 \
    --out .loop/eval_set.jsonl

# 2. Run empirical search + gated promotion
AUTORAG_OPTIMIZER_ENABLED=1 PROMOTION_GATE_ENABLED=1 \
  python3 scripts/run_autorag_empirical.py \
    --eval-set .loop/eval_set.jsonl \
    --out .loop/autorag_search_report.json \
    --best .loop/best_config.json

# 3. Inspect what got promoted (and what got rejected) in the last 7 days
BEST_CONFIG_HISTORY_ENABLED=1 \
  python3 scripts/best_config_history.py --days 7

# 4. Wire the loaded config into running services (per request)
BEST_CONFIG_LOADER_ENABLED=1 ./scripts/restart-services.sh
# Then verify via the operator dashboard:
curl http://localhost:8000/api/v1/health/best-config
curl http://localhost:8001/api/v1/health/best-config
```

## Composes with

- `§38` governance: every promotion logged with version + provenance + actor
- `§43` drill discipline: 9 drills × 8 steps = 72 step-locks on this chain
- `§47` fail-safe: every layer of the chain falls back to legacy defaults on error
- `§48` explainability: `trace.step("best_config_defaults")` audit row in `ask()`
- `§49` compose-footer: this doc itself is the cross-reference for the chain
- `§51` forensic substrate: every commit cites Location/Approach/Policies/Verify
- `§54` no Co-Authored-By trailer: applies
- `§56` Stage-1/2 6-gate adoption: each adapter went through gate-1 (eval) → gate-5 (drill)
- `scripts/best_config_loader.py` — TTL-cached registry reader
- `scripts/promote_best_config.py` — gate Stage-1
- `scripts/best_config_history.py` — audit-trail projection
- `services/inference-svc/app/services/rag_inference.py` — Stage-2 wire site
- `services/retrieval-svc/app/services/hybrid_retriever.py` — Stage-2 wire site

## Commit map

| Commit | Title |
|--------|-------|
| `f94eaf4` | best_config registry loader Stage-1 |
| `57a5ad0` | Stage-2 wire into rag_inference.ask |
| `2a939e6` | Stage-2 wire into HybridRetriever |
| `01729e0` | /api/v1/health/best-config on inference-svc |
| `6a1e8f0` | mirror /api/v1/health/best-config on retrieval-svc |
| `d7f9e68` | promotion gate Stage-1 |
| `7256fc4` | Stage-2 wire of gate into AutoRAG runner |
| `b6a6fcf` | best_config_history audit-trail reader |
| `a33ff27` | env-only-gate fix (py3.13 unblock) |
| (this doc) | architecture summary |

## Live empirical winner (2026-05-05)

```json
{
  "config": {
    "chunking_strategy": "recursive_paragraph_sentence",
    "min_score": 0.5,
    "rerank_enabled": false,
    "rerank_top_k": 10,
    "retrieval_top_k": 10
  },
  "pass_rate": 1.0,
  "margin": 1.0,
  "eval_set_size": 5,
  "occam_tie_break": "rerank=False over rerank=True (both at 1.0)"
}
```
