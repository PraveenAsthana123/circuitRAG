# Job Scheduling And Graph Ontology

This document covers two important backend and RAG topics:

- job scheduling
- graph ontology

These often meet in real systems because scheduled jobs are how graph extraction, graph refresh, re-embedding, replay, evaluation, and maintenance tasks are actually executed over time.

## 1. Job Scheduling

Job scheduling is the system by which work is queued, ordered, delayed, retried, partitioned, and executed by workers.

It is not only about cron.
It is about deciding:

- what work should run
- when it should run
- who should run it
- how many jobs may run at once
- what happens when jobs fail

## 2. Core Scheduling Models

### Cron scheduling

Use when work should run on a fixed time schedule.

Examples:

- nightly re-embedding
- hourly graph refresh
- daily drift evaluation
- periodic cleanup

### Interval scheduling

Use when work should run every fixed duration relative to completion or last run.

Examples:

- poll every 30 seconds
- refresh every 10 minutes
- sync every hour

### Event-driven scheduling

Use when work should run because something happened.

Examples:

- document uploaded
- draft created
- policy changed
- graph entity extracted

### Delayed jobs

Use when work should run later, not immediately.

Examples:

- retry after backoff
- replay after cooldown
- deferred cleanup

## 3. Important Scheduling Topics

- retry scheduling
- backoff strategy
- priority queues
- worker pools
- concurrency limits
- queue partitioning
- tenant-aware scheduling
- idempotent job execution
- dead-letter queues
- stuck-job detection
- lease or claim timeout
- exactly-once vs at-least-once tradeoffs
- dependency-aware scheduling
- batch scheduling
- scheduling observability

## 4. Why Scheduling Matters

Weak scheduling design causes:

- duplicate work
- starvation
- queue backlog
- retry storms
- hidden stuck jobs
- cross-tenant unfairness
- high operational noise

Strong scheduling design gives:

- fairness
- bounded concurrency
- visible backlog
- safe retry behavior
- controllable recovery

## 5. Idempotency And Scheduling

If a job can be retried, restarted, duplicated, or replayed, idempotency becomes critical.

Examples:

- replaying a draft
- re-running graph extraction
- regenerating embeddings
- republishing an event

Without idempotency or durable state guards, scheduling failures become correctness failures.

## 6. Priority And Fairness

Schedulers often need to balance:

- urgent work versus normal work
- one tenant versus many tenants
- short tasks versus long tasks
- user-facing recovery versus background maintenance

This is where:

- priority queues
- per-tenant partitioning
- concurrency caps
- queue aging

become important.

## 7. Scheduling Failure Modes

Common failures include:

- job stuck in queued state
- worker crash after partial completion
- repeated retry without progress
- poisoned message or bad payload
- one hot tenant starving everyone else
- long jobs blocking short jobs
- silent dead-letter growth

These are operational design problems, not only coding problems.

## 8. Scheduling Observability

Useful scheduling metrics include:

- queue depth
- oldest queued age
- success rate
- failure rate
- retry count
- dead-letter count
- worker busy/idle ratio
- tenant backlog distribution
- time-to-completion

Without these, a scheduler is mostly invisible until it hurts production.

## 9. Graph Ontology

A graph ontology defines the meaning of the graph:

- what node types exist
- what edge types exist
- what relationships are legal
- what properties matter
- how entities are normalized
- how graph retrieval should interpret the data

An ontology is not just a graph schema.
It is the semantic model behind the graph.

## 10. Taxonomy Vs Ontology

### Taxonomy

A taxonomy is usually a classification hierarchy.

Examples:

- policy -> HR policy -> leave policy
- system -> service -> worker

### Ontology

An ontology goes further and defines:

- entity classes
- relation meaning
- allowed relationships
- property semantics
- identity rules

Ontology is more powerful and more demanding than taxonomy.

## 11. Core Ontology Topics

- ontology design
- entity types
- relation types
- schema evolution
- canonical node identity
- alias resolution
- entity normalization
- edge direction semantics
- edge confidence and provenance
- document-to-entity linking
- tenant-aware graph schema
- temporal edges and historical graph
- ontology validation
- ontology drift
- graph explainability
- graph retrieval mapping

