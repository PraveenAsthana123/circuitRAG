# Model Card — `llama3.1:8b`

## Intended use

Primary LLM for RAG answer generation in `inference-svc`. Operates
on retrieved + reranked chunks plus a system prompt to produce
grounded answers with inline citations. Used in:

- `services/inference-svc/app/services/rag_inference.py` — main RAG path
- `services/inference-svc/app/services/agent.py` — agentic tool calls
- Decision tier: **advisory** (output always passes through guardrails
  + citation-coverage checker; no auto-action without human review for
  regulated decisions per §48 audit row)

## Out-of-scope use

- Direct decision-making on regulated outcomes (credit, hire, insurance)
  without a human-in-the-loop checkpoint
- Generation without retrieval grounding (always RAG-only here)
- Multilingual generation outside English / select Indo-European
  languages — accuracy degrades sharply for low-resource languages
- Code execution or tool calls without scope-checked authorization

## Training data

- **Source**: Meta's official Llama 3.1 release (8B parameter variant)
- **Time period**: Llama 3.1 corpus cutoff is December 2023
- **Volume**: ~15 trillion tokens (Meta-disclosed)
- **Pre-processing**: Meta's tokenizer (128k vocab BPE)
- **License**: Llama 3.1 Community License — commercial use allowed
  with restrictions; serving via local Ollama runtime

## Performance

- **Held-out accuracy** on internal RAG eval (faithfulness +
  answer_relevance from `services/evaluation-svc`):
  - faithfulness: target ≥ 0.85 (current baseline tracked in
    `[tool.coverage.report]` ratchet comments)
  - answer_relevance: target ≥ 0.80
- **Confidence interval**: ±0.03 at n=200 datapoints
- **Per-segment**: long-document queries (>4 chunks) underperform
  short-context by ~8% on faithfulness
- **Last eval baseline**: see `data/baselines/` (regenerated weekly)

## Fairness

- **Disparate impact**: not measured for general-purpose LLM
  (regulator scope is at the decision-system level — see
  `governance-svc` PolicyEngine + HITL queue).
- **Equal-opportunity gap**: N/A at the model level; measured on
  decisions that USE the model (per §48 audit row + counterfactual).
- **Fairness flag in audit row**: passed through from upstream
  decision logic; the LLM itself doesn't determine the flag.

## Explainability

- **Global**: not directly applicable to a generative LLM. Behavior
  is documented per use case in
  [`docs/architecture/llmops-entity-lifecycle-matrix.md`](../architecture/llmops-entity-lifecycle-matrix.md).
- **Local**: per-prediction explanation via
  [`/api/v1/explain?prediction_id=<id>`](../DEMO-EXPLAIN-ENDPOINT.md)
  — returns the audit row including retrieved chunks (citations),
  prompt version, and guardrails fired.
- **Counterfactual**: not generated automatically for LLM outputs
  (counterfactuals are for classifier decisions, not generative ones)
- **Citation traceability**: YES. Every answer span is mapped to a
  source chunk_id; uncited spans are flagged as hallucinations by
  the guardrails layer.

## Limitations

- **Hallucination floor**: ~3-5% even with strict grounding (typical
  for 8B-class models on novel queries)
- **Latency floor**: ~250ms p50 on 8GB VRAM with Ollama; ~600ms p95
- **Token ceiling**: 128k context, but practical recall degrades
  beyond ~32k tokens
- **Languages**: best on English; degrades below 70% accuracy for
  Hindi, Mandarin, Arabic on RAG faithfulness
- **Cost**: shadow-priced at $0.0001/1k input + $0.0003/1k completion
  in `services/finops-svc/cmd/main.go`

## Owner / contact

- **Primary owner**: Inference Team (configured in CODEOWNERS)
- **Slack channel**: `#inference-svc` (project-local convention)
- **On-call**: see [`docs/runbooks/`](../runbooks/) — current
  runbooks list autonomous-loop sessions; AI/LLM on-call wires here
- **Escalation path**: `documind-ai-eng@<your-org>` (placeholder until
  organizational identity-svc deploys)

## Last review date

2026-04-30 — initial card. Quarterly review per §48.10 → next 2026-07-30.

## Version history

| Version | Date | Change | ADR |
|---|---|---|---|
| 8b-instruct | 2026-04-30 | Initial card on existing deploy | iter 20/N |
