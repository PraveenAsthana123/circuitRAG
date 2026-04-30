'use client';

import DeepDiveCrossRefs from '../../../../components/DeepDiveCrossRefs';
import UniversalDeepDive, { type Topic } from '../../../../components/UniversalDeepDive';

const TOPICS: Topic[] = [
  {
    slug: 'next-bff-gateway',
    title: '1. Next.js BFF as the gateway (current state)',
    status: 'shipped',
    coreConcept: 'The Next.js app under services/frontend/app/api/v1/ acts as the Backend-For-Frontend (BFF) gateway. Every browser-originated request lands here first; the BFF terminates the user session, attaches correlation_id, validates inputs with Zod, and proxies to internal services. There is NO separate gateway process in the current compose stack — the BFF is the gateway.',
    problem: 'Browsers cannot speak directly to internal services without leaking auth, exposing internal URLs, or forcing every internal service to support CORS. A gateway provides a single ingress surface that owns authentication, input validation, error envelope shaping, and traffic policy.',
    whyThisApproach: 'Reusing the Next.js app as the BFF gateway is the cheapest path for Phase-1: zero new processes, server-side rendering and gateway logic share auth state, type-safe end-to-end via TypeScript + Zod. When traffic outgrows a single Node process, the BFF logic ports to a dedicated gateway (NGINX + Go) without changing the contract.',
    whenToUse: ['Browser-first apps where SSR + BFF naturally co-locate', 'Single-team Phase-1 deployments', 'TypeScript stacks where type-sharing across BFF + UI matters', 'Services with low fan-out (BFF aggregates 1-3 backends per route)'],
    whenNotToUse: ['High-fan-out aggregation (BFF becomes the bottleneck)', 'Mixed-language internal services where BFF cannot type-share', 'Multi-tenant SaaS at scale where per-tenant rate-limiting requires dedicated gateway', 'Strict separation of concerns (BFF + frontend in same process feels muddy at scale)'],
    input: 'browser request: { method, path, headers, body, cookies }',
    process: [
      'Browser hits /api/v1/<path>',
      'Next.js App Router resolves route handler under app/api/v1/<path>/route.ts',
      'Handler validates body with Zod schema (rejects malformed)',
      'Handler attaches correlation_id (UUID v4) + reads session cookie',
      'Handler calls internal service (sidecar-advisor, agent-orchestrator, etc.) with correlation_id in headers',
      'Handler shapes response into canonical error envelope: {detail, error_code, correlation_id}',
      'Response streamed/returned to browser',
    ],
    output: 'Validated, auth\'d, correlation-tagged proxied response with canonical error shape.',
    flowchart: `flowchart LR
  br[Browser] -->|/api/v1/...| bff[Next.js BFF]
  bff -->|Zod validate| z[Schema check]
  z -->|invalid| 400[400 + envelope]
  z -->|valid| auth[Read session cookie]
  auth --> cor[Attach correlation_id]
  cor --> backend{which service?}
  backend -->|sidecar| sc[sidecar-advisor]
  backend -->|orchestrator| or[agent-orchestrator]
  backend -->|RAG| rag[inference-svc]
  sc --> shape[Shape response envelope]
  or --> shape
  rag --> shape
  shape --> br`,
    sequence: `sequenceDiagram
  autonumber
  participant Br as Browser
  participant BFF as Next.js BFF
  participant Z as Zod validator
  participant SVC as Internal service
  Br->>BFF: POST /api/v1/sidecar/events
  BFF->>Z: validate(body, EventSchema)
  alt invalid
    Z-->>BFF: error
    BFF-->>Br: 400 {detail, error_code, correlation_id}
  else valid
    Z-->>BFF: parsed
    BFF->>BFF: attach correlation_id + read session
    BFF->>SVC: POST /events (correlation_id header)
    SVC-->>BFF: 201 + advice
    BFF-->>Br: 201 {data, correlation_id}
  end`,
    alternatives: [
      { name: 'Dedicated gateway (NGINX + Go)', tradeoff: 'Mature; high-throughput; another process to operate; less type-share with FE' },
      { name: 'No gateway (browser → internal directly)', tradeoff: 'Cheapest; leaks internal URLs; CORS nightmare; auth duplicated' },
      { name: 'Service mesh ingress (Istio Gateway)', tradeoff: 'Mesh-native; requires k8s + control plane; future state per service-mesh deep-dive' },
    ],
    challenges: [
      'BFF route proliferation (one file per endpoint)',
      'Type-sharing discipline across BFF + UI',
      'Correlation_id propagation through every backend hop',
      'Error envelope drift across handlers (one team forgets the shape)',
      'No per-tenant rate-limit at this layer (Phase-1 acceptable)',
    ],
    edgeCases: [
      { case: 'Internal service times out', solution: 'BFF returns 504 with correlation_id; user sees retry option; trace links upstream timeout' },
      { case: 'Session expired mid-stream', solution: 'BFF returns 401 with refresh-hint; UI redirects to login' },
      { case: 'Backend returns non-canonical error shape', solution: 'BFF wraps response in canonical envelope; never leaks raw backend error to browser' },
      { case: 'Multiple backends for one route', solution: 'BFF aggregates with Promise.all + fail-fast or partial-success per route discretion' },
    ],
    failureModes: [
      { mode: 'BFF process OOM under high traffic', detect: 'Node heap usage > 80%; route p99 latency rising', recover: 'Horizontal pod autoscaler on Next.js process; investigate aggregation routes' },
      { mode: 'Correlation_id missing on backend call', detect: 'Backend logs missing request_id; trace reconstruction fails', recover: 'Audit handler middleware; mandatory header injection helper' },
      { mode: 'Error envelope drift', detect: 'Frontend tries to read .detail and finds {error: "..."}', recover: 'Drill drill_api_envelope_canonical fires; helper function for envelope shaping' },
    ],
    monitoring: [
      'documind_bff_request_duration_seconds_p95 (per route)',
      'documind_bff_request_total{status_code}',
      'documind_bff_zod_validation_failures_total{schema}',
      'Next.js telemetry → OTel collector via traceparent baggage',
    ],
    testing: [
      'drill_sidecar_rating_route (BFF route contract for one canonical endpoint)',
      'drill_api_envelope_canonical (PLANNED — every BFF route returns canonical error envelope)',
      'Vitest: services/frontend/tests/sidecar-rating-route.test.ts',
    ],
    security: [
      'Session cookie validation per request (not per session)',
      'Zod schema rejects malformed body before backend call',
      'CORS configured restrictively — no wildcard origins',
      'Correlation_id is server-generated; never accepted from client',
      'Rate-limit at BFF planned for Phase-2 (currently relies on Next.js process limits)',
    ],
    scaling: [
      '10x: single Next.js process handles ~500 RPS for simple proxy routes',
      '100x: horizontal scaling Next.js + dedicated gateway (NGINX) for static asset offload',
      '1000x: split BFF into per-domain BFFs (admin BFF, user BFF, agent BFF) to avoid contention',
    ],
    maturity: {
      mvp: 'Direct browser → backend with CORS + duplicated auth',
      production: 'Next.js BFF with Zod validation + correlation_id + canonical error envelope (current)',
      enterprise: 'Dedicated NGINX/Go gateway in front + service mesh ingress + per-tenant rate-limit + WAF',
    },
    limitations: [
      'No per-tenant rate-limit (Next.js process limits only)',
      'No request body size enforcement at gateway layer (Next.js defaults)',
      'BFF + frontend in same process — split for high-traffic deployments',
      'Auth + session validation on every request (no edge JWT validation)',
    ],
    projectFit: [
      'services/frontend/app/api/v1/ — every BFF route',
      'services/frontend/lib/sidecar.ts — backend call layer',
      'services/frontend/tests/sidecar-rating-route.test.ts — Vitest pattern',
      'docs/architecture/agentic-a2a-langgraph-fastapi-mcp.md — gateway-to-backend contract',
    ],
    interviewLine: 'In Phase-1 the Next.js BFF is the gateway — same process as the SSR app. Cheap, type-safe end-to-end, correlation_id propagated everywhere. When traffic outgrows a single Node process, the BFF logic ports to a dedicated NGINX + Go gateway without changing the contract. The BFF pattern wins until a high-fan-out aggregation route becomes the bottleneck.',
    implementationSteps: [
      { step: 'Route per endpoint', logic: 'app/api/v1/<path>/route.ts with named handlers (GET, POST, etc.).' },
      { step: 'Zod validation first', logic: 'Body parsed with Zod schema; reject before any backend call.' },
      { step: 'Correlation_id middleware', logic: 'UUID v4 generated server-side; attached to backend headers + response.' },
      { step: 'Backend call helper', logic: 'lib/<service>.ts wraps fetch with timeout + AbortController + envelope parsing.' },
      { step: 'Canonical error envelope', logic: '{detail, error_code, correlation_id}; never leak raw backend errors.' },
      { step: 'Trace via OTel baggage', logic: 'traceparent header injected; backend services receive same trace context.' },
      { step: 'Drill the route', logic: 'Per-endpoint drill (e.g. drill_sidecar_rating_route) locks status codes + envelope shape.' },
    ],
    codeExample: {
      language: 'typescript',
      code: `// services/frontend/app/api/v1/sidecar/events/route.ts
import { NextRequest, NextResponse } from 'next/server';
import { z } from 'zod';
import { recordEvent } from '@/lib/sidecar';

const EventSchema = z.object({
  content: z.string().min(1).max(20000),
  source: z.enum(['paste', 'pr', 'cli']).default('paste'),
});

export async function POST(req: NextRequest) {
  const correlation_id = crypto.randomUUID();
  const session = req.cookies.get('sid')?.value;
  if (!session) {
    return NextResponse.json(
      { detail: 'unauthenticated', error_code: 'NO_SESSION', correlation_id },
      { status: 401 },
    );
  }
  let body;
  try {
    body = EventSchema.parse(await req.json());
  } catch (e) {
    return NextResponse.json(
      { detail: 'invalid body', error_code: 'INVALID_BODY', correlation_id },
      { status: 400 },
    );
  }
  try {
    const result = await recordEvent(body, { correlation_id });
    return NextResponse.json({ data: result, correlation_id }, { status: 201 });
  } catch (e: any) {
    return NextResponse.json(
      { detail: e.message, error_code: 'BACKEND_ERROR', correlation_id },
      { status: 502 },
    );
  }
}`,
    },
    starStory: {
      situation: 'Initial Phase-1 design needed a single ingress surface for browser traffic without spinning up a dedicated gateway process. CORS, auth, and correlation_id propagation were duplicating across routes.',
      task: 'Use the existing Next.js app as the BFF gateway with Zod validation + canonical error envelope + correlation_id, scaling path to a dedicated gateway documented.',
      action: 'Authored route handlers under app/api/v1/. Built lib/sidecar.ts and lib/<service>.ts wrappers. Vitest tests + drill_sidecar_rating_route lock route contracts.',
      result: 'Single-process gateway with type-safe end-to-end + correlation_id everywhere + canonical error envelope. Zero new processes. Migration path to dedicated NGINX + Go documented.',
    },
    interviewTraps: [
      'Treating BFF as permanent (it scales to ~500 RPS; planning for 10K RPS without dedicated gateway is naive)',
      'Skipping Zod validation (any body shape reaches backend; injection surface)',
      'Letting backend errors leak raw to browser (PII / internal-path leakage)',
    ],
    finalScript: 'Next.js BFF as the gateway is a Phase-1 decision: zero new processes, type-safe, correlation_id propagated. The contract — Zod-validated input, canonical error envelope, correlation_id — is what makes the upgrade to dedicated gateway non-disruptive. When traffic dictates, the BFF logic ports to NGINX + Go behind the same envelope. The BFF pattern is the bridge from "single Node app" to "split frontend + gateway", and the contract is what makes the bridge work.',
  },
  {
    slug: 'dedicated-gateway-future',
    title: '2. Dedicated gateway + edge layer (planned)',
    status: 'planned',
    coreConcept: 'A dedicated gateway tier (NGINX terminating TLS + Go API gateway validating JWT, attaching correlation_id, applying per-tenant rate-limits) sitting in front of the BFF when traffic outgrows the single-process design. The mesh handles internal mTLS; the gateway handles edge concerns (TLS, rate-limit, JWT validation, header sanitisation).',
    problem: 'Single Next.js BFF maxes out around 500 RPS for proxy routes. Per-tenant rate-limit isn\'t feasible inside Node\'s event loop without specialized middleware. JWT validation belongs at the edge for early rejection of bogus tokens. WAF + DDoS protection requires NGINX-class infrastructure.',
    whyThisApproach: 'Edge concerns (TLS, rate-limit, WAF) and identity validation (JWT) are best handled in NGINX + Go where mature libraries + high throughput exist. The BFF retains its job (route → backend, type-share with UI) but no longer owns edge concerns. Service mesh handles internal mTLS; gateway + mesh together implement zero-trust with edge admission.',
    whenToUse: ['Traffic > 1K RPS sustained', 'Multi-tenant SaaS with per-tenant rate-limit requirements', 'Compliance mandates WAF / DDoS protection', 'JWT-based auth where edge validation matters'],
    whenNotToUse: ['Phase-1 internal-tools deployments', 'Single-tenant deployments where BFF rate-limit is sufficient', 'Cost-constrained projects where extra gateway tier is unjustified'],
    input: 'browser request → NGINX (TLS terminate) → Go gateway (JWT + rate-limit) → BFF or backend',
    process: [
      'Browser hits public endpoint',
      'NGINX terminates TLS, strips unknown headers, applies global rate limits',
      'Go API gateway validates JWT (cached pubkey from JWKS), attaches correlation-id',
      'Per-tenant rate-limit check (token bucket per tenant_id from JWT)',
      'Route to BFF (browser-originated SSR-coupled) or directly to backend (machine-to-machine)',
      'Mesh-internal mTLS from gateway onward',
    ],
    output: 'Edge-validated, rate-limited, mTLS-internal request reaching BFF or backend.',
    flowchart: `flowchart LR
  br[Browser] -->|TLS| ng[NGINX]
  ng -->|HTTP/2| gw[Go API Gateway]
  gw -->|JWT validate| jwks[(JWKS cache)]
  gw -->|rate-limit per tenant| rl[(Redis token bucket)]
  gw -->|mTLS| bff[Next.js BFF]
  gw -->|mTLS| svc[Direct backend]`,
    sequence: `sequenceDiagram
  autonumber
  participant Br as Browser
  participant NG as NGINX
  participant GW as Go Gateway
  participant J as JWKS cache
  participant R as Redis (rate-limit)
  participant BFF as BFF
  Br->>NG: HTTPS request
  NG->>NG: terminate TLS, strip headers, global rate-limit
  NG->>GW: HTTP/2 (internal)
  GW->>J: pubkey for kid
  J-->>GW: pubkey (cached)
  GW->>GW: validate JWT signature
  GW->>R: tenant rate-limit check
  alt under limit
    GW->>BFF: mTLS (correlation_id attached)
    BFF-->>GW: response
    GW-->>NG: response
    NG-->>Br: HTTPS response
  else over limit
    GW-->>NG: 429 Retry-After
    NG-->>Br: 429
  end`,
    alternatives: [
      { name: 'BFF only (Phase-1)', tradeoff: 'Current state; works to ~500 RPS' },
      { name: 'Service mesh ingress only', tradeoff: 'Istio Gateway handles mTLS but per-tenant rate-limit is awkward in mesh' },
      { name: 'Cloud-native (AWS API Gateway)', tradeoff: 'Managed; expensive at scale; vendor lock-in' },
    ],
    challenges: [
      'Operating two new tiers (NGINX + Go gateway) in production',
      'JWKS cache freshness vs rotation',
      'Per-tenant rate-limit precision under burst traffic (token bucket vs sliding window)',
      'Coordinating gateway + BFF + mesh upgrades',
    ],
    edgeCases: [
      { case: 'JWKS rotation during traffic burst', solution: 'Stale-while-revalidate cache; gateway accepts old kid for grace period' },
      { case: 'Tenant rate-limit lookup miss', solution: 'Default-conservative rate (e.g. 10 RPS); operator alert on miss spike' },
      { case: 'NGINX restart loses connection state', solution: 'Connection-pooled HTTP/2 to gateway; reconnect with retry-budget' },
    ],
    failureModes: [
      { mode: 'Gateway saturated under DDoS', detect: 'NGINX 429 rate climbing; queue depth saturating', recover: 'Cloud DDoS protection in front of NGINX; horizontal-scale gateway behind' },
      { mode: 'Redis rate-limit unavailable', detect: 'Rate-limit lookups failing; metric documind_gateway_ratelimit_errors_total', recover: 'Fail-open to per-process limit; alert; recover Redis' },
      { mode: 'JWT validation latency spike', detect: 'gateway p95 latency rising; JWKS calls timing out', recover: 'Increase JWKS cache TTL + circuit-breaker on JWKS endpoint' },
    ],
    monitoring: [
      'documind_gateway_request_duration_seconds_p95 (per tenant)',
      'documind_gateway_ratelimit_rejections_total{tenant}',
      'documind_gateway_jwt_validation_errors_total{reason}',
      'NGINX access log → OTel; per-tenant traffic dashboard',
    ],
    testing: [
      'drill_gateway_jwt_validation (PLANNED — locks JWT contract)',
      'drill_gateway_ratelimit_per_tenant (PLANNED — token bucket correctness)',
      'drill_gateway_correlation_id_propagation (PLANNED — header survives gateway hop)',
    ],
    security: [
      'TLS termination at NGINX with modern cipher suite only',
      'JWT signature validation at edge (early rejection of bogus tokens)',
      'Per-tenant rate-limit prevents tenant noisy-neighbor',
      'WAF rules at NGINX (OWASP CRS) for common injection payloads',
      'Header sanitisation: strip x-forwarded-* before forwarding to BFF',
    ],
    scaling: [
      '10K RPS: NGINX + 3-5 Go gateway pods + Redis cluster for rate-limit',
      '100K RPS: NGINX in front of cloud LB; gateway autoscale; Redis sharded by tenant',
      'Cost driver: Redis throughput for rate-limit checks; tenant-bucket cache locally',
    ],
    maturity: {
      mvp: 'No edge layer — BFF only',
      production: 'PLANNED — when traffic > 1K RPS or per-tenant rate-limit becomes mandatory',
      enterprise: 'Full NGINX + Go gateway + Redis-backed per-tenant rate-limit + WAF + DDoS protection + JWKS caching',
    },
    limitations: [
      'NOT YET SHIPPED — current state is BFF-only',
      'No drill yet locks the JWT validation contract',
      'No per-tenant rate-limit configuration committed to repo',
    ],
    projectFit: [
      'Future: services/api-gateway/ + infra/nginx/',
      'docs/architecture/agentic-a2a-langgraph-fastapi-mcp.md — references the gateway tier',
      '/admin/service-mesh/deep — mesh-internal mTLS picks up after gateway',
      '/admin/security/deep — JWT validation and edge concerns documented',
    ],
    interviewLine: 'A dedicated gateway tier — NGINX terminating TLS + Go validating JWT + Redis-backed per-tenant rate-limit — is the right next step when BFF maxes out or per-tenant rate-limit becomes mandatory. NOT YET SHIPPED. The contract (correlation_id propagation + canonical error envelope) is already locked at the BFF layer; the gateway tier slots in front without breaking it.',
    implementationSteps: [
      { step: 'NGINX baseline', logic: 'TLS termination, OWASP CRS WAF, global rate-limit, header sanitisation.' },
      { step: 'Go gateway service', logic: 'JWT validation against JWKS (cached); attach correlation_id; route to BFF or backend.' },
      { step: 'Per-tenant rate-limit', logic: 'Token bucket in Redis keyed by tenant_id from JWT; fail-open if Redis down.' },
      { step: 'mTLS to internals', logic: 'Gateway → BFF and Gateway → backend over mTLS via service mesh.' },
      { step: 'Correlation_id propagation', logic: 'Header preserved across NGINX → gateway → BFF → backend; drill locks the contract.' },
      { step: 'Drill the gateway', logic: 'Three drills: JWT validation, rate-limit token bucket, correlation_id propagation.' },
      { step: 'Stage rollout', logic: 'Deploy gateway in dev; soak; canary in prod with traffic split per ADR-016.' },
    ],
    codeExample: {
      language: 'go',
      code: `// services/api-gateway/main.go — PLANNED skeleton
package main

import (
    "context"
    "net/http"
    "github.com/golang-jwt/jwt/v5"
    "github.com/redis/go-redis/v9"
)

type Gateway struct {
    jwks  JWKSCache
    rdb   *redis.Client
    bff   string
}

func (g *Gateway) Handle(w http.ResponseWriter, r *http.Request) {
    ctx := r.Context()
    correlationId := newCorrelationId()

    // 1. JWT validation
    tok, err := g.validateJWT(r.Header.Get("Authorization"))
    if err != nil {
        writeEnvelope(w, 401, "INVALID_TOKEN", correlationId)
        return
    }

    // 2. Per-tenant rate-limit
    tenantId := tok.Claims.(jwt.MapClaims)["tenant_id"].(string)
    if !g.checkRateLimit(ctx, tenantId) {
        w.Header().Set("Retry-After", "1")
        writeEnvelope(w, 429, "RATE_LIMITED", correlationId)
        return
    }

    // 3. Forward to BFF with correlation_id
    r.Header.Set("X-Correlation-Id", correlationId)
    proxyTo(g.bff, w, r)
}`,
    },
    starStory: {
      situation: 'BFF-only design hits ceiling around 500 RPS. Multi-tenant SaaS migration mandates per-tenant rate-limit. Compliance review surfaces WAF + DDoS protection as gates.',
      task: 'Design the gateway tier that slots in front of the BFF with NGINX (TLS, WAF) + Go gateway (JWT, rate-limit), without breaking the existing BFF contract.',
      action: 'PLANNED. Contract already locked at BFF (correlation_id, canonical envelope). Gateway implementation deferred until traffic justifies operational cost.',
      result: 'NOT YET SHIPPED. When live: 10K+ RPS, per-tenant fairness, edge JWT validation, WAF protection.',
    },
    interviewTraps: [
      'Adding gateway tier prematurely (operational burden without payoff)',
      'Doing rate-limit in the BFF (Node event loop is the wrong place)',
      'Skipping JWKS caching (every request hits identity provider; latency bomb)',
    ],
    finalScript: 'A dedicated gateway tier is the right next step when BFF maxes out or per-tenant fairness becomes mandatory. NGINX handles edge (TLS, WAF, global rate-limit), Go handles identity (JWT validation against JWKS), Redis handles per-tenant rate-limit. The BFF contract — correlation_id, canonical envelope — survives unchanged. NOT YET SHIPPED. Decision rule: traffic > 1K RPS sustained OR per-tenant rate-limit mandatory → ship. Otherwise BFF wins.',
  },
];

