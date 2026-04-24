# Areas 43–55 · Capacity, Resilience, Release Management

## Area 43 · Capacity Model

| Field | Content |
|---|---|
| **Status** | 🟡 Partial — HPA manifests + custom metric in place; capacity dashboard deferred |
| **Class / file** | `infra/k8s/services/*.yaml` (HPA blocks), `infra/observability/alert-rules.yml` |
| **Components** | HPA (CPU + custom metrics) · Resource requests/limits · Queue depth · Ollama inference RPS · Vector/Graph storage · Cache memory |
| **Technical details** | Per-dimension tracking. Scale triggers per axis: query throughput, ingestion throughput, inference RPS, storage growth. |
| **Implementation** | HPA with CPU% + `inference_inflight` custom metric. Prom rules watch growth rate. Projected utilization on admin dashboard. |
| **Tools & frameworks** | Kubernetes HPA (v2) · VPA · KEDA (Kafka-lag-driven scaling) · Cluster Autoscaler · Karpenter (AWS) |
| **How to implement** | 1. Identify limiting axis per service · 2. Expose as metric · 3. HPA on it · 4. Capacity dashboard · 5. Alert at 70% headroom. |
| **Real-world example** | `inference_inflight` > 8/pod → HPA adds a pod · if pod add fails (quota), alert fires · ops raises GPU quota. |
| **Pros** | Predictable scaling · Cost transparency · Spike absorption |
| **Cons** | Metrics must be accurate · Scaling lag · Cold-starts slow initial response |
| **Limitations** | GPU pods don't scale in seconds · Kafka consumer scaling needs KEDA |
| **Recommendations** | Capacity model BEFORE launch · 2-3x headroom for spike · Game day to validate |
| **Challenges** | Coordinated scale (HPA + VPA + CA) · Model-load time on GPU · Forecast vs reactive |
| **Edge cases + solutions** | Thundering herd on cold pods → pre-warm · GPU quota hit → alert + graceful degrade |
| **Alternatives** | Fixed-size clusters (simple, wasteful) · Serverless (cold-start cost) · Vertical-only scale |

---

## Area 44 · Queue Strategy

| Field | Content |
|---|---|
| **Status** | ✅ Implemented |
| **Class / file** | `libs/py/documind_core/kafka_client.py`; `infra/k8s/data-stores/redis-neo4j-kafka.yaml` |
| **Components** | Kafka topics · Partitioning key · Consumer groups · DLQ per topic · Retention · Compaction |
| **Technical details** | Topics partitioned by `tenant_id` (per-tenant ordering) or `document_id` (per-doc ordering). DLQ after 3 retries. Policy topic uses log compaction. |
| **Implementation** | `document.lifecycle` (6p, key=document_id), `query.lifecycle` (12p, key=tenant_id), `policy.changes` (1p, compacted). |
| **Tools & frameworks** | Apache Kafka · Confluent Cloud · Strimzi operator · Redpanda (simpler) · AWS MSK · Pulsar · NATS JetStream |
| **How to implement** | 1. Topic per domain · 2. Partitioning strategy per topic · 3. Consumer groups per service · 4. DLQ topic per main topic · 5. Retention policy. |
| **Real-world example** | `document.indexed.v1` published with key=document_id → consumed by retrieval cache invalidator + FinOps + eval sampler (3 groups, each reads all partitions). |
| **Pros** | Decouples producers from consumers · Replayable · Horizontal consumer scale |
| **Cons** | Ordering only per-partition · Consumer rebalance churn · Operator complexity |
| **Limitations** | Exactly-once is hard (transactional Kafka helps) · Cross-topic ordering not guaranteed |
| **Recommendations** | Partition by natural key · Plan partition count (hard to increase) · Monitor consumer lag |
| **Challenges** | Hot partition (skewed key) · Schema evolution · Cross-region mirroring |
| **Edge cases + solutions** | Hot key → random suffix + group-by downstream · Poison message → DLQ · Cluster full → scale out brokers |
| **Alternatives** | RabbitMQ (AMQP) · NATS · Redis Streams (simpler, smaller) · AWS SQS+SNS · Google Pub/Sub |

---

## Area 45 · Backpressure Strategy

