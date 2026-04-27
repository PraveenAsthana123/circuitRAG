'use client';

/**
 * Distributed tracing + baggage propagation (deep dive).
 *
 * Two topics: W3C Trace Context + Baggage propagation across service
 * boundaries (the chain that survives every hop), and the "trace →
 * draft → audit" linkage by correlation_id (the operator forensics
 * pattern that turns logs from "noise" into "story").
 */

import DeepDiveCrossRefs from '../../../../components/DeepDiveCrossRefs';
import UniversalDeepDive, { type Topic } from '../../../../components/UniversalDeepDive';

const TOPICS: Topic[] = [
  // ═══════════════════════════════════════════════════════════════
  // TOPIC 1 — W3C Trace Context + Baggage propagation
  // ═══════════════════════════════════════════════════════════════
  {
    slug: 'baggage-propagation',
    title: '1. Baggage propagation — chain of trust across service hops (W3C trace context + baggage)',
    status: 'shipped',
    coreConcept:
      'Distributed tracing without baggage = traces but no context. The W3C `traceparent` header chains spans across services so Jaeger renders one timeline; the W3C `baggage` header carries business context (tenant_id, user_id, request_id, feature_flag) so every downstream service + log line sees the same identifiers WITHOUT plumbing parameters through every function. Default OTel propagator is tracecontext-only — baggage is OFF until a CompositePropagator wires it in. Forgetting this is the most common gap in "we have OTel" deployments.',
    oneLiner: 'traceparent chains spans. baggage chains business context. CompositePropagator wires both. Default = tracecontext-only.',
    businessContext:
      'Operator pages: "user X says checkout slow at 14:02 UTC". Without baggage, the trace exists but tenant_id is on the edge service only — the inference span has no idea which tenant. Adding baggage = every span across every service is filterable by tenant_id; the 7-hop trace becomes one Jaeger query.',
    fiveW: {
      what: 'Two W3C HTTP headers — `traceparent` (trace context) and `baggage` (business context) — propagated automatically across every outbound call by CompositePropagator + HTTPXClientInstrumentor.',
      why: 'A trace without business context is a stack of timestamps. Baggage threads tenant_id / user_id / request_id through every hop so logs + metrics + alerts can be filtered consistently.',
      where: 'Every microservice. Every Kafka producer/consumer. Every async worker that does outbound calls.',
      when: 'On day 1. Retrofitting later means every service log + every span needs a backfill mapping table.',
      who: 'Platform team owns server_common.setup_server_otel; product teams call baggage_set at the request boundary.',
    },
    interview30s:
      'Distributed tracing has two headers: traceparent chains spans across services so Jaeger shows one timeline; baggage carries business context — tenant_id, user_id, request_id — across every hop. Default OTel propagator is tracecontext-only; you have to wire CompositePropagator(TraceContext + Baggage) explicitly. Then HTTPXClientInstrumentor auto-injects both on every outbound call. The result: a 7-hop trace renders as one Jaeger query, filterable by tenant. Without baggage you have spans but no context.',
    hld: `flowchart LR
  Edge[API gateway] --> Auth[identity-svc]
  Auth --> Ret[retrieval-svc]
  Ret --> Embed[embedder]
  Ret --> Vec[vector DB]
  Ret --> Inf[inference-svc]
  Inf --> LLM[Ollama or Bedrock]
  Inf --> Aud[audit log]
  Edge --> Bag[baggage: tenant_id user_id request_id]
  Bag -.propagated.-> Auth
  Bag -.propagated.-> Ret
  Bag -.propagated.-> Inf
  Bag -.propagated.-> Aud`,
    flowchart: `flowchart TD
  Req[Inbound HTTP request] --> Extract[FastAPIInstrumentor extracts traceparent + baggage]
  Extract --> Span[Start span svc-A.handle_request]
  Span --> Set[baggage_set tenant_id and user_id]
  Set --> Out[Outbound httpx call]
  Out --> Inject[HTTPXClientInstrumentor injects traceparent + baggage]
  Inject --> Wire[HTTP request to svc-B]
  Wire --> SvcB[svc-B FastAPIInstrumentor extracts]
  SvcB --> SpanB[svc-B span - parent span svc-A.handle_request]
  SpanB --> SeeBaggage[svc-B sees tenant_id and user_id]`,
    sequence: `sequenceDiagram
  participant Edge as api-gateway
  participant A as identity-svc
  participant B as retrieval-svc
  participant C as inference-svc
  Edge->>A: HTTP traceparent + baggage tenant=acme
  Note over A: extract → ctx; baggage tenant=acme attached
  A->>B: HTTP traceparent child + baggage tenant=acme
  Note over B: span parent of A; baggage available in logs
  B->>C: HTTP traceparent child + baggage tenant=acme
  Note over C: same trace_id; same tenant_id; one Jaeger query`,
    coreLayers: [
      { layer: 'Propagator', responsibility: 'CompositePropagator(TraceContext + Baggage). Without this, baggage header is NEVER emitted.' },
      { layer: 'Inbound', responsibility: 'FastAPIInstrumentor extracts traceparent + baggage from headers; attaches to context.' },
      { layer: 'Business', responsibility: 'Service code calls baggage_set("tenant_id", ...) at request boundary.' },
      { layer: 'Outbound', responsibility: 'HTTPXClientInstrumentor auto-injects both headers on every httpx call.' },
      { layer: 'Async / Kafka', responsibility: 'Manual inject into Kafka headers + extract on consumer side.' },
      { layer: 'Logging', responsibility: 'Log formatter pulls baggage_get_all() into every log record.' },
    ],
    lld: `classDiagram
  class CompositePropagator {
    +propagators: TextMapPropagator[]
    +inject(carrier)
    +extract(carrier) Context
  }
  class TraceContextTextMapPropagator
  class W3CBaggagePropagator
  class HTTPXClientInstrumentor {
    +instrument()
    +uninstrument()
  }
  class FastAPIInstrumentor {
    +instrument_app(app)
  }
  CompositePropagator --> TraceContextTextMapPropagator
  CompositePropagator --> W3CBaggagePropagator`,
    coreBuildingBlocks: [
      'CompositePropagator with TraceContextTextMapPropagator + W3CBaggagePropagator',
      'set_global_textmap() at process startup (idempotent)',
      'FastAPIInstrumentor.instrument_app() — inbound extract',
      'HTTPXClientInstrumentor().instrument() — outbound inject',
      'baggage_set / baggage_get / baggage_get_all helpers',
      'inject_propagation_headers / extract_propagation_context for non-httpx paths (Kafka, raw clients)',
      'Log formatter that pulls baggage_get_all() into every log',
    ],
    architectureRelevance: {
      backend: 'Universal — any service that talks to another service.',
      rag: 'Critical: 5–7 hops (gateway → identity → retrieval → embedder → vector → inference → LLM). Without baggage, each hop is a black box.',
      ai: 'Tenant-scoped cost + token tracking only works if tenant_id rides on every span.',
      microservices: 'The single highest-leverage observability investment.',
    },
    problem:
      'Trace exists but business context lives only on the edge service. To correlate a tenant complaint to a downstream span, operator must join logs by request_id which itself wasn\'t propagated. MTTR balloons.',
    whyThisApproach:
      'W3C-standard headers + auto-instrumentation = zero code change after wiring. Every existing httpx call inherits the context for free. Cross-language interop guaranteed (Java / Go / .NET / Python all honor the same headers).',
    whenToUse: [
      'Any system with > 1 service',
      'Any AI / RAG pipeline',
      'Any multi-tenant SaaS',
      'Any system with audit / compliance requirement',
    ],
    whenNotToUse: [
      'Pure single-process monolith (use logging context vars instead)',
      'Throwaway scripts',
    ],
    input: 'OTel SDK + propagator config + instrumentation packages.',
    process: [
      'Wire CompositePropagator(TraceContext + Baggage) at startup',
      'Auto-instrument FastAPI (inbound) + httpx (outbound)',
      'At request boundary: baggage_set("tenant_id", ...) + baggage_set("request_id", ...)',
      'All downstream httpx calls auto-inject both headers',
      'Downstream services auto-extract on inbound; their spans become children of the upstream span',
      'Log formatter pulls baggage_get_all() into every log record',
      'For Kafka / RabbitMQ: inject_propagation_headers into message headers; extract on consumer side',
    ],
    output: 'One Jaeger trace_id covering N hops + baggage values on every span + filterable logs by tenant_id.',
    implementationSteps: [
      { step: 'Wire CompositePropagator', logic: 'set_global_textmap(CompositePropagator([TraceContext, W3CBaggage])) at startup. Default is TraceContext only — baggage will not work without this.' },
      { step: 'Instrument FastAPI', logic: 'FastAPIInstrumentor.instrument_app(app). Extracts headers → context on every request.' },
      { step: 'Instrument httpx', logic: 'HTTPXClientInstrumentor().instrument() once at startup. Idempotent. Every existing httpx.AsyncClient inherits.' },
      { step: 'Set baggage at boundary', logic: 'In auth middleware: baggage_set("tenant_id", token.tenant). Now every downstream call sees it.' },
      { step: 'Pull baggage into logs', logic: 'Custom log filter: record.baggage = baggage_get_all(). JSON formatter renders as fields.' },
      { step: 'Manual Kafka path', logic: 'Producer: inject_propagation_headers(msg.headers). Consumer: extract_propagation_context(msg.headers) before handler.' },
      { step: 'Cap baggage size', logic: '< 8 entries, < 1 KB total. Each adds bytes to every outbound request.' },
      { step: 'Forbid PII / secrets', logic: 'Baggage is plaintext header. Never put PII or secrets — use opaque IDs.' },
    ],
    codeExample: {
      language: 'python',
      code: `# mcp/server_common.py — propagator + helper wiring
from opentelemetry import baggage as _otel_baggage
from opentelemetry import context as _otel_context
from opentelemetry.baggage.propagation import W3CBaggagePropagator
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.propagate import set_global_textmap, inject, extract
from opentelemetry.propagators.composite import CompositePropagator
from opentelemetry.trace.propagation.tracecontext import (
    TraceContextTextMapPropagator,
)

def setup_server_otel(app, service_name: str) -> None:
    # ... TracerProvider + OTLP exporter wiring elsewhere ...

    # CRITICAL: default OTel propagator is tracecontext-only.
    # Without this set_global_textmap, baggage header is never emitted.
    set_global_textmap(CompositePropagator([
        TraceContextTextMapPropagator(),
        W3CBaggagePropagator(),
    ]))

    FastAPIInstrumentor.instrument_app(app)            # inbound extract
    HTTPXClientInstrumentor().instrument()             # outbound inject

# Helpers that callers use at the request boundary
def baggage_set(key: str, value: str):
    ctx = _otel_baggage.set_baggage(key, value)
    return _otel_context.attach(ctx)

def baggage_get(key: str) -> str | None:
    val = _otel_baggage.get_baggage(key)
    return None if val is None else str(val)

def inject_propagation_headers(headers: dict[str, str]) -> dict[str, str]:
    inject(headers)   # writes traceparent + baggage
    return headers

def extract_propagation_context(headers: dict[str, str]):
    ctx = extract(headers)
    return _otel_context.attach(ctx)


# Application code — set baggage at the request boundary once.
# Every downstream call inherits it for free.
@app.middleware("http")
async def attach_business_context(request, call_next):
    # auth already populated request.state.tenant_id, request.state.user_id
    baggage_set("tenant_id", request.state.tenant_id)
    baggage_set("user_id", request.state.user_id)
    baggage_set("request_id", request.headers.get("x-request-id", str(uuid.uuid4())))
    return await call_next(request)


# Kafka path — inject manually since Kafka isn't auto-instrumented
async def emit_event(producer, topic: str, payload: dict):
    headers: dict[str, str] = {}
    inject_propagation_headers(headers)
    kafka_headers = [(k, v.encode()) for k, v in headers.items()]
    await producer.send(topic, value=payload, headers=kafka_headers)

# Kafka consumer side
async def consume(msg):
    incoming = {k: v.decode() for k, v in (msg.headers or [])}
    token = extract_propagation_context(incoming)
    try:
        await handler(msg.value)   # baggage_get("tenant_id") works inside
    finally:
        if token:
            _otel_context.detach(token)


# Log formatter — pull baggage into every log line
import logging, json
class BaggageFilter(logging.Filter):
    def filter(self, record):
        from mcp.server_common import baggage_get_all
        record.baggage = baggage_get_all()
        return True

# In JSON formatter, baggage becomes a top-level field on every log.`,
    },
    realUseCase:
      'Operator: "tenant acme-prod p95 spiked at 14:02". With baggage: one Jaeger query (`baggage.tenant_id=acme-prod`) over 14:00–14:05 surfaces the slow span (LLM hop, 4.2s). Without baggage: 5 services × log search × manual request_id correlation = 30 min minimum. With baggage = 90 seconds.',
    prosCons: {
      pros: [
        'Single Jaeger query renders 7-hop trace',
        'Logs filterable by tenant_id consistently',
        'Cross-language compatible (W3C standard)',
        'Zero code change after wiring',
        'Foundation for tenant-scoped cost / token rollups',
      ],
      cons: [
        'Adds bytes to every outbound request header (~80–200 B typical)',
        'Plaintext — no PII / secrets',
        'Requires explicit propagator wiring (default is tracecontext-only)',
        'Kafka path needs manual inject/extract',
      ],
    },
    limitations: [
      'Total HTTP header budget ~8 KB — proxies (NGINX, HAProxy) cap',
      'Each baggage entry adds bytes; keep < 8 entries, < 1 KB total',
      'Async tasks NOT spawned via the framework lose context unless you propagate manually',
      'Subprocesses do NOT inherit OTel context',
    ],
    comparison: {
      left: 'Trace context only',
      right: 'Trace context + Baggage',
      rows: [
        { aspect: 'Span chain', left: 'Yes', right: 'Yes' },
        { aspect: 'Business context propagation', left: 'No', right: 'Yes' },
        { aspect: 'Tenant-filterable trace search', left: 'Edge only', right: 'Every hop' },
        { aspect: 'Logs by tenant', left: 'Per-service join', right: 'Single field everywhere' },
        { aspect: 'Header size', left: '~50 B', right: '~150 B typical' },
      ],
    },
    challenges: [
      'Forgetting set_global_textmap — silent failure (no baggage header emitted)',
      'Setting baggage AFTER spawning the outbound call (set must happen before)',
      'Async task escapes context (use contextvars / OTel context.copy)',
      'Header size growth as more entries are added',
      'Kafka headers — easy to forget the manual inject/extract',
    ],
    edgeCases: [
      { case: 'Async task spawned outside request scope', solution: 'context.copy() before scheduling; otherwise baggage is empty in the task' },
      { case: 'Subprocess called', solution: 'Manual inject into env vars; extract in subprocess via parser' },
      { case: 'Non-ASCII baggage value', solution: 'OTel auto percent-encodes per W3C; never pass raw multibyte UTF-8' },
      { case: 'Header size > proxy limit', solution: 'Drop low-value entries; use opaque IDs instead of full names' },
      { case: 'PII accidentally in baggage', solution: 'Block list in the helper; reject baggage_set("email", ...) at the API level' },
    ],
    solutions: [
      { problem: 'No baggage header emitted', solution: 'Wire CompositePropagator with W3CBaggagePropagator explicitly' },
      { problem: 'Inconsistent tenant_id across services', solution: 'Set in auth middleware once; auto-propagates everywhere' },
      { problem: 'Kafka loses context', solution: 'Manual inject/extract on producer + consumer' },
      { problem: 'Logs not tenant-filterable', solution: 'BaggageFilter pulls baggage into every log record' },
      { problem: 'Header bloat', solution: 'Cap entries; document allowed keys per service' },
    ],
    bestPractices: {
      do: [
        'Wire CompositePropagator at startup',
        'Auto-instrument FastAPI + httpx',
        'Set baggage in auth middleware once',
        'Use opaque IDs (uuid, hashed)',
        'Pull baggage into log formatter',
        'Drill propagation per release',
      ],
      avoid: [
        'PII in baggage',
        'Secrets in baggage',
        'More than 8 entries (header bloat)',
        'Setting baggage AFTER outbound call',
        'Skipping the propagator wire (silent fail)',
      ],
      optimize: [
        'Document allowed baggage keys per service',
        'Cap baggage size in middleware',
        'Sample high-cardinality keys',
      ],
    },
    antiPatterns: [
      'Adding tenant_id manually to every function signature',
      'Joining logs across services by timestamp',
      'Trusting "we have OTel" without checking propagator config',
      'PII in baggage values',
      'Forgetting Kafka manual inject/extract',
    ],
    testing: ['Unit: round-trip baggage_set / baggage_get', 'Integration: full inject → carrier → extract chain', 'Drill: cross-service real httpx call', 'Negative: skip extract = zero baggage'],
    testTypes: ['Unit', 'Drill (W3C contract)', 'Integration (cross-service)', 'Chaos (header size limit)'],
    testScenarios: [
      { scenario: 'svc-A baggage_set("tenant", "acme") → svc-B baggage_get("tenant")', expected: 'svc-B reads "acme" via auto-extract' },
      { scenario: 'svc-B did not call extract', expected: 'baggage_get returns None — W3C contract' },
      { scenario: 'Non-ASCII baggage value', expected: 'Percent-encoded in header (RFC 7230 ASCII)' },
      { scenario: 'Child context baggage', expected: 'Does NOT leak to parent context' },
    ],
    testData: [
      { type: 'Real fixture', example: 'tenant_id=acme-prod, user_id=u-42, request_id=req-uuid' },
      { type: 'Edge fixture', example: 'tenant_id=東京 (UTF-8 percent-encoding test)' },
    ],
    debuggingChecklist: [
      'set_global_textmap actually called?',
      'CompositePropagator includes W3CBaggagePropagator?',
      'HTTPXClientInstrumentor instrumented?',
      'Auth middleware sets baggage BEFORE outbound calls?',
      'Inbound service has FastAPIInstrumentor?',
      'Log formatter pulling baggage_get_all()?',
      'Header size under proxy limit?',
    ],
    productionIssues: [
      { issue: 'Logs not tenant-filterable in inference-svc', rootCause: 'Edge service set baggage but never wired propagator → header dropped at hop 1' },
      { issue: 'Kafka events have no trace context', rootCause: 'Manual inject/extract not wired; only httpx is auto' },
      { issue: 'Subprocess in batch worker loses context', rootCause: 'Subprocess does NOT inherit OTel context; pass via env vars' },
      { issue: 'Async task spawned via asyncio.create_task missing baggage', rootCause: 'context.copy() needed at spawn site' },
    ],
    security: [
      'NEVER put PII in baggage (plaintext header)',
      'NEVER put secrets / tokens in baggage',
      'Block list in helper API (reject baggage_set("email") at API)',
      'Audit baggage keys quarterly',
    ],
    performance: [
      'Inject + extract: single-digit microseconds per call',
      'Header size: ~150 B typical, < 1 KB cap',
      'Zero allocation overhead beyond header construction',
    ],
    costConsiderations: [
      'Network: ~150 B per request × QPS × 24h = small but real',
      'Proxy / load balancer header processing — measure under load',
      'Storage in span attributes if you also log baggage (Jaeger storage)',
    ],
    scaling: [
      'Header budget caps at proxy limit (8 KB typical for NGINX)',
      'Cap baggage entries to 8 per service surface',
      'Drop low-value entries before fanout to high-volume downstream',
    ],
    observability: [
      'Jaeger filter by `baggage.tenant_id`',
      'Log query by tenant_id everywhere',
      'Prometheus metric labels include baggage values (low-cardinality only)',
      'Alert: baggage header MISSING (propagator wiring regression)',
    ],
    metrics: [
      { name: 'baggage_header_present_ratio', example: '0.998 — should be ~1.0; below = wiring regression' },
      { name: 'baggage_header_size_bytes_p95', example: '180' },
      { name: 'trace_propagation_failure_count', example: '0 — incremented when extract fails' },
    ],
    failureModes: [
      { mode: 'Propagator never wired', detect: 'No baggage header in tcpdump / proxy log', recover: 'Add set_global_textmap call at startup' },
      { mode: 'Header dropped by proxy', detect: 'svc-A inject succeeds but svc-B extract sees nothing', recover: 'Check proxy header pass-through config' },
      { mode: 'Async task missing context', detect: 'Task logs have empty baggage', recover: 'context.copy() at spawn site' },
      { mode: 'PII leak', detect: 'Code review or dynamic block-list', recover: 'Block list + alert on rejected key' },
    ],
    tradeoffs: [
      { decision: 'Auto-instrument vs manual', tradeoff: 'Auto = zero code change but instruments every httpx; manual = explicit but verbose' },
      { decision: 'Baggage in logs', tradeoff: 'Filterability + storage cost' },
      { decision: 'Sampling', tradeoff: '100% baggage with sampled traces; or sampled both — pick based on incident-debug needs' },
    ],
    decisionMatrix: [
      { option: 'Tracecontext only', whenToUse: 'Single-tenant non-AI single service (rare)' },
      { option: 'Tracecontext + Baggage', whenToUse: 'Default for any production microservice' },
      { option: 'Custom propagator', whenToUse: 'Pre-W3C legacy systems (Zipkin B3) — convert at boundary' },
    ],
    starStory: {
      situation: 'Operator paged: "tenant acme-prod p95 spiked at 14:02; LLM hop slow". Trace visible but tenant_id only on edge service.',
      task: 'Restore tenant-filterable observability across all 7 hops.',
      action: 'Wired CompositePropagator(TraceContext + Baggage) in server_common; auto-instrumented httpx; pulled baggage_get_all() into JSON log formatter. Added drill: 8 steps including 3 negative assertions (no extract = no baggage; non-ASCII percent-encoded; child context isolated).',
      result: 'One Jaeger query (baggage.tenant_id=acme-prod) renders all 7 hops. MTTR for tenant-scoped incidents: 30 min → 90 sec. Zero PII leak risk via block list.',
    },
    interviewTraps: [
      'Saying "we have OTel" without checking propagator config',
      'Forgetting tracecontext-only is the OTel default',
      'No mention of HTTPX auto-instrumentation',
      'No mention of Kafka manual inject/extract',
      'PII in baggage values',
    ],
    finalScript:
      'CompositePropagator(TraceContext + Baggage) at startup. FastAPI + httpx auto-instrumented. baggage_set in auth middleware. Log formatter pulls baggage_get_all. Kafka via manual inject/extract. Result: one Jaeger query covers N hops; logs filterable by tenant everywhere. Default OTel is tracecontext-only — easy to miss; drill it.',
    alternatives: [
      { name: 'Tracecontext only', tradeoff: 'No business context propagation; manual joins everywhere' },
      { name: 'Custom HTTP header (X-Tenant-ID)', tradeoff: 'Works but no W3C interop; fragile across teams' },
      { name: 'Zipkin B3', tradeoff: 'Pre-W3C; convert at boundary if legacy' },
    ],
    monitoring: [
      'baggage_header_present_ratio metric (target ~1.0)',
      'Alert when ratio drops (propagator regression)',
      'Jaeger queries by baggage.tenant_id',
      'Log queries by baggage.tenant_id everywhere',
    ],
    maturity: {
      mvp: 'Tracecontext + Baggage wired; auth middleware sets tenant_id',
      production: 'Add log formatter integration + Kafka manual + drill',
      enterprise: 'Block list for PII + per-service allowed-keys policy + ratio alert',
    },
    projectFit: ['Every microservice', 'Every AI / RAG pipeline', 'Every multi-tenant SaaS', 'Every audit-required system'],
    interviewLine: 'CompositePropagator wires both. Auto-instrument httpx. Log formatter pulls baggage. Default OTel is tracecontext-only — easy gap.',
  },

  // ═══════════════════════════════════════════════════════════════
  // TOPIC 2 — Trace → Draft → Audit linkage
  // ═══════════════════════════════════════════════════════════════
  {
    slug: 'trace-draft-audit-linkage',
    title: '2. Trace → draft → audit — operator forensics by correlation_id (the story behind every decision)',
    status: 'shipped',
    coreConcept:
      'For an AI system, three artifacts must link by request_id: the Jaeger trace (timing of every hop), the draft (the LLM response shown to the user), and the audit row (the policy decision: which prompt version, which model, which tenant, what guardrails fired). Without that linkage, post-incident reconstruction is guesswork. With it: paste a request_id into one query and see the full story — what was asked, what was retrieved, what was generated, what guardrails decided.',
    oneLiner: 'request_id is the join key. Trace = timing. Draft = output. Audit = decision. All three filterable by baggage.request_id.',
    businessContext:
      'A user reports: "the chatbot said something wrong at 14:02". Without trace+draft+audit linkage: 30 min of log spelunking. With it: one query → see the prompt template version, retrieved chunks, model version, guardrail verdict — full story in 90 sec. Compliance / SOC2 / EU AI Act all require this trail.',
    fiveW: {
      what: 'Three persisted artifacts (trace, draft, audit) joined by a single correlation_id propagated via baggage.',
      why: 'Operator incidents demand a single source of truth; piecing it together from N services is too slow.',
      where: 'Persisted in Jaeger (traces), Postgres (drafts + audit rows), Redis cache (where applicable).',
      when: 'Every AI decision; every action with compliance footprint.',
      who: 'AI feature owners + ops + compliance / audit team.',
    },
    interview30s:
      'I link three artifacts by request_id: Jaeger trace for timing, the draft row for the answer the user saw, and the audit row for the policy decision (prompt version, model version, guardrails). All three are filterable by baggage.request_id, which propagates automatically across every hop. Operator pastes a request_id, sees the full story in one view. Compliance gets the evidence trail for free.',
    hld: `flowchart LR
  Req[User request] --> Edge[api-gateway]
  Edge --> Bag[baggage request_id]
  Bag --> Trace[Jaeger trace]
  Bag --> Draft[Postgres drafts row]
  Bag --> Audit[Postgres audit row]
  Trace --> View[Operator forensics view]
  Draft --> View
  Audit --> View
  View --> Story[One screen full story]`,
    flowchart: `flowchart TD
  In[Inbound request] --> Mid[Middleware - baggage_set request_id]
  Mid --> Span[Span attribute - request_id]
  Span --> Drafts[Insert drafts row - request_id]
  Drafts --> Audit[Insert audit row - request_id - prompt_v - model_v]
  Audit --> Done[Response to user]
  Done --> Op{Incident?}
  Op -- yes --> View[Forensics view by request_id]
  View --> Trace[Jaeger trace]
  View --> Draft[Draft text + citations]
  View --> Decision[Audit row policy decision]`,
    sequence: `sequenceDiagram
  participant User
  participant Edge
  participant Inf as inference-svc
  participant DB
  participant J as Jaeger
  User->>Edge: POST /query
  Edge->>Edge: baggage_set request_id=req-abc
  Edge->>Inf: forward + traceparent + baggage
  Inf->>Inf: span attributes incl request_id
  Inf->>DB: INSERT drafts request_id model_version
  Inf->>DB: INSERT audit request_id prompt_v guardrails
  Inf->>J: span finish
  Note over Op: forensics: one query by request_id`,
    coreLayers: [
      { layer: 'Propagation', responsibility: 'Baggage carries request_id to every hop.' },
      { layer: 'Span attributes', responsibility: 'Every span has request_id as searchable Jaeger attribute.' },
      { layer: 'Drafts table', responsibility: 'Persist user-visible LLM output keyed by request_id.' },
      { layer: 'Audit table', responsibility: 'Persist decision: prompt_version, model_version, retrieved chunk ids, guardrail verdicts.' },
      { layer: 'Forensics view', responsibility: 'Single-query operator UI joining trace + draft + audit by request_id.' },
    ],
    lld: `classDiagram
  class Forensics {
    +by_request_id(req_id) FullStory
  }
  class FullStory {
    +trace: JaegerTrace
    +draft: DraftRow
    +audit: AuditRow
  }
  class AuditRow {
    +request_id
    +prompt_version
    +model_version
    +chunks_retrieved
    +guardrails_fired
    +tenant_id
    +decision_type
  }
  class DraftRow {
    +request_id
    +text
    +citations
    +created_at`,
    coreBuildingBlocks: [
      'baggage.request_id propagated via W3C baggage header',
      'Span attributes copied from baggage on every span',
      'Drafts table with request_id index',
      'Audit table with request_id index + prompt_v + model_v',
      'Forensics endpoint: GET /admin/forensics?request_id=...',
      'Compliance export: query audit table by date range + tenant',
    ],
    architectureRelevance: {
      backend: 'Universal — any system that needs incident reconstruction.',
      rag: 'Critical: the chunks retrieved + the prompt + the model are the why behind every answer.',
      ai: 'Required for SOC2 / EU AI Act / compliance audit.',
      microservices: 'request_id is the join key — works across N services.',
    },
    problem:
      'Incident: "the chatbot said something wrong". Without linkage: pull logs from 5 services, join by timestamp, hope you got the right request. With linkage: paste request_id, see the full story.',
    whyThisApproach:
      'request_id propagates for free via baggage; persisting drafts + audit by request_id is one INSERT per service. The forensics view joins three tables — trivial vs reconstructing from logs.',
    whenToUse: [
      'Any AI / LLM system',
      'Any system with audit / compliance footprint',
      'Any system where operator MTTR matters',
      'Any system with regulatory exposure (EU AI Act, SOC2)',
    ],
    whenNotToUse: [
      'Throwaway prototype with no users',
      'Pure-batch system with no per-request decisions',
    ],
    input: 'baggage propagation + drafts table + audit table + forensics endpoint.',
    process: [
      'Edge sets baggage_set("request_id", uuid())',
      'Propagates via W3C baggage to every hop',
      'Each service copies baggage.request_id into its span attributes',
      'inference-svc inserts drafts row keyed by request_id',
      'Policy / guardrail layer inserts audit row keyed by request_id',
      'Operator forensics view joins trace + draft + audit by request_id',
      'Compliance export filters audit by date + tenant',
    ],
    output: 'request_id-keyed: 1 trace + 1 draft + 1 audit row = full story in one query.',
    implementationSteps: [
      { step: 'request_id at edge', logic: 'Auth middleware: baggage_set("request_id", x_request_id or uuid()).' },
      { step: 'Span attribute copy', logic: 'On span start: span.set_attribute("request_id", baggage_get("request_id")).' },
      { step: 'Drafts table', logic: 'CREATE TABLE drafts (request_id text PRIMARY KEY, text text, citations jsonb, ...).' },
      { step: 'Audit table', logic: 'CREATE TABLE audit (request_id text, prompt_v text, model_v text, chunks jsonb, guardrails jsonb, ...). Index by request_id + (tenant_id, created_at) for compliance export.' },
      { step: 'Forensics endpoint', logic: 'GET /admin/forensics?request_id={id} → returns {trace_url, draft, audit}.' },
      { step: 'Compliance export', logic: 'Daily job: dump audit rows by tenant for retention + regulator inquiry response.' },
      { step: 'Retention policy', logic: 'Drafts: 30 days hot + 1 year cold. Audit: 7 years (regulated).' },
    ],
    codeExample: {
      language: 'python',
      code: `# Edge / auth middleware — baggage at boundary
@app.middleware("http")
async def correlation_id_middleware(request, call_next):
    request_id = (
        request.headers.get("x-request-id")
        or str(uuid.uuid4())
    )
    baggage_set("request_id", request_id)
    baggage_set("tenant_id", request.state.tenant_id)
    response = await call_next(request)
    response.headers["x-request-id"] = request_id   # echo back
    return response


# inference-svc — copy baggage into span + persist drafts + audit
@router.post("/query")
async def query(req: QueryRequest, repo: AuditRepo = Depends(...)):
    request_id = baggage_get("request_id")  # propagated via baggage
    tenant_id = baggage_get("tenant_id")
    tracer = get_tracer(__name__)

    with tracer.start_as_current_span("inference.query") as span:
        # Make request_id a searchable Jaeger attribute
        span.set_attribute("request_id", request_id)
        span.set_attribute("tenant_id", tenant_id)
        span.set_attribute("prompt_version", PROMPT_VERSION)
        span.set_attribute("model_version", MODEL_VERSION)

        chunks = await retrieve(req.query)   # baggage flows downstream
        answer, guardrail_verdict = await generate_with_guardrails(
            req.query, chunks
        )

        # Persist drafts + audit keyed by request_id — both filterable
        await repo.insert_draft(
            request_id=request_id,
            text=answer.text,
            citations=answer.citations,
        )
        await repo.insert_audit(
            request_id=request_id,
            tenant_id=tenant_id,
            prompt_version=PROMPT_VERSION,
            model_version=MODEL_VERSION,
            chunks_retrieved=[c.id for c in chunks],
            guardrails_fired=guardrail_verdict.flags,
            decision="auto" if guardrail_verdict.passed else "block",
        )
        return answer


# Forensics endpoint — one query reconstructs the story
@admin_router.get("/forensics")
async def forensics(request_id: str, repo: AuditRepo = Depends(...)):
    draft = await repo.get_draft(request_id)
    audit = await repo.get_audit(request_id)
    jaeger_url = (
        f"{JAEGER_UI}/search?service=rag-platform"
        f"&tags=%7B%22request_id%22%3A%22{request_id}%22%7D"
    )
    return {
        "request_id": request_id,
        "trace_url": jaeger_url,
        "draft": draft,
        "audit": audit,
    }`,
    },
    realUseCase:
      'User: "chatbot said wrong refund policy at 14:02". Operator pastes request_id from user echo header into forensics view. Sees: prompt_v 2.4, model_v llama-3.1, retrieved chunks include outdated policy doc, no guardrail blocked. Root cause = stale ingestion. Fix = re-index + tighten retrieval recency. Total time: 90 sec from page to root cause.',
    prosCons: {
      pros: [
        'Operator MTTR drops from 30 min to 90 sec',
        'Compliance export is "trivial query" not "build a project"',
        'Audit row IS the regulator evidence',
        'request_id propagates for free via baggage',
      ],
      cons: [
        'Audit table grows fast — needs retention + indexing',
        'Drafts table also grows — separate retention',
        'Forensics endpoint needs auth (operator-only)',
      ],
    },
    limitations: [
      'Only as good as request_id discipline (must be set at edge)',
      'If a service skips audit insert, the row is missing',
      'Async tasks must propagate context to keep request_id',
    ],
    comparison: {
      left: 'Manual log join',
      right: 'Trace + draft + audit by request_id',
      rows: [
        { aspect: 'Operator MTTR', left: '30 min', right: '90 sec' },
        { aspect: 'Compliance export', left: 'Custom build', right: 'One query' },
        { aspect: 'Coverage', left: 'Best-effort', right: 'Every request' },
        { aspect: 'Storage', left: 'Logs only', right: 'Logs + drafts + audit' },
      ],
    },
    challenges: [
      'request_id discipline (must be set at edge unconditionally)',
      'Audit insert reliability (transactional with the response)',
      'Retention policy: hot vs cold storage',
      'Compliance export performance under high cardinality',
      'Forensics endpoint auth (sensitive data)',
    ],
    edgeCases: [
      { case: 'request_id missing at edge', solution: 'Auth middleware ALWAYS generates if not provided; never None' },
      { case: 'Audit insert fails after response sent', solution: 'Outbox pattern: audit row in same transaction as draft' },
      { case: 'Tenant requests their data export', solution: 'Audit table indexed by tenant_id + created_at; one query' },
      { case: 'Forensics endpoint exposes PII', solution: 'Auth + role-based redaction + audit log of forensics queries' },
    ],
    solutions: [
      { problem: 'Slow incident reconstruction', solution: 'Forensics view by request_id' },
      { problem: 'Missing audit rows', solution: 'Outbox pattern + transaction discipline' },
      { problem: 'Compliance export slow', solution: 'Index audit by (tenant_id, created_at)' },
      { problem: 'Lost request_id in async task', solution: 'context.copy() at spawn site' },
    ],
    bestPractices: {
      do: [
        'request_id at edge unconditionally',
        'Span attribute copy from baggage',
        'Audit row in same transaction as draft',
        'Forensics endpoint with operator auth',
        'Retention policy: drafts 30d, audit 7y',
      ],
      avoid: [
        'request_id only when caller provides',
        'Fire-and-forget audit insert',
        'Audit table without indexes',
        'Forensics endpoint open to non-admins',
      ],
      optimize: [
        'Partition audit by month',
        'Cold storage after 30d',
        'Forensics cache by request_id (5 min TTL)',
      ],
    },
    antiPatterns: [
      'Logs only — no persisted audit',
      'request_id different at each hop',
      'Audit row missing the prompt_v / model_v',
      'Forensics endpoint open',
    ],
    testing: ['Unit: drafts insert + retrieve', 'Integration: end-to-end request → 3 artifacts visible', 'Drill: forensics endpoint returns full story', 'Compliance: tenant export query'],
    testTypes: ['Unit', 'Integration', 'Forensics drill', 'Compliance export drill'],
    testScenarios: [
      { scenario: 'Request → 3 artifacts', expected: 'trace + draft + audit all keyed by same request_id' },
      { scenario: 'Forensics by request_id', expected: 'Returns trace_url + draft + audit in < 100ms' },
      { scenario: 'Tenant export', expected: 'Returns all audit rows for tenant in date range' },
      { scenario: 'Async task', expected: 'request_id preserved across asyncio.create_task' },
    ],
    testData: [
      { type: 'Real fixture', example: 'request_id=req-abc-123; tenant=acme-prod; prompt_v=2.4; model_v=llama-3.1' },
      { type: 'Compliance fixture', example: 'tenant export over 30d; expect N audit rows' },
    ],
    debuggingChecklist: [
      'request_id set at edge?',
      'Baggage propagated to every hop?',
      'Span attribute copy from baggage?',
      'Audit row inserted on every response?',
      'Audit row indexed for tenant + date?',
      'Forensics endpoint auth wired?',
    ],
    productionIssues: [
      { issue: 'Forensics shows trace but no audit row', rootCause: 'Audit insert happened after response → fire-and-forget lost on crash. Use transaction.' },
      { issue: 'request_id different across hops', rootCause: 'Service generated its own; auth middleware should be the only generator' },
      { issue: 'Compliance export takes 30 min', rootCause: 'No index on (tenant_id, created_at); add it' },
    ],
    security: [
      'Forensics endpoint requires admin role',
      'PII in drafts redacted on export',
      'Audit log of forensics queries (audit the audit)',
      'Tenant isolation: tenant cannot query another\'s drafts',
    ],
    performance: [
      'Forensics by request_id < 100ms',
      'Tenant export indexed: < 10s for 30 days',
      'Audit insert in same transaction as response',
    ],
    costConsiderations: [
      'Audit table grows ~1 KB / request × QPS × retention',
      'Cold storage after 30 days = 80% cost reduction',
      'Compliance retention (7y for regulated) dominates storage',
    ],
    scaling: ['Partition audit by month', 'Move > 30d to cold storage', 'Read replicas for forensics endpoint'],
    observability: ['Forensics latency p95 metric', 'Audit insert success rate', 'Drafts insert success rate', 'Compliance export latency'],
    metrics: [
      { name: 'forensics_latency_ms_p95', example: '85' },
      { name: 'audit_insert_success_rate', example: '0.9999' },
      { name: 'drafts_table_size_gb', example: '12' },
      { name: 'audit_table_size_gb', example: '180 (7 years × tenants × QPS)' },
    ],
    failureModes: [
      { mode: 'Audit row missing', detect: 'Forensics view shows trace but no audit', recover: 'Outbox pattern; transaction with response' },
      { mode: 'request_id mismatch across hops', detect: 'Audit row has different request_id than trace', recover: 'Single generator at edge; reject if downstream sets it' },
      { mode: 'Compliance export slow', detect: 'Export latency > 30s', recover: 'Add (tenant_id, created_at) index' },
    ],
    tradeoffs: [
      { decision: 'Audit in same transaction', tradeoff: 'Slower response; reliable audit' },
      { decision: 'Forensics cache', tradeoff: 'Stale window; faster operator UX' },
      { decision: 'Cold storage', tradeoff: 'Slower retrieval after 30d; massive cost saving' },
    ],
    decisionMatrix: [
      { option: 'Logs only', whenToUse: 'Tiny system, no compliance' },
      { option: 'Trace + audit only', whenToUse: 'Operator-driven; not user-visible' },
      { option: 'Trace + draft + audit', whenToUse: 'AI / LLM / regulated systems' },
    ],
    starStory: {
      situation: 'AI chatbot incident: "wrong refund policy at 14:02". 3 hour log spelunking previously.',
      task: 'Build forensics view by request_id.',
      action: 'Wired baggage.request_id at edge; copied to span attributes; persisted drafts + audit rows keyed by request_id; built /admin/forensics endpoint that joins trace_url + draft + audit.',
      result: 'Operator MTTR for AI quality incidents: 30 min → 90 sec. Compliance export: 1 day project → 1 query. Annual audit prep: 2 weeks → 4 hours.',
    },
    interviewTraps: [
      'No persisted audit (just logs)',
      'No prompt_version / model_version in audit',
      'request_id not propagated via baggage',
      'Forensics endpoint open to non-admins',
    ],
    finalScript:
      'baggage.request_id at edge → span attribute on every hop → drafts row + audit row keyed by it → forensics endpoint joins all three. Operator MTTR drops from minutes to seconds; compliance export is one query.',
    alternatives: [
      { name: 'Logs only', tradeoff: 'No structure; slow forensics; no compliance evidence' },
      { name: 'Trace only', tradeoff: 'Timing visible; no decision record' },
      { name: 'Audit only', tradeoff: 'Decision visible; no timing context' },
    ],
    monitoring: ['Forensics latency dashboard', 'Audit insert success', 'Compliance export latency', 'Audit log of forensics queries'],
    maturity: {
      mvp: 'Trace + audit keyed by request_id',
      production: 'Add drafts + forensics endpoint + retention policy',
      enterprise: 'Add cold storage + partitioning + compliance export + admin-only auth',
    },
    projectFit: ['AI / LLM systems', 'Regulated SaaS', 'Multi-tenant', 'Operator-debugged production'],
    interviewLine: 'request_id is the join key. Trace + draft + audit. One query reconstructs the story.',
  },
];

