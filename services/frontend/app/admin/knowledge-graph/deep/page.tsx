'use client';

import DeepDiveCrossRefs from '../../../../components/DeepDiveCrossRefs';
import UniversalDeepDive, { type Topic } from '../../../../components/UniversalDeepDive';

const TOPICS: Topic[] = [
  {
    slug: 'ontology-design',
    title: '1. Ontology design (entities + relations + canonical IDs)',
    status: 'planned',
    coreConcept: 'An ontology is a typed schema for a knowledge graph: which entities exist, which relations connect them, what each entity\'s canonical identifier is. Designing the ontology BEFORE building the graph is the difference between a queryable knowledge surface and a pile of unjoinable nodes. For this codebase the ontology covers project artifacts: ADRs, drills, services, agents, prompts, tenants — and how they reference each other.',
    problem: 'Knowledge graphs without ontology design accrete arbitrary node + edge types until queries become impossible. "What ADR is implemented in which file by which agent role?" requires consistent IDs across ADR.id, file.path, AgentRoleSpec.role_id. Ad-hoc graph construction loses these constraints; the graph becomes a junk drawer.',
    whyThisApproach: 'Define the ontology as a schema (entity types + relation types + canonical IDs + cardinality constraints) before any graph data lands. Document in docs/architecture/ontology/. Per global §39 RAG architecture standards: "Define ontology BEFORE building graph". Schema versioning + relation cardinality constraints prevent drift; canonical IDs enable cross-graph joins.',
    whenToUse: ['Multi-hop queries across project artifacts', 'Compliance-grade knowledge bases (regulatory taxonomies)', 'Domain with explicit relations (legal, medical, codebase artifacts)', 'When vector retrieval misses canonical-document signal'],
    whenNotToUse: ['Pure semantic search (vectors win for fuzzy match)', 'Domains without explicit relations', 'Throwaway exploratory work where ontology design cost is unjustified'],
    input: 'domain inventory + entity types + relation types + canonical ID rules',
    process: [
      'Inventory entity types: ADR, Drill, Service, Agent, Prompt, Tenant',
      'For each entity, define canonical ID rule (ADR.id = "ADR-NNN"; Service.name = directory name)',
      'Inventory relation types: REFERENCED_BY, IMPLEMENTED_BY, AUDITED_BY, OWNED_BY',
      'Define cardinality + direction (1:N, N:M; directed)',
      'Version the ontology (v1 → v2 with deprecation notes)',
      'Validate sample queries against the schema before any data load',
    ],
    output: 'Ontology schema document + per-entity ID rules + relation catalog.',
    flowchart: `flowchart LR
  inv[Domain inventory] --> ent[Entity types]
  inv --> rel[Relation types]
  ent --> id[Canonical ID rules]
  rel --> card[Cardinality + direction]
  id --> sch[Ontology schema]
  card --> sch
  sch --> v[Versioned + deprecation discipline]
  v --> q[Sample-query validation]`,
    sequence: `sequenceDiagram
  autonumber
  participant D as Domain owner
  participant O as Ontology designer
  participant S as Schema doc
  participant V as Validator
  D->>O: list real-world entities + relations
  O->>O: design entity types + ID rules
  O->>S: write schema vN
  D->>S: list sample queries
  S->>V: validate queries against schema
  alt schema covers all queries
    V-->>O: APPROVE
    O->>O: freeze schema vN
  else schema misses
    V-->>O: missing entity / relation X
    O->>O: extend; bump to vN+1
  end`,
    alternatives: [
      { name: 'Build graph first, schema later', tradeoff: 'Anti-pattern; junk drawer; queries impossible' },
      { name: 'No ontology — pure RDF triples', tradeoff: 'Maximum flexibility; loses join consistency; harder to query' },
      { name: 'Use existing standard ontology (Schema.org / FOAF)', tradeoff: 'Reuses community work; may not match domain; bridge mappings needed' },
    ],
    challenges: [
      'Identifying canonical IDs (multiple natural keys per entity)',
      'Schema versioning + deprecation without breaking existing queries',
      'Cardinality constraints (1:N vs N:M; directed vs undirected)',
      'Cross-domain entity unification (same ADR known by N projects)',
    ],
    edgeCases: [
      { case: 'Entity has multiple natural IDs', solution: 'Pick one canonical; map others as alias relations' },
      { case: 'Relation crosses tenant boundary', solution: 'Tenant-scoped relations; separate cross-tenant relation type if needed' },
      { case: 'Schema evolution adds entity type used by old data', solution: 'Backfill on migration; default to "unknown" type initially' },
    ],
    failureModes: [
      { mode: 'Schema drift from data', detect: 'Graph contains entity types not in schema vN', recover: 'Audit data; either bump schema or clean data; never both at once' },
      { mode: 'Canonical ID collision', detect: 'Two entities with same ID', recover: 'Add disambiguator suffix; document in schema; backfill' },
      { mode: 'Relation cardinality violated', detect: 'N:1 relation has multiple values for one entity', recover: 'Validate at insert; reject violation' },
    ],
    monitoring: [
      'documind_ontology_schema_version (current)',
      'documind_graph_entity_count{entity_type}',
      'documind_graph_relation_count{relation_type}',
      'documind_ontology_drift_total (entities with type not in schema)',
    ],
    testing: [
      'drill_ontology_schema_versioning (PLANNED — schema vs data consistency)',
      'drill_ontology_canonical_ids (PLANNED — no ID collisions)',
      'drill_ontology_cardinality (PLANNED — relation cardinality enforced at insert)',
    ],
    security: [
      'Per-tenant ontology subgraph (no cross-tenant relation traversal)',
      'Schema is public; data may have access controls',
      'Ontology evolution is audited (every version committed to repo)',
    ],
    scaling: [
      '10x: in-process schema validator; sub-ms per insert',
      '100x: schema registry service (per /admin/output-eval prompt-version pattern)',
      'Cost driver: schema versioning storage + deprecated-entity cleanup',
    ],
    maturity: {
      mvp: 'No ontology — ad-hoc graph (not built yet)',
      production: 'PLANNED — versioned schema + canonical IDs + cardinality constraints',
      enterprise: 'Per-tenant ontology variants + cross-tenant alias relations + automated drift detection',
    },
    limitations: [
      'NOT YET SHIPPED — ontology design is roadmap; no graph constructed yet',
      'No drill catalogs yet for ontology validation',
      'No schema-registry service yet',
    ],
    projectFit: [
      'docs/architecture/ — future docs/architecture/ontology/ schema docs',
      'services/agent-orchestrator-svc/app/agent_registry.py — entity-of-the-graph (Agent, Role)',
      'docs/architecture/adr/ — ADR entities for the graph',
      'mcp/tests/drill_*.py — Drill entities with audit relations',
    ],
    interviewLine: 'Ontology design is the schema for a knowledge graph: entity types + relation types + canonical IDs + cardinality. Designed BEFORE building the graph per global §39. NOT YET SHIPPED in this codebase; the inventory (ADRs, drills, services, agents) is canonical and ready to model.',
    implementationSteps: [
      { step: 'Domain inventory', logic: 'List entity types + their natural keys (ADR.id, Service.name, AgentRoleSpec.role_id, Drill.path).' },
      { step: 'Canonical ID rules', logic: 'Pick one ID per entity type; document; alias the others.' },
      { step: 'Relation catalog', logic: 'Type + cardinality + direction (e.g. ADR -[IMPLEMENTED_BY{cardinality:N}]-> File).' },
      { step: 'Schema versioning', logic: 'v1 frozen on commit; vN bumps with deprecation notes; no schema-data drift.' },
      { step: 'Sample-query validation', logic: 'Define 10 representative queries; validate each maps cleanly to schema.' },
      { step: 'Drill the schema', logic: 'Three drills: schema-vs-data consistency, canonical-ID uniqueness, cardinality enforcement.' },
      { step: 'Versioned docs', logic: 'docs/architecture/ontology/v1.md is the canonical reference.' },
    ],
    codeExample: {
      language: 'yaml',
      code: `# Future: docs/architecture/ontology/v1.yaml — PLANNED schema
ontology:
  version: v1
  entities:
    - name: ADR
      canonical_id: id  # "ADR-022"
      properties:
        - title: string
        - status: enum [Proposed, Accepted, Superseded]
    - name: Drill
      canonical_id: path  # "mcp/tests/drill_<topic>.py"
      properties:
        - resources: list[string]
        - status: enum [readonly, write]
    - name: Service
      canonical_id: name  # directory name
    - name: Agent
      canonical_id: role_id
      properties:
        - prompt_template_path: string
        - tool_grants: set[string]
  relations:
    - name: IMPLEMENTED_BY
      from: ADR
      to: File
      cardinality: 1:N
    - name: AUDITED_BY
      from: Service
      to: Drill
      cardinality: 1:N
    - name: USES
      from: Agent
      to: Tool
      cardinality: N:M`,
    },
    starStory: {
      situation: 'Plans for vectorless / hybrid RAG (per /admin/scaling-patterns) require a knowledge graph. The graph requires an ontology. No ontology exists yet; building the graph first would create a junk drawer.',
      task: 'Design the ontology before any graph data lands; cover the project\'s artifact types (ADR, drill, service, agent) with canonical IDs + relations.',
      action: 'PLANNED. Inventory complete; schema doc + drill catalog deferred until graph build is prioritized. ADR-008 transport-breaker provides the future graph transport.',
      result: 'NOT YET SHIPPED. When designed: queryable knowledge graph with consistent IDs + cardinality enforcement; powers vectorless RAG + multi-hop project queries.',
    },
    interviewTraps: [
      'Building graph before ontology (junk drawer; unrecoverable)',
      'No canonical IDs (cross-graph joins impossible)',
      'No cardinality enforcement (relation explosion)',
    ],
    finalScript: 'Ontology design is the schema for a knowledge graph: entities + relations + canonical IDs + cardinality. Per global §39, designed BEFORE the graph; without it, the graph is a junk drawer. NOT YET SHIPPED here. Inventory of project artifacts (ADRs, drills, services, agents) is canonical and ready to model when graph build is prioritized.',
  },
  {
    slug: 'graph-construction',
    title: '2. Graph construction (Neo4j + entity resolution + maintenance)',
    status: 'planned',
    coreConcept: 'Constructing a knowledge graph from project artifacts: ingest entities (ADRs, drills, services), extract relations from source-of-truth (commit history, code references, ADR cross-links), persist in Neo4j (or equivalent), and maintain via periodic re-sync. ADR-008 transport-breaker is the future stable contract for graph queries during partial graph outages.',
    problem: 'A knowledge graph without a maintenance story drifts: the graph snapshots reality at one moment, then reality moves on (new ADRs land, services rename, drills move). Stale graph + queries based on stale data = wrong answers. Maintenance discipline is the difference between a graph that informs and one that misleads.',
    whyThisApproach: 'Source-of-truth ingestion: every entity comes from a versioned source (git for code, repo for docs, postgres for runtime state). Entity resolution unifies aliases (file moved, ADR superseded). Periodic re-sync keeps graph fresh. Transport-breaker (ADR-008) protects callers when graph DB is slow / unavailable. Hybrid with vector retrieval per /admin/scaling-patterns#vectorless-rag.',
    whenToUse: ['Multi-hop queries over project artifacts', 'AIOps incident summarization (cross-artifact correlation)', 'Onboarding (new engineer queries the graph to learn)', 'Audit (trace ADR → implementation → drill)'],
    whenNotToUse: ['Pure semantic queries (vectors win)', 'Cost-sensitive paths (graph DB ops cost)', 'Sub-ms latency requirements (graph traversal can\'t guarantee)'],
    input: 'source artifacts (git history, ADRs, drills, services) + entity-resolution rules + ontology schema',
    process: [
      'Periodic re-sync job scans sources (git log + ADR files + service directories + drill catalog)',
      'Extract entities per ontology rules (canonical IDs)',
      'Extract relations from source signals (commit body parse + ADR cross-link + code references)',
      'Entity resolution: unify aliases (renamed file → same entity)',
      'Upsert into Neo4j; track sync version',
      'Validate against ontology schema; flag drift',
      'Surface graph queries via /admin/agentic + /admin/forensics',
    ],
    output: 'Refreshed knowledge graph + drift report.',
    flowchart: `flowchart LR
  src[Source artifacts] --> ext[Entity extractor]
  src --> rel[Relation extractor]
  ext --> er[Entity resolution]
  er --> upsert[Neo4j upsert]
  rel --> upsert
  upsert --> val[Schema validate]
  val --> graph[(Knowledge graph)]
  graph --> q[Operator queries]
  graph -.transport breaker.-> q`,
    sequence: `sequenceDiagram
  autonumber
  participant Sync as Sync job
  participant Src as Sources
  participant ER as Entity resolution
  participant Neo as Neo4j
  participant V as Schema validator
  participant Op as Operator
  Sync->>Src: read git + ADRs + drills + services
  Sync->>ER: candidate entities
  ER->>ER: unify aliases (rename, supersede)
  ER->>Neo: UPSERT entities + relations
  Neo->>V: validate against ontology vN
  V-->>Sync: drift report
  Op->>Neo: query (multi-hop)
  Neo-->>Op: paths + entities
  alt Neo4j slow
    Op-.transport breaker open.->Op
  end`,
    alternatives: [
      { name: 'In-process graph (NetworkX)', tradeoff: 'Cheapest; no persistence; lost on restart' },
      { name: 'Neo4j (chosen path)', tradeoff: 'Mature; query language; commercial pricing past free tier' },
      { name: 'PostgreSQL + recursive CTE', tradeoff: 'Reuses existing PG; weaker query language; awkward for deep traversal' },
    ],
    challenges: [
      'Source-of-truth selection per entity (git for code; PG for runtime)',
      'Entity resolution under rename / merge (commit detects rename; needs alias)',
      'Re-sync cadence vs freshness vs cost',
      'Schema evolution mid-sync (atomic upgrade; never partial)',
    ],
    edgeCases: [
      { case: 'File renamed mid-sync', solution: 'Git rename detection; alias old path → canonical entity' },
      { case: 'ADR superseded', solution: 'Add SUPERSEDED_BY relation; old ADR keeps entity; queries respect status' },
      { case: 'Service deleted', solution: 'Mark entity as deleted; preserve relations for audit; queries filter by active' },
      { case: 'Graph DB unavailable', solution: 'ADR-008 transport breaker fast-fails; UI shows degraded retrieval banner' },
    ],
    failureModes: [
      { mode: 'Sync stuck mid-flight', detect: 'sync_version stuck; new commits not represented', recover: 'Manual sync trigger; investigate; rebuild from scratch if needed' },
      { mode: 'Entity resolution wrong (false unification)', detect: 'Two distinct entities collapsed', recover: 'Add disambiguator; rebuild affected entities' },
      { mode: 'Schema drift detected', detect: 'documind_ontology_drift_total > 0', recover: 'Either bump schema or clean data; never both at once per ADR-018' },
    ],
    monitoring: [
      'documind_graph_sync_lag_seconds (last successful sync)',
      'documind_graph_entity_resolution_total{outcome}',
      'documind_graph_query_latency_seconds_p95',
      'documind_graph_transport_breaker_state (per ADR-008)',
    ],
    testing: [
      'drill_graph_sync_freshness (PLANNED — sync_lag below SLO)',
      'drill_graph_entity_resolution (PLANNED — rename detection works)',
      'drill_graph_transport_breaker (PLANNED — degraded retrieval contract per ADR-008)',
    ],
    security: [
      'Per-tenant subgraph isolation (no cross-tenant traversal)',
      'Sync job runs with read-only credentials on sources',
      'Audit row per entity update (who changed, when, why)',
      'Graph DB access limited to retrieval-svc + sync-job',
    ],
    scaling: [
      '10x: single Neo4j instance; sub-100ms multi-hop queries',
      '100x: Neo4j cluster with read replicas; per-tenant subgraphs',
      'Cost driver: Neo4j commercial license + sync compute; tune re-sync cadence',
    ],
    maturity: {
      mvp: 'No graph (current state)',
      production: 'PLANNED — Neo4j + scheduled sync + entity resolution + transport breaker',
      enterprise: 'Multi-region graph + per-tenant subgraphs + auto-tuned sync cadence + full provenance trail',
    },
    limitations: [
      'NOT YET SHIPPED — graph construction is roadmap',
      'ADR-008 transport breaker exists for vector + graph; graph half not yet active',
      'No drill catalogs yet for graph maintenance',
    ],
    projectFit: [
      'docs/architecture/adr/008-transport-breakers-vector-graph.md — graph transport contract',
      '/admin/scaling-patterns/deep#vectorless-rag — hybrid retrieval that consumes the graph',
      '/admin/breakers/deep — transport breaker pattern',
      'Future: services/graph-svc/ + services/graph-sync-job/ + drill_graph_*.py',
    ],
    interviewLine: 'Graph construction needs an ontology + entity resolution + sync discipline + transport breaker. Source-of-truth ingestion (git + ADRs + drills + services) keeps the graph fresh; entity resolution handles renames + supersedes; ADR-008 transport breaker protects callers under graph degradation. NOT YET SHIPPED here.',
    implementationSteps: [
      { step: 'Source-of-truth list', logic: 'Per entity type: git for code, repo for docs, PG for runtime state, file system for drills.' },
      { step: 'Entity extractor', logic: 'Read source; emit (entity_type, canonical_id, properties).' },
      { step: 'Relation extractor', logic: 'Parse commit bodies, ADR cross-links, code references; emit (from, type, to).' },
      { step: 'Entity resolution', logic: 'Detect renames (git --follow); merge aliases; track in alias relation.' },
      { step: 'Sync job', logic: 'Periodic full + incremental; tracked via sync_version.' },
      { step: 'Schema validator', logic: 'Every upsert validated against ontology vN; reject drift.' },
      { step: 'Transport breaker', logic: 'ADR-008 — graph DB slow → fast-fail; degraded retrieval banner.' },
      { step: 'Drill the path', logic: 'Three drills: sync freshness, entity resolution, transport breaker.' },
    ],
    codeExample: {
      language: 'python',
      code: `# Future: services/graph-sync-job/app/sync.py — PLANNED skeleton
from neo4j import GraphDatabase

def sync_adrs(driver):
    """Read ADRs from docs/architecture/adr/; upsert as ADR entities.
    Detect supersedes via cross-link parsing."""
    with driver.session() as s:
        for adr in scan_adr_dir():
            s.run("""
                MERGE (a:ADR {id: $id})
                SET a.title = $title, a.status = $status
            """, id=adr.id, title=adr.title, status=adr.status)
            for sup_id in adr.supersedes:
                s.run("""
                    MATCH (a:ADR {id: $id}), (s:ADR {id: $sup_id})
                    MERGE (a)-[:SUPERSEDES]->(s)
                """, id=adr.id, sup_id=sup_id)

def sync_drills(driver):
    """Read drills from mcp/tests/drill_*.py; emit AUDITED_BY relations."""
    with driver.session() as s:
        for drill in scan_drill_catalog():
            s.run("""
                MERGE (d:Drill {path: $path})
                SET d.resources = $resources, d.status = $status
            """, path=drill.path, resources=list(drill.resources), status=drill.status)
            for service in drill.audits:
                s.run("""
                    MATCH (d:Drill {path: $path}), (s:Service {name: $svc})
                    MERGE (s)-[:AUDITED_BY]->(d)
                """, path=drill.path, svc=service)`,
    },
    starStory: {
      situation: 'Multi-hop questions ("which ADR is implemented in which service by which agent?") require a knowledge graph. None exists. Building one without sync discipline + entity resolution would create a stale junk drawer.',
      task: 'Design graph construction with source-of-truth ingestion + entity resolution + sync cadence + transport breaker (ADR-008).',
      action: 'PLANNED. Skeleton + drill catalog deferred until graph build is prioritized. ADR-008 transport-breaker contract already locked for the day graph activates.',
      result: 'NOT YET SHIPPED. When live: queryable project knowledge graph; AIOps incident correlation; new-engineer graph-walk onboarding; multi-hop audit traces.',
    },
    interviewTraps: [
      'No re-sync (graph snapshots reality once; drifts forever)',
      'Naive entity resolution (renames create duplicate entities; queries miss data)',
      'No transport breaker (graph DB outage cascades to all retrieval)',
    ],
    finalScript: 'Graph construction is source-of-truth sync + entity resolution + schema validation + transport breaker. Ontology before graph (per topic 1). Source for every entity type. Resolution under renames. Periodic re-sync. ADR-008 protects callers under partial outage. NOT YET SHIPPED here; ADR-008 + ontology design are the prerequisites; the build is one focused effort away.',
  },
];

