# Security Review — OWASP + STRIDE + SOC2 + AI Threats

> Per CLAUDE.md §47.6 (4-lens security) + §57.1 (production-grade
> only) + §38 (governance gates 4 — security review).
>
> Security is not a Phase-2 polish. From day 1, every component
> ships with: input validators, default-deny policy, structured
> exception envelope, secret scanning, and a STRIDE row.

## The 4 lenses

Every container / service / agent on the platform is reviewed
through ALL FOUR lenses. Missing any lens = release blocked.

### Lens 1 — OWASP Top 10 (2025) + AI threats

| ID | Threat | Where it bites us | Mitigation in this repo |
|---|---|---|---|
| A01 | Broken access control | MCP scope check skipped | `enforce_scope()` in `mcp/server_common.py`; drill `drill_mcp_server_scope.py` |
| A02 | Cryptographic failure | Secrets in logs / commits | `detect-secrets` pre-commit; structured logger masks `*token*` `*password*` |
| A03 | Injection (SQL/cmd/path) | `documents.db_query_select` user input | SQL allowlist rejects 10 write keywords; path-traversal `.resolve()` guard |
| A04 | Insecure design | Single-replica, no rollback | §47.7 4-layer rollback; ADR-required for any write surface |
| A05 | Misconfig (CORS, default creds) | `allow_origins=["*"]` | `settings.cors_origins` from `BaseSettings`; never `*` |
| A06 | Vulnerable components | Outdated `requirements.txt` | `pip-audit` in CI; Dependabot; Snyk MCP (iter-44 drill) |
| A07 | Auth failures (JWT) | Stale tokens accepted | JWT verifier with kid rotation + audience claim drill |
| A08 | Software/data integrity | Unsigned model drops | Model registry (§40.2) with SHA256 + ADR-005 rollback path |
| A09 | Logging / monitoring failure | Silent crash, no trace | OTel span every RPC; `request_id` propagated; §47 baggage rule |
| A10 | SSRF | Outbound URL not validated | URL allow-list per MCP server (`GITHUB_ALLOWED_REPOS` etc.) |
| A11 (AI) | Prompt injection | User-supplied prompt overrides system | Council reviewer agent + Pydantic schema enforcement (§55 Tier-1) |
| A12 (AI) | Insecure output handling | LLM JSON consumed without parse validation | Pydantic models on every council/agent output |
| A13 (AI) | Training data poisoning | Tainted ingestion → tainted embeddings | `documents.csv_parse` row cap; ingest provenance audit row |
| A14 (AI) | Model theft | API responses leak weights | No `/api/serve_model` endpoint; Ollama runs local-only |
| A15 (AI) | Excessive agency | Agent calls write-tool without approval | Per-tool `required_scopes`; default-deny OPA bundle; agent task board apply gate |

### Lens 2 — STRIDE per container

For every L2 box in C4 (each container), maintain a STRIDE table:

| Container | S poofing | T amper | R epudiation | I nfo disclosure | D oS | E levation |
|---|---|---|---|---|---|---|
| inference-svc | JWT verify | request signature | audit row per call | tenant filter on logs | rate limit | scope enforcement |
| agent-orchestrator-svc | mTLS to MCP | idempotency-key | `request_id` propagation | RLS in postgres_store | circuit breaker | role-based dispatch |
| Each MCP server | bot-token verify | input validator | structured log row | scope per tool | per-tool circuit breaker | required_scopes default-deny |
| Postgres | SCRAM-SHA-256 | row checksum (audit) | append-only audit table | RLS per `tenant_id` | connection pool | per-role grants |
| Kafka | mTLS broker | producer signature | offset commit log | topic ACL per role | rate limit per topic | producer ACL |
| Frontend | session cookie HttpOnly | CSP header | console error capture | XSS sanitization | rate limit on BFF | role-gated routes |

### Lens 3 — DevSecOps shift-left (CI gates)

Every PR runs:

1. **Secret scan** — `detect-secrets` pre-commit + CI fail
2. **SAST** — `bandit -r backend/ -ll` (severity: low+)
3. **Dependency audit** — `pip-audit -r requirements.txt`
4. **SBOM generation** — Syft on container image
5. **Container scan** — Trivy + Grype on built image
6. **Image signing** — Cosign attached
7. **Drill suite** — `scripts/run_drills.py --parallel 4` (≥3 negative per drill)
8. **Deploy gate** — scorecard ≥ threshold per `/admin/production-readiness`

Skipping any gate without explicit operator approval = release blocked.

### Lens 4 — Cloud + SOC2 IAM

| Control | What it requires | Where in repo |
|---|---|---|
| CC6.1 access | Principle of least privilege, role-based | `config/policies/agent_dispatch.rego` (default-deny) |
| CC6.2 secrets | Vault / KMS / env-only | `BaseSettings` from env; `.env.template` documents shape; never inline |
| CC6.6 segmentation | Network policy / namespace isolation | k8s `NetworkPolicy`; tenant_id RLS |
| CC7.2 anomaly | Drift / fairness / cost monitoring | `mcp_<ns>_circuit_open` gauge; §41 cost dashboard |
| CC7.3 IR | Incident playbook | `ops/runbook/<ns>.md` per tool |
| CC8.1 change | ADR for every locked decision | `docs/architecture/adr/` |
| CC9.2 vendor | Tool review per addition | `docs/architecture/tool-reviews/<tool>.md` (§52) |

## Pre-deploy security checklist

Before any merge to main / push to staging:

- [ ] No new endpoint without input validator (regex / Pydantic / allowlist)
- [ ] No new write surface without ADR (§47.3) + scope (`required_scopes`)
- [ ] No new external call without timeout + circuit breaker + retry policy
- [ ] No new secret reference without `BaseSettings` + `.env.template` entry
- [ ] No new container without STRIDE row in this README
- [ ] No new tool without OPA Rego rule (default-deny) — see `policy.opa_bundle` in catalog
- [ ] Secret scan + SAST + dep audit + drill suite all green in CI
- [ ] Scorecard `G1_governance_38` ≥ 80 + `G2_architecture_47` ≥ 80

## The brutal rule

> Security is not a feature; it is a continuous gate. Every commit
> passes through the 4 lenses, or the commit is technical debt
> with a half-life of days. The §38 audit trail must show:
> identifiable, reproducible, explainable, versioned, auditable.
> If a regulator asks "what did this change touch?" within 5 minutes
> of asking, the answer must be on the screen.
