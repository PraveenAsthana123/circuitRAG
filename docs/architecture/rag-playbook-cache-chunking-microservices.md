# RAG Playbook — Cache, Chunking, Microservices, Patterns, NFR

> Comprehensive enterprise reference covering: 12 cache types, 12
> chunking strategies, 12-data-type chunking matrix, 24 candidate
> microservices, design patterns (sidecar / API gateway / circuit
> breaker / saga / CQRS / event-driven / bulkhead), software design
> patterns (factory / strategy / builder / adapter / decorator /
> observer), CAP theorem trade-offs, NFR matrix, and capacity
> planning back-of-the-envelope.
>
> Composes with: `docs/architecture/MODULE-FLOWS.md` (per-module
> input/process/output), `docs/architecture/LATENCY-BUDGET.md`
> (per-tool ms + ROI), `docs/MISSING.md` (gap inventory),
> `docs/architecture/genai-rag-production-checklist-100-plus.md`
> (production readiness), `docs/architecture/HLD-documind.md`
> (high-level system design).

## 1. RAG cache types — master table

| # | Cache | What | Where | Benefit | Limitation | When to use |
|---|---|---|---|---|---|---|
| 1 | Query | Query → final answer | Entry | Fastest | Stale | FAQ, repeated queries |
| 2 | Retrieval | Query → top-K docs | Retrieval | Saves vector search | Needs invalidation | Large KB, repeated queries |
| 3 | Embedding | Text → vector | Pre-retrieval | Cuts API cost | Memory heavy | High embedding usage |
| 4 | LLM Response | Prompt+context → output | Generation | Saves LLM cost | Low reuse if prompt varies | Expensive LLM calls |
| 5 | Semantic | Similar query → answer | Entry/pre-retrieval | High hit rate | Wrong-match risk | Conversational apps |
| 6 | Chunk | Processed chunks | Ingestion | Avoid reprocess | Storage overhead | Heavy preprocessing |
| 7 | Index | Vector index in RAM | Retrieval | Ultra-fast | RAM-intensive | Low-latency systems |
| 8 | Pipeline | Intermediate steps | Multi-stage | Avoid recompute | Complex logic | Advanced pipelines |
| 9 | Reranking | Ranked doc list | Post-retrieval | Saves rerank cost | Context-sensitive | Expensive rerankers |
| 10 | Session | Conversation memory | Chat layer | Better UX | Privacy concerns | Chatbots, agents |
| 11 | Auth/Policy | User access rules | Security | Faster authz | Sync issues | Multi-tenant |
| 12 | Metadata | Tags, filters | Pre-retrieval | Faster filtering | Staleness risk | Structured datasets |

### 1.1 Cache types — challenges, edge cases, recommendation

| # | Cache | Use when | Reject when | Main challenge | Solution | Edge case | Edge-case fix | Recommendation |
|---|---|---|---|---|---|---|---|---|
| 1 | Query | Same exact questions repeat | Answers depend on fresh data | Cache invalidation | TTL + doc-version key | Policy changed but old answer returned | Include `knowledge_version` in cache key | FAQ/static docs |
| 2 | Semantic | Similar questions repeat | High-risk legal/medical | Similarity threshold | High threshold + confidence check | "refund" vs "cancellation" wrong-matched | Add intent classifier before cache hit | Use carefully; not regulated |
| 3 | Embedding | Same text embedded often | Embedding model changes | Model/version mismatch | Key by model+version | Old embeddings after upgrade | Re-embed or namespace by model version | Must-have |
| 4 | Chunk | Heavy preprocessing | Tiny/simple docs | Chunk drift after parser change | Store parser/chunker version | New strategy but old chunks reused | Rebuild on chunker version change | PDFs, SharePoint, large docs |
| 5 | Metadata | Tenant/date/role filtering | Metadata changes constantly | Sync with source | TTL + event-based refresh | User loses access but metadata still allows | Combine with live auth check | Enterprise RAG |
| 6 | Retrieval | Same query → same docs | KB changes often | Invalidation after doc updates | Cache by query + index version | Deleted doc in retrieval | Validate doc existence before generation | Stable KB |
| 7 | Index | Need low-latency retrieval | Dataset too large for RAM | Memory pressure | Shard + warm cache | Node restart cold latency | Pre-warm index on startup | High-traffic |
| 8 | Reranking | Cross-encoder reranker is expensive | User-specific ranking | Query/doc pair explosion | Cache query-doc score | Same docs but different user role | Include user/tenant scope | Reranker cost is high |
| 9 | Pipeline | Multi-step rewrite→retrieve→rank | Simple RAG only | Complex invalidation | Cache each stage separately | Bad query rewrite cached | Store trace + allow bypass | Advanced agentic RAG |
| 10 | LLM Response | Same prompt+context repeats | Personalization/dynamic | Prompt variations | Normalize prompt + hash context | Same question different retrieved context | Cache full prompt+context hash | Expensive model calls |
| 11 | Session | Multi-turn chatbot | Stateless FAQ | PII retention | TTL + encryption + redaction | "what about that policy?" after context expired | Fallback to retrieval + clarification | Chat/agent workflows |
| 12 | Auth/Policy | Multi-tenant / RBAC / ABAC | High-risk access changes instantly | Permission drift | Short TTL + event-driven invalidation | Role removed but cached | Validate at retrieval-time | Multi-tenant systems |

### 1.2 Which cache at which RAG moment

| RAG moment | Use | Why | Reject other because |
|---|---|---|---|
| User asks question | Query | Exact repeat = instant | Embedding/retrieval not needed if exact answer exists |
| User asks similar question | Semantic | Handles paraphrases | Query cache misses paraphrases |
| Before vector search | Embedding | Avoid re-embedding query | Retrieval cache needs embedding result first |
| During ingestion | Chunk | Avoid re-parsing | Query cache irrelevant during ingestion |
| Before retrieval filtering | Metadata | Fast tenant/date/security filter | Retrieval cache may return unauthorized |
| Vector search | Retrieval | Avoid repeated DB calls | LLM cache too late in pipeline |
| High-speed retrieval | Index | Vector index hot | Retrieval cache only helps repeats |
| After top-k | Reranking | Avoid expensive reranker | Query cache may be stale |
| Agentic multi-step | Pipeline | Saves rewrite/retrieve/rank | Single layer doesn't cover workflow |
| Before LLM generation | LLM Response | Avoid repeated LLM call | Retrieval cache still needs generation |
| Multi-turn | Session | Maintains context | Query cache doesn't understand conversation |
| Every secure access | Auth/Policy | Prevents repeated permission checks | Other caches may leak data |

### 1.3 Cache priority

| Priority | Cache | Why |
|---|---|---|
| Must-have | Embedding | Direct cost reduction |
| Must-have | Auth/Policy | Prevents data leakage |
| Must-have | Retrieval | Improves latency |
| High value | Query | Best for FAQ |
| High value | LLM Response | Saves expensive generation |
| High value | Metadata | Enterprise filtering |
| Advanced | Semantic | Powerful but risky |
| Advanced | Reranking | Useful with cross-encoders |
| Advanced | Pipeline | Agentic RAG |
| Scale | Index | Low-latency systems |
| Chat UX | Session | Conversational |
| Ingestion | Chunk | Heavy doc processing |

