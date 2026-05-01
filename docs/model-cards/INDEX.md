# Model Cards Index

> §48.3 mandate: every deployed model must have a model card with
> intended use, training data, performance, fairness, explainability,
> limitations, ownership, and version history. Updates without a
> card are release-blocked.

## Currently deployed (production) models

| Model | Card | Type | Where used |
|---|---|---|---|
| `llama3.1:8b` | [`llama3.1-8b.md`](llama3.1-8b.md) | LLM (instruction-tuned) | `inference-svc` answer generation |
| `mistral:7b` | [`mistral-7b.md`](mistral-7b.md) | LLM (instruction-tuned) | `inference-svc` fallback |
| `phi-3:mini` | [`phi-3-mini.md`](phi-3-mini.md) | LLM (small, fast) | `inference-svc` low-latency tier |
| `bge-m3` | [`bge-m3.md`](bge-m3.md) | Embedding (1024-dim) | `ingestion-svc` chunk vectorization |

The deployed list is the source of truth in
[`services/finops-svc/cmd/main.go`](../../services/finops-svc/cmd/main.go)
(`shadowRates` table for LLMs) plus the embedder configured in
`ingestion-svc` (`bge-m3` per `reembed_worker.py`).

## How to author a new model card

1. Copy [`TEMPLATE.md`](TEMPLATE.md) to `<model-name>.md`
2. Fill in all 9 required sections per §48.3
3. Add a row to this index
4. Add the model to the production list above
5. Add the model to `services/finops-svc/cmd/main.go` `shadowRates`
   if it's an LLM (so cost tracking works)
6. Run `mcp/tests/drill_model_cards.py` — must stay green

## Drill

[`mcp/tests/drill_model_cards.py`](../../mcp/tests/drill_model_cards.py)
locks the contract: every model in the production-deployed list
has a card, and every card has the 9 §48.3 sections.

## Why this matters

§48.12 says: "if a regulator demands an explanation of a specific
past decision and you cannot produce one within minutes, your AI
system is not deployable in any regulated jurisdiction." Model
cards are the **second** half of that contract — the
[`/api/v1/explain`](../DEMO-EXPLAIN-ENDPOINT.md) endpoint serves
per-decision answers; model cards serve the per-model context
those answers reference.
