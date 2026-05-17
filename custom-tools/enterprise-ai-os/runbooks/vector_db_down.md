# Runbook: Vector DB Down

## Symptoms
- Qdrant unavailable
- retrieval timeout
- low grounding score
- RAG context empty

## Immediate Action
1. Check Qdrant health.
2. Open circuit for vector retriever.
3. Fallback to keyword retriever.
4. Reduce top_k if latency is high.
5. Trigger incident if retrieval remains degraded.

## Recovery
- Restore Qdrant pod/service.
- Validate collection availability.
- Run sample semantic search.
- Close circuit after successful test.

## Escalation
- Sev1 if retrieval is required for regulated output.
- Sev2 if keyword fallback works.

## Logs to Check
- `retrieval_started`
- `retrieval_failed`
- `fallback_to_keyword`
- `grounding_failed`