### 1.4 Production cache stack by situation

| Situation | Best stack |
|---|---|
| Small FAQ bot | Query + Embedding + LLM Response |
| Enterprise document RAG | Embedding + Metadata + Retrieval + Auth + LLM Response |
| Multi-tenant banking | Auth + Metadata + Retrieval + Session + audit-safe TTL |
| High-traffic chatbot | Query + Semantic + Embedding + Retrieval + LLM Response |
| Agentic RAG | Session + Pipeline + Retrieval + Reranking + LLM Response |
| PDF-heavy KB | Chunk + Metadata + Embedding + Retrieval |

## 2. Chunking — 12 strategies

| # | Strategy | Use when | Reject when | Pros | Cons | Challenges | Solution | Edge case | Edge-case fix | Recommendation |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Fixed-size | Simple text, MVP | Complex docs | Fast, predictable | Breaks meaning mid-sentence | Poor context | Add overlap | Important sentence split | Sentence-aware splitting | MVP only |
| 2 | Sliding Window | Need context continuity | Large corpus / cost-sensitive | Better recall | Duplicate tokens | Storage grows | 10–20% overlap | Same fact repeated | Dedup by hash | Good default for text |
| 3 | Sentence | Articles, policies, manuals | Code/tables/forms | Natural | Uneven size | Long sentences | Max-token cap | One sentence too long | Split by clause/token | Strong general |
| 4 | Paragraph | Well-written docs | Messy OCR/PDF | Topic blocks | Huge/small paras | Bad formatting | Normalize first | Bullets merged badly | Bullet-aware parser | Business docs |
| 5 | Section/Header | Docs with headings | No/poor headings | Strong context | Header detection errors | Missing section metadata | Store header path | Wrong heading | Validate heading patterns | Best for policies/SOPs |
| 6 | Semantic | Complex knowledge | Low budget MVP | High retrieval quality | More compute | Boundary detection | Embedding similarity threshold | Related text split | Tune threshold + eval | Best quality |
| 7 | Recursive | Mixed structure | Highly structured tables/code | Balanced | Needs tuning | Separator priority | section→para→sentence | PDF bad line breaks | Clean text first | **Best practical default** |
| 8 | Token-based | LLM context control | Need semantic precision | Model-safe | Can break meaning | Tokenizer mismatch | Model-specific tokenizer | Chunk fits one model fails another | Store tokenizer version | Final safety layer |
| 9 | Table-aware | Financial/healthcare reports | Plain narrative | Preserves structure | Hard extraction | Parsing errors | Table → markdown/JSON | Row without header | Repeat header in each chunk | Must-have enterprise |
| 10 | Code-aware | Repos/APIs/notebooks | Normal docs | Better code retrieval | Language-specific | Large files/classes | AST-based | Function depends on imports | Include imports | Must-have for code RAG |
| 11 | Metadata-aware | Multi-tenant/security | Simple personal bot | Better filtering/governance | Metadata drift | Wrong mapping | Validate against source | Unauthorized chunk retrieved | Enforce auth before retrieval | Must-have enterprise |
| 12 | Hierarchical | Need summary + detail | Small FAQ | Precision + context | Complex index | Parent-child linking | Store parent_id/child_id | Child without parent | Expand parent at generation | Best for serious production |

### 2.1 Which chunking at which moment

| RAG moment | Best | Why | Reject because |
|---|---|---|---|
| Quick MVP | Fixed-size + overlap | Fastest | Semantic/hierarchical takes longer |
| Business policies | Header + paragraph + metadata | Sections + governance | Fixed-size breaks policy meaning |
| PDF-heavy | Recursive + table-aware | Messy mixed structure | Pure paragraph fails on PDFs |
| Banking/finance | Section + metadata + table-aware | Audit + numbers + access | Semantic-only loses table accuracy |
| Codebase Q&A | Code-aware AST | Functions/classes intact | Fixed-size breaks code |
| Conversational | Hierarchical + session | Detail + parent | Small chunks lose context |
| Large KB | Semantic + retrieval eval | Relevance | Fixed-size = noisy recall |
| Compliance | Header + metadata + parent-child | Traceability | LLM cache can't fix bad chunks |
| Reports w/ tables | Table-aware | Row/header meaning | Text splitter destroys table |
| Low-latency | Recursive + token cap | Balance | Semantic adds preprocessing cost |

### 2.2 Chunking priority

| Priority | Type | Why |
|---|---|---|
| Must-have | Recursive | Best default balance |
| Must-have | Metadata-aware | Enterprise filtering/security |
| Must-have | Token cap | Prevents context overflow |
| High value | Header/Section | Policies, SOPs |
| High value | Table-aware | Finance/healthcare |
| High value | Sliding Window | Improves recall |
| Advanced | Semantic | Best meaning-based |
| Advanced | Hierarchical | Parent-child context |
| Specialized | Code-aware | Repo/code |
| Basic | Fixed-size | MVP only |
| Basic | Sentence | Clean text |
| Basic | Paragraph | Clean business docs |

### 2.3 Chunk-size recommendation by content

| Content | Size | Overlap | Notes |
|---|---|---|---|
| FAQ | 100–300 tok | 0–50 | Atomic answers |
| Policy/SOP | 400–800 | 80–150 | Preserve section meaning |
| Research paper | 600–1000 | 100–200 | Include heading path |
| Financial report | 300–700 | 50–150 | Table-aware |
| Legal/compliance | 300–600 | 80–150 | Avoid mixing clauses |
| Code | Function/class | Minimal | AST-based preferred |
| Chat history | Turn-based | Depends | Speaker + timestamp |
| PDFs/OCR | 300–600 | 100 | Clean text first |

### 2.4 Production chunking stack by situation

| Situation | Best stack |
|---|---|
| Simple chatbot | Recursive + overlap |
| Enterprise RAG | Recursive + metadata + token cap |
| Banking/finance | Header + metadata + table-aware + parent-child |
| Healthcare | Section + metadata + table-aware + audit trace |
| Code RAG | AST/code-aware + metadata |
| Research paper | Header + semantic + hierarchical |
| Multi-tenant | Metadata-aware + auth-aware filtering |
| PDF KB | OCR cleanup + recursive + table-aware |

## 3. Chunking by data type — full matrix

