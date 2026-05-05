# ADR-023: Empirical RAG-config promotion loop

## Status

Accepted — closed end-to-end across 15 commits 2026-05-04 → 2026-05-05.
Live empirical winner promoted; meta-gate (`stage3_earned_check`)
correctly refuses Stage-3 default-flip until 10+ cycles accumulate.

## Context

Before this work, retrieval defaults (`top_k=5`, `min_score=0.0`,
`rerank=False`) were hard-coded constants in the `RetrieveRequest` /
`AskRequest` Pydantic schemas. The empirical RAG test on 2026-05-04
(`docs/architecture/rag-deep-test-2026-05-04.md`) found:

* `min_score=0.0` → 0% pass-rate (Q1 "Half-Life 2" returned 5
  unrelated chunks against a corpus with no Half-Life content)
* `min_score=0.5` → 100% pass-rate

But there was **no chain to propagate that empirical winner into the
request defaults**, and **no safety gate** to refuse promotion when
the eval set was too small or the margin too narrow. So:

1. Operators tweaking config in code = §38 reproducibility gap.
2. Blind "highest pass-rate wins" = silently promotes degraded eval runs.
3. No audit trail = can't reconstruct *why* the live config is what it is.

## Decision

Build a six-stage promotion loop, each stage a separate file with a
single `is_available` gate, fail-safe defaults per §47, and a §43
drill that locks the contract:

1. `scripts/eval_set_generator.py` — auto-curate Q&A pairs from corpus
2. `scripts/run_autorag_empirical.py` — orchestrator (8 configs × 5 questions)
3. `scripts/promote_best_config.py` — 3 thresholds + Occam tie-break
4. `scripts/best_config_loader.py` — TTL-cached registry reader
5. Stage-2 wires into `rag_inference.ask` + `HybridRetriever.retrieve`
6. `scripts/best_config_history.py` + `/api/v1/health/best-config*` — audit/visibility
7. `scripts/stage3_earned_check.py` — meta-gate refuses speculative default-flips

## Four discipline rules (NON-NEGOTIABLE — drilled)

### Rule 1: `model_fields_set` is the only correct override-vs-intent guard

```python
if "top_k" not in request.model_fields_set:
    effective_top_k = best_config.top_k
```

`request.top_k == 5` doesn't tell you whether the caller meant `5`
or accepted the default. `model_fields_set` does. Without this guard,
explicit `min_score=0.0` (caller disabling the floor) gets silently
overridden to `0.5` from `best_config` — caller intent destroyed.

Drilled: `drill_best_config_in_inference_stage2.py` step 4 +
`drill_best_config_in_retriever_stage2.py` step 4.

### Rule 2: cache fingerprint reads request literal, NOT effective override

`hybrid_retriever.py:120` — `min_score=str(req.min_score)`. Two callers
with different intent (one explicit `0.0`, one omitting → best_config
`0.5`) MUST hit different cache rows. If we fingerprinted on
`effective_min_score`, they'd collide.

Drilled: `drill_best_config_in_retriever_stage2.py` step 7.

### Rule 3: visibility endpoints NEVER raise

`/api/v1/health/best-config*` are surfaces operators read DURING
incidents. A 500 there masks the real outage they're investigating.
Lazy import + try/except + always-200 + descriptive `enabled+loaded`
fields are the contract. Drilled.

### Rule 4: every promotion decision logged — success OR rejection

`.loop/best_config_history.jsonl` is append-only. A gate that
*rejects* without *logging the rejection with reason* is just a noisy
filter. Three-tier classification (`promoted` / `rejected` / `skipped`)
maps to the three states an audit needs.

## Consequences

### Positive

* **§38 governance achieved.** Every promotion attempt records
  `decided_at_ts`, `gates_failed`, `pass_rate`, `margin`,
  `eval_set_size`, `raw_winner_signature`. Operators can reconstruct
  why the live config is what it is.
* **§47 fail-safe at every layer.** Loader missing? defaults. Loader
  malformed? defaults. Loader disabled? request unchanged. Three
  commits, no new failure modes.
* **§56 Stage-1/2 6-gate adoption.** Each adapter has explicit env
  flag + drill + Stage-2 wire site documented in next_stage.