| Field | Content |
|---|---|
| **Status** | ✅ Implemented |
| **Class / file** | `infra/nginx/nginx.conf` (L4), `services/api-gateway/internal/middleware/ratelimit.go`, `libs/py/documind_core/rate_limiter.py`, `breakers.py::CircuitBreaker` |
| **Components** | L4 rate limit (nginx) · L7 rate limit (gateway Redis) · Per-tenant quotas · Kafka consumer throttle · Service concurrency · Circuit breakers |
| **Technical details** | 4 layers of backpressure. Anyone layer can reject to protect the next. |
| **Implementation** | nginx `limit_req`, gateway Redis sliding window, service `RateLimitMiddleware`, Kafka `max.poll.records`, CB on external calls. |
| **Tools & frameworks** | nginx · Envoy RL · Redis · aiokafka · custom CB |
| **How to implement** | 1. L4 per-IP floor · 2. L7 per-tenant · 3. Service concurrency cap · 4. Kafka max.poll.records · 5. CB on downstream. |
| **Real-world example** | Burst of 10k rps from one IP → nginx rejects past 30rps · polite clients retry with `Retry-After` · protected system scales as needed. |
| **Pros** | Graceful degradation · DoS shield · System doesn't die |
| **Cons** | Tuning thresholds · False blocks on legit spikes · Complexity |
| **Limitations** | Rate limit alone doesn't solve slow-origin · Kafka backpressure is per-consumer-group |
| **Recommendations** | Tight L4 + generous L7 + CB on deps · `Retry-After` always · Monitor rejects vs capacity |
| **Challenges** | Legitimate burst vs abuse · Per-region rate budget · Shared CDN clients |
| **Edge cases + solutions** | Legit burst → raise bucket + scale · Abuse → add IP to deny-list · Downstream slow → CB opens, fail fast |
| **Alternatives** | Token bucket (bursty OK) · Leaky bucket (smooth) · Adaptive (based on latency) |

---

## Area 46 · Database Strategy

| Field | Content |
|---|---|
| **Status** | ✅ Implemented |
| **Class / file** | `libs/py/documind_core/db_client.py`, `services/*/migrations/001_initial.sql`, `infra/k8s/data-stores/postgres.yaml` |
| **Components** | Postgres 16 · Schema-per-service · RLS · Connection pool (asyncpg) · Migration runner · WAL mode · Indexes |
| **Technical details** | One DB, schemas per service, RLS for tenant isolation, WAL for crash safety, PgBouncer-compatible DSN. |
| **Implementation** | `DbClient` with `tenant_connection` (SET app.current_tenant) and `admin_connection` (RLS bypass, audited). Migrations tracked in `public._migrations`. |
| **Tools & frameworks** | Postgres · asyncpg (Python) · pgx (Go) · PgBouncer · pg_partman · pgbackrest · CloudNativePG operator |
| **How to implement** | 1. Schema per service · 2. RLS on all tenant-scoped tables · 3. Migration runner idempotent · 4. WAL + replica · 5. PgBouncer pool. |
| **Real-world example** | Ingestion writes `ingestion.documents` row; retrieval reads it from a read replica. Both go through tenant_connection — RLS enforces tenant scope. |
| **Pros** | ACID · Mature ecosystem · Proven at scale · RLS is structural isolation |
| **Cons** | Single point for everything per cluster · Write scalability · Schema migrations under load |
| **Limitations** | Vertical-only writes unless sharded · Connection count cap · Vacuuming |
| **Recommendations** | RLS on everything · Indexes on FKs + WHERE/ORDER BY columns · Monitor replication lag · Quarterly DR drill |
| **Challenges** | Sharding strategy (tenant-id modulo?) · Migrations with live traffic · Cross-schema joins (forbidden) |
| **Edge cases + solutions** | Huge migration → expand-migrate-contract · Vacuuming bloat → autovacuum tuning · Hot tenant → dedicated schema or shard |
| **Alternatives** | CockroachDB (global, SQL, Postgres-compat) · Yugabyte · MySQL/MariaDB · DynamoDB (NoSQL) · Spanner (Google) |

---

## Area 47 · Vector DB Strategy

