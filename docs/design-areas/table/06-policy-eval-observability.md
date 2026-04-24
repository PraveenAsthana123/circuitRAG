# Areas 56–67 + Extra CCB · Policy, Eval, Observability, Design Principles, Socio-Technical

## Area 56 · Policy-as-Code

| Field | Content |
|---|---|
| **Status** | 🟡 Partial — schema + example policies; full CEL engine deferred |
| **Class / file** | `services/governance-svc/migrations/001_initial.sql` (policies table) |
| **Components** | Rule engine · CEL expressions · Categories (access, content, cost, quality, compliance) · Sync vs async evaluation · Version + approval workflow |
| **Technical details** | Policies are versioned rows. Sync evaluation for critical (content safety); async for monitoring (cost). |
| **Implementation (planned)** | `POLICY_ENGINE.evaluate(policy, context) → action`. CEL runtime evaluates `response.confidence < 0.6`. Action → flag/block/log/notify. |
| **Tools & frameworks** | CEL (cel-go) · OPA (Rego) · Cerbos · OpenFGA · custom |
| **How to implement** | 1. Policy schema · 2. CEL runtime · 3. Policy cache (30s TTL) · 4. Per-policy metrics · 5. Approval workflow. |
| **Real-world example** | Rule `response.contains_pii == true → BLOCK` evaluated in inference pipeline · PII detected → response swapped for safe fallback + audit row. |
| **Pros** | Runtime behavior change · Auditable · Testable |
| **Cons** | CEL learning curve · Policy conflicts · Sync overhead |
| **Limitations** | CEL lacks loops/recursion · Policy complexity grows |
| **Recommendations** | Keep policies SIMPLE · One concern per policy · Unit-test every policy |
| **Challenges** | Ordering / priority · Performance at scale · Policy drift |
| **Edge cases + solutions** | Policy conflict (two rules disagree) → priority via severity · Bad policy → staging eval before activate |
| **Alternatives** | OPA (Rego) — more expressive · Cerbos — permissions-focused · Hardcoded rules (no runtime change) |

---

## Area 57 · Human-in-the-Loop (HITL)

| Field | Content |
|---|---|
| **Status** | 🟡 Partial — HITL queue schema; reviewer UI deferred |
| **Class / file** | `services/governance-svc/migrations/001_initial.sql` (hitl_queue table) |
| **Components** | HITL queue · Reviewer dashboard · Actions (approve/reject/edit/escalate) · SLA (1h review) · Feedback to eval |
| **Technical details** | Flagged responses land in queue with question+chunks+answer+confidence+flag_reason. Reviewer decides. Outcome feeds back to eval metrics. |
| **Implementation (planned)** | governance-svc stores items. Frontend `/admin/hitl` queue. Timer enforces SLA. `hitl_decision` event published on resolve. |
| **Tools & frameworks** | Scale · Labelbox · Argilla · Label Studio · custom queue |
| **How to implement** | 1. Schema in place · 2. Flag router from inference · 3. Reviewer UI · 4. Action webhook · 5. SLA alerts. |
| **Real-world example** | Low-confidence answer (CCB interrupted) → queue · reviewer sees question + 5 chunks · edits answer · publishes · user gets reviewed version. |
| **Pros** | Safety net for edge cases · Generates training data · Trust with users |
| **Cons** | Scaling humans · SLA pressure · Reviewer bias |
| **Limitations** | Latency for the user whose response is queued · Reviewer cost |
| **Recommendations** | Target HITL volume < 5% of traffic · Triage by severity · Consensus for high-stakes |
| **Challenges** | Reviewer training · Consistency · Queue explosion on model regression |
| **Edge cases + solutions** | Queue overflow → escalate/expand team · Reviewer disagreement → senior-review lane |
| **Alternatives** | Fully automated (risky) · HITL at sampling (subset) · Skip HITL, accept risk |

---

## Area 58 · Feedback Architecture

