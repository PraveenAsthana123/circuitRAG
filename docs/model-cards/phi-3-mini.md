# Model Card — `phi-3:mini`

## Intended use

Low-latency / low-cost LLM tier in `inference-svc`. Used when:
- Query has tight latency budget (<200ms p95)
- Token budget is constrained (per-tenant cost ceiling)
- A small model is "good enough" — short factual queries with
  high-quality retrieval

Decision tier: **advisory** with stricter guardrails (smaller model
→ higher hallucination rate → tighter citation-coverage threshold).

## Out-of-scope use

- Long-form generation (>500 tokens output) — quality degrades
- Multi-step reasoning chains
- Any decision where a 5-7% additional hallucination risk is not
  acceptable
- Default routing — operators must explicitly route here, not get
  it as a silent default

## Training data

- **Source**: Microsoft's Phi-3 mini variant (3.8B parameters)
- **Time period**: October 2023 cutoff
- **Volume**: ~3.3 trillion tokens (Microsoft-disclosed) — heavy
  emphasis on textbook-style + filtered web data
- **Pre-processing**: Microsoft's tokenizer (32k vocab)
- **License**: MIT — fully permissive

## Performance

- **Held-out accuracy** on internal RAG eval:
  - faithfulness: ~0.74 (notably below llama3.1:8b — small model)
  - answer_relevance: ~0.71
- **Confidence interval**: ±0.05 at n=200 datapoints
- **Per-segment**: best on factual / short queries; weakest on
  reasoning-heavy queries
- **Last eval baseline**: weekly regen in `data/baselines/`

## Fairness

- Not measured at model level (rationale per llama3.1:8b card)
- Smaller model has less coverage of less-represented training
  data → flagged as **higher fairness risk** in advisory tier
- Operators routing here MUST monitor disparate-impact dashboards
  more closely

## Explainability

- **Local**: per-prediction via `/api/v1/explain?prediction_id=<id>`
- **Citation traceability**: YES — but watch for higher false-citation
  rate (the model invents plausible-looking citations more often
  than the larger models)
- **Counterfactual**: N/A for generative

## Limitations

- **Hallucination floor**: ~7-10% (highest of the three LLMs)
- **Latency floor**: ~80ms p50 on 8GB VRAM (fastest)
- **Token ceiling**: 4k effective context — DO NOT use for
  long-document RAG
- **Languages**: English-only practically usable
- **Cost**: shadow-priced at $0.00005/1k input + $0.0002/1k completion
  (cheapest in `shadowRates`)

## Owner / contact

- **Primary owner**: Inference Team
- **Slack channel**: `#inference-svc`

## Last review date

2026-04-30 — initial card. Next review 2026-07-30.

Phi-3:mini's higher hallucination rate means quarterly reviews are
the **floor**, not the cap. Trigger an immediate re-review if any
of these fire:
- faithfulness eval drops > 5% week-over-week
- guardrails_triggered rate jumps > 3% on this model's traffic
- a regulated-decision incident traces back to phi-3:mini output

## Version history

| Version | Date | Change | ADR |
|---|---|---|---|
| mini | 2026-04-30 | Initial card on existing deploy | iter 20/N |
