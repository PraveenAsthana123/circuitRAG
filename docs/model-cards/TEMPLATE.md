# Model Card — `<model-name>`

> §48.3 template. Copy to `<model-name>.md`, fill in every section.
> Drill `mcp/tests/drill_model_cards.py` enforces section presence.

## Intended use

What the model is used for in this system. Be specific:
- Service name
- Pipeline stage
- Decision tier (auto-decision / human-review / advisory)

## Out-of-scope use

What the model MUST NOT be used for. Per CLAUDE.md §38.6:
- Decisions affecting protected classes without human review
- Anything outside its training distribution
- Cases where confidence < 0.5 (route to fallback)

## Training data

- **Source**: who trained it / where the weights come from
- **Time period**: when the training data was gathered
- **Volume**: corpus size
- **Pre-processing**: tokenization, filtering, etc.
- **License**: weights and data licenses

## Performance

- **Held-out accuracy / metric value**
- **Confidence interval**
- **Per-segment performance** (any group with measurable disparity)
- **Eval baseline date and dataset**

## Fairness

- **Disparate impact ratio**: target ≥ 0.8 across protected groups
- **Equal-opportunity gap**: target < 5%
- **Calibration parity** across groups
- **Last fairness audit date**
- **Fairness flag in decision audit row**: `pass` | `warn` | `fail`

## Explainability

- **Global**: SHAP feature importance, where attached
- **Local**: per-prediction explanation via
  [`/api/v1/explain?prediction_id=<id>`](../DEMO-EXPLAIN-ENDPOINT.md)
- **Counterfactual support**: yes/no, method
- **Citation traceability** (RAG models): yes/no

## Limitations

- Known failure modes
- Hallucination rate (for LLMs / RAG models)
- Latency floor
- Token / cost ceiling
- Languages supported
- Domain limitations

## Owner / contact

- **Primary owner**: name + handle
- **Backup owner**: name + handle
- **Slack / email**: contact channel
- **On-call rotation**: link or schedule reference

## Last review date

`YYYY-MM-DD` — quarterly review per CLAUDE.md §48.10.

## Version history

| Version | Date | Change | ADR |
|---|---|---|---|
| v1.0 | YYYY-MM-DD | Initial deploy | ADR-XXX |
