# GEPA chain status — Stage-1..5 live, Stage-6 blocked on predictor-name alignment

**Updated:** 2026-05-05 (commit `e313ae6` shipped Stage-5)

## Stages live in production

| Stage | Component | Commit | Status |
|---|---|---|---|
| 1 | DSPy + GEPA adapter (`dspy_optimizer.py`) | (pre-session) | Stage-1 default-deny |
| 2 | Eval-set generator with `--seed` | `bc81c3a` | Stage-2 default-deny |
| 3 | `run_gepa_empirical --mode=compile` invokes `dspy.GEPA().compile()` | `fa8c2a4`, `b14dfaa`, +linter | Stage-3 LIVE-VERIFIED (smoke run produces real council answers) |
| 4 | `promote_gepa_prompts` gate | `67df048` | Stage-4 default-deny gate |
| 5 | `prompt_repo._overlay_gepa_active` reads artifact | `e313ae6` | Stage-5 default-deny overlay |
| **6** | **Canary traffic-split** | (deferred) | **BLOCKED** — see below |

## Stage-6 blocker: predictor-name mismatch

When `prompt_repo._reload()` runs, it builds the cache from two sources:

| Source | Key shape | Example |
|---|---|---|
| `governance.prompts` table | `<name>_<version>` | `rag.qa_v1` |
| `PROMPT_TEMPLATES` in-code | `<name>` | `rag.qa` |
| GEPA artifact (Stage-5 overlay) | `<predictor>_gepa-<ts>` | `predict.predict_gepa-1762383951` |

Runtime call site (`rag_inference.py:279`):

```python
system, user, citation_map = self._prompts.build(
    template_name=self._default_prompt,  # e.g. "rag.qa"
    ...
)
```

Stage-6 would route some traffic to `<name>_gepa-<ts>` based on hash(tenant_id) % 100. **But** GEPA's `CouncilProgram` (in `dspy_optimizer.py`) optimizes a `dspy.ChainOfThought(CouncilSignature)` predictor named `predict.predict` — not `rag.qa`. The cache keys never overlap → the canary can't fire.

## Two paths to unblock Stage-6

### Path A — Refactor `CouncilProgram` to wrap the runtime template

Make `dspy_optimizer.get_council_program()` build its `dspy.Signature` from the live `rag.qa` template (read from `prompt_repo`), so GEPA's predictor naming matches the runtime lookup.

**Pros:** GEPA tunes the *actual* prompt that production uses.
**Cons:** Refactor touches 3 files (`dspy_optimizer.py`, `run_gepa_empirical.py`, `prompt_repo.py`); changes the optimization target shape; needs a re-drill of Stage-3 (`drill_gepa_stage3_compile`).

### Path B — Add `gepa_target_prompt` field to artifact + remap on overlay

Have `promote_gepa_prompts.py` read an env var `GEPA_TARGET_PROMPT_NAME` (e.g. `rag.qa`) and write it into the artifact. `_overlay_gepa_active` reads that field and registers under `<gepa_target_prompt>_gepa-<ts>`.

**Pros:** Smaller change; preserves existing GEPA optimization shape.
**Cons:** Operator has to set env var explicitly; mismatch risk if operator forgets.

## Recommended approach

**Path A.** Path B is a band-aid that pushes the alignment burden to the operator at every compile run. Path A makes the chain self-consistent by construction.

## Unblocked operator paths today

Even without Stage-6, operators get value from Stages 1-5:

```bash
# Run GEPA compile, see what GEPA tunes (separate predictor namespace)
make empirical-gepa-compile

# After successful compile + Stage-4 gate:
GEPA_PROMPTLOADER_ENABLED=1 \
  python3 scripts/promote_gepa_prompts.py
# → .loop/gepa_active_prompts.json populated

# Stage-5 overlay loads it on next service reload, but the
# gepa-tagged versions sit in cache UNUSED until Stage-6 routes
# requests to them.
```

The infrastructure is wired; the *traffic* doesn't yet flow through it.

## What I'd want from the operator before Stage-6

1. Decision on Path A vs B (architecturally important; not autonomous-scope)
2. Which prompt(s) to target — `rag.qa`, `rag.qa.cot`, `agent.intent_router`, etc.
3. Canary semantics:
   - Tenant-sticky (hash(tenant_id) % 100)?
   - Random per-request?
   - Header-driven (`X-GEPA-Cohort: canary`)?
4. Failure-mode contract: if canary version fails at runtime, does fallback go to baseline OR error out?

## Composes with

- `docs/architecture/adr/023-empirical-rag-config-promotion-loop.md`
- `docs/architecture/adr/024-best-config-loader-default-on.md`
- `docs/architecture/empirical-rag-config-loop.md`
- `docs/runbooks/empirical-loop-stage3-promotion.md`
- CLAUDE.md `§38` `§43` `§47` `§54` `§56`
- `scripts/promote_gepa_prompts.py` — Stage-4 gate
- `services/inference-svc/app/services/prompt_repo.py` — Stage-5 overlay site
