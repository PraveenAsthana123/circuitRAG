# GenAI / RAG Production Checklist (100+ Items)

This checklist is for taking a GenAI, RAG, fine-tuning, or agentic system from demo quality to production quality.

## 1. Data Strategy

- Dataset registry exists
- Dataset versions are immutable
- Raw vs cleaned dataset lineage is tracked
- Source provenance is stored
- Dataset ownership is assigned
- Retention policy is defined
- Deletion policy is defined
- Data refresh cadence is defined
- Data quality scoring exists
- Duplicate detection exists
- PII detection exists
- PII masking exists
- Sensitive-data policy tagging exists
- Access-level metadata exists
- Tenant metadata exists
- Synthetic data policy is defined
- Synthetic data is labeled as synthetic
- OpenLineage-style data lineage is available

## 2. Retrieval Corpus

- Chunk versioning exists
- Embedding model version is stored
- Index version is stored
- Re-index strategy exists
- Chunk metadata schema is defined
- Tenant filter is mandatory
- Access-control filter is mandatory
- Corpus refresh strategy exists
- Rebuild rollback strategy exists
- Retrieval corpus ownership is defined

## 3. Evaluation Datasets

- Golden dataset exists
- Validation dataset exists
- Adversarial dataset exists
- Edge-case dataset exists
- Dataset version is tracked
- Human-validated answers exist
- Retrieval ground truth exists
- Safety cases exist
- Regression dataset is updated after incidents
- Benchmark coverage is reviewed regularly

## 4. Prompt / Model / Experiment Control

- Prompt registry exists
- Prompt versioning exists
- Prompt ownership exists
- Prompt rollback exists
- Model registry exists
- Model versioning exists
- Model metadata exists
- Experiment tracking exists
- Candidate vs active model distinction exists
- Commit / prompt / model linkage is recorded

## 5. Runtime Retrieval Quality

- Hybrid retrieval strategy is defined
- Metadata filtering is enforced
- Reranking exists where needed
- Token budget policy exists
- Context packing strategy exists
- Deduplication exists
- Query rewrite policy exists
- Low-confidence retrieval handling exists
- No-answer behavior exists
- Retrieval quality metrics exist

## 6. Feedback Loop

- Explicit user feedback exists
- Implicit feedback signals are captured
- Feedback taxonomy exists
- Human review queue exists
- Reviewer workflow exists
- Feedback-to-dataset path exists
- Feedback-to-prompt path exists
- Feedback-to-retrieval path exists
- Feedback-to-finetuning path exists
- Closed-loop improvement cadence exists

## 7. Testing

- Unit tests exist
- Integration tests exist
- End-to-end tests exist
- Regression tests exist
- Safety tests exist
- Prompt injection tests exist
- Load tests exist
- Chaos tests exist
- Multi-tenant isolation tests exist
- Golden dataset gate exists

## 8. Runtime Control

- Timeouts exist on every external call
- Retries are bounded
- Circuit breakers exist
- Fallback paths exist
- Degraded responses are explicit
- Cache key normalization exists
- TTL policy exists
- Semantic cache policy is defined
- Streaming policy is defined
- Cancelation behavior is defined

## 9. Agent Control

- Max iteration count exists
- Wall-clock timeout exists
- Cost budget exists
- Tool allowlist exists
- Tool scope enforcement exists
- Human escalation path exists
- Kill switch exists
- Retry policy is bounded
- Draft fallback exists for failed actions
- Agent audit trail exists

## 10. Security

- RBAC or ABAC is enforced
- Tenant isolation is enforced
- Prompt injection defense exists
- Data poisoning mitigation exists
- Prompt leakage mitigation exists
- Tool abuse prevention exists
- Secrets management exists
- Output redaction exists
- Audit trail exists
- Compliance evidence path exists

## 11. Performance And Cost

- Latency budget exists
- Cost per answer is measured
- Token usage is measured
- Cache hit rate is measured
- Retrieval latency is measured
- Model latency is measured
- Reranking cost is measured
- Model routing policy exists
- Small vs large model policy exists
- Batching strategy exists

## 12. Deployment

- Dev environment exists
- Staging environment exists
- Canary strategy exists
- Rollback strategy exists
- Deployment version is visible
- Build ID is visible
- Prompt rollout strategy exists
- Model rollout strategy exists
- Index rollout strategy exists
- Post-deploy verification exists

## 13. Observability

- Logs are structured
- Correlation IDs propagate end-to-end
- Traces exist on major boundaries
- Metrics exist for retrieval, generation, and errors
- Error dashboards exist
- Latency dashboards exist
- Cost dashboards exist
- Feedback dashboards exist
- Evaluation dashboards exist
- Alerts exist for key SLOs

## 14. Business Metrics

- Cost per answer exists
- Conversion metric exists
- Retention metric exists
- User satisfaction metric exists
- Answer acceptance metric exists
- Human-escalation rate exists
- Retrieval failure rate exists
- Support deflection metric exists
- Revenue or LTV alignment exists
- Business-owner review cadence exists

## 15. Final Readiness Gate

- Data is versioned
- Evaluation is measurable
- Feedback loop is active
- Runtime controls are present
- Agent behavior is bounded
- Security controls are enforced
- Cost is understood
- Deployment is reversible
- Drift can be detected
- Ownership is clear

## Final Insight

If these controls do not exist, you do not have a platform.
You have a feature demo with operational risk.