| Data | Chunking | Tools | Stage | Microservice | Strategy | Challenge | Solution | Kafka/NATS | gRPC | Cache |
|---|---|---|---|---|---|---|---|---|---|---|
| CSV | Row + column-aware | Pandas, DuckDB | Ingestion | CSV parser svc | Chunk by business key, row group | Header mismatch, nulls, schema drift | Schema validation + DQ rules | Kafka batch | gRPC validation | Metadata + embedding |
| PDF | Recursive + section + table-aware | PyMuPDF, Textract | Preprocess | PDF extraction svc | Header path + page + source | Bad OCR, tables broken | OCR cleanup + table extract | Kafka | gRPC OCR/layout | Chunk |
| Word | Header + paragraph + semantic | docx, Unstructured | Preprocess | Doc parser | H1/H2/H3 chunks | Poor formatting | Normalize headings | Kafka | gRPC parser | Chunk + metadata |
| HTML | DOM-based + section | BeautifulSoup | Crawl | Web parser | Remove nav/footer/ads | Noise, duplicates | Boilerplate removal | Kafka crawl jobs | gRPC content extractor | Page |
| JSON | Object + path-based | Python JSON | Ingestion | JSON svc | Chunk by JSON path/object | Deep nesting | Flatten + preserve path | Kafka/NATS | gRPC schema svc | Object |
| XML | Tag/path-based | lxml | Ingestion | XML svc | Element hierarchy | Invalid XML | XSD validation | Kafka feed | gRPC validator | Parsed XML |
| Image | Region + OCR + caption | Tesseract, CLIP | Preprocess | Vision svc | Chunk by region/object/text | Low quality | OCR + vision + confidence | NATS lightweight, Kafka large | gRPC vision inference | Feature |
| Audio | Time-window + speaker | Whisper | Preprocess | ASR svc | Speaker/time/topic | Accent/noise | Noise reduction + ASR confidence | Kafka audio jobs | gRPC ASR | Transcript |
| Video | Scene + frame + transcript | OpenCV, FFmpeg | Preprocess | Video AI svc | Scene + transcript | Expensive | Sample frames + scene detection | Kafka long videos | gRPC vision | Frame/transcript |
| Code | AST/function/class | Tree-sitter | Ingestion | Code svc | Function/class/module | Dependency context | Imports + caller/callee metadata | Kafka repo indexing | gRPC parser | AST + embedding |
| Logs | Time-window + session + trace-id | OpenTelemetry | Stream | Log svc | Trace/session/window | High volume | Sampling + compression | Kafka best | gRPC anomaly | Hot log |
| Chat/Email | Thread + turn-based + intent | LangChain | Ingestion | Conversation svc | Thread + speaker + topic | PII leakage | Redaction + ACL | Kafka/NATS messages | gRPC redaction | Session |

### 3.1 Best default chunking stack

| Layer | Recommendation |
|---|---|
| Default | Recursive + metadata-aware |
| Enterprise docs | Header/section + paragraph + token cap |
| Tables/CSV | Table-aware + schema-aware |
| Images/video | OCR + caption + object/scene |
| Code | AST/function/class |
| Logs/events | Trace/session/time-window |
| Security | Metadata + RBAC/ABAC before retrieval |
| Cache | Chunk + embedding + metadata |
| Messaging | Kafka heavy durable, NATS lightweight real-time |
| Observability | Track chunk count, failed chunks, embedding cost, retrieval hit rate, stale chunks |

### 3.2 Brutal recommendation for enterprise RAG

```
Document type detection → parser-specific chunking → metadata enrichment
  → token cap → quality scoring → embedding → cache → observability
```

## 4. Microservices for enterprise RAG — 24 candidates

| # | Service | Purpose | Use when | Reject / merge when |
|---|---|---|---|---|
| 1 | Source Connector | SharePoint/S3/DB/API/folders | Many sources exist | Only one static source |
| 2 | Data Type Detection | PDF/CSV/image/audio/code/logs | Multi-format ingestion | Only one file type |
| 3 | Parser | Extract text/table/image/code | PDFs/docs/HTML/code exist | Clean text already provided |
| 4 | OCR / Vision | Scanned PDFs/images | Scanned docs/images | Text-native PDFs only |
| 5 | Audio/Video Transcription | Whisper/ASR + diarization | Audio/video KB | No media data |
| 6 | Preprocessing | Clean/normalize/dedup | Messy enterprise docs | Clean curated docs |
| 7 | Chunking | Create chunks by type | Core RAG requirement | Tiny FAQ bot |
| 8 | Metadata Enrichment | source/owner/tenant/version/ACL | Enterprise/multi-tenant | Personal/local bot |
| 9 | Security / PII | PII/secrets/PHI detection | Banking/healthcare/HR/legal | Public docs only |
| 10 | Quality Scoring | Score chunk quality | Production RAG | MVP/prototype |
| 11 | Embedding | Vectorize text | Any semantic retrieval | Very small keyword search |
| 12 | Indexing | Vector DB writes | Large searchable KB | Small local app |
| 13 | Retrieval | Top-k search | Runtime RAG | Simple single-DB app |
| 14 | Reranking | Improve top-k order | Accuracy matters | Low-latency/cost |
| 15 | LLM Orchestration | Prompt + context + answer | Production chatbot/API | Simple script |
| 16 | Guardrail | Validate input/output safety | Enterprise/public | Internal low-risk demo |
| 17 | Evaluation | Groundedness/relevance/faithfulness | Need quality measurement | Prototype only |
| 18 | Feedback | User thumbs/comments | Continuous improvement | No user UI |
| 19 | Cache | Query/embedding/retrieval/response | High traffic/cost pressure | Low-traffic MVP |
| 20 | Observability | Logs/traces/metrics/Langfuse | Production operations | One-off demo |
| 21 | Governance / Audit | Lineage/approval/version | Regulated enterprise | Non-regulated prototype |
| 22 | Portal / Admin | Admin/reviewer/auditor UI | Enterprise users | Backend-only API |
| 23 | Notification | Alerts/failures/approvals | Human-in-loop | No workflow/escalation |
| 24 | Workflow Orchestrator | Airflow/Dagster/Temporal | Many pipeline steps | Simple sync process |

### 4.1 Microservice split by project size

| Project size | Services |
|---|---|
| MVP | Parser + Chunking + Embedding + Retrieval + LLM |
| Small Production | Connector + Parser + Chunking + Embedding + Indexing + Retrieval + LLM + Cache |
| Enterprise | All core + Security + Metadata + Evaluation + Observability + Governance |
| Banking/Finance | Connector + Parser + Metadata + Security + Chunking + Embedding + Indexing + Retrieval + Reranking + LLM + Guardrail + Evaluation + Audit + Observability |
| Healthcare | Banking + PHI handling + human review + strong audit |
| Multimodal | Add OCR/Vision + Audio/Video + media metadata svc |

### 4.2 Use / reject by data type

