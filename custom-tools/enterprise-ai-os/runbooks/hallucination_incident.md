# Runbook: Hallucination / Unsupported Answer

## Symptoms
- grounding score failed
- citation validation failed
- user reports wrong answer
- answer contains unsupported claim

## Immediate Action
1. Capture trace_id.
2. Retrieve prompt, context, answer, sources.
3. Check retrieved chunks.
4. Run evaluation again.
5. Disable affected prompt version if needed.
6. Route similar queries to human review.

## Recovery
- Improve retrieval filters.
- Improve chunking.
- Add citation gate.
- Update prompt.
- Re-run golden dataset.

## Escalation
- Sev1 for regulated/high-risk domain.
- Sev2 for internal knowledge error.

## Logs to Check
- `retrieval_completed`
- `evaluation_completed`
- `citation_failed`
- `quality_gate_failed`