| Field | Content |
|---|---|
| **Status** | 🟡 Partial — feedback table schema; 👍/👎 capture deferred |
| **Class / file** | `services/evaluation-svc/migrations/001_initial.sql` (feedback table) |
| **Components** | Explicit feedback (👍/👎) · Implicit (follow-up questions, dwell time) · Feedback events · Routing to eval + governance · Prompt/model tuning signal |
| **Technical details** | Feedback events → Kafka `feedback.events` → eval service aggregates → governance flags topics with persistent negative feedback. |
| **Implementation (planned)** | Frontend `POST /api/v1/feedback` with thumbs + notes. Kafka event. Eval aggregates. Alert when negative > 20% on a topic. |
| **Tools & frameworks** | Kafka · Prom counters · dbt for feedback analysis · Braze/Mixpanel for implicit |
| **How to implement** | 1. UI thumbs buttons · 2. API + Kafka · 3. Aggregation in eval-svc · 4. Alert on patterns · 5. Use for prompt tuning. |
| **Real-world example** | Users downvoting answers about "contract renewal" → aggregation flags topic → review shows retrieval miss · corpus enrichment job triggered. |
| **Pros** | Real user signal · Catches blind spots · Trust loop |
| **Cons** | Low thumbs response rate · Self-selection bias · Noisy signal |
| **Limitations** | Requires UX affordance · Late signal (user already saw bad answer) |
| **Recommendations** | Combine explicit + implicit · Reward for rich notes · Anonymized aggregation |
| **Challenges** | Signal-to-noise · Attribution (which step of the pipeline caused the bad answer?) |
| **Edge cases + solutions** | User thumbs-downs correct answer (they wanted different info) → disambiguate in UI · Adversarial feedback → rate-limit per user |
| **Alternatives** | Implicit only (cheap, weaker signal) · Explicit only · Third-party surveys |

---

## Area 59 · Offline Evaluation Architecture

| Field | Content |
|---|---|
| **Status** | ✅ Implemented |
| **Class / file** | `services/evaluation-svc/app/main.py`, `app/metrics/` |
| **Components** | Eval datasets (Q + GT answer + expected sources) · Scheduled runs · Metric suite · Baseline comparison · Report generator |
| **Technical details** | Runs full pipeline on eval data. Computes 6 metrics. Stores in `eval.runs`. Compares to baseline. |
| **Implementation** | `POST /api/v1/evaluation/run` with datapoints. Cron triggers nightly. Results aggregated; posted to Slack/dashboard. |
| **Tools & frameworks** | RAGAS · TruLens · DeepEval · HELM · custom |
| **How to implement** | 1. Curate dataset · 2. Runner + metric computation · 3. Baseline comparison · 4. Alert on regression · 5. Dashboard. |
| **Real-world example** | Nightly: 500 Qs → metrics vs last week · 5% faithfulness drop · alert fires · prompt v3 rolled back via flag. |
| **Pros** | Objective quality signal · Catches regression before users do · A/B ready |
| **Cons** | Dataset curation labor · Metric-UX gap · Cost (full pipeline per Q) |
| **Limitations** | Dataset ages · Small set = high variance · Metric proxy limitations |
| **Recommendations** | Ground-truth from domain expert · Version dataset · LLM judge for nuanced metrics |
| **Challenges** | Dataset maintenance · GT refresh · Statistical significance |
| **Edge cases + solutions** | Multiple correct answers → LLM judge / semantic sim · Dataset contaminated → rotate |
| **Alternatives** | Manual spot-checks (cheap, unreliable) · User-survey-driven (slow) |

---

## Area 60 · Online Evaluation Architecture