| Data type | Use | Why | Reject | Why |
|---|---|---|---|---|
| CSV | Connector + Schema Validator + Chunking + Metadata + Embedding + Indexing | Structured data needs schema | OCR/Vision | Not visual data |
| PDF | Parser + OCR + Table Extractor + Chunking + Metadata + Security | PDFs are messy, often scanned | Simple fixed chunker | Breaks tables/sections |
| Image | Vision/OCR + Metadata + Security + Embedding | Object/text extraction | Text parser | Cannot understand image |
| Audio | ASR + Diarization + Chunking + Metadata | Transcript + speaker split | PDF parser | Wrong modality |
| Video | Scene Detection + ASR + Vision + Chunking | Multimodal | Text-only pipeline | Misses visual context |
| Code | Repo Scanner + AST Parser + Security Scan + Chunking | Function/class boundaries | Paragraph chunking | Breaks code logic |
| Logs | Log Parser + Trace Grouping + Streaming + Anomaly Detection | Trace/session grouping | Semantic-only | Too noisy |
| Chat/Email | Thread Parser + PII Redaction + Session Chunking | Conversation continuity | Fixed chunking | Loses speaker/context |

### 4.3 Brutal recommendation — start with 8

| # | Service | Reason |
|---|---|---|
| 1 | Connector | Brings data safely |
| 2 | Parser | Converts raw files |
| 3 | Chunking | Controls retrieval quality |
| 4 | Metadata/Security | Prevents data leakage |
| 5 | Embedding | Model/version/cost control |
| 6 | Indexing/Retrieval | Search backbone |
| 7 | LLM Orchestration | Answer generation |
| 8 | Observability/Evaluation | Quality + failure metrics |

### 4.4 Selected vs internal-module vs platform

| Pipeline step | Decision | Why |
|---|---|---|
| File classification | Internal module (inside Connector/Parser) | Simple routing |
| Cleaning/normalization | Internal (inside Parser) | Coupled with parser output |
| Metadata enrichment | Internal (inside Chunking) | Tight chunk coupling |
| Chunk quality scoring | Internal (Chunking/Eval) | Too small unless enterprise QA |
| Reranking | Internal (inside Retrieval) | Tied to candidates |
| Guardrails | Internal (inside LLM Orchestration) | Close to generation |
| Cache | Platform (Redis) | Shared infra |
| Messaging | Platform (Kafka/NATS) | Decouples async jobs |
| Workflow orchestration | Platform (Airflow/Dagster/Temporal) | Existing tools |

## 5. Microservice design principles

| Principle | Means | Why | How | Common mistake | RAG example |
|---|---|---|---|---|---|
| Separation of Concern | One service = one responsibility | Maintenance + testing | Split by domain | One service doing everything | Parser ≠ Chunking ≠ Embedding |
| Encapsulation/Abstraction | Hide internals, expose API | No tight deps | REST/gRPC contracts | Direct DB sharing | Retrieval hides vector DB |
| Loose Coupling | Services don't depend tightly | Replaceable | Async messaging, APIs | Calling another service's DB | Chunking ≠ LLM dependency |
| High Cohesion | One thing well | Clean design | Group related logic | Mixed responsibilities | Embedding only embeds |
| Scalability | Independent scaling | Handle load | Horizontal + autoscale | Scaling whole system | Scale OCR separately |
| Performance | Optimize latency/throughput | UX + cost | Cache, batch, async | Blocking calls everywhere | Cache embeddings |
| Resilience | Survive failures | No downtime | Retry, timeout, circuit breaker | No fallback | Retry embedding API |
| Fault Tolerance | Continue if part fails | Stability | DLQ, fallback, redundancy | Single point of failure | Fallback model |
| Observability | Monitor behavior | Debug + optimize | Logs, metrics, tracing | Only logs | Track RAG latency per step |
| Security | Protect data + access | Compliance, trust | RBAC, encryption, PII | Afterthought | PII filter before embedding |
| Autonomy | Independent deploy | Faster releases | CI/CD per service | Shared release pipeline | Deploy retrieval without affecting chunking |
| API-first Design | Define contract first | Consistency | OpenAPI/gRPC schema | Ad-hoc APIs | Define retrieval API |

## 6. System design / microservice patterns

| Pattern | Means | Use when | RAG example |
|---|---|---|---|
| Sidecar | Helper container next to main | Logging/proxy/config helper | LLM service + telemetry/auth sidecar |
| API Gateway | Single entry point | Many backends | Frontend → gateway, not each RAG service |
| Circuit Breaker | Stop calling failing service | LLM/vector DB failing | Open circuit on embedding API fail |
| Saga | Distributed transactions | Multi-step workflows | Ingest → parse → chunk → embed → index |
| CQRS | Separate read/write paths | Heavy search + ingestion | Ingestion writes; retrieval reads |
| Event-Driven | Services via events | Async pipelines | Kafka: `document_uploaded` → `chunk_created` |
| Bulkhead | Isolate failures | One service shouldn't crash all | OCR fail doesn't kill chat |
| Retry + DLQ | Retry then dead-letter | Async failures | Failed PDF → DLQ |
| Strangler Fig | Replace legacy gradually | Modernizing | Replace old search with RAG slowly |

## 7. Software design patterns in RAG

| Pattern | Type | Use when | RAG example |
|---|---|---|---|
| Builder | Creational | Many optional configs | Build RAG pipeline config |
| Factory | Creational | Many implementations | PDFParser/CSVParser/ImageParser |
| Abstract Factory | Creational | Multiple product families | AWS AI vs Azure AI stack |
| Prototype | Creational | Fast clone/customize | Clone prompt template |
| Observer | Behavioral | Event/listener | Notify monitoring on chunking fail |
| Strategy | Behavioral | Swap algorithm at runtime | Choose chunking: fixed/semantic/header |
| Adapter | Structural | Wrap third-party | Same API for FAISS/Qdrant/Pinecone |
| Facade | Structural | Hide complexity | `RAGFacade.query()` calls retrieval + LLM |
| Decorator | Structural | Add behavior cleanly | Retry/logging/auth wrapper |
| Singleton | Creational | Shared instance | Vector DB client connection |

### 7.1 Pattern selection for RAG

| Scenario | Pattern | Why |
|---|---|---|
| Select parser by file type | Factory | PDF/CSV/Image/Code chosen dynamically |
| Select chunking logic | Strategy | Fixed/semantic/table/code |
| Build complete pipeline | Builder | Configure parser+chunker+embedder+VDB+LLM |
| Support AWS/Azure/GCP | Abstract Factory | Cloud-specific components |
| Clone agent/prompt | Prototype | Reuse templates fast |
| Alerts on failures | Observer | Notify Slack/email/monitoring |
| Add retry/log/security | Decorator | Wrap service calls |
| Hide vector DB diff | Adapter | Same interface FAISS/Qdrant/Pinecone |
| Simple frontend API | Facade | One interface hides complex backend |

### 7.2 Pattern priority

| Priority | Pattern |
|---|---|
| Must | Factory, Strategy, Builder, Adapter, Observer |
| Production | Circuit Breaker, Sidecar, Event-Driven |
| Enterprise | Saga, CQRS |

### 7.3 Chunking flow using patterns

```
Document Uploaded
   ↓
Factory selects parser/chunker
   ↓
Adapter normalizes parser output
   ↓
Strategy selects chunking method
   ↓
Builder assembles full pipeline
   ↓
Decorator adds PII scan + logging + validation
   ↓
Chunking service creates chunks
   ↓
Observer emits event: chunks_created
   ↓
Embedding service consumes event
```