## 12. Why Ontology Matters

Without a clear ontology, graph systems become messy quickly:

- duplicate entities
- vague edges
- unclear traversal semantics
- poor explainability
- weak retrieval quality
- hard-to-maintain extraction logic

Strong ontology design improves:

- graph consistency
- multi-hop retrieval quality
- explainability
- governance
- interoperability across pipelines

## 13. Canonical Identity

One of the most important ontology concerns is:

when are two nodes actually the same entity?

Examples:

- `HR`
- `Human Resources`
- `hr-department`

These may need to normalize to one canonical entity depending on the ontology rules.

This is where:

- alias resolution
- normalization
- identity keys
- provenance tracking

become essential.

## 14. Edge Semantics

Edges need meaning, not just existence.

Examples:

- `OWNS`
- `APPROVES`
- `DEPENDS_ON`
- `MENTIONS`
- `REPORTS_TO`

Questions that matter:

- is direction important?
- is the edge temporal?
- is the edge inferred or explicit?
- what confidence or provenance supports the edge?

## 15. Ontology Evolution

Ontologies change over time.

Examples:

- new entity types
- split relation types
- improved normalization rules
- different provenance requirements

This creates migration questions:

- how are old nodes handled?
- how do extraction jobs update existing graph state?
- how do retrieval paths handle mixed ontology versions?

## 16. Graph Explainability

One major value of graph-based retrieval is explainability.

A good system should often be able to say:

- which entities were traversed
- which relations connected them
- which documents or events created those edges
- why this graph path mattered

This matters especially in enterprise and governance-heavy systems.

## 17. Job Scheduling And Ontology Together

These topics connect directly in real systems.

Examples:

- scheduled graph refresh job
- scheduled re-embedding after ontology change
- event-driven entity extraction after document upload
- delayed retry of failed graph extraction
- tenant-scoped graph build queues
- ontology version migration job

A graph system is only as healthy as the jobs that maintain it.

## 18. Good Combined Scenarios

- scheduled re-embedding job
- scheduled graph refresh job
- ontology update requiring re-extraction
- delayed retry of failed graph extraction
- priority scheduling for urgent replay or ingestion jobs
- tenant-scoped worker queues for graph-building tasks
- historical ontology version versus current ontology version
- graph traversal using ontology-constrained relations

## 19. Common Failure Patterns

- cron jobs overlap and duplicate work
- retries create duplicate side effects
- one tenant dominates worker capacity
- graph extraction uses stale ontology definitions
- alias resolution merges entities incorrectly
- ontology changes without migration plan
- graph edges lack provenance and cannot be trusted
- scheduling metrics are missing so backlog is discovered too late

## 20. Senior-Level Questions

A strong engineer asks:

- what scheduling model actually fits this work?
- what makes this job safe to retry?
- how is tenant fairness enforced?
- what tells us this worker queue is unhealthy?
- what exactly does this graph edge mean?
- how are entities normalized and versioned?
- can the graph explain the answer path?
- what job updates the graph when the ontology changes?

## 21. Best Next Topics

Natural follow-up topics are:

- worker design and queue orchestration
- retry and idempotency strategy
- graph extraction pipeline design
- hybrid graph + vector retrieval
- ontology validation and migration
- scheduler observability and SLOs

---

## 22. How Scheduling And Ontology Map To DocuMind Today

### Scheduling — already covered

