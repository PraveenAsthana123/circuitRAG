'use client';

import DeepDiveCrossRefs from '../../../../components/DeepDiveCrossRefs';
import UniversalDeepDive, { type Topic } from '../../../../components/UniversalDeepDive';

const TOPICS: Topic[] = [
  {
    slug: 'autonomous-drift-detection',
    title: '1. Autonomous drift detection (ratchet-pattern AIOps)',
    status: 'shipped',
    coreConcept: 'Self-tuning anomaly detection over operational metrics. Floors walk down (KNOWN_*) to match observed reality; ceilings walk up (DOMAIN_*) to track legitimate growth. When a metric crosses its current floor or ceiling, the watcher REJECTs the commit and surfaces the drift to the operator.',
    problem: 'Static thresholds are wrong on day one and wrong forever. Hardcoded "alert at >5 REJECTs" is a junk metric — drift happens in cascades and the threshold either fires constantly (operator burns out) or never fires (drift hides). AIOps means the threshold itself is a function of recent reality.',
    whyThisApproach: 'ADR-015 ratchet pattern: every threshold is a documented value, walked monotonically, with rationale per move. The watcher REJECTs only on regression past the current floor, not on absolute count. Operator sees both the current floor AND the historical max in the drill output.',
    whenToUse: ['Self-pacing CI gates that adapt to feature velocity', 'SLO drift on operational metrics (latency, error rate, queue depth)', 'Cascade detection (consecutive failures, not single spikes)', 'Threshold-driven incident alerts where false-positives kill operator trust'],
    whenNotToUse: ['Hard regulatory limits (PCI/HIPAA — never adjust)', 'Sub-millisecond decision paths (ratchet read latency dominates)', 'One-shot validation (no history to ratchet against)'],
    input: 'observed metric value + history file (.loop/last_drill_outcome.json or equivalent)',
    process: [
      'Read current value (e.g. consecutive_rejects=8)',
      'Read recorded floor / ceiling from drill source',
      'Compare: regression past floor → REJECT; cross ceiling → REJECT',
      'When drift is "real" (not noise) → drill author walks the floor with rationale comment',
      'Operator sees the drift trail in commit history (every walk has a Phase-N reason)',
    ],
    output: 'binary REJECT/APPROVE + rationale-rich audit trail in source code.',
    flowchart: `flowchart LR
  m[Observed metric] --> w{value worse than floor?}
  w -->|yes| reject[REJECT + surface]
  w -->|no| approve[APPROVE]
  reject --> root{is drift real?}
  root -->|yes — walk floor| commit[ratchet commit + Phase-N comment]
  root -->|no — fix root cause| fix[code/process fix]
  commit --> next[next iteration: floor matches reality]
  fix --> next`,
    sequence: `sequenceDiagram
  autonumber
  participant Author as Drill author
  participant W as Watcher
  participant H as History (.loop/...json)
  participant Repo as Repo source
  W->>H: read recent N outcomes
  W->>Repo: read MAX_CONSECUTIVE_REJECTS floor
  W->>W: observed > floor?
  alt regression
    W-->>Author: REJECT (rule N triggered)
    Author->>Repo: walk floor + Phase-N comment
    Author->>W: re-run
    W-->>Author: APPROVE
  else within floor
    W-->>Author: APPROVE
  end`,
    alternatives: [
      { name: 'Static thresholds', tradeoff: 'Wrong day 1; alert fatigue or silent drift; no learning' },
      { name: 'ML-based anomaly detection', tradeoff: 'Heavy; needs training data; black-box decisions; hard to audit' },
      { name: 'Manual SLO review', tradeoff: 'Slow; relies on operator memory; drift detected only at quarterly review' },
    ],
    challenges: [
      'Distinguishing real drift from noise (single spike vs cascade)',
      'Avoiding floor-creep where every miss walks the floor',
      'Documenting WHY a floor moved (rationale rot)',
      'Coordinating ratchets across parallel work streams',
    ],
    edgeCases: [
      { case: 'One-time outlier walks floor permanently', solution: 'Walk only after 3+ confirmed observations; otherwise REJECT and investigate' },
      { case: 'Two streams ratchet same floor concurrently', solution: 'ADR-022 convergent-work pattern; merge with EXACT measured value' },
      { case: 'Floor drifts so far it loses signal', solution: 'Periodic review — if floor=10 but historic max=5, walk back UP to add headroom' },
      { case: 'Stale-snapshot REJECT pollutes the floor', solution: 'Pre-commit hook 5F refreshes snapshot when drill_*.py is staged' },
    ],
    failureModes: [
      { mode: 'Floor walks every iteration', detect: 'Phase-comment density rising; operator asks "why again?"', recover: 'Pause the loop; root-cause; fix the cascade source' },
      { mode: 'Watcher never REJECTs', detect: 'Floor=∞ effectively; drift invisible', recover: 'Re-baseline floors against last 30-day history' },
      { mode: 'False-positive cascade from snapshot lag', detect: '3+ consecutive REJECTs all citing stale snapshot', recover: 'Pre-commit hook refresh; ADR-019 graceful degradation' },
    ],
    monitoring: [
      'documind_loop_drift_rate (rolling REJECT rate over last N commits)',
      'documind_loop_consecutive_rejects (current cascade length)',
      'documind_audit_iteration_latency (commits between feature + audit)',
      '/admin/monitoring drift panel',
    ],
    testing: [
      'drill_drift_rate_dashboard (locks both floors)',
      'drill_drift_volume_meta (separates KNOWN_* ratchets from DOMAIN_* categorization)',
      'drill_drill_status_freshness (catches stale-snapshot REJECT cascades)',
      'drill_adr020_audit_cadence (audit-latency SLO)',
    ],
    security: [
      'No PII in drift metrics — only commit shas + numeric counters',
      'Ratchet floors are public in source; no privacy concern',
      'Watcher rejection cannot exfiltrate data — REJECT is a binary flag',
    ],
    scaling: [
      '10x: ratchet read is O(1); scales with repo size for git-blame attribution',
      '100x: per-namespace ratchets to avoid global contention',
      'Cost driver: history depth scanned per drill (HISTORY_DEPTH=100 in current config)',
    ],
    maturity: {
      mvp: 'Manual SLO review + Slack alerts on threshold breach',
      production: 'Ratchet pattern in drill source + watcher REJECT + Phase-N rationale',
      enterprise: 'Cross-namespace ratchet coordination + ML-augmented forecast + auto-remediation runbook',
    },
    limitations: [
      'No automatic root-cause inference (operator must classify drift type)',
      'No predictive forecast of when next ratchet walk is due',
      'Cross-stream coordination is manual (operator delegates per ADR-018)',
    ],
    projectFit: [
      'mcp/tests/drill_drift_rate_dashboard.py — drift-rate ratchet',
      'mcp/tests/drill_drift_volume_meta.py — KNOWN/DOMAIN separation',
      'mcp/tests/drill_drill_status_freshness.py — stale-snapshot detector',
      'docs/architecture/adr/015-ratchet-pattern-for-discipline-drift.md — pattern definition',
      'docs/architecture/adr/021-pre-shipped-drill-audit-cadence.md — inverted cadence',
    ],
    interviewLine: 'AIOps in this codebase means thresholds are a function of recent reality, not a constant. Floors walk down (KNOWN_*) to match the observed worst case; the rationale lives in source comments, not in a wiki. When the metric crosses the floor, the watcher REJECTs the commit — so drift is impossible to hide.',
    implementationSteps: [
      { step: 'Define a ratchet floor in drill source', logic: 'KNOWN_X = observed_value with Phase-N comment.' },
      { step: 'Watcher reads floor + observation', logic: 'Loop watcher rule N: regression past floor → REJECT.' },
      { step: 'Operator walks floor with rationale', logic: 'Edit drill source; add Phase comment; re-run watcher.' },
      { step: 'Surface drift rate in dashboard', logic: 'Drill_drift_rate_dashboard exposes rolling rate; floors are first-class.' },
      { step: 'Detect cascade vs noise', logic: '3+ consecutive REJECTs = cascade; single REJECT = noise.' },
      { step: 'Audit floor moves in commit history', logic: 'Every walk has Phase-N + reason in commit message.' },
      { step: 'Drill the watcher itself', logic: 'drill_drift_volume_meta locks the floor-vs-ceiling distinction.' },
    ],
    codeExample: {
      language: 'python',
      code: `# mcp/tests/drill_drift_rate_dashboard.py — ratchet pattern in source

# Floor walked down empirically. Phase 7W set 0.50 from observed
# state at the time. Recent cascades dropped recent rate to 35%.
# Per ADR-015 ratchet: floor matches reality; future improvement
# above 50% is the goal, not a constraint.
MIN_APPROVE_RATE_RECENT = 0.35

# Floor matches observed historical max. Per ADR-015 ratchet
# pattern, the floor walks up with reality:
#   * Phase 7W (init): 5
#   * Phase 7VV: 6 — stale-snapshot cascade
#   * Phase 7WW: 8 — continued REJECTs during cadence iterations
#   * Phase 7YY (now): 10 — one more post-commit REJECT landed
# Future regressions to 11+ fire this assertion.
MAX_CONSECUTIVE_REJECTS = 10

def main() -> int:
    rate = compute_recent_approve_rate()
    if rate < MIN_APPROVE_RATE_RECENT:
        raise AssertionError(
            f"recent rate {rate:.2f} below floor {MIN_APPROVE_RATE_RECENT}; "
            f"either fix the cascade or walk the floor with rationale"
        )
    return 0`,
    },
    starStory: {
      situation: '3-REJECT-in-a-row cascades were appearing between phases without operator action. Static thresholds either fired on every cascade (alert fatigue) or never fired (drift hidden).',
      task: 'Self-tuning thresholds that match observed reality + force a rationale-bearing commit when drift is real.',
      action: 'Built ratchet pattern in drill source (KNOWN_* floors). Pre-commit hook refreshes snapshots when drill_*.py is staged. Each floor-walk requires a Phase-N comment with reason. ADR-015 documents the discipline.',
      result: 'Drift cascade root cause identified within 2 iterations every time. Operator sees the drift trail in source, not in scattered Slack threads. Floors converge toward observed worst case + 1 unit of headroom.',
    },
    interviewTraps: [
      'Static thresholds — "let\'s just alert at >5 REJECTs" (wrong day 1, wrong forever)',
      'Hidden ratchet decisions in PR comments instead of source (rationale rot)',
      'Walking floor without verifying drift is real (hides the cascade root cause)',
    ],
    finalScript: 'AIOps in this codebase is the ratchet pattern. Every operational threshold lives in drill source as a documented constant; every walk has a Phase-N rationale; the watcher REJECTs regressions past the floor. This is what makes drift detection self-tuning: when reality changes, the source code changes with it, and the rationale survives in git blame. ML-based anomaly detection would be a different bet — heavier, more flexible, less auditable. We chose auditability.',
  },
  {
    slug: 'llm-incident-summarization',
    title: '2. LLM-based incident summarization (planned)',
    status: 'planned',
    coreConcept: 'A retrieval-augmented summarizer that takes recent commits + drill REJECTs + alertmanager fires + trace samples and produces a 5-bullet incident narrative for the operator. Runs on cadence (every N commits or on first cascade detection).',
    problem: 'When 3+ REJECTs cascade, the operator must read 5+ files of drill output, git log, alertmanager noise, and trace samples to construct the timeline. AIOps should produce that timeline automatically; the operator should review, not assemble.',
    whyThisApproach: 'The advisory council pattern (sidecar) already exists with prompt registry + decision audit + scope-grant logging. An incident summarizer slots into the same scaffolding: prompt-versioned, audit-logged, citation-traced (every claim must point at a commit / drill output / trace ID).',
    whenToUse: ['Cascade detection (3+ consecutive REJECTs)', 'Multi-commit incident triage', 'Post-mortem first draft', 'On-call handoff brief'],
    whenNotToUse: ['Single-commit failures (operator can read the drill output)', 'Hard-stop releases (governance gate is binary; no narrative needed)', 'Real-time decisions (LLM latency dominates the 30-second response budget)'],
    input: 'time window (e.g. "last 12 commits") + scope (drill outputs / alertmanager fires / trace samples) + prompt template version',
    process: [
      'Detect trigger (3+ consecutive REJECTs OR cadence cron)',
      'Pull artifacts: drill outputs, git log, alertmanager fires, trace samples',
      'Construct prompt with citations to each artifact (chunk_id pattern from RAG)',
      'Run LLM via the council prompt registry (audit row mandatory per §38)',
      'Verify every claim cites a real artifact (hallucination guardrail)',
      'Surface narrative in /admin/aiops + post to alertmanager receiver',
    ],
    output: '5-bullet incident narrative with per-claim citations + audit row + cost trace.',
    flowchart: `flowchart LR
  trig[3+ REJECT cascade] --> pull[Pull artifacts]
  cron[Cadence cron] --> pull
  pull --> prompt[Build prompt with citations]
  prompt --> llm[LLM via council registry]
  llm --> guard{every claim cited?}
  guard -->|no| reject[Reject + flag hallucination]
  guard -->|yes| out[5-bullet narrative]
  out --> ui[/admin/aiops]
  out --> am[Alertmanager receiver]`,
    sequence: `sequenceDiagram
  autonumber
  participant Trig as Trigger
  participant AIOPS as AIOps service
  participant REG as Prompt registry
  participant LLM as LLM
  participant AM as Alertmanager
  Trig->>AIOPS: cascade detected
  AIOPS->>AIOPS: pull artifacts (commits + drills + alerts + traces)
  AIOPS->>REG: get prompt vN
  AIOPS->>LLM: render(prompt, artifacts)
  LLM-->>AIOPS: narrative + citations
  AIOPS->>AIOPS: verify each citation resolves
  alt all cited
    AIOPS->>AM: forward narrative
    AIOPS->>AIOPS: write audit row
  else hallucination
    AIOPS->>AIOPS: reject + flag
  end`,
    alternatives: [
      { name: 'Operator reads everything manually', tradeoff: 'Status quo; 30-min handoff; no LLM cost; high cognitive load' },
      { name: 'Rule-based timeline builder', tradeoff: 'Deterministic; no narrative; misses cross-artifact patterns' },
      { name: 'External AIOps SaaS (Datadog/Splunk)', tradeoff: 'Mature; expensive; cannot cite project-internal commits/drills' },
    ],
    challenges: [
      'Citation discipline (every claim must point at a real artifact)',
      'Prompt versioning under evolving artifact schemas',
      'Cost budget (LLM tokens per incident)',
      'Latency vs depth (30 seconds vs full multi-hop trace)',
    ],
    edgeCases: [
      { case: 'Artifacts contain secrets', solution: 'Pre-prompt redaction; never send raw env vars or auth tokens to LLM' },
      { case: 'LLM cites a commit that doesn\'t exist', solution: 'Citation-resolver guardrail; reject narrative; flag as hallucination' },
      { case: 'Cascade extends beyond LLM context window', solution: 'Map-reduce: per-commit summaries → meta-summary' },
      { case: 'Same incident triggers narrative twice', solution: 'Idempotency key on (trigger_event_id, prompt_version)' },
    ],
    failureModes: [
      { mode: 'Hallucination passes citation check', detect: 'Operator reads narrative; cited commit unrelated to claim', recover: 'Tighten verifier; add embedding-similarity check between claim + cited chunk' },
      { mode: 'Token cost spikes', detect: 'documind_aiops_cost_usd alert', recover: 'Map-reduce window; truncate trace samples; switch to cheaper model for first pass' },
      { mode: 'Trigger fires too often', detect: 'Cascade detection too sensitive', recover: 'Walk trigger threshold per ratchet pattern (topic 1)' },
    ],
    monitoring: [
      'documind_aiops_narratives_total{trigger,outcome}',
      'documind_aiops_citation_pass_rate',
      'documind_aiops_cost_usd (per narrative)',
      'documind_aiops_latency_seconds_p95',
    ],
    testing: [
      'drill_aiops_citation_resolver (no hallucinated commits)',
      'drill_aiops_redaction (no secrets in prompt)',
      'drill_aiops_idempotency (same trigger → same narrative)',
    ],
    security: [
      'Pre-prompt redaction of secrets/PII (mandatory per §48 explainability)',
      'Audit row per narrative (prompt_version + model_version + cost_tokens)',
      'Citation trail makes every claim reproducible',
    ],
    scaling: [
      '10x: per-tenant prompt registries; cost budget per tenant',
      '100x: streaming narrative generation; map-reduce for long windows',
      'Cost driver: artifact volume per cascade; truncate aggressively',
    ],
    maturity: {
      mvp: 'Operator reads drill output manually + git log',
      production: 'PLANNED — citation-traced LLM narrative on cascade trigger',
      enterprise: 'Cross-service incident correlation + auto-remediation runbook proposal',
    },
    limitations: [
      'NOT YET SHIPPED — requires sidecar prompt-registry to support new prompt class',
      'No auto-remediation — narrative + operator action only',
      'Single-LLM dependency; fallback model not yet specified',
    ],
    projectFit: [
      'services/sidecar-advisor/* — existing prompt registry to slot into',
      'docs/architecture/adr/021-pre-shipped-drill-audit-cadence.md — cadence trigger pattern',
      '/admin/aiops/deep — this page (planning surface)',
      'Future: services/aiops-summarizer/ + drill_aiops_*.py catalog',
    ],
    interviewLine: 'AIOps incident summarization is a planned next-step. The scaffolding is already in place — the council\'s prompt registry, the audit row schema (§38), the citation-traced retrieval (RAG §39). What\'s missing is the trigger + the prompt class. The bet: citation discipline makes hallucination detectable; without that, an LLM narrative is just plausible-sounding noise.',
    implementationSteps: [
      { step: 'Trigger source', logic: 'Reuse cascade detector from topic 1 (3+ REJECTs) + cadence cron.' },
      { step: 'Artifact puller', logic: 'Read git log + drill outputs + alertmanager fires + trace IDs in time window.' },
      { step: 'Citation-aware prompt', logic: 'Each artifact gets a chunk_id; LLM must cite by chunk_id in narrative.' },
      { step: 'Citation verifier', logic: 'Post-LLM, parse citations; resolve each to a real artifact; fail if any miss.' },
      { step: 'Audit row write', logic: 'prompt_version + model_version + cost_tokens + cited chunk_ids per narrative.' },
      { step: 'Surface narrative', logic: '/admin/aiops shows last 10 narratives with full citation trail expandable.' },
      { step: 'Drill the path', logic: '3 drills: citation-resolver, redaction, idempotency.' },
    ],
    codeExample: {
      language: 'python',
      code: `# services/aiops-summarizer/app/summarizer.py — PLANNED skeleton
from dataclasses import dataclass

@dataclass
class IncidentArtifact:
    chunk_id: str  # commit_sha / drill_output_id / trace_id
    kind: str      # "commit" / "drill" / "alert" / "trace"
    content: str

def build_narrative(artifacts: list[IncidentArtifact],
                    prompt_version: str,
                    model: str) -> dict:
    """Returns {narrative, citations[chunk_id], audit_row}."""
    prompt = render_template(prompt_version, artifacts)
    response = llm.generate(prompt, model=model)
    citations = parse_citations(response.text)
    # Citation discipline: every claim must cite a chunk_id
    for c in citations:
        if c.chunk_id not in {a.chunk_id for a in artifacts}:
            raise CitationError(f"hallucinated chunk: {c.chunk_id}")
    return {
        "narrative": response.text,
        "citations": citations,
        "audit_row": {
            "prompt_version": prompt_version,
            "model_version": model,
            "cost_tokens": response.usage.total_tokens,
            "cited_chunks": [c.chunk_id for c in citations],
        },
    }`,
    },
    starStory: {
      situation: 'Cascade triage takes 30 minutes per incident. The operator reads drill outputs, git log, alertmanager fires, and trace samples to construct a timeline. The cognitive load makes incident response slow.',
      task: 'Auto-generate a 5-bullet narrative with per-claim citations on cascade trigger, without inventing facts.',
      action: 'PLANNED. Slot into sidecar prompt registry; reuse council audit-row schema; add citation-resolver guardrail. Three drills: citation, redaction, idempotency.',
      result: 'NOT YET SHIPPED. When live: 30-min triage → 30-second review of pre-built narrative.',
    },
    interviewTraps: [
      'LLM narrative without citation discipline (plausible-sounding hallucinations)',
      'No audit row (decision irreproducible; §38 violation)',
      'Sending raw artifacts to LLM (secrets leak; §48 violation)',
    ],
    finalScript: 'AIOps incident summarization is a citation-traced LLM applied to operational artifacts. The scaffolding (prompt registry, audit row, redaction) already exists; the missing piece is the prompt class + citation verifier. Hallucination is the failure mode; citation discipline is the defence. Three drills lock that contract: citation-resolver (no hallucinated commits), redaction (no secrets in prompt), idempotency (same trigger → same narrative). Without those, the narrative is just noise.',
  },
  {
    slug: 'otel-everywhere-tool-coverage',
    title: '3. OpenTelemetry must link with every tool (per-tool span coverage)',
    status: 'partial',
    coreConcept:
      'Every tool, MCP server, agent, and retrieval / inference call emits OTel spans tagged with the canonical request_id baggage. Spans land in the OTel collector and propagate to Jaeger + Langfuse so a single correlation_id traces the full execution graph: API Gateway → Coordinator (Hub) → Specialist Agent → Tool Call → Retrieve → LLM → Council Review → HITL. Without per-tool span coverage, the audit row is a tombstone — you can prove a decision happened but cannot reconstruct WHY it took the path it did.',
    problem:
      'Per §47.6 + §48, every AI decision must be reproducible from the trace alone. Today the OTel collector runs (helm release shipped), Jaeger renders the span tree, Langfuse covers the LLM-specific layer — but rag_inference.py has 0 direct OTel refs (verified empirically), most MCP servers do not emit per-tool-call spans, and the Hybrid Architect just shipped without per-step OTel spans (only Langfuse). Result: the trace tree on a real request is patchy. Some hops show as spans; others are inferred from logs. An auditor cannot reconstruct the full path in minutes.',
    whyThisApproach:
      'OTel as the unifying telemetry standard means one wire format for every emitter. Adding it tool-by-tool keeps each integration small (one decorator + one trace.start_as_current_span call) without rewriting the world. The request_id propagation contract means downstream services see the same span context the gateway saw. Langfuse and Jaeger consume the same OTLP stream — one wire, two views.',
    whenToUse: [
      'Every new tool added to the MCP fleet (instrument BEFORE merge)',
      'Every new agent role added to the council',
      'Every new retrieval path (vector / graph / hybrid / cache)',
      'Every external API call from inside an agent',
      'Every breaker / fallback path (so the audit shows why fallback fired)',
    ],
    whenNotToUse: [
      'Pure-static utilities (formatters, validators) — span overhead exceeds work cost',
      'Hot tight loops inside a single span (sample, do not span-per-iteration)',
      'Already-spanned code paths (no double-instrumentation)',
    ],
    input:
      'OTel SDK + collector endpoint (OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318) + the request_id baggage from the gateway',
    process: [
      '1. SDK init: each service registers the OTLP exporter at startup; service.name attribute set to the service name',
      '2. Span emission: every public entrypoint opens a top-level span; nested calls open child spans via context propagation',
      '3. Attribute discipline: each span MUST carry request_id, tenant_id, actor, tool, latency_ms, outcome (per §57.6 canonical fields)',
      '4. Baggage propagation: request_id flows through HTTP headers + Kafka headers + gRPC metadata so the trace tree stays connected across service boundaries',
      '5. Sampling policy: head-based sampling for normal traffic; tail-based always-keep for errors / outcome=failed',
      '6. Drill: every new tool ships with a drill that asserts at least one span is emitted with the canonical attributes',
    ],
    output:
      'A connected span tree per request, queryable by correlation_id in Jaeger AND Langfuse. The audit row references the trace_id; clicking it surfaces the full execution graph.',
    flowchart: `flowchart LR
  user[User Request] --> gw[API Gateway: open root span]
  gw --> coord[Coordinator span: hybrid_architect.process]
  coord --> hub[Hub span: agent_cli.run_council]
  coord --> council[Council span: council_engine.run_council]
  hub --> tool1[MCP tool span: kubectl.list_pods]
  hub --> tool2[MCP tool span: github.search_issues]
  council --> agent1[Agent span: primary_expert.run_role]
  council --> agent2[Agent span: opponent.run_role]
  tool1 --> ret[Retrieve span: vector + graph]
  ret --> llm[LLM span: ollama.generate]
  llm --> coll[OTel Collector]
  coord --> coll
  coll --> jg[Jaeger UI]
  coll --> lf[Langfuse UI]
  jg --> ops[Ops dashboard]
  lf --> ops`,
    alternatives: [
      { name: 'Logs only', tradeoff: 'No span tree; correlation requires grep + timestamps; audit reconstruction takes hours not minutes' },
      { name: 'Vendor APM (Datadog / New Relic)', tradeoff: 'Per-host pricing scales badly; vendor lock-in; closed wire format' },
      { name: 'Per-tool custom telemetry', tradeoff: 'N tools × N tracking systems; nothing connects across tool boundaries' },
    ],
    challenges: [
      'Bolting OTel onto a service that started without it (refactor cost)',
      'Avoiding span explosion (one span per row in a list = useless)',
      'Sampling that keeps errors but reduces volume (head sampling alone drops failures)',
      'Cross-runtime baggage (Python ↔ Node ↔ Go all need correct context propagation)',
      'Cost: every span = bytes through the collector + Jaeger storage',
    ],
    edgeCases: [
      { case: 'Tool error before span open → no span at all', solution: 'Open the span in a context manager BEFORE the tool call; record exception on the span' },
      { case: 'Async call leaks context across event-loop boundaries', solution: 'Use OTel async context propagators; never copy baggage manually' },
      { case: 'Span attribute exceeds size limit', solution: 'Truncate to ≤256 bytes; log full value; reference log_id in span attribute' },
    ],
    failureModes: [
      { mode: 'Spans drop because collector is unreachable', detect: 'Jaeger query returns empty for a known-active request_id', recover: 'OTel SDK has retry + buffer; add circuit-breaker around exporter so emitter survives collector outage' },
      { mode: 'request_id baggage truncated by intermediate proxy', detect: 'Trace tree splits — root span has no children visible', recover: 'Verify trust list on every proxy + load balancer; add a drill that asserts cross-service propagation' },
      { mode: 'Sampling too aggressive — error trace missing', detect: 'Audit row references trace_id that returns 404 in Jaeger', recover: 'Tail-based always-keep sampler for outcome ∈ {failed, denied, timeout}' },
    ],
    monitoring: [
      'Live integrations panel (this page → /admin/monitoring → IntegrationsHealth shows OTel collector reachability)',
      'Per-service span count rate in Grafana (sudden drop = emitter broken)',
      'Span duration histogram per tool (regression detection)',
      'Trace completeness rate (root spans / leaf spans ratio over a sample window)',
    ],
    testing: [
      'drill_otel_actor_outcome_attrs.py — locks the canonical span attributes (request_id / tenant_id / actor / tool / outcome)',
      'drill_guardrail_otel_attributes.py — locks span attributes for guardrail decisions',
      'drill_circuit_breaker_observability.py — locks breaker → OTel emission path',
      'drill_observability_stack_provisioning.py — locks the stack itself is up',
      'drill_aiops_deep_otel_topic.py — this topic exists with status=partial + lists canonical tool inventory (locked)',
    ],
    finalScript:
      'OTel coverage is a per-tool obligation, not a platform feature. Every new tool that lands without a drill asserting it emits the canonical span attributes is technical debt with a half-life of days — the day someone needs the trace, it will be gone. The infrastructure is ready (collector + Jaeger + Langfuse all running). What is missing is the discipline: every PR that adds a tool MUST also add the OTel emission and a drill that locks it. The status here is "partial" until that discipline is enforced at PR-review time.',
  },
];