| Field | Content |
|---|---|
| **Status** | ❌ Designed only |
| **Class / file** | `spec §60`; planned consumer of production events |
| **Components** | Sampling (5%) · Shadow eval · Drift detection (KL divergence) · A/B metric delta |
| **Technical details** | Sample X% of prod queries, re-score async against reference model or ground truth. Track drift via distribution divergence. |
| **Implementation (planned)** | Kafka consumer samples from `query.lifecycle.generated`. Async re-eval with reference. Prom metrics track drift. |
| **Tools & frameworks** | Kafka sampler · scipy.stats (KL) · Arize · WhyLabs · Evidently |
| **How to implement** | 1. Sample consumer · 2. Reference pipeline · 3. Metric delta · 4. Drift alerts · 5. Dashboards. |
| **Real-world example** | Confidence distribution shifts left (dropping) day-over-day → drift alert · investigate: model regression vs corpus drift? |
| **Pros** | Production-truth signal · Continuous · Catches subtle drift |
| **Cons** | Double cost (re-eval) · Complex infrastructure · Reference model upkeep |
| **Limitations** | Sampling bias · Reference drift |
| **Recommendations** | Start with 1% · Budget separately · Cross-check with offline |
| **Challenges** | Reference model freshness · KL on small samples noisy |
| **Edge cases + solutions** | Sampled query has PII → scrub before re-eval · Reference-model cost spike → lower sample rate |
| **Alternatives** | Offline only (miss real-time drift) · Manual audits (slow) · WhyLabs / Arize (SaaS) |

---

## Area 61 · Regression Gate Architecture

| Field | Content |
|---|---|
| **Status** | 🟡 Partial — AIops alert rule active; blocking CI check deferred |
| **Class / file** | `infra/observability/alert-rules.yml` (EvalFaithfulnessRegression), `scripts/aiops_retrain_trigger.py` |
| **Components** | Pre-deploy eval · Thresholds per metric · Override with audit · CI/CD integration |
| **Technical details** | Before deploy, run eval suite · compare to baseline · block if faithfulness -5% or latency +20%. Admin override logged. |
| **Implementation** | CI job calls evaluation-svc; pipeline fails on regression. AlertManager routes to Slack. |
| **Tools & frameworks** | GitHub Actions · Argo CD · Flagger (auto-rollback) · GitLab CI |
| **How to implement** | 1. Defined thresholds · 2. CI job calls eval-svc · 3. Exit code gates deploy · 4. Override with reason · 5. Audit log. |
| **Real-world example** | PR bumps temperature → eval shows faithfulness -8% → CI red → merge blocked · author investigates. |
| **Pros** | Prevents prod regression · Objective gate · Forces eval investment |
| **Cons** | Slows deploy · Noisy on small samples · Threshold tuning |
| **Limitations** | Gate only as good as eval · Fast-fail culture needed |
| **Recommendations** | Start with warning · Tighten as dataset grows · Per-metric threshold |
| **Challenges** | Flaky evals · Legit degradation for new capability |
| **Edge cases + solutions** | Capability tradeoff (new feature worth -3% on old metric) → documented override |
| **Alternatives** | Post-deploy monitoring + rollback · Gradual rollout only · No gate (risky) |

---

## Area 62 · Observability by Design

| Field | Content |
|---|---|
| **Status** | ✅ Implemented |
| **Class / file** | `libs/py/documind_core/observability.py`, `logging_config.py`, breaker-guarded exporters |
| **Components** | Metrics (Prom) · Logs (JSON, Loki/ES) · Traces (OTel) · Correlation IDs · Span naming · ObservabilityCircuitBreaker |
| **Technical details** | Three pillars + correlation IDs propagated via ContextVars. Structured JSON with tenant+user+trace+span IDs. |
| **Implementation** | `setup_observability` + `setup_logging` at service startup. FastAPI/asyncpg/redis/httpx auto-instrumented. CID in every log line. |
| **Tools & frameworks** | OpenTelemetry SDK + Collector · Prometheus · Grafana · Jaeger · Loki/Kibana · Kiali |
| **How to implement** | 1. Every service inherits libs · 2. Auto-instrument at startup · 3. CID middleware · 4. Structured JSON logs · 5. Prom endpoint. |
| **Real-world example** | Slow request → Jaeger trace shows retrieval took 3s · logs filtered by CID show Qdrant 2.8s · fix by adding payload index. |
| **Pros** | Debug time plummets · SLOs measurable · On-call happy |
| **Cons** | Cardinality traps · Log volume cost · Telemetry infra upkeep |
| **Limitations** | Prom label cardinality (avoid user_id) · Jaeger retention short · Log PII risk |
| **Recommendations** | SLO-centric dashboards · Correlation IDs everywhere · Log redaction at source |
| **Challenges** | Cross-service trace context · Async event trace continuation · Cost at scale |
| **Edge cases + solutions** | Telemetry infra down → ObservabilityCircuitBreaker skips silently · High cardinality → sample / strip labels |
| **Alternatives** | Datadog / New Relic / Honeycomb · SigNoz (OSS APM) · AWS CloudWatch |