| Field | Content |
|---|---|
| **Status** | ✅ Implemented |
| **Class / file** | `services/ingestion-svc/app/repositories/qdrant_repo.py` |
| **Components** | One shared collection · Tenant-id payload filter · HNSW index · Cosine distance · Scalar quantization · Payload indexes (tenant_id, document_id, created_at) |
| **Technical details** | Single-collection multi-tenant design scales better than one-per-tenant. Payload filter is structural. HNSW m=16, ef_construct=128. |
| **Implementation** | `QdrantRepo.ensure_collection` idempotent. Upserts include tenant_id in payload. Delete by `document_id` filter for saga compensation. |
| **Tools & frameworks** | Qdrant · Weaviate · Pinecone · Milvus · pgvector · Chroma · Vespa |
| **How to implement** | 1. Collection config (dim, distance, HNSW) · 2. Payload indexes for filters · 3. Quantization on big collections · 4. Backup via snapshots. |
| **Real-world example** | 10M vectors, tenants query with must-filter on tenant_id → HNSW skips non-matching, ~50ms p95. |
| **Pros** | Sub-100ms semantic search at scale · Filterable · Metadata-rich |
| **Cons** | Eventual consistency · Memory-hungry (even with quantization) · No joins |
| **Limitations** | HNSW recall/speed tradeoff · Huge collections need sharding (Qdrant supports distributed mode) |
| **Recommendations** | Quantize early · Per-tenant payload indexes · Shard by tenant for enterprise tenants · Monitor recall |
| **Challenges** | Cross-tenant isolation (tested with unit test) · Re-indexing · Cold starts |
| **Edge cases + solutions** | Tenant with millions of vectors → dedicate a collection · Deleted doc → filter-delete; async vacuum |
| **Alternatives** | Weaviate (built-in hybrid) · Pinecone (managed) · pgvector (Postgres-native) · Milvus (cloud-native) |

---

## Area 48 · Graph Strategy

| Field | Content |
|---|---|
| **Status** | ✅ Implemented |
| **Class / file** | `services/ingestion-svc/app/repositories/neo4j_repo.py`, `services/retrieval-svc/app/services/graph_searcher.py` |
| **Components** | Nodes (Document, Chunk, Entity, Concept) · Relationships (HAS_CHUNK, MENTIONS, RELATED_TO, IS_A) · Tenant property on every node · Unique constraints |
| **Technical details** | Tenant on every node. Unique constraints prevent cross-tenant collisions. Graph for multi-hop reasoning, not for primary text. |
| **Implementation** | Constraints on `(tenant_id, id)`. Cypher queries always filter on tenant. Entity extraction is stubbed; real NER via spaCy/LLM in future. |
| **Tools & frameworks** | Neo4j · ArangoDB · JanusGraph · Amazon Neptune · Dgraph · NetworkX (in-memory for small) |
| **How to implement** | 1. Ontology design FIRST · 2. Unique constraints per tenant · 3. NER pipeline · 4. Relationship extraction · 5. Query patterns documented. |
| **Real-world example** | "What indemnification clauses apply to vendor X?" → MATCH (v:Entity {name:"X"})-[:RELATED_TO*1..3]-(:Entity)-[:MENTIONED_IN]-(c:Chunk) → multi-hop answer. |
| **Pros** | Multi-hop reasoning · Explicit relationships · Expressive queries |
| **Cons** | Ontology effort · Entity extraction quality · Query latency |
| **Limitations** | Scale ceiling (Neo4j single-node) — use Fabric for sharding · NER accuracy |
| **Recommendations** | Ontology before coding · Property indexes on hot filters · Graph for reasoning, vector for similarity |
| **Challenges** | Ontology drift · Relationship extraction precision · Cross-domain entity linking |
| **Edge cases + solutions** | Entity aliases → NER resolution step · Orphan nodes → nightly cleanup · Ontology change → migration script |
| **Alternatives** | ArangoDB (multi-model) · Amazon Neptune · RDF + SPARQL · Property graphs in Postgres (Apache AGE) |

---

## Area 49 · HA Strategy