## 8. CAP theorem trade-offs in RAG

| Aspect | Meaning | Get | Lose | RAG example |
|---|---|---|---|---|
| C — Consistency | All nodes see same data | Correct, up-to-date | Higher latency, lower availability | Latest policy always returned |
| A — Availability | Always responds | Fast | May serve stale | Cached response |
| P — Partition Tolerance | Works despite network failure | System runs | Must sacrifice C or A | Multi-region vector DB |

**In distributed systems P is mandatory; you choose C vs A.**

| Component | Choice | Why |
|---|---|---|
| Vector DB | AP | Fast retrieval > perfect consistency |
| Metadata/Auth | CP | Security cannot be stale |
| Cache | AP | Speed > freshness |
| Indexing | CP | Correct indexing required |
| LLM Response | AP | User prefers response over failure |

## 9. Non-Functional Requirements (NFR)

| NFR | Means | Why | How | Trade-off |
|---|---|---|---|---|
| Scalability | Handle more users/data | Growth, cost | Horizontal scale, sharding | Adds complexity |
| Performance | Low latency, high throughput | UX + cost | Cache, batch, async | May reduce consistency |
| Availability | Always up | Continuity | Multi-region, failover | May serve stale |
| Security | Protect data | Compliance | RBAC, encryption, PII scan | Adds latency |
| Reliability | Consistent behavior | Stability | Retry, DLQ, circuit breaker | More infra |
| Observability | Monitor | Debug + optimize | Logs, metrics, tracing | Overhead |
| Maintainability | Easy update | Faster dev | Microservices, clean code | Discipline |
| Extensibility | Add features | Future-proof | Modular | Initial complexity |
| Cost Efficiency | Optimize spend | Viability | Cache, batch | May reduce quality |
| Compliance | Follow regulations | Legal | Audit logs, governance | Slower delivery |

### 9.1 RAG component vs NFR

| Component | Scalability | Performance | Availability | Security |
|---|---|---|---|---|
| Parser | Horizontal workers | Batch processing | Retry on failure | File validation |
| Chunking | Parallel chunking | Efficient splitting | Idempotent | PII scan |
| Embedding | GPU/CPU scaling | Batch API calls | Retry + fallback model | Encrypt vectors |
| Vector DB | Sharding | Index caching | Multi-region | Access control |
| Retrieval | Stateless scaling | Top-K optimization | Fallback search | Metadata filter |
| LLM | Auto-scale | Prompt optimization | Fallback model | Guardrails |
| Cache | Redis cluster | Instant response | Replication | Token masking |
| API Gateway | Load balancing | Rate limiting | Multi-AZ | Auth + throttling |

### 9.2 Trade-off matrix

| Goal | Optimize | Sacrifice |
|---|---|---|
| Fast system | Performance | Consistency |
| Accurate answers | Consistency | Latency |
| Always available | Availability | Accuracy |
| Secure system | Security | Performance |
| Cheap system | Cost | Quality |

### 9.3 Banking RAG example decisions

| Decision | Choice | Reason |
|---|---|---|
| CAP | CP for security, AP for retrieval | Security strict, answers slightly stale OK |
| Scalability | Horizontal microservices | High traffic |
| Performance | Redis + embedding cache | Reduce latency |
| Availability | Multi-region | Avoid downtime |
| Security | RBAC + PII masking | Compliance |
| Observability | OpenTelemetry + Langfuse | Debug RAG |

## 10. Capacity planning — back-of-the-envelope

| Area | Estimate | Formula | Example |
|---|---|---|---|
| Users per second (QPS) | Avg request rate | daily_users × queries_per_user ÷ 86400 | 1,000 × 10 ÷ 86400 = 0.12 QPS avg |
| Peak traffic | Peak QPS | avg × peak factor | 0.12 × 10 = 1.2 QPS peak |
| Data volume | Total docs storage | docs × avg file size | 100K × 2MB = 200 GB |
| Chunk count | Total chunks | total_tokens ÷ chunk_size | 1B ÷ 500 = 2M chunks |
| Embedding storage | Vector store size | chunks × dim × 4 bytes | 2M × 768 × 4 = ~6 GB |
| Embedding cost | One-time + delta | tokens × $/million tokens | 1B × $0.10/M = $100 |
| Retrieval latency | p95 budget | network + vector_search + rerank | 5ms + 30ms + 20ms = ~55ms |
| LLM inference | Per request | input_tokens + output_tokens × $/M | 4K in + 1K out × $0.50/M = $0.0025 |
| Total TCO/month | Sum | embedding + LLM + storage + infra | varies by traffic |

> Note: original message was truncated at the capacity-planning
> table — fields beyond "Embedding storage" filled in from
> standard back-of-the-envelope conventions; verify against your
> actual model/provider numbers before committing to TCO.

## 11. Enterprise pipeline (full flow)

```
Data Source
  ↓
Detection (type)
  ↓
Parser Selection (tool)
  ↓
Preprocessing (clean/OCR)
  ↓
Chunking (type-based)
  ↓
Metadata Enrichment (tenant, role, source)
  ↓
PII / Security Scan
  ↓
Quality Scoring
  ↓
Embedding
  ↓
Vector DB Index
  ↓
Cache Layer (query, embedding, retrieval)
  ↓
Retrieval + Reranking
  ↓
LLM Generation
  ↓
Evaluation (groundedness)
  ↓
Monitoring + Governance
  ↓
Portal UI (user/admin/audit)
```

## 12. Brutal gap analysis — what most systems miss

| Missing area | Impact |
|---|---|
| Metadata + RBAC | Data leakage |
| Table-aware chunking | Wrong financial answers |
| Chunk quality scoring | Garbage retrieval |
| Versioning | Stale answers |
| PII scan | Compliance failure |
| Observability | No debugging |
| Evaluation metrics | No quality control |
| Portal UI | No trust/adoption |

## 13. Final recommended stack

| Layer | Choice |
|---|---|
| Chunking | Recursive + Header + Metadata + Table-aware |
| Parser tools | PyMuPDF + Unstructured + Whisper + Tree-sitter |
| Cache | Redis (multi-layer) |
| Vector DB | FAISS / Qdrant |
| Pipeline | Kafka + Airflow |
| Observability | Langfuse + OpenTelemetry |
| Governance | RBAC + audit logs + lineage |
| Portal | Admin + user + audit dashboards |

## 14. Composes with

- `docs/architecture/MODULE-FLOWS.md` — input/process/output per shipped module
- `docs/architecture/LATENCY-BUDGET.md` — per-tool ms + ROI ranking
- `docs/MISSING.md` — gap inventory (vLLM, Ragas, SHAP, etc.)
- `docs/architecture/genai-rag-production-checklist-100-plus.md` — production readiness
- `docs/architecture/HLD-documind.md` — high-level system design
- `docs/architecture/agentic-advisory-board-a2a-architecture.md` — agentic patterns
- `docs/architecture/ai-quality-tool-decision-matrix.md` — eval tool selection