---

## Area 63 · Auditability by Design

| Field | Content |
|---|---|
| **Status** | 🟡 Partial — audit_log table + hash-chain field; writer helper deferred |
| **Class / file** | `services/governance-svc/migrations/001_initial.sql` (audit_log with previous_hash + entry_hash) |
| **Components** | Immutable append-only log · Hash-chained entries · Actor + action + resource · Correlation ID · 1-year retention |
| **Technical details** | Each row: `entry_hash = SHA256(previous_hash || row_json)`. Tamper in place → hash chain breaks. |
| **Implementation (planned)** | `AuditLogger.append(action, actor, resource, details, correlation_id)`. Chain-writer preserves order. WORM storage in prod. |
| **Tools & frameworks** | Postgres append-only + trigger · AWS QLDB · Amazon Ledger · immudb |
| **How to implement** | 1. Append-only table · 2. Hash-chain writer · 3. Periodic verification job · 4. Export to WORM · 5. Retention cron. |
| **Real-world example** | Every document upload, state transition, admin action, HITL decision logged · incident investigation: "what happened at 14:22 on doc X?" answered in 2 minutes. |
| **Pros** | Compliance-ready · Forensics-friendly · Accountability |
| **Cons** | Volume + cost · Cannot delete (even buggy entries) · Hash-chain verification overhead |
| **Limitations** | Postgres isn't truly immutable; admin can DELETE (guard with RLS + role) · Verification on large chain is O(N) |
| **Recommendations** | WORM storage for exports · Periodic verification · RBAC on audit_log table |
| **Challenges** | GDPR right-to-be-forgotten vs immutable audit · Volume management · Hash-chain verification |
| **Edge cases + solutions** | Corrupt entry → break-glass recovery protocol · User deletion request → pseudonymize (keep audit, remove PII) |
| **Alternatives** | Cloud audit services (AWS CloudTrail) · QLDB · Blockchain-based (overkill) |

---

## Area 64 · SLO-Driven Design

| Field | Content |
|---|---|
| **Status** | ✅ Implemented |
| **Class / file** | `services/observability-svc/migrations/001_initial.sql` (slo_targets seeded), `infra/observability/alert-rules.yml` |
| **Components** | SLI definitions · SLO targets · Error budgets · Burn rate alerts · Freeze policy |
| **Technical details** | Availability 99.5%, p95 latency < 3s, retrieval precision@5 > 80%, faithfulness > 90%. Error budget = 1 - SLO; burn rate alerts multi-window. |
| **Implementation** | SLO rows in DB. Prom alert rules compute burn rate. AlertManager routes warning (50%) / critical (80%) / freeze (100%). |
| **Tools & frameworks** | Prometheus · AlertManager · Sloth (SLO generator) · Nobl9 · Datadog SLOs |
| **How to implement** | 1. Define SLIs · 2. Set SLOs · 3. Compute burn rate · 4. Burn-rate alerts · 5. Freeze policy when budget exhausted. |
| **Real-world example** | Budget 3.6h/month · 2h already burned in week 2 → burn-rate alert · deploy freeze · team focuses reliability. |
| **Pros** | Balances feature vs reliability · Objective freeze criterion · Shared language |
| **Cons** | Hard to define good SLIs · Culture shift · Alert tuning |
| **Limitations** | Multi-dependency SLOs are tricky · Compound SLO calc |
| **Recommendations** | Start with 3 SLOs · Multi-window burn-rate alerts · Quarterly SLO review |
| **Challenges** | Buy-in from product · Correlation with UX · Under-ambitious SLOs |
| **Edge cases + solutions** | Budget busted mid-month → freeze non-critical · Flaky SLI → widen window |
| **Alternatives** | SLAs only (contractual, less useful operationally) · No SLOs (ad-hoc, worst) · Google SRE book patterns |