| Field | Content |
|---|---|
| **Status** | ✅ Implemented |
| **Class / file** | K8s manifests with `replicas >=2`, `podAntiAffinity`, readiness/liveness probes; Istio DR outlier-detection |
| **Components** | Multiple replicas · Pod anti-affinity · Readiness/liveness · Graceful shutdown · Data-store replication · Istio retries |
| **Technical details** | Min 2 replicas per service, anti-affinity spreads across nodes, rolling deploy with `maxUnavailable: 0`, 30s shutdown grace. |
| **Implementation** | Deployment has probes, anti-affinity, graceful shutdown. Istio VS retries on 5xx (2 attempts). Postgres streaming replica; Qdrant replication factor 2; Redis Sentinel. |
| **Tools & frameworks** | K8s Deployments + HPA · Istio retries · Postgres streaming replication · Redis Sentinel/Cluster · CloudNativePG · Strimzi for Kafka |
| **How to implement** | 1. `replicas >= 2` · 2. Anti-affinity · 3. Probes · 4. SIGTERM handling · 5. Data-store replication · 6. Istio retries. |
| **Real-world example** | Node drain → K8s evicts one pod → another pod serves uninterrupted → new pod schedules on different node · no user sees error. |
| **Pros** | Survives node failure · Rolling deploys · No single SPOF |
| **Cons** | 2x cost (minimum) · Distributed consensus for data stores · Complexity |
| **Limitations** | Multi-AZ requires topology-aware scheduling · Kafka needs ≥3 replicas for quorum |
| **Recommendations** | Spread across ≥2 AZs · Test by draining a node monthly · Data-store HA before app HA |
| **Challenges** | Split-brain · Replica lag · Rolling deploy during cert rotation |
| **Edge cases + solutions** | Zone failure → traffic shifts automatically · Replica falls behind → alert + promote if needed |
| **Alternatives** | Active-passive (simpler, bigger blast on failover) · Single-AZ with backup (cheap, slow recovery) |

---

## Area 50 · DR Strategy

| Field | Content |
|---|---|
| **Status** | 🟡 Partial — docs/runbooks/DR_RUNBOOK.md + backup commands; automated restore test deferred |
| **Class / file** | `docs/runbooks/DR_RUNBOOK.md` |
| **Components** | RPO per store · RTO · Backup procedure · Restore procedure · Monthly DR drill · Runbook |
| **Technical details** | RPO 15min for Postgres (WAL), 1h Qdrant/Neo4j (snapshots), 0 for Kafka (replicated). RTO 30min-1h per store. |
| **Implementation** | `pg_dump` nightly + WAL archive. Qdrant `POST /snapshots`. Neo4j `neo4j-admin dump`. Automated monthly drill script (planned). |
| **Tools & frameworks** | pgBackRest · WAL-G · Velero (K8s) · AWS Backup · Cloud SQL automated backup · Qdrant snapshot API |
| **How to implement** | 1. Define RPO/RTO per store · 2. Automated backup · 3. Offsite copy · 4. Monthly restore test · 5. Runbook per service. |
| **Real-world example** | Region-wide outage → failover to standby region with 15-min-old data · RTO 30min · users see staleness but service continues. |
| **Pros** | Business continuity · Compliance · Audit-friendly |
| **Cons** | Storage cost · Drill overhead · Keeping runbooks current |
| **Limitations** | Some data lost (RPO > 0) · Snapshot consistency across stores · Human error during restore |
| **Recommendations** | Automate drills · Test restore monthly · Document every step · Multi-region for critical tenants |
| **Challenges** | Cross-store snapshot consistency · Drill interference with prod · Forgotten secrets in restore |
| **Edge cases + solutions** | Backup corrupt → keep N generations · DR region behind on data → set expectations + UX message |
| **Alternatives** | Cloud-native (S3 versioning, RDS snapshots, etc.) · Mirrored clusters (hot standby, higher cost) |

---

## Area 51 · Multi-Region Strategy