export default function ApiGatewayDeepPage() {
  return (
    <>
      <div className="page-header">
        <div className="page-header-copy">
          <h1 className="section-title">API gateway deep dive</h1>
          <p className="page-subtitle">
            Two surfaces — Next.js BFF as gateway (current) and dedicated
            NGINX + Go gateway tier (planned) — explained through the
            universal 20-dimension framework.
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
          { href: '/admin/service-mesh/deep', label: 'Service mesh + Istio', why: 'gateway handles edge admission; mesh handles internal mTLS — they compose together for full ingress story' },
          { href: '/admin/security/deep', label: 'Security deep-dive', why: 'JWT validation, WAF, rate-limit are §47 Design Area 2 (edge security) responsibilities' },
          { href: '/admin/breakers/deep', label: 'Circuit breakers', why: 'gateway is one of four circuit-breaker placement layers (edge, gateway, service, dependency)' },
          { href: '/admin/tracing/deep#baggage-propagation', label: 'Baggage propagation', why: 'correlation_id propagation across NGINX → gateway → BFF → backend is the trace foundation' },
          { href: '/admin/checklist/deep#governance-ops-checklist', label: 'Governance gate', why: 'no rate-limit + no WAF on a public gateway = release blocked per §38 hard-stop' },
        ]}
      />
    </>
  );
}
