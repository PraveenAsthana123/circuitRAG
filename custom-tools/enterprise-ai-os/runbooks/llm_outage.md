# Runbook: LLM Provider Outage

## Symptoms
- LLM calls timing out
- 5xx provider errors
- circuit breaker opened
- fallback model activated

## Immediate Action
1. Check provider status.
2. Confirm circuit breaker state.
3. Route traffic to fallback provider.
4. Reduce non-critical workloads.
5. Notify support channel.

## Recovery
- Move from OPEN → HALF_OPEN.
- Send test request.
- If successful, close circuit.
- If failed, keep fallback active.

## Escalation
- Sev1 if all providers fail.
- Sev2 if primary provider fails but fallback works.

## Logs to Check
- `llm_called`
- `llm_failed`
- `circuit_opened`
- `fallback_triggered`