| Field | Content |
|---|---|
| **Status** | ❌ Designed only |
| **Class / file** | `spec §51`; interfaces abstracted so swap is config, not code |
| **Components** | Active-passive regions · Tenant affinity · Data replication (Postgres logical, Qdrant, Kafka MirrorMaker) · DNS failover |
| **Technical details** | Each tenant pinned to a primary region. Secondary receives async replication. Failover via DNS. |
| **Implementation (planned)** | `DOCUMIND_REGION` env var. Data replication jobs per store. DNS with health checks. Tenant→region mapping in identity-svc. |
| **Tools & frameworks** | AWS Route53 health checks · Postgres logical replication · Kafka MirrorMaker 2 · Qdrant snapshots · Cloudflare GeoDNS |
| **How to implement** | 1. Tenant→region map · 2. Replicate data async · 3. Route by tenant · 4. Failover DNS · 5. Reconcile post-failover. |
| **Real-world example** | us-east primary down → DNS fails over to us-west · tenants on us-east lose up to 5min of data · restore when us-east recovers. |
| **Pros** | Survives region loss · Data sovereignty (EU tenants in EU) · Lower latency for distant users |
| **Cons** | Complexity · Replication cost · Split-brain risk · Compliance review |
| **Limitations** | RPO > 0 for async replication · Conflict resolution during brief active-active |
| **Recommendations** | Start active-passive · Tenant affinity · Quarterly cross-region drill |
| **Challenges** | Conflict resolution · Network partitions · Cross-region compliance (GDPR) |
| **Edge cases + solutions** | Split-brain → fence old primary · Slow replication → backpressure writes |
| **Alternatives** | Single region + backups (cheapest) · Active-active multi-writer (CRDT/Spanner) · Per-region separate instances (isolation) |

---

## Area 52 · Blast Radius Control

| Field | Content |
|---|---|
| **Status** | ✅ Implemented |
| **Class / file** | `infra/k8s/base/03-netpol-default.yaml`, `infra/k8s/services/*.yaml` NetworkPolicy blocks, `infra/istio/50-authorization.yaml` |
| **Components** | NetworkPolicy default-deny · Per-service egress allowlist · Istio AuthorizationPolicy · Resource quotas · Schema-per-service · Tenant quotas · Feature flags |
| **Technical details** | Multiple layers: network, identity, data, resource, tenancy. One failure can't consume all. |
| **Implementation** | Default-deny ingress+egress in namespace. Per-service egress allows only what's needed. Istio AuthorizationPolicy per service. K8s `limits` per pod. |
| **Tools & frameworks** | K8s NetworkPolicy · Istio AuthorizationPolicy · Cilium (eBPF) · ResourceQuota · LimitRange |
| **How to implement** | 1. Default-deny · 2. Per-service rules · 3. Resource limits · 4. Tenant quotas · 5. Feature-flag new risk. |
| **Real-world example** | Inference-svc compromised → NetworkPolicy blocks its egress to anywhere except retrieval-svc + Ollama · attacker can't pivot to DB. |
| **Pros** | Containment · Fewer cross-cutting incidents · Auditor-friendly |
| **Cons** | Policy authoring overhead · Debugging "why is my service blocked?" |
| **Limitations** | NetworkPolicy doesn't understand L7 (use Istio AuthZ for that) · Tight policies break legitimate changes |
| **Recommendations** | Deny-by-default + explicit allow · Test policies in staging · Per-service NetPol owner |
| **Challenges** | Policy drift · Debugging denied flows · Dev-vs-prod differences |
| **Edge cases + solutions** | New dep missed in allowlist → monitoring alerts on deny, owner updates · Emergency access → break-glass role with audit |
| **Alternatives** | Flat network (simple, unsafe) · Service mesh only (partial coverage) · Cilium CNP (eBPF, more expressive) |

---

## Area 53 · Release Isolation

| Field | Content |
|---|---|
| **Status** | ✅ Implemented |
| **Class / file** | `infra/istio/30-virtualservice.yaml` (canary), `infra/istio/40-destinationrule.yaml` (subsets), K8s rolling-update strategy |
| **Components** | Istio VirtualService (traffic split) · DestinationRule subsets (stable/canary) · Rolling update (`maxUnavailable: 0`) · Shadow traffic · Feature flags |
| **Technical details** | Canary gets 10% traffic; shadowing mirrors 100% for telemetry without affecting users. |
| **Implementation** | VS weights subset.stable=90, canary=10. Canary pods labeled `version: canary`. Per-tenant canary via `X-Canary: true` header. |
| **Tools & frameworks** | Istio VS/DR · Argo Rollouts · Flagger · Flipper (Ruby) · LaunchDarkly (flag-driven) |
| **How to implement** | 1. Subsets in DR · 2. Weight in VS · 3. Promote via weight bump · 4. Automated rollback on metric breach (Flagger). |
| **Real-world example** | Deploy `inference-svc:v2` → 10% traffic for 1h · Flagger monitors error rate · if clean, bump to 50% · then 100% · if degraded, roll back. |
| **Pros** | Safe rollout · Fast rollback · Real production signal |
| **Cons** | Canary period extends rollout · Traffic-shift glitches during weight change |
| **Limitations** | Stateful services can't canary trivially · Protobuf schema changes need coordinated deploy |
| **Recommendations** | Automate with Flagger · Tie to SLOs · Never canary DB migrations |
| **Challenges** | Defining "healthy" canary · Stateful workloads · Cross-service canary |
| **Edge cases + solutions** | Canary metric noise → widen observation window · Canary-only bug → auto-rollback on SLO breach |
| **Alternatives** | Blue-green (instant swap) · Feature flags only (simpler) · Full rolling (no subset control) |