---

## Area 65 · Design-for-Change

| Field | Content |
|---|---|
| **Status** | ✅ Implemented |
| **Class / file** | every `*/base.py` — `EmbeddingProvider`, `DocumentParser`, `Chunker`, `VectorSearcher`, `GraphSearcher`, `CognitiveSignal` |
| **Components** | Interfaces/protocols · Plugin registries · Config-driven behavior · API versioning · DB migrations · Feature flags |
| **Technical details** | Every external dep behind an interface. Swap = config change. Plugin pattern for parsers, chunkers, signals, embedders. |
| **Implementation** | `ParserRegistry`, `Chunker` ABC, `EmbeddingProvider` ABC, `VectorSearcher`, `GraphSearcher` — all allow substitution. |
| **Tools & frameworks** | Python ABC / Protocol · Go interfaces · plugin discovery (entry-points) |
| **How to implement** | 1. Interface first · 2. Default impl · 3. Config selector · 4. Tests against interface · 5. Never import concrete from app code. |
| **Real-world example** | Swap Qdrant → Weaviate: implement `VectorSearcher` for Weaviate, change `DOCUMIND_VECTOR_DB=weaviate` in env. App code unchanged. |
| **Pros** | Lock-in minimized · Easier testing (fakes) · Vendor shopping easier |
| **Cons** | Interface overhead · Over-abstracted code · Leaky abstractions |
| **Limitations** | Interface can't hide all dep quirks (performance, consistency) · New deps may need interface changes |
| **Recommendations** | Interfaces at stable boundaries · Don't prematurely abstract · Document what's swappable |
| **Challenges** | Finding the right seam · Keeping interfaces thin · Avoiding anemic abstractions |
| **Edge cases + solutions** | New backend has unique feature → optional method with `NotImplementedError` · Interface evolves → version it |
| **Alternatives** | Hexagonal architecture · Ports & adapters · Dependency injection frameworks |

---

## Area 66 · Design-for-Debuggability

| Field | Content |
|---|---|
| **Status** | ✅ Implemented |
| **Class / file** | `?debug=true` query in inference-svc, CID propagation, `CognitiveCircuitBreaker.snapshot`, CB metrics, `/health` + metrics endpoints |
| **Components** | Correlation IDs · Debug mode flag · Request replay · Structured errors · Dynamic log levels · Query explain |
| **Technical details** | `?debug=true` returns retrieval scores, graph traversal, rerank scores, prompt version, token counts, CCB snapshot. |
| **Implementation** | CID middleware binds to ContextVar. Breakers expose state. Logs link to traces via trace_id. Grafana dashboards per service. |
| **Tools & frameworks** | OpenTelemetry · Jaeger · Kibana saved searches · pprof (Go) · py-spy |
| **How to implement** | 1. CID everywhere · 2. `?debug=true` opt-in · 3. Structured error envelope · 4. Request replay from logs · 5. Dynamic log-level admin endpoint. |
| **Real-world example** | User reports bad answer → they share the correlation ID from the UI footer → ops filters logs → replays query with `?debug=true` → sees retrieval returned wrong chunks. |
| **Pros** | Short time-to-understanding · Less guess-work · User self-service debug |
| **Cons** | Debug payload can leak internals · Replay requires careful access control |
| **Limitations** | Debug mode restricted to admins · Replay with side-effects needs dry-run mode |
| **Recommendations** | Default correlation ID in error messages · Restrict debug to admins · Record enough to replay |
| **Challenges** | Non-admins can't share debug info easily · Replay of side-effects · Sensitive info in debug |
| **Edge cases + solutions** | User reports without CID → generate from timestamp+user · Replay POST → dry-run mode |
| **Alternatives** | Black-box debugging (slow) · Customer copy of traces (security risk) |

---

## Area 67 · Socio-Technical Operating Model

