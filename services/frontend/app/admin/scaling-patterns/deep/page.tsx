'use client';

import DeepDiveCrossRefs from '../../../../components/DeepDiveCrossRefs';
import UniversalDeepDive, { type Topic } from '../../../../components/UniversalDeepDive';

const TOPICS: Topic[] = [
  {
    slug: 'load-balancing',
    title: '1. Load balancing (current state + scaling path)',
    status: 'partial',
    coreConcept: 'Load balancing distributes requests across multiple replicas of a service to spread load + survive single-replica failures. In this codebase the BFF + backends run as single-replica processes in docker-compose; load balancing is a Phase-2 concern that activates when k8s migration lands. The scaling path: Service mesh (Istio) handles internal LB via outlier detection; cloud LB or NGINX handles edge LB.',
    problem: 'Single-replica deployments cannot survive any restart, OOM, or crash without user-visible downtime. As traffic grows, a single Node BFF process saturates around 500 RPS for proxy routes. Without LB, scaling = restart the bigger box; eventually a vertical wall is hit.',
    whyThisApproach: 'Phase-1 single-replica is a deliberate tradeoff: zero LB operational cost, simpler debugging, cheaper infra. The migration path (k8s + Service mesh + cloud LB) is documented; the contracts (correlation_id, canonical envelope, idempotent steps) are already in place so adding replicas does not change application code.',
    whenToUse: ['Stateful services where session affinity matters (sticky sessions to BFF replica)', 'Latency-sensitive paths where round-robin is too crude (least-conn / weighted)', 'Multi-region deployments (geo-routed LB)', 'High-throughput backends (>500 RPS)'],
    whenNotToUse: ['Single-replica Phase-1 (overhead with no benefit)', 'Stateless paths where caching dominates load (cache before LB matters)', 'Sub-ms latency where LB hop adds non-trivial overhead'],
    input: 'incoming request + replica health state + LB policy (round-robin / least-conn / weighted)',
    process: [
      'Edge LB (cloud LB or NGINX) terminates TLS and applies global rate limit',
      'Edge LB picks backend replica via policy + health',
      'Mesh-internal LB (Istio outlier detection) picks healthy replica downstream',
      'Each backend replica runs locally; horizontal scaling = more pods',
      'Failed replica ejected by outlier detection; traffic auto-routed to healthy peers',
    ],
    output: 'Per-request routing to a healthy replica with per-policy distribution.',
    flowchart: `flowchart LR
  br[Browser] -->|TLS| edge[Edge LB / NGINX]
  edge -->|round-robin| g1[Gateway-1]
  edge -->|round-robin| g2[Gateway-2]
  g1 -->|outlier-aware| svc1[Backend-1]
  g1 -->|outlier-aware| svc2[Backend-2]
  g2 -->|outlier-aware| svc1
  g2 -->|outlier-aware| svc2
  svc1 -.failed.-> ejected[Ejected]`,
    sequence: `sequenceDiagram
  autonumber
  participant Br as Browser
  participant LB as Edge LB
  participant GW as Gateway pool
  participant SVC as Backend pool
  Br->>LB: request
  LB->>LB: pick gateway (round-robin)
  LB->>GW: forward
  GW->>SVC: pick backend (least-conn)
  alt healthy
    SVC-->>GW: response
    GW-->>LB: response
    LB-->>Br: response
  else outlier-detected
    SVC-->>GW: 5xx
    GW->>GW: eject + retry next
    GW->>SVC: retry on healthy peer
  end`,
    alternatives: [
      { name: 'Single replica (current)', tradeoff: 'Cheapest; no LB; restart = downtime' },
      { name: 'Cloud LB only', tradeoff: 'Edge LB + naive round-robin to k8s service; no internal outlier detection' },
      { name: 'Service-mesh-only LB', tradeoff: 'Internal mesh handles LB; no edge protection (TLS, WAF, global rate-limit)' },
    ],
    challenges: [
      'Sticky-session requirements (BFF session-cookie affinity)',
      'Replica warmup (cold replica in pool causes p99 spikes)',
      'Geographic LB across regions (latency vs availability tradeoff)',
      'Connection pooling under LB churn',
    ],
    edgeCases: [
      { case: 'All replicas of a service down', solution: 'Edge LB returns 503; circuit breaker on caller side fast-fails downstream' },
      { case: 'Sticky session needed but replica restarted', solution: 'Session in Redis (not memory); any replica can serve any session' },
      { case: 'Replica added but not yet healthy', solution: 'Readiness probe gates LB inclusion (k8s 3-probe pattern per global §47)' },
    ],
    failureModes: [
      { mode: 'Outlier detection ejects all replicas', detect: 'Backend pool empty in mesh; all traffic 503', recover: 'Increase consecutiveErrors threshold; investigate root cause; deploy fix' },
      { mode: 'Sticky-session cookie leak', detect: 'Replica receiving traffic for sessions it never created', recover: 'Audit cookie scope + signing; ensure session is in Redis not memory' },
      { mode: 'Connection pool exhaustion', detect: 'maxConnections hit; new requests queue', recover: 'Tune connection pool; reduce keepalive; investigate backend latency' },
    ],
    monitoring: [
      'documind_lb_request_total{replica}',
      'documind_lb_outlier_ejections_total',
      'documind_lb_active_connections{replica}',
      'k8s readiness probe success rate per replica',
    ],
    testing: [
      'drill_lb_replica_health (PLANNED — outlier detection contract)',
      'drill_session_affinity (PLANNED — sticky session works under replica churn)',
      'drill_readiness_probe_gate (PLANNED — replica not in pool until ready)',
    ],
    security: [
      'Edge LB terminates TLS; backend traffic is mesh-internal mTLS',
      'No client IP exposure to backends — LB strips x-forwarded-for, replaces with SPIFFE identity',
      'Per-tenant rate-limit at edge LB (planned per /admin/api-gateway)',
    ],
    scaling: [
      '10x: 5-10 replicas per service; cloud LB + mesh outlier detection',
      '100x: multi-region LB (geo-routing) + per-region replica pools + cross-region failover',
      'Cost driver: cloud LB hourly + per-GB; outlier-detection metric volume',
    ],
    maturity: {
      mvp: 'Single replica per service in docker-compose (current)',
      production: 'PARTIAL — service mesh authz YAML committed; LB via mesh + cloud LB is k8s-future',
      enterprise: 'Multi-region LB + geo-routing + sticky-session in Redis + canary rollout via mesh weighted routing',
    },
    limitations: [
      'NOT YET SHIPPED in compose stack — single replica per service',
      'No drill yet locks the LB / outlier-detection contract',
      'No session-state externalization to Redis (BFF uses in-process for now)',
    ],
    projectFit: [
      'docker-compose.yml — single-replica baseline',
      'infra/istio/50-authorization.yaml — service mesh authz (foundation for mesh LB)',
      '/admin/service-mesh/deep — mesh LB lives there',
      '/admin/api-gateway/deep — edge LB tier',
    ],
    interviewLine: 'Phase-1 is single-replica; load balancing is a Phase-2 concern when k8s migration lands. The migration path: cloud LB or NGINX at edge + Istio outlier detection internally. The contracts that make horizontal scaling non-disruptive — correlation_id, canonical envelope, idempotent steps — are already in place. The decision is timing: scale to multi-replica when single-process latency p95 begins drifting, not before.',
    implementationSteps: [
      { step: 'Externalize session', logic: 'Move BFF session from in-process to Redis; any replica serves any session.' },
      { step: 'Readiness probes', logic: 'k8s 3-probe pattern per §47 — replica not in LB pool until ready.' },
      { step: 'Edge LB', logic: 'Cloud LB or NGINX in front of gateway pool; round-robin or least-conn policy.' },
      { step: 'Mesh outlier detection', logic: 'DestinationRule consecutiveErrors=5 → eject replica for N seconds.' },
      { step: 'Connection pooling', logic: 'Tune maxConnections per service; HTTP/2 multiplex where possible.' },
      { step: 'Drill the LB', logic: 'drill_lb_replica_health forces a replica failure; verify outlier detection ejects + restores.' },
      { step: 'Multi-region', logic: 'Geo-routed LB with per-region pools; cross-region failover via DNS or LB priority.' },
    ],
    codeExample: {
      language: 'yaml',
      code: `# Future: infra/istio/destination-rules.yaml — mesh-level LB + outlier detection
apiVersion: networking.istio.io/v1beta1
kind: DestinationRule
metadata:
  name: api-gateway-lb
  namespace: documind
spec:
  host: api-gateway
  trafficPolicy:
    connectionPool:
      tcp: { maxConnections: 200 }
      http:
        http1MaxPendingRequests: 50
        http2MaxRequests: 1000
    loadBalancer:
      simple: LEAST_CONN
    outlierDetection:
      consecutiveErrors: 5
      interval: 30s
      baseEjectionTime: 30s
      maxEjectionPercent: 50`,
    },
    starStory: {
      situation: 'Phase-1 ships single-replica services in docker-compose. Restart = downtime. Single Node BFF saturates ~500 RPS. Migration to multi-replica needed but not urgent.',
      task: 'Document the LB scaling path so contracts at the BFF layer (correlation_id, canonical envelope, idempotent steps) are designed for non-disruptive horizontal scaling.',
      action: 'PARTIAL — service mesh authz YAML in place (foundation). Cloud LB + DestinationRule outlier detection deferred until k8s migration. BFF contract already enforces correlation_id propagation across replicas.',
      result: 'When LB activates: contracts unchanged, replicas added incrementally, outlier detection auto-ejects unhealthy replicas, no application code changes required.',
    },
    interviewTraps: [
      'Adding LB tier prematurely (operational burden without payoff)',
      'In-process session state (cannot scale horizontally)',
      'No readiness probe (cold replica in pool causes p99 spikes)',
    ],
    finalScript: 'Load balancing is a tiered concern: edge LB (TLS + global rate-limit) + mesh-internal LB (outlier detection) + per-replica connection pooling. Phase-1 is single-replica; Phase-2 activates with k8s migration. The contracts that make scaling non-disruptive — correlation_id, canonical envelope, idempotent steps, externalized session — must be in place before the first replica is added. Otherwise scaling reveals every coupling.',
  },
  {
    slug: 'page-index-rag',
    title: '2. Page-level index (RAG pre-retrieval optimization)',
    status: 'planned',
    coreConcept: 'Beyond chunk-level vector search, an additional page-level index records which document pages contain which chunks. Pre-retrieval, the page index narrows the candidate document set; chunk-level vector search runs only over chunks belonging to the candidate pages. Two-stage retrieval cuts latency + cost while improving precision because document-level signal augments chunk similarity.',
    problem: 'Pure chunk-level vector search treats every chunk independently. A query like "what does the security ADR say about JWT?" returns top chunks by vector similarity but may miss the canonical document because chunks within it are individually weaker. Document-level priors (title match, document type, recency) can\'t express through chunk similarity alone.',
    whyThisApproach: 'Two-stage: page-level keyword/BM25 + chunk-level vector. The page stage uses cheap features (title, headings, document type, freshness) to score pages; the chunk stage runs vector search only over chunks of the top-K pages. Latency improves (smaller chunk pool to search), precision improves (document signal informs chunk selection), explainability improves (citation chain says "this page, this chunk").',
    whenToUse: ['Long documents where chunk-level signal is weak', 'Queries with document-type intent ("what does the README say about...")', 'Citation requirements (page-level identity matters for source attribution)', 'Multi-document search where document-level priors matter'],
    whenNotToUse: ['Short documents where chunks are document-equivalent', 'Pure semantic queries with no document-type intent', 'Single-document corpora where page-stage adds nothing'],
    input: 'query → page-level rerank → top-K page IDs → chunk vector search constrained to those pages',
    process: [
      'Build page index: for each ingested document, extract title + headings + type + freshness + chunk IDs',
      'At query time: BM25 / keyword score over (title + headings) for each page',
      'Combine page features into page score; pick top-K pages',
      'Chunk vector search: filter by chunk_id ∈ chunks(top-K pages); cosine over the filtered set',
      'Return chunks with both page-rank and chunk-rank signals; rerank composite',
      'Citation chain: chunk_id → page_id → document for full traceability',
    ],
    output: 'Top chunks with page-level + chunk-level scoring, full citation chain.',
    flowchart: `flowchart LR
  q[Query] --> p_idx[Page index BM25]
  p_idx --> top_p[Top-K pages]
  q --> c_emb[Query embedding]
  c_emb --> c_search[Chunk vector search]
  top_p --> c_search
  c_search --> rerank[Composite rerank]
  rerank --> ans[Top chunks + citation chain]`,
    sequence: `sequenceDiagram
  autonumber
  participant Q as Query
  participant P as Page index (BM25)
  participant V as Chunk vector index
  participant R as Reranker
  Q->>P: rank pages by title + headings
  P-->>Q: top-K page IDs
  Q->>V: vector search constrained to top-K pages
  V-->>Q: top chunks
  Q->>R: combine page-rank + chunk-rank
  R-->>Q: composite-ranked chunks + citation chain`,
    alternatives: [
      { name: 'Chunk-only vector search (current)', tradeoff: 'Simple; works for short docs; misses document-level signal' },
      { name: 'Document-only retrieval (no chunking)', tradeoff: 'Coarse; loses snippet precision; cannot cite specific passage' },
      { name: 'Reranker-only (after chunk search)', tradeoff: 'Improves precision; doesn\'t reduce vector search cost; no document priors' },
    ],
    challenges: [
      'Maintaining page index in sync with chunk index (re-embed on doc update)',
      'BM25 + vector signal weighting (tune per query class)',
      'Page features extraction (title vs body, headings vs prose)',
      'Storage cost (page index in addition to chunk index)',
    ],
    edgeCases: [
      { case: 'Page has only one chunk', solution: 'Page-stage = chunk-stage; no narrowing benefit; pass-through' },
      { case: 'Top-K pages return no chunks above threshold', solution: 'Fallback to chunk-only search over full corpus; flag low-confidence retrieval' },
      { case: 'Page index out of sync with chunk index', solution: 'Versioned indexes; reject mismatched-version retrieval; rebuild' },
    ],
    failureModes: [
      { mode: 'Page-stage filters out the right doc', detect: 'Citation pass rate drops; operator notices missing canonical sources', recover: 'Tune page features; add document-type weight' },
      { mode: 'Both indexes drift apart', detect: 'chunk_id references page_id that no longer exists', recover: 'Atomic re-index per document update; transactional swap' },
      { mode: 'Top-K too small', detect: 'recall drops; queries miss relevant docs', recover: 'Walk K up per ratchet; trade latency for recall' },
    ],
    monitoring: [
      'documind_rag_page_index_recall_at_k',
      'documind_rag_two_stage_latency_seconds_p95',
      'documind_rag_page_chunk_drift_total (mismatch detections)',
    ],
    testing: [
      'drill_rag_page_index_freshness (PLANNED — page index updates on doc change)',
      'drill_rag_two_stage_recall (PLANNED — page-stage doesn\'t drop relevant docs)',
      'drill_rag_citation_chain (PLANNED — citation traceable through page → chunk)',
    ],
    security: [
      'Page index inherits chunk index PII redaction',
      'Per-tenant page index — no cross-tenant document leak',
      'Versioned indexes ensure replay reproducibility per §48 explainability',
    ],
    scaling: [
      '10x: in-memory BM25 over page index for sub-ms page rank',
      '100x: distributed BM25 (Elasticsearch / Tantivy) + sharded chunk index',
      'Cost driver: page features storage + BM25 query cost; tune by query class',
    ],
    maturity: {
      mvp: 'Chunk-only vector search (current — single-stage)',
      production: 'PLANNED — two-stage retrieval with page index narrowing',
      enterprise: 'Page index + chunk index + reranker + per-query class feature weights + per-tenant tuning',
    },
    limitations: [
      'NOT YET SHIPPED — current retrieval is chunk-only',
      'No drill catalogs yet for two-stage retrieval',
      'Page-feature extraction not implemented',
    ],
    projectFit: [
      'services/inference-svc/* — current chunk-only retrieval',
      'docs/architecture/adr/ — RAG ADRs (foundation)',
      '/admin/rag/deep — current single-stage retrieval documented',
      'Future: services/page-index-svc/ + drill_rag_two_stage_*.py',
    ],
    interviewLine: 'Page-level index is RAG pre-retrieval optimization: filter pages first by cheap features, then vector-search chunks within top pages. Latency improves (smaller chunk pool), precision improves (document signal informs chunk selection), citation chain gains a level of traceability. NOT YET SHIPPED in this codebase — current retrieval is chunk-only.',
    implementationSteps: [
      { step: 'Page feature extraction', logic: 'On doc ingest: title, headings, type, freshness, chunk IDs.' },
      { step: 'BM25 page index', logic: 'Tantivy or Elasticsearch indexes page features.' },
      { step: 'Two-stage query', logic: 'Page rerank → top-K → chunk vector search constrained.' },
      { step: 'Composite reranker', logic: 'Combine page-rank + chunk-rank with tunable weights per query class.' },
      { step: 'Index sync discipline', logic: 'Versioned per doc; atomic re-index on update; no partial state.' },
      { step: 'Citation chain', logic: 'chunk_id → page_id → document; explainability §48.' },
      { step: 'Drill the path', logic: 'Three drills: page index freshness, two-stage recall, citation chain.' },
    ],
    codeExample: {
      language: 'python',
      code: `# Future: services/page-index-svc/app/two_stage.py — PLANNED skeleton
from dataclasses import dataclass

@dataclass
class PageScore:
    page_id: str
    bm25: float
    freshness: float
    type_weight: float

def page_rank(query: str, page_features: dict) -> list[PageScore]:
    return sorted(
        [PageScore(pid, bm25(query, f), freshness(f), type_weight(f))
         for pid, f in page_features.items()],
        key=lambda s: s.bm25 + s.freshness + s.type_weight,
        reverse=True,
    )

def two_stage_retrieve(query: str, K_pages: int = 5,
                       K_chunks: int = 10) -> list[dict]:
    pages = page_rank(query, load_page_features())[:K_pages]
    candidate_chunks = [c for p in pages for c in chunks_of(p.page_id)]
    q_emb = embed(query)
    scored = [(c, cosine(q_emb, embedding(c))) for c in candidate_chunks]
    return sorted(scored, key=lambda x: x[1], reverse=True)[:K_chunks]`,
    },
    starStory: {
      situation: 'Chunk-level vector search occasionally misses canonical documents because chunks within them are individually weaker than scattered shorter chunks. Operators noticed citation chains pointing at non-canonical sources.',
      task: 'Design the two-stage retrieval that uses document-level features (title, type, freshness) to narrow before chunk vector search.',
      action: 'PLANNED. Reference architecture documented; service skeleton defined. Defer implementation until single-stage limitations measurably cap retrieval quality.',
      result: 'NOT YET SHIPPED. When live: latency drops (smaller chunk pool), precision improves (document priors), citation chain gains page-level identity for §48 explainability.',
    },
    interviewTraps: [
      'Single-stage retrieval as a permanent design (works to ~10K chunks; falls over with longer docs)',
      'No index versioning (page-chunk drift silently breaks retrieval)',
      'Static K (top-K must adapt to query class; "summarize the README" needs different K than "find the JWT clause")',
    ],
    finalScript: 'Page-level index turns RAG into two-stage retrieval. Page-stage uses cheap features (BM25 + title + type + freshness); chunk-stage runs vector search constrained to top-K pages. Latency, precision, and explainability all improve. NOT YET SHIPPED here. The pattern composes with: chunk-level retrieval (current), reranker (post-stage), citation guardrail (output-eval), explainability evidence (audit trail).',
  },
  {
    slug: 'vectorless-rag',
    title: '3. Vectorless RAG (graph + structured retrieval)',
    status: 'planned',
    coreConcept: 'RAG without vectors. Retrieval routes through a knowledge graph (entities + relations) and structured indexes (BM25, entity-resolution) instead of a vector index. Useful for high-recall multi-hop queries where graph traversal beats embedding similarity, and for domains where embeddings are expensive or unavailable. Often paired with vector retrieval for hybrid coverage.',
    problem: 'Vector embeddings are not always the right index. Multi-hop questions ("which JWT clause is referenced by which ADR which is implemented in which file?") require graph traversal, not similarity. Cost-sensitive deployments cannot afford embedding costs at scale. Some domains (regulatory, taxonomic) have explicit ontologies that vectors flatten.',
    whyThisApproach: 'Graph + structured retrieval gives explainability, multi-hop reasoning, and cost predictability. Each hop in the graph is auditable; each entity has a canonical identifier; queries express as graph patterns. Composes with vector retrieval — graph-only is rare; hybrid is common.',
    whenToUse: ['Multi-hop questions where graph traversal beats similarity', 'Domain with explicit ontology (legal, medical, taxonomy)', 'Cost-sensitive deployments (no embedding compute budget)', 'High-precision use cases where graph hops are auditable evidence'],
    whenNotToUse: ['Pure semantic search (vectors win for fuzzy match)', 'Domains without explicit relations (graph is sparse)', 'Latency-sensitive paths (graph traversal can be slower than vector lookup)'],
    input: 'query → entity extraction → graph pattern → traversal → matched nodes/edges',
    process: [
      'Parse query: NER + intent classifier extract entities + relations sought',
      'Construct graph pattern (e.g. JWT_CLAUSE -[REFERENCED_BY]-> ADR -[IMPLEMENTED_IN]-> FILE)',
      'Traverse graph (Neo4j Cypher, GraphDB SPARQL, or in-process)',
      'Score paths by relevance + path length + entity confidence',
      'Optional: combine with vector retrieval over node descriptions (hybrid)',
      'Return top paths as evidence with entity citations',
    ],
    output: 'Graph paths with entity citations, optionally augmented with vector-retrieved chunks.',
    flowchart: `flowchart LR
  q[Query] --> ner[NER + intent]
  ner --> pat[Graph pattern]
  pat --> g[(Knowledge graph)]
  g --> trav[Traverse paths]
  trav --> score[Score by relevance]
  score --> ans[Top paths + entity citations]
  ans -.optional.-> vec[Augment with vector chunks]`,
    sequence: `sequenceDiagram
  autonumber
  participant U as User
  participant NER as NER + intent
  participant G as Graph DB
  participant V as Vector DB (optional)
  U->>NER: query
  NER-->>U: entities + relations
  U->>G: traverse pattern
  G-->>U: paths
  alt hybrid
    U->>V: vector search over node descs
    V-->>U: chunks
  end
  U->>U: score + combine
  U-->>U: top paths`,
    alternatives: [
      { name: 'Vector-only retrieval (current)', tradeoff: 'Mature; fuzzy match; weak on multi-hop' },
      { name: 'Hybrid graph + vector', tradeoff: 'Best of both; operational complexity higher' },
      { name: 'BM25-only', tradeoff: 'Cheap; lexical only; no semantic + no relational' },
    ],
    challenges: [
      'Building + maintaining the knowledge graph (entity resolution, relation extraction)',
      'NER + intent quality on user queries',
      'Graph traversal latency at scale',
      'Schema evolution (new entity types, new relations)',
    ],
    edgeCases: [
      { case: 'Entity not in graph', solution: 'Fallback to vector retrieval; flag for graph enrichment' },
      { case: 'Multi-hop path too long', solution: 'Cap hops; rank shorter paths higher; explainability suffers past 3-4 hops' },
      { case: 'Ambiguous entity', solution: 'Entity disambiguation step before traversal; use context window for tie-break' },
    ],
    failureModes: [
      { mode: 'Graph drift from real data', detect: 'Queries return stale entities; relations point at deleted nodes', recover: 'Periodic graph re-sync from source-of-truth' },
      { mode: 'NER misclassification', detect: 'Wrong entities extracted; traversal returns irrelevant paths', recover: 'Tune NER model; add fallback to vector retrieval' },
      { mode: 'Traversal timeout', detect: 'p95 graph query latency exceeding threshold', recover: 'Limit hops + path count; cache common patterns' },
    ],
    monitoring: [
      'documind_rag_graph_traversal_latency_seconds_p95',
      'documind_rag_graph_entity_match_rate (queries with entities found)',
      'documind_rag_hybrid_fusion_ratio (graph vs vector contribution)',
    ],
    testing: [
      'drill_rag_graph_traversal (PLANNED — multi-hop pattern returns expected paths)',
      'drill_rag_entity_resolution (PLANNED — disambiguation correctness)',
      'drill_rag_hybrid_fusion (PLANNED — graph + vector signals composed)',
    ],
    security: [
      'Per-tenant graph (no cross-tenant edge traversal)',
      'NER may surface PII — redaction on extraction',
      'Graph audit log for explainability per §48',
    ],
    scaling: [
      '10x: single Neo4j or in-process graph; sub-100ms traversal',
      '100x: sharded graph (Neptune, GraphDB Enterprise); per-tenant subgraphs',
      'Cost driver: graph query cost (Neo4j commercial); shard locality',
    ],
    maturity: {
      mvp: 'Vector-only retrieval (current)',
      production: 'PLANNED — vectorless / hybrid for multi-hop queries',
      enterprise: 'Hybrid graph + vector + reranker + per-domain entity ontology + audit trail per traversal',
    },
    limitations: [
      'NOT YET SHIPPED — current retrieval is vector-only',
      'No knowledge graph constructed yet for project artifacts',
      'No drill catalogs yet for graph traversal',
    ],
    projectFit: [
      'docs/architecture/adr/008-transport-breakers-vector-graph.md — graph transport contract',
      'services/inference-svc/* — current vector-only retrieval (graph slot exists)',
      '/admin/rag/deep#hybrid-retrieval — hybrid surface',
      'Future: services/graph-svc/ + drill_rag_graph_*.py',
    ],
    interviewLine: 'Vectorless RAG = graph + structured retrieval, no embeddings. Useful for multi-hop questions where graph traversal beats similarity, for cost-sensitive deployments, and for domains with explicit ontologies. Often hybrid with vector retrieval. NOT YET SHIPPED here — current retrieval is vector-only.',
    implementationSteps: [
      { step: 'Knowledge graph build', logic: 'Entity resolution + relation extraction from project artifacts (ADRs, drills, docs).' },
      { step: 'NER + intent classifier', logic: 'Map user query to entity-pattern; e.g. "JWT clause" → JWT_CLAUSE entity.' },
      { step: 'Graph pattern construction', logic: 'Cypher/SPARQL pattern from extracted entities + relations.' },
      { step: 'Traversal + scoring', logic: 'Limit hops; score by relevance + path length + entity confidence.' },
      { step: 'Hybrid fusion', logic: 'Combine graph-paths + vector-chunks via reranker per /admin/rag/deep#post-retrieval.' },
      { step: 'Audit trail per traversal', logic: 'Every hop logged with entity_id; explainability §48.' },
      { step: 'Drill the path', logic: 'Three drills: traversal, entity resolution, hybrid fusion.' },
    ],
    codeExample: {
      language: 'python',
      code: `# Future: services/graph-svc/app/traverse.py — PLANNED skeleton
from neo4j import GraphDatabase

def graph_query(pattern: str, params: dict, max_hops: int = 3) -> list[dict]:
    """Traverse the knowledge graph along a pattern.

    Example pattern:
        MATCH (j:JwtClause)-[:REFERENCED_BY]->(a:ADR)-[:IMPLEMENTED_IN]->(f:File)
        WHERE j.name = $clause_name
        RETURN j, a, f
        LIMIT $max_paths
    """
    with GraphDatabase.driver(URL, auth=AUTH).session() as s:
        result = s.run(pattern, **params)
        return [{"path": r.values(), "score": score_path(r)} for r in result]

def hybrid_retrieve(query: str) -> list[dict]:
    entities = ner(query)
    pattern = build_pattern(entities)
    graph_paths = graph_query(pattern, {"clause_name": entities.get("clause")})
    vector_chunks = vector_search(query, top_k=10)
    return rerank_fusion(graph_paths, vector_chunks)`,
    },
    starStory: {
      situation: 'Multi-hop questions ("which ADR implements which JWT clause in which file?") were poorly served by chunk-level vector search. Each hop required a separate query; chains across files were lost.',
      task: 'Design vectorless / hybrid RAG over a project knowledge graph; combine with vector retrieval for fuzzy queries.',
      action: 'PLANNED. ADR-008 already specifies graph transport breaker (foundation). Service skeleton + Cypher pattern library deferred until multi-hop usage justifies build.',
      result: 'NOT YET SHIPPED. When live: multi-hop queries answered via graph traversal; hybrid fusion combines graph paths + vector chunks; per-traversal audit trail enables §48 explainability.',
    },
    interviewTraps: [
      'Saying "vectors are universal" (multi-hop + ontological domains break vectors)',
      'Treating graph + vector as alternatives (hybrid is the production answer)',
      'Skipping audit trail (graph traversal without per-hop logging breaks explainability)',
    ],
    finalScript: 'Vectorless RAG is graph + structured retrieval. Strong on multi-hop, ontological domains, and cost-sensitive paths. Composes with vector retrieval as hybrid (production answer for most projects). NOT YET SHIPPED here. ADR-008 lays the transport-breaker foundation; service skeleton + drills are next iteration when usage justifies it.',
  },
];