export default function AiopsDeepPage() {
  return (
    <>
      <div className="page-header">
        <div className="page-header-copy">
          <h1 className="section-title">AIOps deep dive</h1>
          <p className="page-subtitle">
            Two surfaces — autonomous drift detection (shipped, ratchet
            pattern) and LLM incident summarization (planned, citation-traced
            narrative) — explained through the universal 20-dimension
            framework.
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
          { href: '/admin/breakers/deep', label: 'Circuit breakers', why: 'breaker-open rate is one of the metrics the ratchet pattern tracks; cascade detection composes here' },
          { href: '/admin/monitoring', label: 'Monitoring + health', why: 'AIOps drift detectors surface in the same panels; this page explains the ratchet that drives them' },
          { href: '/admin/forensics', label: 'Forensics (trace → draft → audit → HITL)', why: 'incident summarization narratives must thread the same correlation_id pipe forensics relies on' },
          { href: '/admin/explainability/deep', label: 'Explainability evidence', why: 'every LLM narrative must produce a §48 audit row with citations + prompt + model version' },
          { href: '/admin/checklist/deep#governance-ops-checklist', label: 'Governance gate', why: 'an AIOps narrative without citation discipline = release blocked per §38 hallucination guardrail' },
        ]}
      />
    </>
  );
}