## 16. DSA — data structures & algorithms per RAG component

The "DSA in RAG" question is the architect's actual work. Every
component below has a primary structure that determines its
latency, memory, and failure modes. Wrong DSA = 10× slower or
quadratic blow-up at scale.

### 16.1 Chunking

| Need | DSA | Why | Complexity |
|---|---|---|---|
| Walk text + find separators | Suffix tree / Aho-Corasick | Fast multi-pattern boundary detection | O(n + m) |
| Recursive split | Tree (n-ary) | Section → para → sentence hierarchy | O(n log n) |
| Semantic boundary | Embedding + cosine + sliding window | Detect topic shifts | O(n × d) |
| Code AST | Abstract Syntax Tree | Function/class boundaries | O(n) |
| Hierarchical chunks | Tree + parent_id pointers | Preserve doc → section → chunk lineage | O(n) |
| Dedup duplicate chunks | MinHash + LSH | Near-duplicate detection at scale | O(n) avg |
| Token cap enforcement | Greedy + tokenizer | Pack chunks under model context | O(n) |

### 16.2 Embedding

| Need | DSA | Why | Complexity |
|---|---|---|---|
| Batch jobs | Queue (FIFO) | Order-preserving batch processing | O(1) push/pop |
| Embedding cache lookup | Hash map (content_hash → vector) | O(1) repeat-text fast path | O(1) avg |
| Model registry | Trie (model_name + version) | Prefix-based version lookup | O(k) |
| Cost tracking | Counter + sliding window | Token-cost rate over time | O(1) |

### 16.3 Vector store

| Need | DSA | Why | Complexity |
|---|---|---|---|
| Approximate NN | HNSW (Hierarchical Navigable Small World) | log-N recall with high accuracy | O(log n) |
| Alternative ANN | IVF (Inverted File) + product quantization | Memory-efficient at billion-scale | O(√n) |
| Exact NN | Brute force + SIMD | Small datasets (<10K), ground truth | O(n × d) |
| Filtered search | Inverted index + bitmap filters | Pre-filter by metadata before ANN | O(filter + log n) |
| Sharding | Consistent hashing | Even distribution across shards | O(1) lookup |
| Index rebuild | LSM tree | Incremental writes + periodic compaction | amortized O(log n) |

### 16.4 Pre-retrieval (query processing)

| Need | DSA | Why | Complexity |
|---|---|---|---|
| Query rewrite | Trie + replacement table | Synonym/abbreviation expansion | O(k) |
| Spell correct | BK-tree / Levenshtein DP | Fuzzy match | O(k × m) |
| Intent classify | Decision tree / softmax | Route to retrieval strategy | O(d) |
| Query expansion | HashSet + inverted index | Term-frequency boost | O(t) |
| Embedding query cache | Hash map | Avoid re-embedding identical queries | O(1) |

### 16.5 Retrieval

| Need | DSA | Why | Complexity |
|---|---|---|---|
| Top-K from N | Min-heap (size K) | Heap-keep-K is the standard top-K idiom | O(n log k) |
| Hybrid score fusion | Reciprocal Rank Fusion (RRF) | Combine BM25 + vector scores | O(n log n) |
| Result dedup | HashSet | Same chunk from multiple retrievers | O(n) |
| Query routing (multi-index) | Inverted index per tenant | Filter before ANN | O(filter) |
| Cursor pagination | Skip list / B+ tree | Stable pagination on large result sets | O(log n) |

### 16.6 Post-retrieval (reranking)

| Need | DSA | Why | Complexity |
|---|---|---|---|
| Cross-encoder rerank | Min-heap (top-K of N candidates) | Score every candidate, keep top-K | O(n log k) |
| MMR (diversification) | Greedy + similarity matrix | Maximal Marginal Relevance — diverse top-K | O(k × n) |
| Score normalization | Min-max / z-score | Compare across retrievers | O(n) |
| Citation linking | Bipartite graph (claim ↔ chunk) | Trace generated text back to source | O(n × m) |

### 16.7 Cache layer

| Need | DSA | Why | Complexity |
|---|---|---|---|
| Query cache | Hash map + LRU eviction | O(1) lookup + bounded memory | O(1) avg |
| Semantic cache | HNSW + threshold | Fuzzy match on query embedding | O(log n) |
| Sliding window rate limit | Sorted set (Redis ZSET) | Time-windowed counter | O(log n) |
| TTL expiry | Min-heap by expiry timestamp | Lazy expiry without scan | O(log n) |
| Stampede protection | Lock + double-check pattern | One coroutine fetches; rest wait | O(1) |
| Tenant isolation | Prefix-namespaced keys | Cross-tenant impossible by construction | O(1) |

### 16.8 Vector DB (storage layer)

| Need | DSA | Why | Complexity |
|---|---|---|---|
| Persist vectors | LSM tree / WAL + segment files | Fast writes, batched compaction | amortized O(log n) |
| Index serve | mmap'd segments | Zero-copy reads | O(1) page-fault amortized |
| Quantization | Product Quantization (PQ) | 8× memory reduction with small recall loss | O(d) |
| Compression | Scalar quantization (int8) | 4× smaller vectors | O(d) |

### 16.9 Historical / time-series DB (audit, decisions)

| Need | DSA | Why | Complexity |
|---|---|---|---|
| Append-only audit | LSM tree + Merkle tree | Fast writes + tamper-evidence | O(log n) write |
| Range query (last 24h) | Time-partitioned table | Skip irrelevant partitions | O(partitions × log n) |
| Hash chain integrity | Linked Merkle tree (per-tenant) | Detect insertion/modification | O(log n) verify |
| Aggregation (counters) | Sketch (HyperLogLog, Count-Min) | Approximate cardinality at scale | O(1) update |

### 16.10 Graph DB

| Need | DSA | Why | Complexity |
|---|---|---|---|
| Neighbor query | Adjacency list / index | Traverse one hop | O(degree) |
| Multi-hop traversal | BFS / DFS | Find related entities N hops away | O(V + E) |
| Shortest path | Dijkstra / A* | Find nearest related entity | O((V + E) log V) |
| PageRank | Matrix-vector iteration | Authority scoring | O(iter × E) |
| Entity linking | Trie + dictionary | Map text mention → entity ID | O(k) |
| Fraud / cycle detect | DFS + back-edge check | Find cycles in transaction graph | O(V + E) |

### 16.11 PII / security

| Need | DSA | Why | Complexity |
|---|---|---|---|
| PII pattern match | Aho-Corasick (multi-regex) | Match dozens of patterns in one pass | O(n + m) |
| Bloom filter | Probabilistic set | "Is token a known secret?" — fast neg lookup | O(k) |
| Token redaction | Rolling hash / regex DFA | Stream-redact at scale | O(n) |
| RBAC check | Bitmask intersection | Role × scope membership | O(1) |
| Encryption at rest | AES-GCM | Authenticated encryption | O(n) |