export default function KnowledgeGraphDeepPage() {
  return (
    <>
      <div className="page-header">
        <div className="page-header-copy">
          <h1 className="section-title">Knowledge graph deep dive</h1>
          <p className="page-subtitle">
            Two surfaces — ontology design (entities + relations + canonical
            IDs) and graph construction (Neo4j + entity resolution + sync +
            transport breaker per ADR-008) — explained through the universal
            20-dimension framework. Both PLANNED.
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
          { href: '/admin/scaling-patterns/deep#vectorless-rag', label: 'Vectorless RAG', why: 'graph is the substrate vectorless RAG queries; this page details the construction + maintenance' },
          { href: '/admin/breakers/deep', label: 'Circuit breakers', why: 'ADR-008 transport breaker for graph queries is one of the per-transport breakers; this page details the graph half' },
          { href: '/admin/explainability/deep', label: 'Explainability evidence', why: 'graph traversal audit trail is §48 explainability; entity-IDs are the citation chain' },
          { href: '/admin/agent-registry/deep', label: 'Agent registry', why: 'Agent + Role entities are first-class in the ontology; registry is canonical source' },
          { href: '/admin/checklist/deep#governance-ops-checklist', label: 'Governance gate', why: 'graph without ontology + sync = junk drawer; release blocked per §38 hallucination guardrail' },
        ]}
      />
    </>
  );
}