---

## Area 54 · Rollback Isolation

| Field | Content |
|---|---|
| **Status** | ✅ Implemented |
| **Class / file** | K8s `kubectl rollout undo` + governance feature flags + Istio VS weight revert |
| **Components** | `kubectl rollout undo` · `down.sql` per migration · Feature flag kill switch · Kafka offset reset · Container immutability |
| **Technical details** | Multiple rollback paths. Feature flag is fastest (seconds); kubectl rollout is fast (minutes); DB rollback is slowest (depends). |
| **Implementation** | Every migration has a `down.sql`. Every feature flag has a default-safe value. VS weights reverted on rollback. |
| **Tools & frameworks** | K8s rollouts · Atlas for DB migrations · Flipper / LaunchDarkly / homegrown |
| **How to implement** | 1. `down.sql` per migration · 2. Flag kill switch · 3. Rollout undo tested in staging · 4. Runbook per rollback class. |
| **Real-world example** | New prompt regresses faithfulness → flip `prompt_version` flag back to `v2` · zero-deploy rollback · root-cause investigation in parallel. |
| **Pros** | Fast recovery · Multiple paths for different risks · Testable |
| **Cons** | Migration rollback needs discipline · Flag sprawl · Runbook maintenance |
| **Limitations** | Non-reversible migrations (column drops) need forward-only mitigation · Data migrations |
| **Recommendations** | Expand-migrate-contract for DB · Flag every risky change · Test rollback in staging |
| **Challenges** | Schema evolution · Data migration reversal · Cross-service coordination |
| **Edge cases + solutions** | Rollback after users see new UX → add migration note · Flag default changed → review every tenant |
| **Alternatives** | Version-tagged deployments · GitOps reverts · Rollforward (fix, don't rollback) |

---

## Area 55 · Feature Flag Strategy

| Field | Content |
|---|---|
| **Status** | 🟡 Partial — governance schema + docs; runtime client deferred |
| **Class / file** | `services/governance-svc/migrations/001_initial.sql` (feature_flags table); client code deferred |
| **Components** | Flag definition (name, scope, default, status) · Scopes (global/tenant/user/percentage) · Lifecycle (draft/active/deprecated) |
| **Technical details** | Flags scoped with priority: user > tenant > percentage > global. Percentage rollout deterministic by hash(user_id). |
| **Implementation (planned)** | `FeatureFlagClient.is_enabled(flag, tenant_id, user_id)` reads from Redis cache (30s TTL). Governance writes flip cache. |
| **Tools & frameworks** | Unleash · LaunchDarkly · Flipper · Split · GrowthBook (OSS) · GitHub Flipt |
| **How to implement** | 1. Flag schema · 2. Polling client with cache · 3. Scopes + priority · 4. Percentage via stable hash · 5. Deprecation workflow. |
| **Real-world example** | Roll out new reranker to 10% → `is_enabled("new_reranker", user.id)` returns true for 10% · monitor · expand if clean. |
| **Pros** | Instant rollout/rollback · A/B testing · Gated release · No deploy required |
| **Cons** | Flag sprawl · Code complexity · Deprecation discipline |
| **Limitations** | Stale cache (eventual) · Flag dependencies · Testing every flag combo |
| **Recommendations** | Every flag has an owner + deprecation date · Flag-cleanup sprint quarterly · Default-safe values |
| **Challenges** | Flag graveyards · Cross-service consistency · Testing cartesian product |
| **Edge cases + solutions** | Flag fetch fails → use last-known-good · Percentage-bucket change → user suddenly on/off |
| **Alternatives** | Config files (deploy-to-change) · ENV vars (per-pod) · LaunchDarkly (SaaS, rich) |
