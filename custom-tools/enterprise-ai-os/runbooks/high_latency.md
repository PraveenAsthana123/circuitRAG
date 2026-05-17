# Runbook: High Latency

## Symptoms
- p95 > 2s
- p99 > 5s
- timeout increase
- queue depth growing

## Immediate Action
1. Check Kiali service graph.
2. Identify slow service/span in OpenTelemetry.
3. Check LLM latency, vector DB latency, DB latency.
4. Enable cache or smaller model.
5. Reduce retrieval top_k.
6. Scale API/worker pods.

## Recovery
- Confirm p95 and p99 return to SLO.
- Review recent release/canary.
- Rollback if latency started after deployment.

## Escalation
- Sev1 if user-facing API unavailable.
- Sev2 if degraded but available.

## Logs to Check
- `operation_latency_ms`
- `tool_timeout`
- `llm_latency`
- `retriever_latency`