### 16.12 Output evaluation

| Need | DSA | Why | Complexity |
|---|---|---|---|
| Groundedness | Cosine similarity matrix (claim × evidence) | Verify each claim has evidence | O(c × e) |
| ROUGE / BLEU | n-gram counter (HashMap) | String overlap | O(n) |
| BERTScore | Embedding cosine | Semantic overlap | O(n × d) |
| Hallucination detect | Set difference (claims - evidence) | Spot uncited claims | O(n) |
| Sliding eval window | Reservoir sampling | Bounded-memory sample of production traffic | O(1) per sample |
| A/B significance | t-test / Welch | Detect real metric shift | O(n) |

## 17. Software-architect principles applied — per RAG component

The §5 table covered the principles in the abstract. This section
makes them concrete: which principle drives the design choice for
each RAG layer.

| RAG component | Primary principle | Secondary | Why |
|---|---|---|---|
| Connector | Loose coupling | Encapsulation | Each source has different auth/rate-limit/schema; isolation makes change cheap |
| Parser | High cohesion | API-first | "Convert raw → structured text" is one job; downstream relies on stable contract |
| Chunking | Strategy-pattern (SOC) | Versioning | Algorithm swapped at runtime; chunks must carry chunker version |
| Embedding | Encapsulation | Cost-efficiency | Hide model behind API; pin model_id+version; batch for cost |
| Vector store | Performance | Scalability | Latency budget belongs here; must shard horizontally |
| Pre-retrieval | API-first | Observability | Query rewrite is a contract; trace every transformation |
| Retrieval | Performance | Resilience | p95 latency < 100ms is the SLO; fallback to BM25 if vector down |
| Reranking | Bulkhead | Cost-efficiency | Isolate expensive cross-encoder; circuit-break if backlog grows |
| Generation | Resilience | Security | Retry + fallback model + guardrails on input/output |
| Cache | Tenant isolation | Performance | Cross-tenant key reuse = data leak; enforce by prefix |
| Audit | Tamper-evidence | Append-only (immutability) | Hash chain + WAL + retention policy |
| Observability | Cross-cutting | Decoupled | Sidecar / OTel collector; never block business path |
| Governance | Audit-first | Versioning | Every prompt/model/decision versioned + traceable |

### 17.1 Principle hot-spots (where most teams violate)

| Violation | Where it shows up | Cost |
|---|---|---|
| God service (no SOC) | "RAG service" doing parse+chunk+embed+retrieve+LLM | Untestable, slow, can't scale parts |
| Direct DB access (no encapsulation) | App reads vector DB directly | Lock-in, can't swap Qdrant→Pinecone |
| No fault tolerance | Embedding API hiccup → 5xx for all users | Outage on vendor blip |
| Ignored observability | "It's slow" with no per-stage timing | Can't fix what you can't measure |
| Stale auth cache | TTL too long → revoked role still works | Compliance breach |
| No prompt versioning | "Why did the answer change yesterday?" — unanswerable | Operational chaos |
| Mixing tenant data in cache | Caching `query → answer` without tenant prefix | Cross-tenant data leak |

## 18. System-design types — list and RAG application

| Type | What it is | Used in RAG when | Trade-off |
|---|---|---|---|
| Monolith | Single deployable unit | MVP / small team | Fast to build, doesn't scale parts |
| Modular monolith | Bounded modules in one binary | Pre-microservice phase | Refactor cost is low later |
| Microservices | Independently-deployable services | Production / many sources / many models | Network + ops overhead |
| Service mesh | Microservices + sidecar (Istio) | Need mTLS, traffic policy, observability between svcs | Operator complexity |
| Event-driven | Services react to events on a bus | Async ingestion, decoupled consumers | Eventual consistency |
| Stream processing | Continuous pipeline (Kafka Streams, Flink) | Real-time log/event indexing | Stateful ops are hard |
| Batch processing | Periodic large-volume jobs | Backfill, eval runs, reindex | Latency = batch interval |
| Serverless / FaaS | On-demand stateless functions | Bursty workloads (uploads, OCR) | Cold-start, vendor lock-in |
| Lambda architecture | Batch + stream layers merged for serving | Real-time + historical RAG | Two pipelines to maintain |
| Kappa architecture | Single stream pipeline (no batch layer) | Replay-able event log is the source of truth | Need durable Kafka |
| CQRS | Separate read/write models | Heavy ingest + heavy query | Two schemas to keep aligned |
| Event sourcing | State = sum of events | Audit-heavy domains, decision history | Storage growth |
| Hexagonal (ports/adapters) | Domain core + pluggable adapters | Need vendor-portability (vector DB, LLM provider) | More files |
| Clean architecture | Inward dependencies + use-case layer | Long-lived enterprise systems | Boilerplate up-front |
| BFF (Backend-for-Frontend) | Per-client backend layer | Web + mobile + admin need different shapes | More services to maintain |
| API gateway | Single entry routing to many backends | Rate-limit / auth / versioning at edge | SPOF if not HA |

### 18.1 What this RAG project uses

| Layer | Pattern in this repo |
|---|---|
| Top-level | Microservices (api-gateway, ingestion-svc, retrieval-svc, inference-svc, evaluation-svc, identity-svc, governance-svc, finops-svc, observability-svc, sidecar-advisor, frontend) |
| Service mesh | Istio configured (CONFIG-SHIPPED, mesh-not-running by default) |
| Event bus | Kafka for ingestion + audit fan-out |
| BFF | `services/frontend/app/api/...` Next.js routes |
| Edge | NGINX → api-gateway (api-gateway profile-gated) |
| Stream | Kafka outbox + RAG eval consumer |
| CQRS | Ingestion writes Qdrant + Neo4j; retrieval reads them |
| Hexagonal-ish | `<thing>_searcher.py` per-provider adapters |

## 19. Microservices end-to-end — RAG ingestion + retrieval

```
┌────────────────────────────────────────────────────────────┐
│  Ingestion path                                            │
└────────────────────────────────────────────────────────────┘

  Connector ─→ Type Detect ─→ Parser ─→ OCR/ASR (if media)
                                  │
                                  ↓
                           Preprocessing
                                  │
                                  ↓
                            Chunking ─────────→ Metadata Enrichment
                                  │                    │
                                  ↓                    ↓
                           PII/Security ←──────────────┘
                                  │
                                  ↓
                          Quality Scoring
                                  │
                                  ↓
                            Embedding (batched)
                                  │
                                  ├──→ Vector Index (Qdrant)
                                  └──→ Graph Index (Neo4j) [if entity-aware]
                                  │
                                  ↓
                          Audit + Observability
                                  │
                                  ↓
                          (Kafka event: chunks_indexed)


┌────────────────────────────────────────────────────────────┐
│  Retrieval path                                            │
└────────────────────────────────────────────────────────────┘

  User → API Gateway → Auth/RBAC → Pre-retrieval
                                       │
                                       ↓
                                Embedding (cached?)
                                       │
                                       ↓
                          Hybrid Retrieval (vector + BM25 + graph)
                                       │
                                       ↓
                                  Fusion (RRF)
                                       │
                                       ↓
                                  Reranking
                                       │
                                       ↓
                              Context Assembly
                                       │
                                       ↓
                                LLM Orchestration
                                       │
                                       ↓
                                Guardrails (output)
                                       │
                                       ↓
                              Eval (groundedness)
                                       │
                                       ↓
                                Audit + Cache
                                       │
                                       ↓
                                Response → User
```