| Field | Content |
|---|---|
| **Status** | ✅ Implemented (as docs + conventions) |
| **Class / file** | `docs/runbooks/INCIDENT_RESPONSE.md`, `docs/runbooks/DR_RUNBOOK.md`, `docs/architecture/ADRs/*.md` |
| **Components** | Service ownership · Team topology · On-call rotation · Incident response · Post-mortems · ADRs · Communication channels · RACI |
| **Technical details** | Per-service owner. Platform+AI+Governance teams. SEV1/2/3 classification. Blameless post-mortems within 48h of SEV1/2. |
| **Implementation** | Runbooks in repo. ADRs for every significant decision. Severity playbook. |
| **Tools & frameworks** | PagerDuty · Statuspage · Incident.io · Slack incident channels · Confluence for RACI · C4 for team/service map |
| **How to implement** | 1. Per-service owner · 2. Runbook per SEV1/2 scenario · 3. Post-mortem template · 4. ADR for every decision · 5. On-call rotation. |
| **Real-world example** | Ollama OOM → SEV2 pages on-call · runbook step 1: restart container · step 2: check memory · post-mortem finds chunking regression · action item: chunk-size guardrail. |
| **Pros** | Reliable ops · Knowledge captured · Blameless culture · Team scale |
| **Cons** | Documentation upkeep · Conway's Law friction · Reorgs invalidate structure |
| **Limitations** | Culture > docs · Hiring is the hard part · Distributed teams have coordination cost |
| **Recommendations** | Team Topologies (book) · Stream-aligned teams on services · Platform team for shared infra |
| **Challenges** | Ownership drift · Burnout from on-call · Knowledge hoarding |
| **Edge cases + solutions** | Critical service with no owner → emergency assignment + hire · Post-mortem politicized → external facilitation |
| **Alternatives** | Ad-hoc structure (doesn't scale) · Central platform team owns all (bottleneck) · Fully devolved (no shared infra) |

---

## Extra · Cognitive Circuit Breaker (CCB)

| Field | Content |
|---|---|
| **Status** | ✅ Implemented (new design area added 2026-04-23) |
| **Class / file** | `libs/py/documind_core/breakers.py::CognitiveCircuitBreaker`, signal classes (`RepetitionSignal`, `CitationDeadlineSignal`, `ForbiddenPatternSignal`, `LogprobConfidenceSignal`), `docs/design-areas/CCB-cognitive-circuit-breaker.md` |
| **Components** | Signal interface · Built-in signals · Per-token evaluation · Interrupt mechanism · Fallback injection |
| **Technical details** | Intrinsic reliability — checks during generation, not after. Every ~32 tokens, signals evaluate partial output. BLOCK → abort and swap fallback. |
| **Implementation** | `ccb.start()` + `ccb.on_tokens(delta)` in the stream loop. Raises `CognitiveInterrupt`. Inference service catches, returns safe fallback. |
| **Tools & frameworks** | Custom · arXiv 2604.13417 reference · applicable on any streaming LLM call |
| **How to implement** | 1. Define signal set per tenant · 2. `on_tokens` in stream · 3. Fallback response · 4. Metrics per signal · 5. Calibration via eval set. |
| **Real-world example** | LLM begins generating "Your SSN is..." → ForbiddenPatternSignal BLOCKs · user never sees the leak · HITL gets the prompt+partial for review. |
| **Pros** | Catches hallucination before user sees it · Latency win (abort early) · Cost win (don't finish bad generation) |
| **Cons** | Calibration per-tenant needed · False positives block valid answers · Vendor dependency (logprobs) |
| **Limitations** | Not a replacement for data quality / retrieval grounding / policy / offline eval |
| **Recommendations** | Pair with post-hoc Guardrails · Calibrate against eval dataset · Per-tenant signal sets via feature flag |
| **Challenges** | Over-blocking · Signal ordering · Thresholds per corpus |
| **Edge cases + solutions** | Valid answer triggers regex → add context-aware NER · Signal fails (exception) → log, don't block |
| **Alternatives** | Post-hoc only (misses real-time win) · LLM-judge mid-stream (expensive) · No intrinsic check (accept hallucination risk) |
