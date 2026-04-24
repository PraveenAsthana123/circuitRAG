# Areas 1–8 · System, Boundaries, and Planes

## Area 1 · System Boundary

| Field | Content |
|---|---|
| **DocuMind status** | ✅ Implemented |
| **Class / file** | `infra/nginx/nginx.conf` (edge), `services/api-gateway/cmd/main.go`, `infra/istio/10-gateway.yaml` |
| **Components** | Ingress (nginx + Istio Gateway) · Edge WAF/TLS · Go API gateway · L7 router · Egress controller |
| **Technical details** | Define ONE external entry (TLS-terminated at nginx). No service is Internet-reachable. Internal traffic is mTLS via Istio. Boundary = what's in the mesh + what isn't. |
| **Implementation** | nginx listener on 443 → upstream `api-gateway:8080` (k8s Service). Istio Gateway handles the in-cluster variant. All other pods only listen on the pod network. |
| **Tools & frameworks** | nginx, Istio, Envoy, AWS ALB / GCP HTTPS LB / Cloudflare as prod replacements |
| **How to implement** | 1. Write ingress config with TLS + HTTP→HTTPS redirect · 2. Single upstream (gateway) · 3. Enforce no NodePort Service on internal services · 4. Egress via controlled proxy · 5. Document the boundary in C4 Context. |
| **Real-world example** | User hits `https://documind.local` → nginx → gateway → inference-svc. User CANNOT reach inference-svc directly because no Service is exposed as NodePort or LoadBalancer. |
| **Pros** | Single chokepoint for WAF, rate limit, auth, TLS. Surface area minimized. Easy to audit. |
| **Cons** | Single chokepoint IS a chokepoint — you must scale it horizontally. One misconfiguration can expose everything. |
| **Limitations** | L7 inspection at the edge is expensive at high QPS. mTLS-only prevents quick debugging with curl. |
| **Recommendations** | Always terminate TLS at the edge, re-establish mTLS inside. Separate the ingress pool from the service pool (failure isolation). Never skip the WAF tier. |
| **Challenges** | Zero-downtime cert rotation · DDoS at L4 (nginx can't help) · IPv6 readiness |
| **Edge cases + solutions** | Giant uploads → `client_max_body_size` + streaming `proxy_request_buffering off` · Websockets → explicit `Upgrade` header pass-through · HTTP/3 clients → Envoy (nginx HTTP/3 is experimental) |
| **Alternatives** | AWS API Gateway (serverless) · Kong · Traefik · HAProxy · Google Cloud Armor |

---

## Area 2 · Responsibility Boundary

| Field | Content |
|---|---|
| **DocuMind status** | ✅ Implemented |
| **Class / file** | per-service Postgres schemas (`identity`, `ingestion`, `eval`, `governance`, `finops`, `observability`) enforced by `DbClient.tenant_connection` |
| **Components** | Bounded contexts · Domain models · Database-per-service · RACI matrix · Service API contracts |
| **Technical details** | Each service owns ONE bounded context (DDD). No cross-schema joins. Changes to another service's table require going through its API. |
| **Implementation** | Postgres schemas are literal: `ingestion.documents`, `governance.policies`. Repos can only access their own schema because RLS + schema-path enforce it. Every service has a `BOUNDARIES.md` (inherit from `spec §Area 2`). |
| **Tools & frameworks** | Postgres schemas · RLS · DDD (bounded-context pattern) · Team Topologies (book) · RACI matrix templates |
| **How to implement** | 1. List bounded contexts before writing code · 2. Assign each context one owner service · 3. Lock down with schema + RLS + Istio AuthorizationPolicy · 4. Document RACI · 5. Review on every new endpoint: does this cross a boundary? |
| **Real-world example** | Ingestion needs a user's display name → it calls `identity-svc.GetUser`, not `SELECT FROM identity.users`. |
| **Pros** | Independent deploys · Clearer code ownership · Smaller blast radius · Parallel team velocity |
| **Cons** | Cross-context reads need API calls (latency + coupling) · Tempting to "just query the other table" violates the boundary |
| **Limitations** | Saga complexity goes up when you can't use DB transactions across boundaries · Sometimes the right model IS shared (currency, locale) |
| **Recommendations** | Use Team Topologies stream-aligned teams as the boundary source. Do a Responsibility Assignment Matrix BEFORE coding. Enforce boundaries in CI with dep graphs. |
| **Challenges** | Eventual consistency between contexts · Shared master data · Organizational churn moves boundaries |
| **Edge cases + solutions** | Two services need the same read → either an API or a read-replica with limited scope · Legacy monolith porting → use the Strangler Fig pattern |
| **Alternatives** | Shared DB (monolith) · Function-level modular monolith · Serverless with IAM-based data isolation |

---

## Area 3 · Trust Boundary

| Field | Content |
|---|---|
| **DocuMind status** | ✅ Implemented |
| **Class / file** | `libs/py/documind_core/middleware.py`, `encryption.py`, `services/api-gateway/internal/middleware/jwt.go`, `infra/istio/20-peer-authentication.yaml`, `50-authorization.yaml` |
| **Components** | JWT (RS256) · mTLS (Istio STRICT) · AuthorizationPolicy · Fernet at-rest encryption · Correlation ID propagation |
| **Technical details** | Four trust zones: **0 untrusted** (Internet), **1 DMZ** (nginx + gateway), **2 trusted** (mesh), **3 restricted** (data stores, Ollama). Crossing a zone requires auth. |
| **Implementation** | Gateway is the only verifier of external JWTs. Gateway forwards signed tenant/user headers. Istio AuthorizationPolicy ensures only the gateway SA can call identity-svc. Secrets encrypted with Fernet before DB write. |
| **Tools & frameworks** | OIDC providers (Keycloak, Auth0, AWS Cognito) · Istio · SPIFFE/SPIRE · Vault · HashiCorp Boundary · Fernet (`cryptography` PyPI) |
| **How to implement** | 1. Define zones · 2. JWT verification at exactly one gateway · 3. mTLS mesh-wide · 4. Least-privilege AuthorizationPolicy per service · 5. Per-service DB credentials · 6. Encrypt secrets at rest. |
| **Real-world example** | User logs in → gets JWT from identity-svc · gateway verifies on every request · forwards `X-Tenant-ID` + `X-User-ID` to downstream · ingestion-svc trusts the header because Istio proved it came from the gateway SA. |
| **Pros** | Compromise of one zone doesn't compromise all · Secrets leaked from DB are useless without encryption key · Auditors love zones. |
| **Cons** | JWT rotation complexity · mTLS debugging is painful · Self-signed certs break curl tests. |
| **Limitations** | JWT size grows with claims · mTLS CPU overhead (~5-10%) · Not all SaaS dependencies support SPIFFE IDs. |
| **Recommendations** | Short-lived access tokens (15min) + long refresh (7d) · Public keys rotated via JWKS · Vault or external-secrets for secret stores. |
| **Challenges** | Revocation of JWTs (use short TTLs + deny-list) · Key rotation without downtime · Cross-cluster mesh identity. |
| **Edge cases + solutions** | Compromised admin key → rotate + publish deny-list · Clock skew → allow ±30s · Lost sidecar → pod failure (fail-closed) |
| **Alternatives** | OPAQUE tokens with introspection · mTLS without JWT (SPIFFE all the way) · AWS IAM for everything · Macaroons |

---

## Area 4 · Failure Boundary

| Field | Content |
|---|---|
| **DocuMind status** | ✅ Implemented |
| **Class / file** | `libs/py/documind_core/circuit_breaker.py` + `breakers.py` (5 specialized), `infra/istio/40-destinationrule.yaml` |
| **Components** | Circuit breakers (app + mesh) · Bulkheads · Pod resource limits · Timeouts · Retries with backoff · Fallbacks |
| **Technical details** | Contain faults to the smallest scope possible. Ollama dies → only inference affected, retrieval keeps serving, ingestion queues work for later. |
| **Implementation** | App-level CB per external call (Ollama, Qdrant, Neo4j, retrieval). Istio DR outlier-detection ejects bad pods. K8s `resources.limits` prevent OOM cascade. Graceful shutdown drains connections. |
| **Tools & frameworks** | Resilience4j (Java) · Polly (.NET) · `tenacity` / custom (Python) · Istio DestinationRule · Envoy · Hystrix (legacy) |
| **How to implement** | 1. Wrap every external call with a breaker · 2. Set timeout < SLO budget · 3. Define a safe fallback (cached, degraded, or explicit error) · 4. Set pod limits · 5. Test by killing dependencies. |
| **Real-world example** | Ollama container OOMs → CB opens after 5 failures → inference returns 503 with "service busy" → frontend shows retry UI · pods restart · CB half-opens · one probe succeeds · closed. |
| **Pros** | Fast failure (no thread pile-up) · Degraded service > dead service · Dependency recovery time without user-side DOS |
| **Cons** | Tuning thresholds is empirical · Cascading false-opens if a noisy metric · Fallbacks can hide real bugs |
| **Limitations** | Per-process state (multi-pod means per-pod CB state; mesh-level breaker covers this) · Won't detect semantic failures (the CCB fills that gap) |
| **Recommendations** | Two-layer: mesh (Istio outlier) + app (typed CB). Log every open/close. Alert on open. Never swallow CB exceptions silently. |
| **Challenges** | Calibrating `failure_threshold` · Distinguishing "slow" from "broken" · Test in prod-like chaos |
| **Edge cases + solutions** | Flappy network → add half-open probe hysteresis · Burst of legitimate traffic opens CB → scale up, don't just raise threshold · Fallback cache stale → TTL + mark response `degraded=true` |
| **Alternatives** | Timeouts only (weaker) · Retries without CB (causes cascade) · Bulkheads only (per-pool) · Bulk reject at the LB |

---

## Area 5 · Tenant Boundary

| Field | Content |
|---|---|
| **DocuMind status** | ✅ Implemented |
| **Class / file** | `DbClient.tenant_connection`, `Cache.tenant_key`, `rate_limiter.tenant_key`, migrations with RLS policies, `QdrantRepo` payload filter, `Neo4jRepo` property filter |
| **Components** | RLS policies (Postgres) · Payload filter (Qdrant) · Property filter (Neo4j) · Tenant-namespaced Redis keys · Per-tenant rate buckets · `tenant_id` in every Kafka message header |
| **Technical details** | Defense in depth — enforce at every layer. A bug in app code must NOT be able to leak across tenants because the DB / cache / index would refuse. |
| **Implementation** | `SELECT set_config('app.current_tenant', '<uuid>', true)` on every connection acquire. Qdrant `must: [{key:"tenant_id", match:{value:X}}]`. Neo4j `WHERE n.tenant_id = $tid`. Redis `tenant:{id}:...`. Kafka header `tenantid`. |
| **Tools & frameworks** | Postgres RLS · Qdrant / Weaviate / Pinecone payload filters · Neo4j property indexes · Keycloak groups/claims · AWS STS tenant IAM |
| **How to implement** | 1. Every tenant-scoped table has `tenant_id` + RLS policy · 2. Repos ONLY use tenant-scoped connection · 3. Every cache key goes through `Cache.tenant_key` · 4. Write a test that proves cross-tenant read returns empty. |
| **Real-world example** | Tenant A uploads a contract; Tenant B asks "summarize my contracts" → B's retrieval query's Qdrant filter excludes A's vectors; RLS ensures B can't even see the doc rows. |
| **Pros** | Structural isolation — bugs can't leak · Simplifies compliance (SOC2 / HIPAA / PCI) · Per-tenant quotas + billing become trivial |
| **Cons** | Every query pays a filter cost (small) · Migrations must account for RLS · Operator bypass must be explicit (`admin_connection`) |
| **Limitations** | Noisy-neighbor at the data-store level (Qdrant: one tenant's huge corpus slows searches) · RLS bypass via `BYPASSRLS` role is a foot-gun |
| **Recommendations** | Default tenant-scoped; admin is opt-in. Test cross-tenant isolation in CI. Track per-tenant metrics (cardinality: tenant_id is an OK label IF your tenant count is bounded). |
| **Challenges** | Shared analytics views · Data residency per tenant · Onboarding huge tenants to shared infra |
| **Edge cases + solutions** | Platform-admin cross-tenant report → explicit `admin_connection` with audit log · Deleted tenant → soft delete + purge cron · Noisy neighbor → per-tenant Qdrant collection for enterprise tier |
| **Alternatives** | Dedicated DB per tenant (stronger isolation, higher cost) · Row-level encryption per tenant (performance cost) · Separate clusters (paid tier) |

---

## Area 6 · Control Plane

| Field | Content |
|---|---|
| **DocuMind status** | 🟡 Partial — governance-svc is Go skeleton; CEL engine deferred |
| **Class / file** | `services/governance-svc/cmd/main.go`, `services/identity-svc/cmd/main.go`, `governance.policies` + `governance.feature_flags` tables |
| **Components** | Policy engine · Feature flag registry · Model Control Portal (MCP) · Rate limit configuration · Routing rules |
| **Technical details** | Controls HOW the system behaves, not WHAT data flows. Services READ from control plane (cached) but control plane doesn't sit on the hot path. |
| **Implementation** | governance-svc owns policies/flags. Services fetch at startup + poll every 30s. MCP admin UI lists / tweaks models, budgets, policies. |
| **Tools & frameworks** | CEL (Common Expression Language) · OPA · LaunchDarkly · Unleash · Argo Rollouts · Flagger · Istio (config plane) |
| **How to implement** | 1. Define policy schema · 2. CEL engine for rule evaluation · 3. Flag scopes: global/tenant/user/percentage · 4. Policy change → Kafka event for cache invalidation · 5. MCP UI · 6. Audit every change. |
| **Real-world example** | Platform admin flips a flag "enable_ccb_logprob_signal" from 0% → 10% tenants · governance publishes `policy.changes` event · inference-svc picks it up · next generation uses the new signal set. |
| **Pros** | Runtime behavior change without deploy · A/B ready · Audit-friendly |
| **Cons** | Config drift between regions · "Policy spaghetti" when unmaintained · Fetch latency adds to cold path |
| **Limitations** | CEL expressiveness (no loops) · Eventual consistency of config · Requires governance discipline |
| **Recommendations** | Cache with short TTL (30s) + event-driven invalidation · Version every policy · Deprecation window for flags (delete old flags). |
| **Challenges** | Consistent rollout across regions · Policy conflicts · "Who owns this rule?" |
| **Edge cases + solutions** | Policy fetch fails → use last-known-good cache · Flag removed mid-flight → default value · Conflicting policies → priority ordering by severity |
| **Alternatives** | Static config (deploy-to-change) · etcd-backed config · Kubernetes CRDs as policies |

---

## Area 7 · Data Plane

| Field | Content |
|---|---|
| **DocuMind status** | ✅ Implemented |
| **Class / file** | `services/ingestion-svc`, `services/retrieval-svc`, `services/inference-svc`, `services/evaluation-svc` |
| **Components** | Stateless request handlers · Chunker · Embedder · Retriever · Reranker · LLM orchestrator · Guardrails |
| **Technical details** | Handles actual docs + queries. Stateless — all state lives in data stores. Horizontally scalable. Reads policies from control plane but control plane is NOT on the hot path. |
| **Implementation** | FastAPI apps behind HPA; any pod can handle any request. Connection pools per service. Workers stateless; state in Postgres / Qdrant / Neo4j / Redis / Kafka. |
| **Tools & frameworks** | FastAPI · Uvicorn · asyncpg · qdrant-client · neo4j-python-driver · Ollama / vLLM / OpenAI · aiokafka |
| **How to implement** | 1. Stateless services · 2. Dependency injection for clients · 3. Probes (liveness + readiness) · 4. Graceful shutdown on SIGTERM · 5. Horizontal scale. |
| **Real-world example** | Query lands on retrieval pod 3 · pod 3 has no cache locally → hits Redis (miss) → parallel Qdrant + Neo4j → RRF merge → cache in Redis → reply. Next query can land on pod 7 with identical behavior. |
| **Pros** | Scales linearly · Rolling deploys easy · Kill-and-replace any pod · Multi-region possible |
| **Cons** | State in externalised stores adds latency · Every request pays a DB round trip · More moving parts |
| **Limitations** | GPU-bound services (inference) don't scale as linearly · Stateful bits (session) must stay fast in Redis |
| **Recommendations** | Strict "no local state" rule · Readiness probes that reflect dep health · Run chaos test: kill any pod, confirm no user sees an error |
| **Challenges** | Long-tail latency from far-from-optimal pod-to-data placement · Sticky-session replacement · GPU affinity |
| **Edge cases + solutions** | Cold-start latency → pre-warm pods · Connection pool exhausted → quick dep (Redis queue) · Hot tenant → shard |
| **Alternatives** | Stateful services with sticky sessions (avoid unless forced) · Actor-model frameworks (Akka, Orleans) |

---

## Area 8 · Management Plane

| Field | Content |
|---|---|
| **DocuMind status** | 🟡 Partial — observability-svc skeleton + Prometheus / Grafana / Kibana / Kiali deployed |
| **Class / file** | `services/observability-svc`, `infra/observability/*`, `infra/kiali/*`, docker-compose entries for Elastic / Kibana / Filebeat |
| **Components** | Metrics (Prometheus) · Logs (ELK) · Traces (Jaeger) · Dashboards (Grafana) · Mesh viz (Kiali) · Cost (FinOps) · Capacity (HPA+VPA) · Alerts (AlertManager) |
| **Technical details** | Operational lens — never touches user data. Aggregates across all services. Used by SREs + platform team, not end users. |
| **Implementation** | OTel collector scrapes services and fans out to Jaeger (traces) + Prometheus (metrics) + stdout→Filebeat→Elasticsearch (logs). Kiali reads Prometheus + Jaeger + Istio. |
| **Tools & frameworks** | Prometheus · Grafana · Jaeger · Loki/Kibana · OpenTelemetry · Kiali · PagerDuty · Datadog (SaaS alt) · New Relic |
| **How to implement** | 1. Every service emits OTel (traces+metrics) · 2. JSON logs to stdout · 3. Filebeat ship to ES · 4. Grafana dashboards per service · 5. SLO targets in `observability.slo_targets` · 6. Alerts in `alert-rules.yml`. |
| **Real-world example** | p95 latency crosses 3s → Prometheus alert fires → PagerDuty pages on-call → on-call opens Grafana → sees inference CPU @ 100% → scales pods. |
| **Pros** | Debugging time plummets · SLO tracking cheap · Post-mortems have data |
| **Cons** | Cost of TSDB + log store at scale · Cardinality explosions · Alert fatigue |
| **Limitations** | Prometheus cardinality (avoid `user_id` labels) · Logs cost > metrics cost at scale · Jaeger retention is usually short |
| **Recommendations** | Metrics first, logs for diagnosis, traces for causation · SLO-centric dashboards · Burn-rate alerts (multi-window) |
| **Challenges** | Unified querying across logs/metrics/traces (SigNoz/Tempo/Loki-LogQL getting there) · Log schema drift · Retention policies |
| **Edge cases + solutions** | Noisy service → per-service retention · PII in logs → mask at source (never rely on log-level redaction) · Telemetry down → `ObservabilityCircuitBreaker` skips export, never blocks app |
| **Alternatives** | Datadog / New Relic / Honeycomb (SaaS) · Splunk (logs) · AWS CloudWatch · Google Cloud Operations |
