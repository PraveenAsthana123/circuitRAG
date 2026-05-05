# Runbook: drive Stage-3 verdict from `stable_single_winner` to `earned`

**Audience:** operator running the empirical RAG-config promotion loop
(commits `f94eaf4..bc81c3a`, ADR-023).

**Goal:** flip the Stage-3-earned check verdict so the operator can
deliberately promote `BEST_CONFIG_LOADER_ENABLED=1` to default-on per
CLAUDE.md §56.3.

## Prerequisites

- Local Ollama running on `http://localhost:11434` with `gemma3:1b`
  pulled (used by `eval_set_generator.py`).
- Corpus CSV at a known path (e.g. `/tmp/rag-deep-test/bbc-news-data.csv`).
- `.loop/best_config_history.jsonl` exists (created by
  `promote_best_config.py` on first run).

## Why the verdict is `stable_single_winner`

Run the check:

```bash
STAGE3_EARNED_CHECK_ENABLED=1 \
  python3 scripts/stage3_earned_check.py
```

If the verdict is `stable_single_winner`, the rationale will read
something like:

```
12 promotions but only 1 distinct config(s); need ≥2 winners across
diverse eval sets to prove generalization. Likely overfitting — vary
the eval set or set STAGE3_MIN_DISTINCT=1 to accept.
```

Same eval set + deterministic search = same winner every time. That's
not generalization. The empirical winner has only been validated
against ONE query distribution.

## The fix: vary the eval set across runs

The `eval_set_generator.py` script accepts `--seed N`. Different seed
→ different chunk shuffle → different first-N corpus rows get questions
generated → distinct eval set → distinct empirical winners over time.

### Step 1: Generate N distinct eval sets

```bash
for seed in 1 2 3 4 5 6 7 8; do
  EVAL_SET_GENERATOR_ENABLED=1 OLLAMA_HOST=http://localhost:11434 \
    python3 scripts/eval_set_generator.py \
      --corpus /tmp/rag-deep-test/bbc-news-data.csv \
      --max 8 \
      --limit-chunks 100 \
      --seed "$seed" \
      --out ".loop/eval_set_seed${seed}.jsonl"
  echo "→ wrote eval_set_seed${seed}.jsonl"
done
```

Each file contains a different 8-question eval set drawn from a different
corpus prefix. ~3-5 minutes per seed (Ollama generation cost).

### Step 2: Run the empirical loop on each eval set

```bash
for seed in 1 2 3 4 5 6 7 8; do
  AUTORAG_OPTIMIZER_ENABLED=1 PROMOTION_GATE_ENABLED=1 \
    python3 scripts/run_autorag_empirical.py \
      --eval-set ".loop/eval_set_seed${seed}.jsonl" \
      --out ".loop/autorag_search_report_seed${seed}.json" \
      --best ".loop/best_config.json" 2>&1 | tail -5
  echo "---seed ${seed}---"
done
```

Each iteration appends one row to `.loop/best_config_history.jsonl`.

### Step 3: Verify diversity grew

```bash
BEST_CONFIG_HISTORY_ENABLED=1 \
  python3 scripts/best_config_history.py --days 7
```

Expect ≥2 distinct configs in the latest decisions if the eval sets
genuinely vary the empirical winner.

### Step 4: Re-check Stage-3 verdict

```bash
STAGE3_EARNED_CHECK_ENABLED=1 \
  python3 scripts/stage3_earned_check.py
```

Target verdict: `earned`.

## What can go wrong

**Verdict still `stable_single_winner` after 8 seeds.** The simulated
`run_rag` in `run_autorag_empirical.py` is deterministic given a config
— it doesn't actually USE the eval set's content. So even with diverse
eval sets, the empirical winner is the same. To get distinct winners
the operator must:

1. Replace simulated `run_rag` with a real Ollama-backed pipeline
   (heavy; ~10x slower per cycle), OR
2. Add real RAGAS scoring (the `score_fn` callback) so different
   eval sets produce different per-config rankings, OR
3. Accept `stable_single_winner` as sufficient via
   `STAGE3_MIN_DISTINCT=1` env override (documented in
   `scripts/stage3_earned_check.py` — but **only do this if you've
   read and understood the overfitting risk**).

**Verdict `flapping`.** Cycles + diversity met but success_ratio < 0.8.
Means the gate keeps rejecting: `pass_rate` or `margin` thresholds
are too aggressive for the actual eval distribution. Lower
`PROMOTION_MIN_PASS_RATE` or `PROMOTION_MIN_MARGIN` based on the
rejection rationale logged in history.jsonl.

**`promote_best_config.py` errors during loop.** Check
`PROMOTION_GATE_ENABLED=1` is exported. Per §47 the gate is fail-safe
on import errors — silent skip would be a regression.

## After verdict flips to `earned`

**As of 2026-05-05 (commit `4be8498` + ADR-024) the default-flip has
already happened.** New deploys consume the empirical winner by default;
operators opt OUT explicitly via `BEST_CONFIG_LOADER_ENABLED=0`.

If you ever need to manually re-do the default-flip cycle (e.g., for a
new adapter that's at Stage-2 today), the recipe is:

1. Read the env-flag site (e.g. `scripts/best_config_loader.py:50`).
2. Flip the default from opt-in to opt-out form.
3. Update the drill that locks the new default-on contract.
4. Write a NEW ADR superseding the prior one (§47.3 — never edit
   accepted ADRs; supersede them).
5. Commit + push. Audit row in `.loop/best_config_history.jsonl`.

ADR-024 is the worked example of this transition for `best_config_loader`.

## Stage-3 GEPA prompt optimization

After the empirical-config loop earned its Stage-3 default-flip, the
NEXT stage is GEPA prompt optimization for the Gemma council.
Implementation shipped in commit `6cc6ddd` via `--mode=compile`:

```bash
make empirical-gepa-preflight              # cheap shape check
make empirical-gepa-compile                # full compile (10-120 min)
GEPA_AUTO=heavy make empirical-gepa-compile  # ~60-120 min, exhaustive
```

The compile invokes `dspy.GEPA().compile()` against the council program
and persists optimized prompts to `.loop/gepa_optimized_prompts.json`.
Stage-4 (deferred) wires those optimized prompts back into
`services/inference-svc/app/services/prompt_repo.py`.

## Composes with

- `docs/architecture/empirical-rag-config-loop.md` — chain overview
- `docs/architecture/adr/023-empirical-rag-config-promotion-loop.md`
- `scripts/stage3_earned_check.py` — meta-gate
- `scripts/eval_set_generator.py` — `--seed` flag
- `scripts/best_config_history.py` — audit-trail projection
- CLAUDE.md `§38` `§43` `§47` `§56.3`
