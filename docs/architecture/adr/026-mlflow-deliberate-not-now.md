# ADR-026: MLflow deliberate-not-now (Langfuse covers LLM obs)

## Status

Accepted — 2026-05-06. Re-evaluation triggered when **either** of the
re-eval conditions in §Consequences fires.

## Context

The architecture matrix surfaced on 2026-05-06 listed MLflow as
❌ deliberate ("Langfuse covers LLM obs"). The matrix-truth
reconciliation in `docs/architecture/tier1-matrix-truth.md` and
CLAUDE.md §45.4 (no checkbox flips without code) require an explicit
ADR to back any deliberate-not-now status; flipping the matrix to ✅
without that ADR is a §43 drill regression.

This ADR documents the reasoning + the explicit re-eval trigger.

### What MLflow would give us

- **Experiment tracking**: params, metrics, artifacts per training run
- **Model registry**: versioned model artifacts with stage transitions
  (Staging → Production → Archived) + canonical lineage from data → model
- **Reproducible pipelines**: `mlflow run` against a `MLproject` file
- **Vendor-neutral**: works with any framework (sklearn, torch, xgboost…)

### What we already have via Langfuse + the model registry

- **Prompt + LLM obs**: every prompt template + model version + decision
  audit row already lands in Langfuse (`docker-compose ps langfuse`)
- **Model registry (LLM-side)**: `governance.tools` SQL surface + the
  prompt-version registry surface (`/admin/llmops/deep`)
- **Cost tracking**: per-request `cost_usd` already aggregated by
  provider via `paperclip_manager.aggregate_provider_comparison()`
- **Decision audit**: `governance.audit_log` carries prompt_version +
  model_version + tenant_id + correlation_id (§38 governance)
- **Reproducibility**: best_config.json + ADR-024 (best-config-loader-
  default-on) already version-pin the inference path

## Decision

**Do not adopt MLflow at this time.**

The circuitRAG roadmap is RAG/LLM-first. The current observability stack
(Langfuse + governance.audit_log + paperclip aggregator) covers every
operator question MLflow would answer for the LLM-track:

- "What prompt was used for request X?" → Langfuse + audit_log
- "Which model version is in prod for tenant Y?" → governance.tools
- "What did this request cost?" → paperclip provider_comparison
- "Can I reproduce the answer?" → audit_log replay via correlation_id

MLflow's primary value-add (classical-ML experiment tracking with
hyperparam grids + sklearn artifacts) is not the current focus.

## Consequences

### Positive

- **Reduced surface area**: one observability stack (Langfuse) instead
  of two (Langfuse + MLflow) — fewer dashboards, fewer integrations,
  fewer auth boundaries.
- **No migration cost**: every existing audit/decision row stays
  authoritative; nothing has to be retrofit into MLflow's data model.
- **No vendor split**: ops, governance, and explainability all read
  from the same audit surfaces.

### Negative

- **Classical-ML opportunity gap**: if a future iteration needs to
  train a custom reranker (sklearn cross-encoder fine-tune), bandit
  classifier, or fairness-correction model with hyperparameter sweeps,
  the current stack has no tracking surface for it. The first such
  ask is the re-eval trigger below.
- **Dual-tracking blindspot**: a regulator audit comparing "LLM model
  card" with "classical-ML model card" would have to consult two
  different surfaces. Acceptable today (no classical-ML in prod);
  blocking when classical-ML lands.

### Re-evaluation triggers (file a new ADR superseding this one)

This ADR is **automatically re-opened** when **either** trigger fires:

1. **Classical-ML in prod**: the first sklearn / xgboost / pytorch
   training pipeline that lands in `services/*-svc/app/` with a
   `train.py` entry point. (Not eval-time only — actual training in
   the inference path.)
2. **Hyperparameter-sweep ask**: an operator ticket explicitly
   asking "we need to compare 50+ hyperparameter combos with
   per-run metric tracking" — the use case Langfuse cannot serve.

When either fires, file ADR-NNN superseding this one. The new ADR
must include: empirical comparison MLflow vs. extending Langfuse
(some custom experiment tables + Grafana dashboards may close the
gap without adding MLflow).

## Alternatives considered

### A1. Adopt MLflow now (eager)
**Rejected**: no current ML training in prod; building infrastructure
for a use case that isn't pulling = §13 ("no over-engineering") +
§45.4 ("no aspirational implementation").

### A2. Build custom experiment-tracking on Langfuse
**Deferred**: Langfuse's data model is prompt+session+score-centric,
not run+param+artifact-centric. A custom layer might close the gap;
the re-eval trigger above fires before that bet pays off.

### A3. Use Weights & Biases / Neptune / DVC instead of MLflow
**Deferred**: same re-eval trigger applies. The choice between
ML-tracking vendors is the right ADR to file when the re-eval lands.

## References

- `docs/architecture/adr/024-best-config-loader-default-on.md`
- `docs/architecture/tier1-matrix-truth.md` (matrix reconciliation)
- CLAUDE.md §40 (decision system) + §45.4 (no checkbox flips without code)
- CLAUDE.md §38 (governance: every AI decision auditable) — covered
  today by `governance.audit_log` without MLflow
