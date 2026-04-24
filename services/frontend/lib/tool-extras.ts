/**
 * Extra per-tool architecture artifacts rendered below the 6-tab view.
 *
 * For tools that need more depth than a single Mermaid diagram, this file
 * supplies: flowchart, sequence diagram, network-flow diagram, explicit
 * input/process/output, and an extended interview talking point.
 *
 * Not every tool needs this. Only tools where reviewers or interviewers
 * ask "walk me through a request" benefit.
 */

export type ToolExtras = {
  flowchart?: string;
  sequence?: string;
  networkFlow?: string;
  ipo?: {
    input: string[];
    process: string[];
    output: string[];
  };
  analysis?: {
    comparison: { scenario: string; behavior: string }[];
    edgeCases: string[];
    limitations: string[];
    challenges: string[];
    solutions: string[];
  };
  business?: {
    valueProposition: string;
    kpis: { name: string; target: string }[];
    roi: string;
  };
  audit?: {
    checklist: string[];
    qualityMatrix: { dimension: string; score: string; note: string }[];
    externalLinks: { label: string; url: string }[];
  };
  interviewTalkingPoint?: string;
};

export const TOOL_EXTRAS: Record<string, ToolExtras> = {
  // ------------------------------------------------------------- istio
  istio: {
    flowchart: `flowchart LR
  client([External Client]) --> ingress{Istio Ingress\\nGateway}
  ingress -->|mTLS terminated| inbound[Sidecar A<br/>Envoy inbound]
  inbound -->|local TCP| appA[Service A]
  appA -->|egress request| outbound[Sidecar A<br/>Envoy outbound]
  outbound -->|mTLS STRICT| inboundB[Sidecar B<br/>Envoy inbound]
  inboundB --> appB[Service B]
  appB --> inboundB
  inboundB --> outbound
  outbound --> inbound
  inbound --> ingress
  ingress --> client

  classDef ctrl fill:#e0e7ff,stroke:#4f46e5
  pilot([istiod\\ncontrol plane]):::ctrl -.config.-> ingress
  pilot -.config.-> inbound
  pilot -.config.-> outbound
  pilot -.config.-> inboundB`,
    sequence: `sequenceDiagram
  autonumber
  participant C as Client
  participant IG as Istio Ingress
  participant SA as Sidecar A
  participant A as Service A
  participant SB as Sidecar B
  participant B as Service B
  participant P as istiod

  C->>IG: HTTPS + JWT
  IG->>IG: TLS terminate, JWT verify
  IG->>SA: mTLS (cert from istiod)
  SA->>SA: AuthorizationPolicy check
  SA->>A: plain-text localhost
  A->>SA: upstream call to B
  SA->>SB: mTLS + retry + timeout (VirtualService rules)
  SB->>SB: AuthorizationPolicy check
  SB->>B: plain-text localhost
  B-->>SB: response
  SB-->>SA: mTLS
  SA-->>A: response
  A-->>SA: final response
  SA-->>IG: mTLS
  IG-->>C: HTTPS
  Note over P,SB: istiod pushes PeerAuth,<br/>AuthPolicy, VS, DR via xDS`,
    networkFlow: `flowchart TB
  subgraph externalnet [Public internet]
    c([client])
  end
  subgraph clustert [Kubernetes cluster]
    subgraph dpi [Data plane — ingress]
      ig[Istio Ingress Gateway<br/>Envoy]
    end
    subgraph dpp [Data plane — pods]
      sa[Sidecar A]
      appa[App A]
      sb[Sidecar B]
      appb[App B]
      sa <-->|localhost| appa
      sb <-->|localhost| appb
    end
    subgraph cp [Control plane]
      istiod[istiod]
    end
  end
  c -->|TLS 443| ig
  ig -->|mTLS 15443/grpc| sa
  sa -->|mTLS| sb
  istiod -.xDS config.-> ig
  istiod -.xDS config.-> sa
  istiod -.xDS config.-> sb`,
    ipo: {
      input: [
        'External HTTPS request + JWT',
        'Internal service-to-service gRPC/HTTP',
        'istiod control-plane config (PeerAuth, VS, DR, AuthPolicy)',
      ],
      process: [
        'TLS termination at ingress',
        'JWT validation + header normalization',
        'mTLS between every pod pair (STRICT mode)',
        'AuthorizationPolicy: is source allowed to call target?',
        'VirtualService: route + canary split + retries + timeouts',
        'DestinationRule: subsets, outlier detection, LB policy',
        'Telemetry v2: emit metrics + traces on every hop',
      ],
      output: [
        'Forwarded request to target service',
        '4xx/5xx with envelope on policy failure',
        'Prometheus metrics (request_count, duration, tcp_opened)',
        'OTel spans per hop with peer.address + response.code',
      ],
    },
    interviewTalkingPoint:
      "Istio is the substrate every inter-service policy rides on. The key thing I'd say in an interview: the value isn't 'mTLS' in isolation — it's that mTLS, authz, canary, retries, circuit-breaking, and telemetry are implemented ONCE in the sidecar, not re-implemented per language. When someone asks about cost, I'd be honest: sidecars add ~30MB RAM + measurable p99 latency per pod. Worth it when you have more than 3–4 services; probably overkill for a monolith-plus-worker.",
    analysis: {
      comparison: [
        { scenario: 'With Istio', behavior: 'mTLS + authz + retries + tracing uniform across all services; one policy surface.' },
        { scenario: 'Without Istio', behavior: 'Every service reimplements mTLS/retries badly; policy drift; multi-language security holes.' },
        { scenario: 'Linkerd alternative', behavior: 'Lighter sidecar (Rust), simpler config, narrower feature set; no EnvoyFilter power.' },
        { scenario: 'Cilium service-mesh', behavior: 'eBPF in-kernel, no sidecar; less CPU overhead, tied to Linux kernel capabilities.' },
      ],
      edgeCases: [
        'Sidecar injection fails silently on namespaces missing the istio-injection label.',
        'AuthorizationPolicy ordering mistakes can block legitimate traffic; always test in a canary namespace first.',
        'Clock skew between pods breaks JWT expiry checks; ensure NTP on all nodes.',
        'Large gRPC frames (>4MB default) need listener tuning or they fail with UNKNOWN.',
      ],
      limitations: [
        'Sidecar CPU + memory overhead (~30MB RAM, ~1-2ms p99).',
        'Envoy ramp-up time affects cold-start latency.',
        'Complex learning curve; small teams often misconfigure AuthorizationPolicy.',
        'Layer-7 features require the request to be HTTP-parseable — raw TCP bypasses them.',
      ],
      challenges: [
        'Teaching new engineers when to reach for VirtualService vs DestinationRule.',
        'Keeping istioctl + mesh version + sidecar versions in sync during upgrades.',
        'Auditing AuthorizationPolicy — text rules don’t reveal resulting allow/deny matrix.',
      ],
      solutions: [
        'Adopt progressive mTLS (PERMISSIVE → STRICT) to avoid day-one outage.',
        'Use Kiali to visualize the mesh + run a weekly AuthorizationPolicy diff.',
        'Bake istioctl version into CI checks; reject drift.',
      ],
    },
    business: {
      valueProposition: 'Security + resilience + observability as a platform capability, independent of application code. One policy surface for every service.',
      kpis: [
        { name: 'mTLS coverage', target: '100% of pod-to-pod traffic' },
        { name: 'AuthorizationPolicy denies / hour', target: 'Trend baseline; alert on spike' },
        { name: 'p99 sidecar latency', target: '< 3ms' },
        { name: 'Mesh cert expiry', target: '> 7 days remaining, always' },
      ],
      roi: 'Replaces ~3 person-months of per-service mTLS+retry+metrics work; single control plane = fewer on-call escalations on policy bugs.',
    },
    audit: {
      checklist: [
        'PeerAuthentication STRICT across all namespaces with workloads',
        'AuthorizationPolicy default-deny + explicit allows',
        'Sidecar injection enabled on every app namespace',
        'VirtualService retry + timeout defaults sane (not default 15s)',
        'Kiali graph reviewed quarterly for orphan services',
        'istioctl analyze returns clean on every deploy',
      ],
      qualityMatrix: [
        { dimension: 'Security', score: 'High', note: 'mTLS STRICT + authz policies enforced' },
        { dimension: 'Availability', score: 'High', note: 'Retries + outlier detection on DR' },
        { dimension: 'Observability', score: 'High', note: 'Automatic metrics + traces per hop' },
        { dimension: 'Performance', score: 'Medium', note: 'Sidecar adds ~1-2ms p99 + ~30MB RAM' },
        { dimension: 'Complexity', score: 'High', note: 'Learning curve for VS / DR / AuthPolicy interactions' },
      ],
      externalLinks: [
        { label: 'Istio docs', url: 'https://istio.io/latest/docs/' },
        { label: 'Istio security best practices', url: 'https://istio.io/latest/docs/ops/best-practices/security/' },
        { label: 'Envoy docs', url: 'https://www.envoyproxy.io/docs/envoy/latest/' },
        { label: 'Kiali docs', url: 'https://kiali.io/docs/' },
      ],
    },
  },

  // ----------------------------------------------------- circuit-breakers
  'circuit-breakers': {
    flowchart: `flowchart LR
  start([caller makes call]) --> state{Breaker state?}
  state -->|CLOSED| attempt[Attempt upstream call]
  state -->|OPEN, timeout not elapsed| reject[Raise CircuitOpenError<br/>no network round-trip]
  state -->|OPEN, timeout elapsed| halfo[Transition to HALF_OPEN]
  halfo --> attempt
  attempt --> outcome{Result?}
  outcome -->|success| success[Reset failure counter<br/>if HALF_OPEN → CLOSED]
  outcome -->|failure| fail[Increment failure count]
  fail --> check{failures ≥ threshold<br/>OR HALF_OPEN?}
  check -->|yes| open[Transition to OPEN<br/>record opened_at]
  check -->|no| back[Stay CLOSED]
  success --> fin([return value])
  back --> fin
  open --> err([bubble exception])
  reject --> err`,
    sequence: `sequenceDiagram
  autonumber
  participant Caller
  participant CB as Circuit Breaker
  participant Ollama
  Caller->>CB: call_async(fn)
  CB->>CB: _before_call (check state)
  alt OPEN (recent)
    CB-->>Caller: CircuitOpenError (fast fail)
  else CLOSED / HALF_OPEN
    CB->>Ollama: fn()
    alt success
      Ollama-->>CB: result
      CB->>CB: _on_success (reset counter)
      CB-->>Caller: result
    else failure
      Ollama-->>CB: exception
      CB->>CB: _on_failure (count++, maybe OPEN)
      CB-->>Caller: original exception
    end
  end
  Note over CB: If 5 failures accumulate,<br/>next call sees OPEN,<br/>fails fast for 60s`,
    networkFlow: `flowchart LR
  subgraph inf [inference-svc pod]
    app[App code]
    tcb[TokenCircuitBreaker]
    ocb[Ollama CircuitBreaker]
    ccb[Cognitive CB]
    app --> tcb
    tcb --> ocb
    ocb --> outs([egress])
  end
  subgraph ret [retrieval-svc pod]
    app2[App code]
    qcb[Qdrant CB]
    ncb[Neo4j CB]
    app2 --> qcb
    app2 --> ncb
    qcb --> outs2([egress])
    ncb --> outs2
  end
  outs -->|HTTP| Ollama[(Ollama)]
  outs2 -->|gRPC| Qdrant[(Qdrant)]
  outs2 -->|bolt| Neo4j[(Neo4j)]
  subgraph obs [observability-svc]
    metrics[(Prometheus)]
  end
  tcb -.metrics.-> metrics
  ocb -.metrics.-> metrics
  qcb -.metrics.-> metrics
  ncb -.metrics.-> metrics
  ccb -.metrics.-> metrics`,
    ipo: {
      input: [
        'Call target: async callable (lambda: http_client.post(...))',
        'Expected exception type(s) that count as failure',
        'Current breaker state (CLOSED / OPEN / HALF_OPEN)',
        'Thresholds: failure_threshold, recovery_timeout_s',
      ],
      process: [
        'Guard: if OPEN and recovery_timeout not elapsed → fast-fail',
        'Guard: if OPEN and recovery_timeout elapsed → HALF_OPEN',
        'Invoke target',
        'On success: reset counter; HALF_OPEN → CLOSED',
        'On expected exception: counter++; maybe transition to OPEN',
        'Emit metric transitions + record opened_at',
      ],
      output: [
        'Return value from target (CLOSED/HALF_OPEN path)',
        'CircuitOpenError (OPEN path — no upstream call)',
        'Original exception (on expected failure, propagated)',
        'Prometheus: state gauge, failures counter, opens counter, rejections counter',
      ],
    },
    interviewTalkingPoint:
      "Circuit breaker is the single pattern I'd deploy first when hooking up any external dependency. The state machine is simple — CLOSED, OPEN, HALF_OPEN — but the subtle bit is the HALF_OPEN probe: one request, not a flood, and a single failure tips it back to OPEN. In DocuMind we have five specialized breakers layered on top of the generic one, including an 'inverted-polarity' breaker on the OTel exporter so that dead telemetry NEVER blocks user requests. Telemetry is best-effort; user requests are not.",
    analysis: {
      comparison: [
        { scenario: 'With CB (DocuMind)', behavior: 'Slow Ollama trips the breaker in <1s; subsequent calls fail fast; upstream recovery automatic.' },
        { scenario: 'Without CB', behavior: 'Threads pile up waiting; pod thread pool exhausts; liveness probe fails; K8s evicts; cascade.' },
        { scenario: 'Retry-only (no CB)', behavior: 'Retries hammer a struggling upstream, making recovery slower or impossible.' },
        { scenario: 'Bulkhead (alternative)', behavior: 'Isolates pools of threads/connections per tenant; complements but doesn’t replace CB.' },
      ],
      edgeCases: [
        'Flaky-but-recovering upstream: threshold too tight = permanent OPEN. Tune with real data.',
        'HALF_OPEN probe races with user traffic — lock the transition to one caller.',
        'Non-idempotent calls under OPEN — surface CircuitOpenError to user, don’t silently retry later.',
        'Metric cardinality explosion if breaker name includes tenant_id — use static names only.',
      ],
      limitations: [
        'CB cannot tell you why upstream is slow; pairs with metrics/traces.',
        'Per-process state — three pods have three independent breakers. Not global.',
        'Only protects the caller, not the callee.',
      ],
      challenges: [
        'Choosing failure_threshold without historical data.',
        'Setting recovery_timeout: too short causes thrashing, too long delays recovery.',
        'Distinguishing transient network blips from real outages.',
      ],
      solutions: [
        'Start with failure_threshold=5, recovery_timeout=60s; measure in staging; tune.',
        'Emit transitions to a dashboard; pattern-match false positives.',
        'Use tail-based sampling on traces so OPEN-state requests are always captured.',
      ],
    },
    business: {
      valueProposition: 'Converts a slow or flapping upstream from a cascading outage into a graceful degradation. MTTR measured in seconds instead of minutes.',
      kpis: [
        { name: 'Cascading incidents / quarter', target: '0' },
        { name: 'CB OPEN events / day', target: 'Alerting threshold tuned per dependency' },
        { name: 'HALF_OPEN success rate', target: '> 80% (higher = recovery is real)' },
        { name: 'MTTR when upstream fails', target: '< 60s to graceful degrade' },
      ],
      roi: 'One avoided cascading incident per quarter typically justifies the entire investment; plus lower on-call load.',
    },
    audit: {
      checklist: [
        'Every external call wrapped in a CB',
        'Breaker names are static (no tenant_id in labels)',
        'Thresholds documented and reviewed quarterly',
        'Metrics dashboards exist per named breaker',
        'HALF_OPEN probe lock prevents thundering-herd',
        'Alert on open > 5 min (possible stuck state)',
      ],
      qualityMatrix: [
        { dimension: 'Resilience', score: 'High', note: 'Prevents thread-pool exhaustion cascade' },
        { dimension: 'Observability', score: 'High', note: '4 metrics per breaker; Grafana dashboard' },
        { dimension: 'Complexity', score: 'Low', note: 'Single state machine; easy to reason about' },
        { dimension: 'Coverage', score: 'High', note: '5 specialized + CCB; every critical path' },
        { dimension: 'Tuning ease', score: 'Medium', note: 'Thresholds need real-traffic data' },
      ],
      externalLinks: [
        { label: 'Martin Fowler — CircuitBreaker', url: 'https://martinfowler.com/bliki/CircuitBreaker.html' },
        { label: 'Netflix Hystrix (deprecated)', url: 'https://github.com/Netflix/Hystrix/wiki' },
        { label: 'resilience4j (JVM ref impl)', url: 'https://resilience4j.readme.io' },
        { label: 'OWASP Top 10 for LLMs (rel. CCB)', url: 'https://owasp.org/www-project-top-10-for-large-language-model-applications/' },
      ],
    },
  },

  // ----------------------------------------------------- api-gateway
  'api-gateway': {
    flowchart: `flowchart LR
  client([client]) --> tls[TLS termination]
  tls --> corr[Inject correlation-id<br/>if missing]
  corr --> auth{JWT valid?}
  auth -->|no| reject[401 + error envelope]
  auth -->|yes| tenant[Extract tenant + role claims]
  tenant --> rl{Rate limit bucket<br/>for tenant+IP}
  rl -->|exceeded| throttle[429 + Retry-After]
  rl -->|ok| idem{Idempotency-Key<br/>present?}
  idem -->|yes + cached| replay[Replay cached 2xx]
  idem -->|no / miss| route[Route by path]
  route -->|/api/v1/docs/*| ingest[ingestion-svc]
  route -->|/api/v1/ask| retr[retrieval-svc + inference-svc]
  route -->|/api/v1/admin/*| admin[admin backend<br/>elevated auth required]
  ingest --> resp[Collect response]
  retr --> resp
  admin --> resp
  resp --> out([client])`,
    sequence: `sequenceDiagram
  autonumber
  participant C as Client
  participant NG as NGINX edge
  participant GW as API Gateway (Go)
  participant ID as identity-svc
  participant BE as Backend svc

  C->>NG: HTTPS request
  NG->>GW: HTTP (mesh-internal mTLS via Istio)
  GW->>GW: Inject X-Correlation-Id
  GW->>GW: Parse Authorization: Bearer <jwt>
  alt JWT verified locally (pubkey cache hit)
    GW->>GW: Local verify + scopes
  else pubkey miss
    GW->>ID: GET /v1/jwks
    ID-->>GW: JWKS
    GW->>GW: Local verify
  end
  GW->>GW: Rate-limit bucket (tenant+IP)
  alt Idempotency-Key cached
    GW-->>C: replay cached 2xx
  else new / miss
    GW->>BE: forward with tenant + correlation-id
    BE-->>GW: response
    GW->>GW: Cache response if Idempotency-Key set
    GW-->>C: response + correlation-id header
  end`,
    networkFlow: `flowchart TB
  net((Public internet))
  subgraph lb [Cloud LB]
    l[Load balancer]
  end
  subgraph edge [Edge tier]
    n[NGINX<br/>TLS + static cache]
  end
  subgraph gw [API Gateway tier]
    g1[api-gateway pod 1]
    g2[api-gateway pod 2]
  end
  subgraph mesh [Istio mesh]
    s1[identity-svc]
    s2[ingestion-svc]
    s3[retrieval-svc]
    s4[inference-svc]
    s5[governance-svc]
  end
  subgraph data [Data tier]
    pg[(Postgres)]
    qd[(Qdrant)]
    rd[(Redis)]
    kf[(Kafka)]
  end
  net --> l --> n
  n -->|mTLS| g1
  n -->|mTLS| g2
  g1 -->|mTLS| s1
  g1 -->|mTLS| s2
  g1 -->|mTLS| s3
  g1 -->|mTLS| s4
  g1 -->|mTLS| s5
  s2 --> pg
  s2 --> qd
  s2 --> rd
  s2 --> kf
  s3 --> pg
  s3 --> qd
  s3 --> rd
  s4 --> rd`,
    ipo: {
      input: [
        'HTTPS request from any client (browser, SDK, curl)',
        'Authorization: Bearer <JWT> OR X-API-Key',
        'X-Correlation-Id (optional; injected if missing)',
        'X-Idempotency-Key (optional; used on POST)',
        'Tenant context derived from JWT claims',
      ],
      process: [
        'TLS termination (at NGINX; gateway is HTTP inside mesh)',
        'JWT verify using cached JWKS from identity-svc',
        'Tenant + role extraction; enforce scopes per path',
        'Per-tenant + per-IP rate bucket (token-bucket algorithm)',
        'Idempotency-Key lookup; replay on hit',
        'Path routing to internal service (internal mTLS via Istio)',
        'Response header injection (correlation-id, security headers)',
      ],
      output: [
        '2xx from backend, forwarded verbatim',
        '401 (bad JWT), 403 (wrong scope), 429 (rate), 5xx (backend)',
        'All responses carry X-Correlation-Id',
        'Metrics: request_count, duration_ms, by_route, by_tenant',
        'OTel span root: parent of every downstream call',
      ],
    },
    interviewTalkingPoint:
      "The API gateway is not 'just' a router — it is the single place where every cross-cutting concern lives so no service re-implements them badly. JWT verification happens once, here; rate limits are enforced here so a bursty tenant can't overwhelm the mesh; idempotency is centralized so every POST is safe to retry. I wrote it in Go specifically because this path is latency-critical and the JWT verify inner loop is hot. The rule I follow: anything that every service would otherwise re-implement goes in the gateway.",
    analysis: {
      comparison: [
        { scenario: 'With gateway', behavior: 'Cross-cutting concerns centralized; services stay thin; one audit surface.' },
        { scenario: 'No gateway', behavior: 'Auth, rate-limit, correlation-id reimplemented per service; drift and bugs inevitable.' },
        { scenario: 'Kong / KrakenD', behavior: 'OSS alternatives; more features but more ops surface; we chose Go + chi for minimal dependency.' },
        { scenario: 'AWS API Gateway', behavior: 'Managed + autoscaling; cost scales with requests; locks us into AWS.' },
      ],
      edgeCases: [
        'JWKS rotation mid-request — keep a short cache with graceful refresh.',
        'Idempotency key collision across tenants — always key by (tenant, key).',
        'Rate-limit while tenant is cold-starting — use soft-start (first 30s) to avoid locking legit traffic.',
        'Gateway restarts during deploy — hold-open existing connections via graceful drain.',
      ],
      limitations: [
        'Single logical control point — scaling is vertical at rate-limit layer.',
        'Any bug here affects every request; highest-blast-radius code in the stack.',
        'Stateful (idempotency cache) — needs Redis, not memory, for horizontal scale.',
      ],
      challenges: [
        'Keeping the hot path under microsecond-scale overhead per request.',
        'Testing the full matrix of auth × rate-limit × idempotency × route.',
        'Safe config changes (a typo in a route rule can cause a global outage).',
      ],
      solutions: [
        'Route config loaded from a versioned ConfigMap with canary rollout.',
        'go-test benchmarks gating PR merges on the JWT verify path.',
        'Idempotency cache in Redis with per-tenant TTL.',
      ],
    },
    business: {
      valueProposition: 'Single control point for auth, rate-limit, correlation — every service stays thin, audit surface is one codebase.',
      kpis: [
        { name: 'Gateway p95 latency', target: '< 10 ms' },
        { name: '401 rate (bad JWT)', target: 'Trend baseline; spike = attack signal' },
        { name: '429 rate', target: 'Per-tenant; capacity planning signal' },
        { name: 'Correlation-id coverage', target: '100% requests' },
      ],
      roi: 'Saves auth + rate-limit + correlation wiring per service (~2 engineer-weeks each); security reviews are one codebase, not N.',
    },
    audit: {
      checklist: [
        'JWT verify uses JWKS from identity-svc (no shared secret)',
        'JWKS cache respects Cache-Control max-age',
        'Rate limits per (tenant, IP) — not just IP',
        'Idempotency cache keyed by (tenant, key) with TTL',
        '/admin/* routes require elevated scope',
        'Security headers set on every response (HSTS, CSP, X-Frame-Options)',
        'Graceful shutdown hooks tested during deploy',
      ],
      qualityMatrix: [
        { dimension: 'Security', score: 'High', note: 'Centralized auth; elevated /admin scope' },
        { dimension: 'Performance', score: 'High', note: 'Go hot path + JWKS cache; p95 < 10ms' },
        { dimension: 'Observability', score: 'High', note: 'Correlation-id root + structured logs' },
        { dimension: 'Availability', score: 'High', note: 'Stateless + horizontal scale + drain' },
        { dimension: 'Risk', score: 'High impact if buggy', note: 'Highest blast radius — test thoroughly' },
      ],
      externalLinks: [
        { label: 'microservices.io — API Gateway', url: 'https://microservices.io/patterns/apigateway.html' },
        { label: 'RFC 7519 — JWT', url: 'https://www.rfc-editor.org/rfc/rfc7519' },
        { label: 'RFC 6750 — Bearer Token', url: 'https://www.rfc-editor.org/rfc/rfc6750' },
        { label: 'Stripe — Idempotency', url: 'https://stripe.com/docs/api/idempotent_requests' },
      ],
    },
  },

  // ----------------------------------------------------- nginx-cdn
  'nginx-cdn': {
    flowchart: `flowchart LR
  client([browser / SDK]) --> dns[DNS resolves<br/>to edge PoP]
  dns --> tls[TLS termination<br/>+ HTTP/2 + HSTS]
  tls --> wl{Static or dynamic?}
  wl -->|/assets, /static| cachek{Cache hit?}
  cachek -->|hit, fresh| srv[Serve from cache<br/>Cache-Control: public]
  cachek -->|miss or stale| orig[Origin fetch:<br/>api-gateway]
  orig --> store[Store in cache<br/>per Cache-Control]
  store --> srv
  wl -->|/api| fwd[Forward to api-gateway<br/>add proxy headers]
  fwd --> rsp[Backend response]
  rsp --> comp[gzip + brotli compress<br/>strip hop-by-hop headers]
  srv --> comp
  comp --> out([client])`,
    sequence: `sequenceDiagram
  autonumber
  participant C as Client
  participant DNS
  participant NG as NGINX edge (PoP)
  participant CACHE as Edge cache
  participant GW as API Gateway

  C->>DNS: GET app.documind.ai
  DNS-->>C: A rec → closest PoP
  C->>NG: HTTPS (TLS 1.3)
  NG->>NG: HSTS, security headers, rate-check
  alt /assets/* (static)
    NG->>CACHE: key=host+path+Vary
    alt cache hit + fresh
      CACHE-->>NG: 200 + X-Cache: HIT
    else miss or stale
      NG->>GW: conditional GET (If-None-Match)
      GW-->>NG: 200 body + ETag OR 304
      NG->>CACHE: write entry (respect Cache-Control)
      CACHE-->>NG: stored
    end
    NG-->>C: 200 with X-Cache: HIT|MISS
  else /api/* (dynamic)
    NG->>GW: proxy_pass + X-Real-IP + X-Correlation-Id
    GW-->>NG: response
    NG-->>C: response (compressed, security headers)
  end`,
    networkFlow: `flowchart TB
  subgraph edge [Edge PoP]
    direction TB
    ng[NGINX]
    cch[(Local cache)]
    ng <--> cch
  end
  subgraph origin [Origin region]
    lb[Internal LB]
    subgraph mesh [Istio mesh]
      gw[api-gateway]
    end
  end
  user([user in EU]) -->|TLS to nearest PoP| ng
  user2([user in US]) -->|TLS to nearest PoP| ng
  ng -->|HTTPS + keep-alive| lb
  lb -->|mTLS| gw`,
    ipo: {
      input: [
        'HTTPS request (browser, SDK, any HTTP client)',
        'Host header, path, cookies',
        'Accept-Encoding (gzip / br)',
        'If-None-Match / If-Modified-Since for validators',
      ],
      process: [
        'TLS 1.3 termination (edge cert)',
        'HTTP/2 or HTTP/3 negotiation',
        'Security header injection: HSTS, X-Frame-Options, CSP',
        'Cache lookup for static paths (key = host + path + Vary)',
        'Origin fetch on miss; write-through on 2xx',
        'Conditional revalidation via ETag / Last-Modified',
        'gzip + brotli compression',
        'Proxy pass for /api/* with X-Real-IP + X-Forwarded-For',
        'Per-IP rate-limit (fallback to gateway for per-tenant)',
      ],
      output: [
        'Cached static response (X-Cache: HIT) or proxied dynamic response',
        '304 Not Modified when validator matches',
        'Compressed body for supported Accept-Encoding',
        'Access log with request_time + upstream_response_time',
        'Metrics: cache_hit_ratio, upstream_5xx_count, tls_session_reuse',
      ],
    },
    interviewTalkingPoint:
      "NGINX at the edge does two things that nothing else should: TLS termination and static-asset caching near the user. The dynamic /api traffic goes right through to the gateway, but /assets and /static hit a local cache at the PoP, so a user in Frankfurt never waits on an origin round-trip to us-east-1. The caching is safe only because we namespace every cache-eligible response with Cache-Control and Vary headers set by the service — the edge doesn't guess. If you want a single sentence: the edge is the latency compressor, the gateway is the policy enforcer, and the mesh is the identity enforcer. Three layers, three jobs.",
    analysis: {
      comparison: [
        { scenario: 'With edge NGINX', behavior: 'Static assets served from nearest PoP; TLS terminated at edge; origin p95 unaffected by static traffic.' },
        { scenario: 'No CDN', behavior: 'Every asset goes to origin; latency scales with user distance; bandwidth bill high.' },
        { scenario: 'Cloudflare / Fastly', behavior: 'Managed global CDN; more PoPs; vendor lock + cost per GB; our NGINX gives us control.' },
        { scenario: 'AWS CloudFront', behavior: 'Deeply AWS-integrated; signed URLs built-in; locks you to AWS.' },
      ],
      edgeCases: [
        'Origin returns stale ETag — edge keeps serving old content until TTL expires. Force-purge on admin action.',
        'Cache poisoning via unvalidated headers — set Vary carefully, never cache on cookie-dependent URLs.',
        'Upload endpoints must bypass the edge (NGINX proxy_request_buffering off) to avoid double-buffering.',
        'Very large responses (>10MB) — disable sendfile-dependent buffering for streaming.',
      ],
      limitations: [
        'Edge cache is strictly static; dynamic personalized content bypasses it.',
        'No per-user caching without risk of cross-user leakage.',
        'TLS certs must be rotated across all edges — automate with cert-manager.',
      ],
      challenges: [
        'Cache invalidation across edges during hot deploys.',
        'Coordinating Cache-Control headers across service teams.',
        'Keeping edge-side rate-limits consistent with gateway-side.',
      ],
      solutions: [
        'purge-on-deploy hook (CI triggers edge purge after a successful rollout).',
        'A shared style guide for Cache-Control in every service.',
        'IP-based rate-limit at edge; tenant-based at gateway (layered defense).',
      ],
    },
    business: {
      valueProposition: 'Latency compressor: users in any region hit a nearby PoP, origin is unloaded. Bandwidth bill drops with cache-hit ratio.',
      kpis: [
        { name: 'Cache-hit ratio', target: '> 85% on static assets' },
        { name: 'Edge p95', target: '< 100ms globally' },
        { name: 'Origin offload', target: 'Assets bandwidth moved to edge' },
        { name: 'TLS session reuse', target: '> 60% (signal of healthy keepalives)' },
      ],
      roi: 'Cache-hit ratio > 85% typically cuts origin bandwidth by 60-80%; direct bill reduction.',
    },
    audit: {
      checklist: [
        'TLS 1.3 minimum; legacy ciphers disabled',
        'HSTS with preload; minimum 1 year',
        'CSP set at edge or gateway (not both, to avoid conflicts)',
        'Cache-Control: public only where safe; private / no-store on dynamic',
        'Upload endpoints bypass the edge (no double buffering)',
        'Rate limits on /api/* with sane burst allowance',
        'Access logs shipped to ELK with correlation-id intact',
      ],
      qualityMatrix: [
        { dimension: 'Latency', score: 'High', note: 'Edge cache + TLS termination near users' },
        { dimension: 'Security', score: 'High', note: 'HSTS, CSP, modern TLS enforced' },
        { dimension: 'Cost control', score: 'High', note: 'Cache-hit ratio cuts origin bandwidth' },
        { dimension: 'Operability', score: 'Medium', note: 'Cache purge across PoPs is the tricky bit' },
      ],
      externalLinks: [
        { label: 'NGINX docs', url: 'https://nginx.org/en/docs/' },
        { label: 'MDN — Cache-Control', url: 'https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Cache-Control' },
        { label: 'HSTS preload list', url: 'https://hstspreload.org' },
        { label: 'Mozilla SSL config', url: 'https://ssl-config.mozilla.org' },
      ],
    },
  },

  // ----------------------------------------------------- kiali (via Istio tool if present, else its own)
  // (Kiali is not its own tool entry; its content lives under Istio visualization.)

  // ----------------------------------------------------- elk
  elk: {
    flowchart: `flowchart LR
  app([service pod]) -->|stdout JSON| fb[Filebeat DaemonSet]
  fb -->|TCP 5044| ls[Logstash]
  ls -->|parse + enrich| es[(Elasticsearch cluster)]
  es --> kb[Kibana]
  kb --> ops([on-call engineer])
  subgraph enrich [enrichment]
    geo[geoip]
    corr[correlation-id link]
    tenant[tenant_id normalization]
  end
  ls -.via filter plugins.-> enrich`,
    sequence: `sequenceDiagram
  autonumber
  participant App as Service pod
  participant FB as Filebeat
  participant LS as Logstash
  participant ES as Elasticsearch
  participant KB as Kibana
  App->>App: structlog.info(event="query.served", correlation_id=cid)
  App->>FB: stdout → container log file
  FB->>FB: tail + multiline parse
  FB->>LS: beats protocol (5044)
  LS->>LS: filter{ json, mutate, grok }
  LS->>ES: bulk index<br/>index=documind-logs-%{+yyyy.MM.dd}
  Note over ES: ILM policy:<br/>hot 7d → warm 30d → cold 90d
  KB->>ES: search by correlation_id
  ES-->>KB: hits
  KB-->>ops: timeline, KQL filters`,
    networkFlow: `flowchart TB
  subgraph k8s [Kubernetes cluster]
    subgraph pod [Every pod]
      app[Service]
    end
    subgraph node [Every node]
      fb[Filebeat DaemonSet]
    end
    subgraph logging [logging namespace]
      ls[Logstash StatefulSet]
      es[(Elasticsearch cluster<br/>3 masters + 3 data)]
      kb[Kibana]
    end
  end
  ops([on-call]) -->|HTTPS| kb
  app -->|stdout| fb
  fb -->|tls| ls
  ls -->|tls| es
  kb -->|tls| es`,
    ipo: {
      input: [
        'JSON log lines from stdout (structlog JsonFormatter)',
        'Every line carries: timestamp, level, correlation_id, tenant_id, event, fields',
        'Filebeat tails /var/log/containers/*.log',
      ],
      process: [
        'Filebeat multiline join (stack traces)',
        'Logstash filter: parse JSON, enrich (geoip, hostname), normalize fields',
        'Index routing by date: documind-logs-YYYY.MM.dd',
        'ILM policy: hot 7d (SSD) → warm 30d (HDD) → cold 90d (frozen) → delete',
        'Field mapping: keyword for IDs, text for messages, date for timestamps',
      ],
      output: [
        'Searchable index in Elasticsearch',
        'Kibana dashboards (service health, error rate, correlation-id timeline)',
        'Saved searches for common triage flows',
        'Watcher alerts on error-rate spikes or specific message patterns',
      ],
    },
    interviewTalkingPoint:
      "ELK is how you find out what actually happened when the metrics say something went wrong. The load-bearing bit is the schema discipline: every log is JSON, every JSON has correlation_id, and the correlation_id is set at the edge. That means a single Kibana KQL — correlation_id:\"abc123\" — shows every hop for a user's request across every service. Without that you're grep-joining stack traces across five pods at 3am. The ILM policy matters too: logs age from hot to cold to deleted so the cluster doesn't bankrupt us.",
    analysis: {
      comparison: [
        { scenario: 'ELK', behavior: 'Deep KQL search + field typing; heavy to operate; expensive at scale.' },
        { scenario: 'Loki', behavior: 'Log-as-stream, label-based search; cheaper; weaker full-text.' },
        { scenario: 'Managed (Datadog/Splunk)', behavior: 'Zero-ops; pay per GB ingested; hard to exit.' },
        { scenario: 'stdout + grep', behavior: 'Works for one pod; useless across services.' },
      ],
      edgeCases: [
        'Large log bursts during incidents — Filebeat backpressure, Logstash queue fills. Add disk spool.',
        'PII in log messages — scrubber plugin + review of log calls.',
        'Index template drift — pin to a version, migrate with reindex API.',
        'Timezone mismatches — always emit UTC with "Z" suffix.',
      ],
      limitations: [
        'Elasticsearch is RAM-hungry; heap management is a continuous ops task.',
        'Full-text search on unbounded fields can drag clusters.',
        'No built-in trace correlation; you bolt that on via correlation_id.',
      ],
      challenges: [
        'Cost control — logs are cheap to write, expensive to store.',
        'Query performance degrades as shards grow; needs ILM to stay fast.',
        'Parsing multiline stack traces reliably.',
      ],
      solutions: [
        'ILM policy (hot 7d → warm 30d → cold 90d → delete).',
        'Shard sizing guide: 30-50GB per shard.',
        'Filebeat multiline regex tuned per language runtime.',
      ],
    },
    business: {
      valueProposition: 'Incident MTTR dominated by "where is this request?" — ELK makes that answer trivial via correlation_id.',
      kpis: [
        { name: 'Log ingestion lag', target: '< 60s end-to-end' },
        { name: 'Index latency', target: '< 10s from event to searchable' },
        { name: 'Kibana query p95', target: '< 3s' },
        { name: 'Storage cost / GB / month', target: 'ILM-managed; trend with traffic' },
      ],
      roi: 'Removing 10 minutes from MTTR on one P1 per quarter ≈ tens of thousands of dollars of avoided user-impact.',
    },
    audit: {
      checklist: [
        'Every log line is JSON with timestamp, level, correlation_id, tenant_id',
        'No PII in log body (scrubbed upstream)',
        'Index template pinned and version-controlled',
        'ILM policy deployed (hot → warm → cold → delete)',
        'Snapshot backup to S3 nightly',
        'Kibana roles match org: SRE read-all, dev read-own-service',
      ],
      qualityMatrix: [
        { dimension: 'Coverage', score: 'High', note: 'All services ship to ELK' },
        { dimension: 'Searchability', score: 'High', note: 'KQL on correlation_id or tenant_id' },
        { dimension: 'Cost', score: 'Medium', note: 'ES RAM-hungry; ILM mitigates' },
        { dimension: 'Reliability', score: 'Medium', note: 'Logstash queue needs disk spool for bursts' },
      ],
      externalLinks: [
        { label: 'Elastic Stack docs', url: 'https://www.elastic.co/guide/' },
        { label: 'Filebeat autodiscover', url: 'https://www.elastic.co/guide/en/beats/filebeat/current/configuration-autodiscover.html' },
        { label: 'ILM overview', url: 'https://www.elastic.co/guide/en/elasticsearch/reference/current/index-lifecycle-management.html' },
        { label: 'Kibana KQL', url: 'https://www.elastic.co/guide/en/kibana/current/kuery-query.html' },
      ],
    },
  },

  // ----------------------------------------------------- otel-stack
  'otel-stack': {
    flowchart: `flowchart LR
  app([service]) -->|OTel SDK| exp[OTel Exporter<br/>wrapped in CB]
  exp -->|OTLP gRPC| coll[OTel Collector]
  coll --> route{By signal}
  route -->|traces| jg[Jaeger]
  route -->|metrics| pr[Prometheus]
  route -->|logs| es[(Elasticsearch)]
  jg --> gf[Grafana]
  pr --> gf
  es --> kb[Kibana]
  gf --> user([SRE])
  kb --> user`,
    sequence: `sequenceDiagram
  autonumber
  participant C as Client
  participant GW as Gateway
  participant R as retrieval-svc
  participant I as inference-svc
  participant Coll as OTel Collector
  participant J as Jaeger
  C->>GW: request
  GW->>GW: start span "http.handle"<br/>trace_id=t, span_id=a
  GW->>R: propagate traceparent
  R->>R: start span "retrieval.ann" (parent=a)
  R->>I: propagate traceparent
  I->>I: start span "inference.llm" (parent=b)
  I-->>R: end span + export (async)
  R-->>GW: end span + export
  GW-->>C: response
  GW-->>Coll: OTLP batch (every 1s)
  R-->>Coll: OTLP batch
  I-->>Coll: OTLP batch
  Coll->>J: tail-based sampling decision
  J->>J: store complete trace
  Note over Coll,J: Observability CB wraps OTLP export —<br/>dead collector never blocks user requests`,
    networkFlow: `flowchart TB
  subgraph pods [App pods]
    a1[retrieval-svc]
    a2[inference-svc]
    a3[ingestion-svc]
  end
  subgraph tel [Telemetry namespace]
    coll[OTel Collector DaemonSet]
    pr[(Prometheus TSDB)]
    jg[(Jaeger Cassandra / Badger)]
    gf[Grafana]
  end
  a1 -->|OTLP:4317| coll
  a2 -->|OTLP:4317| coll
  a3 -->|OTLP:4317| coll
  coll -->|metrics| pr
  coll -->|traces| jg
  pr --> gf
  jg --> gf
  sre([SRE]) --> gf
  alert[Alertmanager] -.reads from.-> pr
  alert -->|webhook| pager([PagerDuty])`,
    ipo: {
      input: [
        'OTel SDK calls from app code (span start/end, metric increment, log emit)',
        'Resource attributes: service.name, deployment.environment, k8s.pod.uid',
        'traceparent header propagated through every inter-service call',
      ],
      process: [
        'SDK batches in memory; wraps exporter in Observability CB',
        'OTel Collector receives OTLP gRPC; applies processors (tail sampling, attribute filter)',
        'Route by signal: traces→Jaeger, metrics→Prometheus, logs→Elasticsearch',
        'Prometheus scrape + alertmanager fan-out to PagerDuty',
        'Grafana dashboards read from Prometheus + Jaeger + Kibana datasources',
      ],
      output: [
        'Distributed trace viewable in Jaeger (one click from correlation-id)',
        'Metrics graphable in Grafana with SLO burn-rate alerts',
        'Logs searchable in Kibana, cross-linked by correlation-id',
        'PagerDuty pages on error-budget-burn or breaker-open events',
      ],
    },
    interviewTalkingPoint:
      "OpenTelemetry is how every other observability tool gets its data. The critical design decision most teams skip is the Observability Circuit Breaker around the exporter: if the collector is down and your exporter retries with a 10-second timeout, every user request hangs 10 seconds waiting on telemetry. A dead collector becomes a full outage. We wrap exporters in an inverted-polarity breaker so dead telemetry is silent — user requests are sacred, telemetry is best-effort. Second point: the traceparent propagation discipline is non-negotiable. If any service forgets to propagate, the trace breaks and you lose multi-hop debugging in exactly the incident where you need it.",
    analysis: {
      comparison: [
        { scenario: 'OTel (DocuMind)', behavior: 'One SDK, vendor-neutral, traces+metrics+logs unified; swap backends by config.' },
        { scenario: 'Vendor SDK (Datadog / New Relic)', behavior: 'Faster onboarding; deep lock-in; harder to exit.' },
        { scenario: 'Prometheus + Jaeger directly', behavior: 'Works, but two SDKs, two wire formats, two sets of context propagation.' },
        { scenario: 'No tracing', behavior: 'Dark in distributed systems; mean time to diagnose 10x worse.' },
      ],
      edgeCases: [
        'Missing traceparent on one hop breaks the whole trace — enforce with middleware.',
        'Exporter blocking under back-pressure — that is what the Observability CB protects against.',
        'High-cardinality labels on metrics cause Prometheus OOM — whitelist label sets.',
        'Sampling decisions made at different hops = truncated traces. Use tail-sampling at the collector.',
      ],
      limitations: [
        'OTel SDK stability varies by language — Python and Go are solid, JS is improving.',
        'Exporters add measurable overhead if poorly tuned.',
        'Tail-sampling needs enough collector memory to hold the window.',
      ],
      challenges: [
        'Coordinating SDK + instrumentation + collector + backend versions.',
        'Teaching developers to add span attributes, not just spans.',
        'Keeping metric cardinality low without losing signal.',
      ],
      solutions: [
        'Pin OTel SDK versions across all services; bump together.',
        'Style guide: span attrs for tenant/correlation; metric labels static only.',
        'Tail-sampling policy: 100% errors, 10% normal, 100% > p99 latency.',
      ],
    },
    business: {
      valueProposition: 'Vendor-neutral observability. One SDK, any backend. Swap vendors by config, not by rewriting instrumentation.',
      kpis: [
        { name: 'Trace completeness', target: '> 99% of requests have end-to-end trace' },
        { name: 'Exporter error rate', target: '< 0.1% (Observability CB should mask transient failures)' },
        { name: 'Metric cardinality', target: '< 100k time-series per service' },
        { name: 'Observability stack availability', target: '99.9% (independent of app SLOs)' },
      ],
      roi: 'Eliminates rewrites when swapping observability vendors; cross-service debugging 5-10x faster.',
    },
    audit: {
      checklist: [
        'OTel SDK version pinned across all services',
        'Trace propagation via W3C traceparent + tracestate',
        'Observability CB wrapping every exporter',
        'Tail-sampling at the collector (100% errors, 10% normal)',
        'Cardinality budget per service documented',
        'Alertmanager → PagerDuty wired with runbook links in payload',
      ],
      qualityMatrix: [
        { dimension: 'Portability', score: 'High', note: 'OTel spec = vendor-agnostic' },
        { dimension: 'Depth', score: 'High', note: 'Three signals unified under one SDK' },
        { dimension: 'Performance impact', score: 'Low', note: 'Batched export, CB-protected' },
        { dimension: 'Ecosystem', score: 'High', note: 'CNCF standard; every major vendor supports' },
      ],
      externalLinks: [
        { label: 'OpenTelemetry docs', url: 'https://opentelemetry.io/docs/' },
        { label: 'W3C Trace Context', url: 'https://www.w3.org/TR/trace-context/' },
        { label: 'Prometheus docs', url: 'https://prometheus.io/docs/' },
        { label: 'Jaeger docs', url: 'https://www.jaegertracing.io/docs/' },
        { label: 'Grafana docs', url: 'https://grafana.com/docs/' },
      ],
    },
  },
};
