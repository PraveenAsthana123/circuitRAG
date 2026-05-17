# GAPS.md — honest review against repo standards

> Per CLAUDE.md §47 (architecture) + §52 (40-row brutal tool review)
> + §43 (drill discipline) + §57 (production-grade discipline) + §38
> (AI Production Governance). Reviewer was asked for honest assessment.
> **Severity:** P0 = will-break-prod or security-critical · P1 =
> silent-degradation · P2 = operational · P3 = polish.

## Top-line verdict

Tool Set 33 (preserved as the source's own gap-closure note) already
classifies this work as **"Production MVP ⚠️ close · Enterprise-grade
❌ not yet · Top 1% platform ⚠️ needs real integrations, security,
durability, SLOs"**. That self-assessment is accurate. This review
adds the specific P0 rows that need closing before any deployment.

**Previously identified Tool Set 35 P0 security bugs are fixed in code and covered by negative drills.** `JWTAuth` now refuses unset, weak, or default secrets, and `/auth/token` now authenticates credentials and derives tenant/roles server-side. Remaining identity gaps are listed below.

---

## Per-tool-set gaps

### Tool Set 11 — Explainability AI

> **Critical framing**: this Tool Set is **named** "Explainability AI"
> but does NOT meet the explainability requirements in CLAUDE.md §48
> (which is the governing policy for any AI feature in this repo).
> What it actually implements is **reasoning-trace storage + score
> reporting** — a thin layer that *labels* outputs, not one that
> *explains* them. Don't deploy this as compliance evidence.

| Gap | Severity | Fix |
|---|---|---|
| **No SHAP / LIME / Integrated-Gradients attribution** (CLAUDE.md §48.2 Local layer) | **P0** | Add `shap` or `captum` for feature attribution; persist top-K factors per prediction |
| **No counterfactual generation** (CLAUDE.md §48.7 — required for EU AI Act Art. 86 right-to-explanation) | **P0** | `dice-ml` or `alibi` for minimal-actionable-plausible counterfactuals |
| **No citation accuracy verification** (CLAUDE.md §48.5 RAG four-part contract requires answer-span → source mapping) — `SourceAttribution.attribute()` just formats sources, never verifies they actually support the answer | **P0** | Span-level extraction + chunk-id verification; uncited claim → hallucination flag |
| **No model card** (CLAUDE.md §48.3) — confidence_score is passed in with no provenance: what computed it? from which model version? against which eval set? | **P0** | Every prediction's audit row must carry `model_version` + `prompt_version` + link to model card |
| **No fairness metrics** (CLAUDE.md §48.8) — no group-level performance, no disparate-impact check | **P0** | Per-group accuracy + disparate-impact ratio; weekly drift check |
| **No decision-audit-row persistence** (CLAUDE.md §48.4) — the engine just `return`s a dict; nothing is stored, nothing survives restart | **P0** | Append-only Postgres `decision_audits` table with the §48.4 schema |
| `ReasoningTrace.steps` is a single shared in-memory list across ALL trace_ids — multi-tenant leak risk if Tenant A's trace contains identifiers visible during Tenant B's listing | **P0** | Per-tenant store + tenant filter on `get_trace`; better: Postgres-backed with tenant_id column + RLS |
| Confidence thresholds (0.85 high / 0.65 medium / 0.8 release) are magic numbers with no calibration history | **P1** | Calibrate against historical human-judgment data; document per-domain thresholds |
| `ExplainabilityEngine` constructs all 4 dependencies in `__init__` — not injectable, hard to mock | **P2** | DI per CLAUDE.md §3 |

### Tool Set 31 — React UI

| Gap | Severity | Fix |
|---|---|---|
| Every component lacks loading/error/empty states beyond a single `<p>` | **P1** | Add skeletons + ErrorBoundary per CLAUDE.md §14 |
| `.jsx` not `.tsx` | **P2** | Migrate to TS for compile-time type checks |
| No a11y review (no ARIA, no heading hierarchy check) | **P2** | WCAG 2.1 AA per CLAUDE.md §14 |
| No tests | **P1** | Vitest + RTL per CLAUDE.md §14 |

### Tool Set 32 — Project Assembly

| Gap | Severity | Fix |
|---|---|---|
| `startup.sh` exports `JWT_SECRET_KEY` nowhere, leaving it unset → triggers P0 #1 above | **P0** | Add hard refusal in `main.py` startup if unset |
| Folder structure references `core/`, `agent_features/`, `llm/`, ... (≥27 folders) that are NOT in source paste | n/a | Tool Sets 1–30 are missing |
| `pip install -r requirements.txt` will fail on `psycopg2-binary` on some macOS/ARM setups | **P2** | Recommend `psycopg[binary]` (psycopg3) instead |
| `main:app` referenced in `startup.sh` but no `main.py` shown | **P0** | Missing entrypoint |

### Tool Set 33 — Gap Closure (the source's own honest note)

| Gap | Severity | Fix |
|---|---|---|
| **No gaps** — this is itself a gap-acknowledgement document | n/a | Already honest; preserved here as a key reference |

The original Tool Set 33 verdict was accurate. This file extends rather
than replaces it.

### Tool Set 34 — Integrations (real SDK clients)

| Gap | Severity | Fix |
|---|---|---|
| `OpenAIClient.chat()` — no retry, no timeout, no circuit breaker | **P1** | Wrap with retry+timeout+CB per Component 7 pattern in `../openclaw-components/07-resilience/` |
| `PostgresClient` — single connection, no pool, no `with` context, no transaction boundaries | **P0** | Use `psycopg_pool` or `asyncpg` pool; explicit `BEGIN`/`COMMIT` |
| `PostgresClient.query()` `params: tuple = ()` — empty tuple as default arg is fine but the SQL-with-no-params idiom invites string concatenation | **P1** | Document that callers MUST use `%s` placeholders and never f-string |
| `RedisClient` — `decode_responses=True` everywhere; binary values (embeddings, images) will break | **P2** | Two clients: one binary, one text |
| `KafkaClient.consumer()` — `enable_auto_commit=True` + at-most-once-semantics with no DLQ | **P1** | Manual commit after successful handler; dead-letter topic for failures |
| `KafkaClient.producer()` — no `acks="all"`, no `enable_idempotence=True` | **P1** | Producer config for at-least-once + idempotent |
| `OpenTelemetrySDK.configure()` — HTTP exporter without TLS, no auth header, no resource attributes | **P1** | TLS endpoint + `Authorization` header + `Resource.create({"service.name": ..., "deployment.environment": ...})` |
| No `__init__.py` in source listing (added on disk for import correctness) | **P3** | Documented |
| Calls block (sync) but FastAPI app is async — risk of blocking the event loop | **P1** | Use `httpx` / `asyncpg` / `aiokafka` / `redis.asyncio` |

### Tool Set 35 — Identity (in addition to the two P0s above)

| Gap | Severity | Fix |
|---|---|---|
| HS256 symmetric algorithm — every verifier holds the signing key | **P0** | RS256/EdDSA + JWKS endpoint |
| No `iss` / `aud` / `nbf` / `iat` validation in `verify_token()` | **P1** | Pass `audience=` and `issuer=` to `jwt.decode` |
| No token revocation (logout / compromise → 60-min wait until expiry) | **P1** | `jti` blacklist in Redis with TTL = remaining lifetime |
| `expire_minutes=60` is hardcoded; short-lived access + refresh token pattern absent | **P1** | 5-15 min access token + refresh token rotation |
| `UserStore` + `TenantStore` + `RoleAssignment` all in-memory `dict` — lost on restart | **P0** | Postgres tables with UNIQUE on `user_id` + foreign keys |
| `RoleAssignment.assign_role` allows duplicate-tolerant insert but no revocation | **P1** | Add `revoke_role`; track grant timestamp + grantor |
| `require_role` checks JWT claim, not DB — role revocation requires waiting for expiry | **P1** | Server-side role check OR short token TTL + DB-backed denylist |
| No tenant binding check (admin in tenant A could call admin in tenant B if `tenant_id` is bag-of-claims) | **P0** | Verify `claims["tenant_id"]` matches path/body tenant_id |
| No CSRF protection if these tokens are stored in cookies | **P1** | Document: tokens must be in Authorization header, never cookies |

### Tool Set 36 — Audit (hash-chain)

| Gap | Severity | Fix |
|---|---|---|
| `previous_hash` field is stored but `verify()` re-computes from scratch — informational only | **P3** | Either remove the field or document its purpose |
| No periodic merkle-root publication to external transparency log | **P1** | Per quarter, publish root hash to a public ledger (or notarize via TSA RFC 3161) |
| `verify()` returns at first failure — doesn't tell you how many records are affected | **P2** | Continue + collect all failures |
| No retention policy (records grow forever) | **P1** | Per CLAUDE.md §48.4: 7 years for regulated, 1 year hot + cold archival otherwise |
| No tenant filter on `list_records` / `search_by_trace` — cross-tenant audit reads possible | **P0** | Add `tenant_id` filter; enforce caller's tenant context |
| No drill per §43 | **P0** | Tampering with `records[i]["payload"]` is caught; deletion is caught; reordering is caught |
| Source's own §5 production note acknowledges Postgres is required | n/a | Already honest; preserved |

### Tool Set 37 — Release Management

| Gap | Severity | Fix |
|---|---|---|
| `release_engine` does NOT actually deploy anything — it builds JSON objects with `status="canary"` but there is no Kubernetes/Argo/Flagger integration | **P0** | Wire to Argo Rollouts CRD or Flagger HTTPRoute or Helm hook |
| `CanaryManager` weights are arithmetic only — no Istio `VirtualService` / NGINX weight apply | **P0** | Apply via service-mesh API |
| `RollbackManager.complete_rollback` marks `status="completed"` immediately — no verification that the rollback actually succeeded | **P0** | Wait for new pods Ready + health probe pass before marking complete |
| No `target_release_id` validation that it exists / is a valid prior version | **P1** | Look up in registry; reject if unknown or itself failed |
| No release-time approval signature check (`approved_by` is a string, not a verified identity) | **P1** | Require admin role + audit row referencing the approval |
| In-memory only — restart loses release history | **P0** | Postgres `releases` table with full state machine |
| No `freeze` mode for high-risk windows (e.g., during incident) | **P2** | Org-wide freeze flag + check before `release_agent_canary` |

### Tool Set 38 — SLO

| Gap | Severity | Fix |
|---|---|---|
| `SLOPolicyRegistry.evaluate()` takes a scalar value — but SLOs are temporal (p95 over 30d, not a single measurement) | **P0** | Real implementation must query Prometheus / a time-series store with PromQL like `histogram_quantile(0.95, ...)` |
| No connection to Prometheus / metric source — pure evaluator on already-collected values | **P0** | Add `PrometheusClient.query_range` + window-aware computation |
| `ErrorBudget.calculate()` uses a single 1.0% allowance without burn-rate alerts | **P1** | Multi-window multi-burn-rate alerts (e.g., 14d window / 2% burn) |
| `cost_per_request` SLO target `0.02` is hardcoded; should be per-tenant + per-model | **P2** | Config-driven per-tenant budgets |
| `AlertRules.evaluate` returns alerts but no routing (Slack, PagerDuty, email) | **P1** | Integrate with notification service |

### Tool Set 39 — Runbooks

| Gap | Severity | Fix |
|---|---|---|
| Each runbook lists "Logs to Check" but no command / dashboard URL / Kibana query | **P1** | Replace event names with copy-pasteable queries: `kubectl logs ... \| jq '.event_type == "llm_failed"'` |
| No on-call rotation reference | **P1** | Add "On-call escalation" section with PagerDuty rotation name |
| No "communication template" (status page update, Slack incident channel) | **P2** | Each Sev1 runbook should include the user-facing status update text |
| `vector_db_down.md` says "Open circuit for vector retriever" but assumes the CB component exists from another Tool Set that was not shipped | **P1** | Cross-link to actual implementation |
| `governance_failure.md` says "Capture audit evidence" but the audit store is in-memory (Tool Set 36 P0 above) | **P0** | Until §36 is durable, audit evidence will be lost on restart |
| No "what to communicate" matrix (who notifies whom) | **P2** | RACI per incident type |
| No post-incident review template | **P2** | Add postmortem template per CLAUDE.md §38 |
| No drill (an unrehearsed runbook is a wish) | **P0** | Quarterly chaos-day execution of each runbook in staging |

## What "production-grade" would actually require

Per CLAUDE.md §53 (Enterprise AI Maturity Stack L4+) — same 10-point
checklist as `../openclaw-components/GAPS.md`. **This folder scores 0/10**:

1. No per-tool-set ADR (§47.3)
2. No per-tool-set 40-row brutal review (§52)
3. No drills per §43
4. No decision audit row schema beyond the trivial hash-chain (§38.3)
5. No explainability evidence (§48)
6. OTel SDK is wired but no collector / exporter config / propagation
7. No tested rollback path (§47.7)
8. No load test (§47.10)
9. No compose-footer (§49)
10. No folder README generator (§58)

## Recommended next steps

1. **DO NOT** run `identity/auth_route_example.py` on any port. Delete
   it or rewrite per the file header before any FastAPI router
   includes it.
2. **DO NOT** start `main.py` (which is not in source anyway) without
   first refusing to boot when `JWT_SECRET_KEY` is unset.
3. **If teaching:** label every "✅ done" in the source's Final Build
   Checklist as "demonstrates pattern; not production-grade". Per CLAUDE.md
   §57.7 honesty — a checkbox without a drill is a wish.
4. **If deploying:** start over from CLAUDE.md §38 + §47 + §52 with
   real OTel, real DB, real auth (Keycloak or Cognito or Auth0, not
   this), real Argo Rollouts, real Prometheus + Grafana. The work
   in `services/` of this repo is much closer to deployable.

## The brutal rule (reprise)

> A "Tool Set" claiming production-grade auth / audit / release / SLO
> capabilities when the underlying code uses in-memory dicts, defaults
> the JWT secret to "change-me", and ships a `/auth/token` endpoint
> that grants admin to anyone — is **not interview material**, it is a
> security incident waiting to happen. The two P0 bugs in Tool Set 35
> must be removed (not just commented) before this folder is shared
> with anyone who might confuse intent for implementation.
