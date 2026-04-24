# DocuMind — Gap Analysis

What we ship. What we don't. What we should.

Scope: the tech stack (chunking, embedding, vector, historical store, ORM, output eval, PII, SSO, LDAP, taxonomy, microservice surface). This is the brutally honest version — every gap here is a known limitation, not a hidden one.

Updated: 2026-04-23.

---

## Legend

- ✅ **Shipped** — implemented, tested, in production path
- 🟡 **Partial** — works for the common case, misses edge cases or alternative modes
- ❌ **Missing** — real gap; should be filed as a design area

---

## 1. Chunking

| What | Status | Notes |
| --- | --- | --- |
| Fixed-size sliding window (512 tokens, 15% overlap) | ✅ | `services/ingestion-svc/app/chunking/windowed.py` |
| Sentence-boundary chunking | ✅ | Uses `pysbd`. Fallback to window when sentences are too long. |
| Structural chunking (markdown headings, PDF sections) | ✅ | `chunking/structural.py`, uses `unstructured` for PDF |
| **Semantic chunking** (embedding-similarity clustering) | ❌ | Proposed by `semantic-router`. Would reduce boundary artifacts on dense prose. |
| **AST-based code chunking** | ❌ | We don't optimize for code-heavy corpora. Tree-sitter backend would fix this. |
| **Late chunking** (embed whole doc, then chunk in embedding space) | ❌ | New in 2025. Worth a POC. |
| Per-doc chunking strategy override | 🟡 | Tenant-level flag only; no per-document override yet. |

**Biggest gap:** semantic chunking. Boundary quality is the #1 predictor of retrieval precision.

---

## 2. Embedding

| What | Status | Notes |
| --- | --- | --- |
| BGE-m3 default (1024-dim, multilingual) | ✅ | Good quality/cost tradeoff. |
| Versioned per chunk (`embedding_model`, `embedding_version`) | ✅ | Re-embed is a shadow-index operation. |
| Batch embedding queue | ✅ | Kafka topic `embed.requests`, worker pool auto-scales. |
| **Cross-encoder reranker** | ✅ | BGE reranker v2. Rerank top-20 → top-5. |
| **Matryoshka / variable-dim** | ❌ | Could cut retrieval latency 3x for initial ANN probe. |
| **Per-modality embeddings** (images, tables, code) | 🟡 | Tables use LayoutLMv3; images and code use a single generic encoder. |
| **Fine-tuned domain embeddings** | ❌ | Would need a customer dataset. Not blocked, just not requested yet. |

**Biggest gap:** Matryoshka embeddings for tiered retrieval. Would let us probe with 128-dim first, re-rank with 1024-dim.

---

## 3. Vector DB

| What | Status | Notes |
| --- | --- | --- |
| Qdrant primary | ✅ | HNSW + scalar quantization. |
| **Tenant payload filter enforced in repo** | ✅ | Impossible to query without `must.tenant_id`. |
| **pgvector fallback** | ❌ | Proposed for small tenants. Repo abstraction is there; backend isn't. |
| **Milvus / Weaviate / Pinecone** | ❌ | Out of scope — we explicitly picked Qdrant. |
| Per-tenant collection isolation option | 🟡 | Available but not default. Adds operational cost; only worth it for regulated tenants. |
| Versioned index for embedding upgrades | ✅ | Shadow collection, flag-flipped rollout. |

**Biggest gap:** pgvector fallback for small tenants. The code is ready, the repo implementation isn't.

---

## 4. Historical / time-series store (Design Area 37)

| What | Status | Notes |
| --- | --- | --- |
| Audit log (Postgres) | ✅ | 90-day hot retention. |
| FinOps token-usage log | ✅ | Partitioned daily. |
| **Cold tier** (S3 Parquet, ≥ 90 days) | ❌ | **This is the single biggest gap in the whole stack.** PG storage grows unboundedly. |
| **Analytics queries on historical** | ❌ | No DuckDB/Athena layer. Every historical query hits hot OLTP. |
| Incident replay from historical | ❌ | Would need the cold tier first. |

**Biggest gap:** Cold-tier archival. This is Design Area 37 — flagged, scoped, unimplemented. Next sprint priority.

---

## 5. ORM

| What | Status | Notes |
| --- | --- | --- |
| No ORM — hand-written SQL in `Repo` classes | ✅ | **Deliberate choice.** RLS requires `SET LOCAL app.current_tenant` per-transaction; most ORMs fight us on this. |
| Parameterized queries via `asyncpg` | ✅ | No f-string SQL anywhere. |
| Connection pool + per-request tenant scoping | ✅ | `tenant_connection()` context manager. |
| **SQLAlchemy 2.0 async alternative** | ❌ | Proposed for teams that want it. We'd need to verify RLS integration; asyncpg is known-good. |
| Migration tool | ✅ | Plain SQL files, numbered, idempotent via `_migrations` table. |

**Why no ORM is a feature, not a gap:** RLS bugs come from developers accidentally leaking tenant scope. Hand-written SQL with an obvious repo boundary makes the leak impossible to introduce without it showing up in code review.

---

## 6. Output evaluation