export default function TracingDeep() {
  return (
    <div className="design-areas-page">
      <header className="design-areas-header">
        <h1 className="section-title">Distributed tracing + baggage (deep dive)</h1>
        <p className="design-areas-sub">
          W3C trace context + baggage propagation across service hops (the
          chain that survives every service boundary), and the trace → draft →
          audit linkage by correlation_id (the operator forensics pattern that
          turns "wrong answer at 14:02" from a 30-minute search into a 90-second
          query).
        </p>
      </header>
      {TOPICS.map((t) => <UniversalDeepDive key={t.slug} t={t} />)}
      <DeepDiveCrossRefs
        refs={[
          { href: '/admin/checklist/deep#governance-ops-checklist', label: 'Hard-stop #5 (no tracing)', why: 'this page IS the implementation of the no-tracing hard-stop check; without baggage propagator, release is blocked' },
          { href: '/admin/c4-model/deep#level-6-observability', label: 'C4 L6 observability', why: 'L6 wires the propagator + log formatter + Jaeger; this page is the L6 reference implementation' },
          { href: '/admin/post-release/deep#pdv-monitoring', label: 'PDV — golden + AI signals', why: 'rollback decisions during PDV are filterable by baggage.tenant_id; one Jaeger query per incident' },
          { href: '/admin/microservices/deep', label: 'Microservices + cross-service', why: 'baggage is the universal microservices contract — N hops, one trace_id, business context everywhere' },
          { href: '/admin/llmops/deep#audit', label: 'Decision audit row', why: 'audit row keyed by request_id (propagated via baggage); forensics joins trace + draft + audit' },
        ]}
      />
    </div>
  );
}
