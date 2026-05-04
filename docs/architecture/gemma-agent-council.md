# Gemma Agent Council — full architecture (Stage-1 adapter)

> Operator-supplied 5-agent local-Gemma orchestrator. Built per the brutal
> rule: **fewer, well-defined roles**. Default chain ships 5 stages;
> shieldgemma:9b only fires for high-risk domains.

## Why this exists

Per CLAUDE.md §39 + §47 + the operator-supplied tool comparison table.
The empirical RAG test (rag-deep-test-2026-05-04.md) showed the existing
3-model council (author + reviewer + advisor) is good for ruff-fix
proposals but isn't the right shape for end-user request orchestration.
This council adds:

- A **safety gate** at both ends (CONTENT safety, orthogonal to PolisAI's
  ACTOR safety)
- **Intent routing** so code requests don't go through a general-purpose
  reasoning model
- A **specialist tier** that picks the right model for the job (codegemma:7b
  for code; gemma2:9b for RAG/reasoning; gemma3:4b for general)
- A **critic stage** that augments — not gates — the answer
- A documented **default chain** (5 stages) and **high-risk chain** (6 stages)

## Architecture

```
User Request
   ↓
[1] Safety Pre-Check       — shieldgemma:2b
   ↓                         (CONTENT safety; orthogonal to PolisAI ACTOR)
[2] Intent Router          — gemma3:1b
   ↓                         (output: code / rag / general)
[3] Planner                — gemma3:4b
   ↓                         (3-5 step plan)
[4] Specialist execution
    ├─ Code task           — codegemma:7b
    ├─ RAG / reasoning     — gemma2:9b
    └─ General             — gemma3:4b
   ↓
[5] Critic / Evaluator     — gemma2:9b
   ↓                         (augments draft with critique notes)
[6] Optional Final Safety  — shieldgemma:9b   ← high_risk=True only
   ↓                         (healthcare/legal/finance/external)
Response
```

## Role → model table

| # | Role | Model | Why |
|---|------|-------|-----|
| 1 | Safety Pre-Check | `shieldgemma:2b` | 1.7 GB fast input scan |
| 2 | Intent Router | `gemma3:1b` | 815 MB cheapest classifier |
| 3 | Planner | `gemma3:4b` | 3.3 GB good general planning |
| 4a | Specialist — Code | `codegemma:7b` | 5.0 GB best local coder |
| 4b | Specialist — RAG | `gemma2:9b` | 5.4 GB strongest local reasoning |
| 4c | Specialist — General | `gemma3:4b` | 3.3 GB shared with planner |
| 5 | Critic / Evaluator | `gemma2:9b` | 5.4 GB same as RAG specialist |
| 6 | Final Safety | `shieldgemma:9b` | 5.8 GB heavy safety reviewer |

All 8 mappings are env-overridable: `GEMMA_ROUTER_MODEL=gemma2:2b` etc.

## Stage-1 contract (per §56)

- **Opt-in via env flag:** `GEMMA_AGENT_COUNCIL_ENABLED=1`
- **Lazy httpx:** module import is fast; httpx loaded inside `_call_ollama`
- **Default-deny:** `is_available()` returns False unless flag AND Ollama reachable
- **Existing scripts unchanged:** `local_council.py` + `agent_router.py` preserved
- **Status surface:** `status()` returns `{stage: 1, available, role_models, default_chain, high_risk_chain, wiring_status, next_stage}`
- **Drill enforces** all of the above (drill_gemma_agent_council_stage1.py — 8 steps, 6 negative)

## Operator opt-in

```bash
# Required
export GEMMA_AGENT_COUNCIL_ENABLED=1

# Optional — point at user-mode Ollama (where Google models live)
export OLLAMA_HOST=http://localhost:11435

# Optional — override which domains trigger safety_post stage
export GEMMA_HIGH_RISK_DOMAINS=healthcare,legal,finance,external

# Optional — A/B test alternative role models
export GEMMA_PLANNER_MODEL=gemma2:9b   # use stronger model for planning
```