* **Meta-gate prevents speculation.** Stage-3 default-flip requires
  the `earned` verdict from `stage3_earned_check` (≥10 cycles AND
  success_ratio ≥ 0.8 AND ≥2 distinct configs). Currently `not_earned`
  (2/10 cycles).
* **Cross-service shape parity.** Inference-svc + retrieval-svc both
  expose `/health/best-config` and `/health/best-config-history` with
  IDENTICAL response shapes. Drill enforces field-set superset.

### Negative

* **One more env flag per operator** (4 new flags: `BEST_CONFIG_LOADER_ENABLED`,
  `PROMOTION_GATE_ENABLED`, `BEST_CONFIG_HISTORY_ENABLED`, `STAGE3_EARNED_CHECK_ENABLED`).
  Mitigation: each defaults off; opt-in is the operator's choice.
* **TTL=300s cache** in loader means config changes propagate slowly.
  Mitigation: `force_reload()` operator hook bypasses cache.
* **Substring scoring** (Stage-2 fast path) doesn't catch semantic
  equivalence. Mitigation: Stage-3 swaps in RAGAS judge for final
  promotion (~10x slower, deferred to scheduled run).

### Risks accepted

* **Tie-break heuristic is opinionated.** Occam (fewer features wins)
  may pick a config the operator wouldn't. Mitigation: tie events
  logged in history; operator can override by tweaking gate thresholds.
* **No frontend page yet.** Operators must `curl` the health endpoints
  or read history.jsonl directly. Acceptable: dashboard surface is a
  parallel-tool stream concern.

## Alternatives considered

| Alternative | Rejected because |
|---|---|
| Hardcode the empirical winner in code | §38 governance gap; no audit trail; reproducibility nightmare |
| Single mega-script (search + gate + write in one) | Drill granularity collapses; can't unit-test the gate independently |
| Auto-flip Stage-3 default after first promotion | §56.3 violation; one cycle is noise, not signal |
| ConfigMap / env-only override (no registry file) | Loses per-promotion provenance; can't replay decisions |
| RAGAS scoring in the runner directly | ~48hr per full grid (96 configs × 5 q × 5 metrics × 20s) — blocks the loop |

## References

* `docs/architecture/empirical-rag-config-loop.md` — operator runbook
* `docs/architecture/rag-deep-test-2026-05-04.md` — original empirical gap
* CLAUDE.md §38 (governance), §43 (drills), §47 (fail-safe),
  §49 (compose-footer), §56 (Stage-1/2 adoption)
* Memory: `project_empirical_loop.md`, `project_autorag_py313_pin.md`

### Commit map

| Hash | Subject |
|---|---|
| `f94eaf4` | best_config registry loader Stage-1 |
| `57a5ad0` | Stage-2 wire into rag_inference.ask |
| `2a939e6` | Stage-2 wire into HybridRetriever |
| `01729e0` | /api/v1/health/best-config (inference-svc) |
| `6a1e8f0` | mirror /api/v1/health/best-config (retrieval-svc) |
| `d7f9e68` | promotion gate Stage-1 (3 thresholds + Occam) |
| `7256fc4` | Stage-2 wire of gate into AutoRAG runner |
| `b6a6fcf` | best_config_history audit-trail reader |
| `a33ff27` | env-only-gate fix (py3.13 unblock) |
| `6bd50e7` | docs/architecture/empirical-rag-config-loop.md |
| `2741a93` | /api/v1/health/best-config-history route |
| `3704514` | drill_min_score_filter accepts effective_min_score |
| `95d5c2b` | doc compose-footer backticks |
| `cd7b2f1` | retrieval-svc mirror /health/best-config-history |
| `9185e76` | Stage-3-earned check + drill |

## Composes with

- `§38` governance — every decision logged with provenance
- `§43` drill discipline — 11 drills × 8 steps = 88 step-locks
- `§47` fail-safe — every layer falls back to legacy defaults
- `§48` explainability — `trace.step("best_config_defaults")`
- `§49` compose-footer — this ADR is the cross-reference root
- `§51` forensic substrate — every commit cites Location/Approach/Policies
- `§54` no Co-Authored-By trailer
- `§56.3` Stage-3 (default-flip) requires 10+ empirical cycles
- `scripts/best_config_loader.py` — Stage-1 reader
- `scripts/promote_best_config.py` — gate
- `scripts/stage3_earned_check.py` — meta-gate