| What | Status | Notes |
| --- | --- | --- |
| Precision@5, Recall@5, nDCG | ✅ | `evaluation-svc` runs on labeled eval sets. |
| Faithfulness (output cited in retrieved context) | ✅ | Simple — embed output, check cosine to context chunks. |
| Answer relevance | 🟡 | Heuristic only; no LLM-as-judge yet. |
| **LLM-as-judge** (GPT-4o / Claude as grader) | ❌ | Industry standard, not implemented. Cost + governance concerns — we'd be calling an external API on customer data. |
| **Ragas** integration | ❌ | Would give us faithfulness/answer-relevance/context-precision free. Open-source. |
| Drift detection (embedding distribution shift) | ✅ | PSI/CSI on embedding distribution vs. reference. |
| Human feedback collection | ✅ | Thumbs up/down + optional comment. Stored in `eval.feedback`. |
| Active learning from feedback | ❌ | Feedback sits there. Nothing retrains. |

**Biggest gap:** LLM-as-judge + Ragas. Would roughly triple eval coverage at moderate cost.

---

## 7. PII

| What | Status | Notes |
| --- | --- | --- |
| Regex-based scanner (emails, phones, SSN, credit card, IP) | ✅ | `PIIScanner` in `libs/py/documind_core/governance/pii.py` |
| Input scanning (before LLM sees it) | ✅ | Fail-closed — request rejected if PII detected without explicit tenant opt-in. |
| Output scanning (before response returns) | ✅ | Second pass. |
| **Presidio NER-backed scanner** | ❌ | MS Presidio gives us named-entity detection — person names, addresses, dates. Regex can't catch those. |
| PII-aware caching | ✅ | Never cache a response containing PII. |
| Redaction (not just detection) | 🟡 | Detection returns offsets; redaction is manual per-caller. |
| Per-tenant PII policy | ✅ | Tenants can declare "we handle PII, don't scan." Logged to audit. |

**Biggest gap:** Presidio integration. Regex misses named entities entirely.

---

## 8. SSO

| What | Status | Notes |
| --- | --- | --- |
| Local username/password | ✅ | Argon2id hashing. |
| API keys with scopes | ✅ | Per-tenant, per-role. Stored Fernet-encrypted. |
| JWT (HS256) — app sessions | ✅ | Short-lived access + refresh. |
| **OIDC (Google, Microsoft, Okta)** | ❌ | **Major enterprise gap.** |
| **SAML 2.0** | ❌ | Required for many enterprise tenants. |
| **SCIM** (automated user provisioning) | ❌ | Without it, admins type usernames by hand. |
| MFA | 🟡 | TOTP implemented for local accounts; not for SSO flows (because there are no SSO flows yet). |

**Biggest gap:** OIDC. Every enterprise prospect asks for it on the first call.

---

## 9. LDAP / directory

| What | Status | Notes |
| --- | --- | --- |
| LDAP bind authentication | ❌ | |
| Group sync from AD | ❌ | |
| Nested group resolution | ❌ | |

**Status:** ❌ entirely. We don't speak LDAP. SSO via OIDC (once added) covers most of the use-case, but some air-gapped enterprises still run LDAP-only.

---

## 10. Text taxonomy / ontology

| What | Status | Notes |
| --- | --- | --- |
| Neo4j schema defined | ✅ | `(Document)-[:CONTAINS]->(Chunk)-[:MENTIONS]->(Entity)` |
| Entity extraction at ingest | ✅ | spaCy NER + LLM-extracted entities. |
| Entity linking (to Wikidata/internal) | 🟡 | Wikidata for common entities; no internal entity registry yet. |
| **Ontology management UI** | ❌ | Tenants can't define their own taxonomy today. |
| **OWL / SKOS import** | ❌ | No way to load a customer's existing ontology. |
| **Hierarchical topic labels** | ❌ | Flat entity types only. |
| Graph-augmented retrieval | ✅ | 1-hop neighbor expansion from top chunks. |

**Biggest gap:** ontology management UI. Enterprise customers often come with a pre-existing taxonomy (ISO, IPC classes, internal product hierarchy) and want to map chunks to it.

---

## 11. Microservice features benefiting the project

Every service's "why it's a separate service" justification. If any of these is weak, we should merge it.

| Service | Load-bearing reason for separation |
| --- | --- |
| `api-gateway` | Different failure domain from business logic; written in Go for low-latency path |
| `ingestion-svc` | Throughput-bound, heavy IO, independent scaling from query path |
| `retrieval-svc` | Latency-critical; co-located with Qdrant in prod |
| `inference-svc` | GPU-scheduled; token budget + CCB is a full subsystem |
| `governance-svc` | Cross-cutting; HITL queue has its own persistence + escalation model |
| `finops-svc` | Billing data is a compliance surface; access control is separate |
| `evaluation-svc` | Batch workload; runs against frozen snapshots, not live traffic |
| `identity-svc` | Isolation: compromising any other service must not yield tokens |
| `observability-svc` | Control-plane for SLO/alerts, not user data |
| `frontend` | Different deployment cadence; Node.js runtime |

**Missing services we might want:**

- `mcp-svc` — Model Context Protocol server for external agents (scoped, not built)
- `export-svc` — bulk export + DSAR/GDPR right-to-be-forgotten workflows (partial, in `governance-svc`)
- `tenant-admin-svc` — self-serve tenant management (today lives in `identity-svc`)

---

## 12. Priority ordering

If I had two engineer-months to close gaps, I'd fund these in order:

1. **OIDC / SSO** — blocks enterprise deals (#8)
2. **Cold-tier historical archive** — PG storage is growing linearly (#4)
3. **Presidio PII NER** — regex PII is embarrassing (#7)
4. **LLM-as-judge eval (Ragas)** — we can't measure what matters (#6)
5. **Semantic chunking** — retrieval precision ceiling (#1)
6. **Ontology management UI** — differentiation vs. competitors (#10)
7. **pgvector fallback** — cost win for small tenants (#3)

Everything else is a nice-to-have.