| Scenario | Where in repo | Drill |
| --- | --- | --- |
| Interval scheduling (autonomous worker loop) | `services/inference-svc/app/workers/draft_replay.py` (`asyncio.wait_for` + interval) | `drill_audit_actor_type` step 4, `drill_worker_metrics`, `drill_worker_auto_reject` |
| Per-draft backoff | `_per_draft_backoff_s` in `DraftReplayWorker` | `drill_worker_auto_reject` honours it |
| Idempotent job execution | `mcp/idempotency.py` (Postgres-backed, `IdempotencyStore` protocol) | `drill_idempotency_durable` (6 steps including durability proof) |
| Stuck-job detection (terminal state) | `auto_reject_threshold` after N consecutive failures | `drill_worker_auto_reject` |
| Concurrency limits | `MAX_CONCURRENT_DRILLS` semaphore in `mcp/server_drills.py` | `drill_runner_hardening` step 5 |
| At-least-once with idempotent consumer | `Idempotency-Key` header → fingerprint check | `drill_idempotency_durable` step 4 (conflict detection) |
| Cron / interval (host-level) | `scripts/scheduled_kaggle_ingest.sh` + cron line in header | run+verified live (commit `2839764`) |
| Dead-letter (terminal) | Auto-rejected drafts → `status='rejected'` (worker stops) | `drill_worker_auto_reject` step 4 |
| Per-tenant sweep | `DOCUMIND_REPLAY_WORKER_TENANTS` (CSV of tenant UUIDs) | covered in lifespan wiring |
| Job-level metrics | `documind_draft_replay_total{namespace, outcome}` | `drill_worker_metrics` |
| Subprocess kill on timeout | `start_new_session=True` + `killpg(SIGKILL)` | `drill_runner_hardening` step 4 |

### Scheduling — gaps

| Gap | Severity |
| --- | --- |
| Priority queues | not implemented — all drafts equal | low |
| Tenant fairness round-robin | iterates `tenants` list in order; one slow tenant blocks others | medium |
| Lease / claim timeout | not used (single worker per service today) | low |
| Distributed scheduler / multi-replica coordination | not implemented (in-process worker only) | high if horizontal scaling lands |
| Backlog age gauge (oldest pending draft) | `documind_draft_pending_age_seconds` was started + abandoned mid-iteration | medium |
| Scheduler SLO (e.g. "p95 sweep < 5s") | no SLI / SLO definitions | medium |
| Backoff strategy | linear (`per_draft_backoff_s`); no exponential / jitter | low |

### Ontology / Graph — already covered

| Scenario | Where in repo |
| --- | --- |
| Tenant-isolated graph data | `app/services/graph_searcher.py` Cypher binds `$tid` on every match |
| Hybrid graph + vector retrieval | `hybrid_retriever.py` runs both then RRF-fuses |
| Document → entity → chunk relation | `Document HAS_CHUNK Chunk` + `Entity MENTIONS Chunk` (per the graph_searcher Cypher) |

### Ontology / Graph — gaps

| Gap | Severity |
| --- | --- |
| Ontology document — entity types, relation types, edge semantics enumerated | **medium-high** — no canonical `docs/architecture/ontology.md` |
| Canonical entity identity / alias resolution | not implemented (entities deduped by surface form only) | medium |
| Edge confidence / provenance | no edge attributes | medium |
| Temporal edges | no `valid_from` / `valid_to` | low (depends on use case) |
| Ontology-version stamp on graph data | none | medium |
| Graph freshness SLO | none | low |
| Path explainability in retrieval | graph_searcher returns chunks; doesn't surface the traversal path | medium |

### Combined-scenario drills (highest value)

1. **Backlog-age gauge** — finish the abandoned
   `documind_draft_pending_age_seconds{namespace}` work.
   Surfaces the slow-leak case (drafts not auto-rejected because
   they keep hitting `cb_wait` / `skipped_backoff`).
2. **Tenant-fairness drill** — seed pending drafts under tenant A
   and tenant B; assert sweep visits BOTH within one cycle even
   if A has 10× more drafts. Today's iteration order is unfair.
3. **Ontology document** — enumerate entity types, relation types,
   edge semantics, alias rules. Gap is documentation-shaped, not
   code-shaped, but it's the seam every future graph drill keys
   off.
4. **Graph-vector consistency drill** — same query that hits both
   backends should return overlapping chunk IDs (vector finds the
   chunk; graph finds the same chunk via entity link). If they
   diverge, indexing is out of sync.
5. **Scheduled re-embedding job** — pair with the embedding-
   version stamp from the rag-data-layers gap list. After an
   embedding model bump, only stale chunks are re-embedded.