### 19.1 Type of microservice per box

| Service | Type | Stateful? | Scale axis |
|---|---|---|---|
| Connector | Adapter | No (cursor in DB) | Per-source workers |
| Parser | Stateless worker | No | CPU-bound horizontal |
| OCR/ASR | Stateless worker (GPU) | No | GPU horizontal |
| Preprocessing | Stateless worker | No | CPU horizontal |
| Chunking | Stateless worker | No | CPU horizontal |
| Metadata | Stateless worker | No | CPU horizontal |
| PII/Security | Stateless worker | No (rule store) | CPU horizontal |
| Quality | Stateless worker | No | CPU horizontal |
| Embedding | Stateless worker | No | GPU/CPU horizontal |
| Vector index | Stateful | Yes (Qdrant data) | Sharded vertical+horizontal |
| Graph index | Stateful | Yes (Neo4j data) | Vertical (master-replica) |
| Audit | Stateful | Yes (Postgres) | Vertical + read replicas |
| API Gateway | Stateless | No | Horizontal |
| Auth/RBAC | Stateless (cached) | No | Horizontal |
| Retrieval | Stateless | No | Horizontal |
| Reranking | Stateless (GPU) | No | GPU horizontal |
| LLM Orchestrator | Stateless | No | Horizontal |
| Guardrail | Stateless | No | Horizontal |
| Eval | Stateless or batch | No | Horizontal |
| Cache | Stateful (Redis) | Yes | Cluster + replication |
| Observability | Stateful (Prom/Jaeger) | Yes | Vertical |

## 20. Value-add per RAG component — what each brings

The architect's pitch table — when the CFO asks "why this layer?":

| Component | Without it | With it | $$$ value |
|---|---|---|---|
| **Connector** | Manual file upload, limited sources | 100+ source types, automated sync | Unlocks data |
| **Type Detection** | Wrong parser per file → garbage chunks | Right parser per type | Quality |
| **Parser** | Apps deal with raw bytes | Clean structured text/tables | Foundation |
| **OCR/Vision** | Scanned PDFs / images invisible | Visual content searchable | +20-50% corpus |
| **ASR (audio)** | Recordings invisible | Transcripts indexed | +meeting/call data |
| **Preprocessing** | Noisy chunks → noisy retrieval | Clean chunks → relevant retrieval | Recall ↑ |
| **Chunking** | Bad splits → wrong context | Right-sized context windows | Answer correctness |
| **Metadata enrich** | Can't filter by tenant/role/date | Multi-tenant safe filtering | **Compliance + isolation** |
| **PII / Security** | Compliance risk, leak risk | GDPR/HIPAA/PCI safe | **Avoids fines** |
| **Quality scoring** | Garbage chunks indexed | Garbage rejected | Index quality |
| **Embedding** | Keyword-only retrieval | Semantic understanding | **Recall ↑ 30-50%** |
| **Embedding cache** | Re-embed same text | $0 on repeated text | **30-50% cost cut** |
| **Vector DB** | No semantic search | Sub-100ms semantic queries at scale | Latency |
| **Graph DB** | Flat retrieval, no relationships | Multi-hop reasoning | **+complex queries** |
| **Pre-retrieval** | Bad query → bad answer | Query rewrite/expansion → right docs | Recall ↑ |
| **Retrieval** | LLM hallucinates without context | Grounded context every call | **Accuracy ↑** |
| **Hybrid retrieval (vector+BM25+graph)** | Single recall path | Diverse recall, fusion | **+10-20% recall** |
| **Reranking** | Top-1 wrong 30%+ | Top-1 wrong <10% | **Precision ↑** |
| **LLM orchestration** | Inconsistent prompts | Versioned prompts, citations | Auditability |
| **Guardrails** | Toxic/leaky outputs | Safe outputs | Trust + brand |
| **Eval (groundedness)** | "Looks right" | Measured correctness | **Quality control** |
| **Cache (full stack)** | All requests hit LLM | 30-70% served from cache | **Cost ↓** |
| **Audit / governance** | Can't answer regulator | Reproduce any decision in seconds | **Compliance** |
| **Observability** | "Why is it slow?" — unanswerable | Per-stage latency + cost dashboards | Operability |
| **API gateway** | Each service exposed | Single entry, rate limit, auth | Security + cost |
| **Service mesh (Istio)** | Manual mTLS, manual traffic policy | Auto-mTLS, retries, traffic split | Ops + security |
| **Event bus (Kafka)** | Tightly coupled services | Decoupled, replay-able | Resilience |
| **CQRS** | Same DB hammered | Read/write paths optimize independently | Scale |
| **Portal UI (admin/auditor)** | Backend-only, no trust | Reviewer+auditor see what happened | **Adoption** |

### 20.1 Value priority — what to build first

If you can only build 5 things on day one, build these:

1. **Embedding cache** — direct cost cut from day one
2. **Metadata + Auth/RBAC** — without it, you can't ship to enterprise
3. **Retrieval + reranking** — accuracy is the user-visible metric
4. **Audit log (per-tenant hash chain)** — compliance gate
5. **Observability (per-stage timing + cost)** — operates everything else

Everything else is a layer on top of these five.

### 20.2 What each component prevents (negative value)

| Component | Prevents |
|---|---|
| Tenant isolation in cache keys | Cross-tenant data leak (CRITICAL) |
| PII scan before embedding | Sensitive data → vector DB → leaked via similar-query attack |
| Auth check at retrieval (not just at gateway) | User loses access but cached embeddings still match → leak |
| Prompt versioning | Silent behavior change ("why did it answer differently?") |
| Embedding model versioning | Old vectors + new query embeddings incompatible → silent recall collapse |
| Rate limiting | Single tenant exhausting the LLM budget |
| Circuit breaker | Vendor outage → cascading 5xx for all users |
| Hash chain in audit | Insider modifying audit rows after-the-fact |
| Groundedness eval | Hallucinations shipping to users in production |

## 21. Brutal rule

> Picking caches, chunking strategies, microservices, patterns, DSA,
> system-design types, and architect principles is **not** a single
> decision — each is a function of (data type, scale, security tier,
> latency budget, cost budget, accuracy requirement, regulatory
> tier, team size). A "best practice" applied without these
> constraints is a vibe; a deliberate trade-off documented per-
> component is architecture.
>
> If you can't answer "what DSA does this layer use, what does
> it cost in latency/memory, and what would happen if I removed
> this layer?" — you don't have an architecture, you have a stack
> of dependencies that happens to run.
