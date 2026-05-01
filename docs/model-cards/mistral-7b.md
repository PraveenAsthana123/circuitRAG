# Model Card — `mistral:7b`

## Intended use

Fallback LLM for `inference-svc` when llama3.1:8b is unavailable
(circuit-breaker-tripped or rate-limited). Same RAG pipeline shape
as the primary; uses a slightly different prompt template tuned
for Mistral's chat format.

- Fallback path in `services/inference-svc/app/services/ollama_client.py`
- Decision tier: **advisory** (same as llama3.1:8b — passes through
  guardrails + citation-coverage)

## Out-of-scope use

- Same restrictions as llama3.1:8b (no direct regulated-decision use)
- Long-context queries (>16k tokens) — Mistral 7B's effective context
  is shorter than Llama 3.1's claimed 128k
- Should NOT be used as the cost-optimization tier — it's slightly
  cheaper than llama but not by enough to matter; phi-3:mini is the
  cost tier

## Training data

- **Source**: Mistral AI's official 7B model (instruct variant)
- **Time period**: training cutoff approximately April 2023
- **Volume**: not publicly disclosed (Mistral hasn't published
  corpus size like Meta)
- **Pre-processing**: Mistral's BPE tokenizer (32k vocab)
- **License**: Apache 2.0 — fully permissive

## Performance

- **Held-out accuracy** on internal RAG eval:
  - faithfulness: ~0.82 (slightly below llama3.1:8b's ~0.85)
  - answer_relevance: ~0.78 (slightly below llama)
- **Confidence interval**: ±0.04 at n=200 datapoints
- **Per-segment**: comparable to llama on short queries; degrades
  faster on long context
- **Last eval baseline**: weekly regen in `data/baselines/`

## Fairness

- Not measured at model level (same rationale as llama3.1:8b)
- Audit row carries the fairness_flag from upstream decision logic

## Explainability

- **Local**: per-prediction via `/api/v1/explain?prediction_id=<id>`
- **Citation traceability**: YES — same RAG pipeline, same
  citation-coverage guardrails
- **Counterfactual**: not generated for generative LLMs

## Limitations

- **Hallucination floor**: ~5-7% (slightly higher than llama3.1:8b)
- **Latency floor**: ~200ms p50 on 8GB VRAM; faster than llama in
  some setups due to smaller weights
- **Token ceiling**: 32k effective context (claimed 8k base extended
  via sliding-window)
- **Languages**: English-strong; weaker than llama on non-English
- **Cost**: shadow-priced at $0.0001/1k input + $0.0002/1k completion

## Owner / contact

- **Primary owner**: Inference Team
- **Slack channel**: `#inference-svc`
- **Fallback escalation**: same as llama3.1:8b card

## Last review date

2026-04-30 — initial card. Next review 2026-07-30.

## Version history

| Version | Date | Change | ADR |
|---|---|---|---|
| 7b-instruct | 2026-04-30 | Initial card on existing deploy | iter 20/N |