## Usage

```python
from gemma_agent_council import run_council, is_high_risk_domain

# Default 5-stage chain
result = run_council("Write a Python Fibonacci function")

# 6-stage chain for high-risk domains
result = run_council(
    "What dosage of ibuprofen is safe for a 65-year-old?",
    high_risk=is_high_risk_domain("healthcare"),
)

print(result.final_output)
for step in result.steps:
    print(f"  {step.role}: {step.model} ({step.latency_ms}ms)")
```

## Composition with existing system

- **CONTENT safety (this council)** ⊥ **ACTOR safety (PolisAI / `policy_check.py`)** —
  both must pass; they're orthogonal axes. PolisAI gates "is this requester
  allowed to use this tool?"; this council gates "is this prompt safe to
  process?".
- **Specialist routing** is a **superset** of `agent_router.py` — that
  router is a 3-class heuristic; this council's `route_intent` is a
  prompt-engineered Gemma classifier and adds the planner+critic stages.
- **Reasoning model (`gemma2:9b`)** composes downstream with the
  retrieval-svc hybrid retrieval + `min_score` floor (just shipped).
  When intent=rag, the specialist receives the user prompt + plan and
  the caller is responsible for injecting retrieved context (hybrid
  search, BGE rerank when wired).
- **§38 audit trail:** every `AgentStep` has `(role, model, prompt_chars,
  output, latency_ms)`. Caller persists the `CouncilResult.steps` list
  to its decision-audit row → reproducible, regulator-readable.

## Stage-2 next steps

| Step | What | Drill required |
|------|------|----------------|
| 2.1 | Wire as fallback in `agent_router.py` when council enabled | new drill — locks fallback semantics |
| 2.2 | Persist `CouncilResult.steps` to `.loop/agent_council_audit.jsonl` | new drill — audit-row schema |
| 2.3 | Frontend `/admin/gemma-council` page (live trace + per-stage latency) | new drill — page composition footer |
| 2.4 | A/B eval: gemma council vs existing 3-model council on RAG-test queries | RAGAS-driven eval |
| 2.5 | Default-flip when 2.4 shows parity or improvement | Stage-3 promotion |

## The brutal rule

> Don't run all 6 stages on every request. The default chain is 5
> stages — safety_post (shieldgemma:9b) is reserved for high-risk
> domains. Adding more agents doesn't make answers better; it makes
> latency worse and debugging harder. This council is the BASELINE for
> local-only RAG/agent work — extend it surgically, drill every change.

## Composes with

- `scripts/gemma_agent_council.py` — the implementation
- `mcp/tests/drill_gemma_agent_council_stage1.py` — Stage-1 contract drill
- `scripts/local_council.py` — existing 3-model council (different shape; complementary)
- `scripts/agent_router.py` — Stage-2 Ollama-backed classifier (this council's intent stage is a superset)
- `scripts/policy_check.py` — PolisAI ACTOR/SCOPE gate (orthogonal to CONTENT safety)
- `services/retrieval-svc/app/services/hybrid_retriever.py` — RAG specialist's data source
- `services/retrieval-svc/app/services/bge_reranker.py` — Stage-1 reranker; composes with this council's RAG path
- `docs/architecture/compression-tools-audit-2026-05-04.md` — table row #15 + #16
- `docs/architecture/rag-deep-test-2026-05-04.md` — empirical test results that motivate the per-role model choice
- §38 — decision audit (every step recorded)
- §39 — RAG architecture standards (multi-stage decision pipeline)
- §43 — drill discipline
- §47 — architecture & design patterns
- §48 — explainability (model + prompt persisted per step)
- §52 — brutal tool review (40-row when wired into request hot path)
- §56 — techstack additions formal 6-gate process (this IS Stage-1)