export default function ScalingPatternsDeepPage() {
  return (
    <>
      <div className="page-header">
        <div className="page-header-copy">
          <h1 className="section-title">Scaling patterns deep dive</h1>
          <p className="page-subtitle">
            Three surfaces — load balancing (Phase-2 with k8s migration),
            page-level RAG index (planned two-stage retrieval), and
            vectorless / hybrid RAG (planned graph traversal) — explained
            through the universal 20-dimension framework.
          </p>
        </div>
      </div>
      <div className="card">
        <strong>Topics ({TOPICS.length})</strong>
        <ul style={{ marginTop: 8, paddingLeft: 18 }}>
          {TOPICS.map((t) => (
            <li key={t.slug}>
              <a href={`#${t.slug}`} style={{ color: '#1e3a8a' }}>{t.title}</a>
            </li>
          ))}
        </ul>
      </div>
      {TOPICS.map((t) => <UniversalDeepDive key={t.slug} t={t} />)}
      <DeepDiveCrossRefs
        refs={[
          { href: '/admin/rag/deep#hybrid-retrieval', label: 'RAG hybrid retrieval', why: 'page-index + vectorless RAG are extensions of the hybrid retrieval surface; this page covers the pre-retrieval layer' },
          { href: '/admin/service-mesh/deep', label: 'Service mesh + Istio', why: 'load balancing relies on mesh outlier detection + DestinationRule; this page details the LB tier' },
          { href: '/admin/api-gateway/deep', label: 'API gateway', why: 'edge LB sits in front of the gateway tier; both compose for the full ingress story' },
          { href: '/admin/explainability/deep', label: 'Explainability evidence', why: 'graph traversal audit trail + page-citation chain are §48 explainability requirements' },
          { href: '/admin/checklist/deep#governance-ops-checklist', label: 'Governance gate', why: 'no fallback / no audit on RAG retrieval = release blocked per §38 hard-stop' },
        ]}
      />
    </>
  );
}
