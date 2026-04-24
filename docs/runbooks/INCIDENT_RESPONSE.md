# Incident response runbook (Design Area 67)

## Severity levels

| Sev | Definition | Response time | Notify |
| --- | --- | --- | --- |
| SEV1 | Production down / data loss / security breach | 15 min | on-call + eng lead + CTO |
| SEV2 | Feature broken for a tenant / quality SLO miss > 10% | 1 hour | on-call |
| SEV3 | Single-service degradation, auto-recovering | 4 hours | on-call |
| SEV4 | Cosmetic / non-blocking | next business day | — |

## Common playbooks

### 1. Ollama is down / slow (SEV2)

Symptom: `inference-svc` logs `CircuitOpenError name=ollama-llm`.

1. Check `docker compose ps` → is Ollama container up?
2. `curl http://localhost:11434/api/tags` → model loaded?
3. Check GPU/RAM: `docker logs documind-ollama --tail=100`
4. If OOM → restart: `docker compose restart ollama`
5. Circuit auto-closes in 60s after Ollama recovers; no manual reset needed.

### 2. Qdrant returns empty results after upload (SEV2)

Symptom: Ask endpoint returns "I don't have enough information" but docs ARE uploaded.

1. Check ingestion saga state: `SELECT id, state, failing_step FROM ingestion.sagas ORDER BY updated_at DESC LIMIT 10;`
2. If `state='failed'` → inspect `error` column.
3. If `state='running'` + stuck > 10 min → the service crashed mid-saga. Options:
   - Manually transition doc → `failed`, re-upload.
   - Run recovery script (TODO: `scripts/saga_recovery.py`).
4. If all green → verify Qdrant has points: `curl http://localhost:6333/collections/chunks` → `points_count`.

### 3. Cross-tenant leakage suspected (SEV1)

If a user reports seeing another tenant's data:

1. Pull logs by tenant: `grep 'tenant_id=<victim>' logs/*.log`
2. Pull logs by correlation ID for the offending request.
3. Inspect RLS context: did the service correctly call `set_config('app.current_tenant', ...)`?
4. Pattern: every `tenant_connection()` wraps its SQL in a transaction with the SET — if an admin-mode handler accidentally used `admin_connection()`, RLS is bypassed.
5. **Do not roll back — preserve evidence for forensics.** Coordinate with security immediately.

### 4. Rate limit too aggressive (SEV3)

Symptom: tenant reports 429s under normal use.

1. Identify offending endpoint from logs.
2. Adjust tenant budget in `finops.budgets` OR raise `DOCUMIND_RATE_LIMIT_*` env var.
3. Restart affected service.

## Post-mortems

Every SEV1 / SEV2 gets a blameless post-mortem within 48 hours:

1. Timeline (UTC timestamps).
2. Impact (customers affected, duration, SLO burn).
3. Root cause (the specific change / condition that triggered).
4. Contributing factors (what made it worse or harder to detect).
5. Action items (with owners + due dates).
6. What went well.

Template: `docs/runbooks/post-mortem-template.md` (add as needed).
