'use client';

import DeepDiveCrossRefs from '../../../../components/DeepDiveCrossRefs';
import UniversalDeepDive, { type Topic } from '../../../../components/UniversalDeepDive';

const TOPICS: Topic[] = [
  {
    slug: 'frontend-stack',
    title: '1. Frontend stack (Next.js + RSC + Mermaid)',
    status: 'shipped',
    coreConcept: 'A Next.js 14+ App Router application under services/frontend that combines server-rendered admin pages, BFF API routes, and the universal deep-dive framework. Server Components by default; client components only where state/effects/event handlers require it. Vanilla CSS via design tokens — no Tailwind, no CSS-in-JS. Mermaid renders diagrams client-side from string source.',
    problem: 'Admin surfaces need rich content (mermaid diagrams, code samples, drill-down navigation) AND interactive bits (forms, ratings, real-time panels) AND server-side data fetching with auth. Picking a stack that does all three without 5 frameworks competing is the actual problem.',
    whyThisApproach: 'Next.js App Router unifies SSR + RSC + BFF in one process — admin pages render server-side with auth context, client components handle interactivity, BFF routes own backend integration. Vanilla CSS + design tokens: variable system survives framework churn. Mermaid client-side: heavy dependency only loads where needed.',
    whenToUse: ['Admin/internal-tool surfaces with rich content + targeted interactivity', 'TypeScript-strict projects where BFF + UI type-share matters', 'Single-team Phase-1 deployments where SSR + BFF co-location wins', 'Content-heavy admin where SSR-cache wins over client-render'],
    whenNotToUse: ['High-throughput public-facing apps (split BFF/UI; dedicated gateway)', 'Mobile-first apps where Next.js SSR adds little (use Expo / React Native)', 'Static-only documentation sites (Docusaurus / VitePress is leaner)'],
    input: 'TypeScript + .tsx files + design tokens + content data',
    process: [
      'Next.js App Router resolves /admin/<topic>/deep/page.tsx',
      'Page renders server-side with content data (no client JS for static parts)',
      'Client components ("use client") activate only where needed (forms, mermaid renderer)',
      'CSS variables in styles/variables.css define the design token surface',
      'BFF routes under app/api/v1/ proxy to backend services with correlation_id',
      'Mermaid client component lazy-loads + renders diagram strings',
    ],
    output: 'SSR admin pages + interactive client components + BFF routes, all in one process.',
    flowchart: `flowchart LR
  br[Browser] -->|/admin/...| ng[Next.js]
  ng -->|RSC| ssr[Server Component]
  ssr --> data[Content data]
  ssr --> css[Design tokens]
  ng -->|"use client"| cli[Client Component]
  cli --> mermaid[Mermaid renderer]
  cli --> form[Interactive forms]
  ng -->|/api/v1/...| bff[BFF route]
  bff --> back[Backend service]`,
    sequence: `sequenceDiagram
  autonumber
  participant Br as Browser
  participant N as Next.js
  participant SSR as Server Component
  participant Cli as Client Component
  participant BFF as BFF route
  participant SVC as Backend
  Br->>N: GET /admin/agent-registry/deep
  N->>SSR: render(page.tsx) server-side
  SSR-->>N: HTML + RSC payload
  N-->>Br: SSR HTML
  Br->>Br: hydrate client components
  Cli->>Cli: lazy-load mermaid
  Br->>BFF: POST /api/v1/sidecar/events
  BFF->>SVC: forward with correlation_id
  SVC-->>BFF: response
  BFF-->>Br: canonical envelope`,
    alternatives: [
      { name: 'Pure SPA (CRA / Vite)', tradeoff: 'No SSR; auth state on client; SEO weak; needs separate BFF process' },
      { name: 'Remix / SvelteKit', tradeoff: 'Comparable feature set; smaller ecosystem; team familiarity may not exist' },
      { name: 'Astro', tradeoff: 'Best-in-class for static; weaker for interactive admin tools' },
    ],
    challenges: [
      'Server vs client component discipline (every "use client" should be necessary)',
      'CSS-variable governance (design tokens must be canonical)',
      'Mermaid SSR support (renders client-side; SEO-blind for diagrams)',
      'BFF route proliferation (one file per endpoint)',
      'Type-share between BFF + UI (Zod schemas in shared lib)',
    ],
    edgeCases: [
      { case: 'Page that needs both server data + client state', solution: 'Server component fetches data; passes to client component as props; client owns interactivity' },
      { case: 'Mermaid breaks on server-side render', solution: 'Wrap in dynamic import with ssr:false; client-only render' },
      { case: 'CSS variable conflict across pages', solution: 'styles/variables.css is canonical; per-page overrides discouraged' },
    ],
    failureModes: [
      { mode: 'Heavy client bundle', detect: 'JS payload > 500KB (per global §30 budget)', recover: 'Audit "use client" placement; lazy-load heavy deps' },
      { mode: 'BFF route timeout cascading', detect: 'Multiple routes returning 504 simultaneously', recover: 'Backend service health; circuit breaker on BFF call' },
      { mode: 'Mermaid render error blank panel', detect: 'No diagram visible; console error', recover: 'Validate mermaid string at content-write time' },
    ],
    monitoring: [
      'documind_bff_request_duration_seconds_p95',
      'documind_frontend_lcp_seconds (Web Vitals)',
      'documind_frontend_cls (cumulative layout shift)',
      'Next.js telemetry → OTel via traceparent baggage',
    ],
    testing: [
      'Vitest: services/frontend/tests/sidecar-rating-route.test.ts (BFF route)',
      'Playwright: e2e/app.spec.js (smoke test per global §19)',
      'drill_*_deep_dive (page-level contract for every /admin/<topic>/deep)',
    ],
    security: [
      'Server components don\'t leak secrets (no NEXT_PUBLIC_* prefix on private vars)',
      'BFF validates inputs with Zod before backend call',
      'CSP headers via next.config.js per global §4.3',
      'Auth state on server only — no JWT in localStorage',
    ],
    scaling: [
      '10x: single Next.js process handles ~500 RPS',
      '100x: horizontal scaling Next.js + dedicated NGINX for static assets',
      'Cost driver: server render time per request; cache static pages aggressively',
    ],
    maturity: {
      mvp: 'Plain React SPA with no SSR',
      production: 'Next.js App Router + RSC + BFF + design tokens + Mermaid client + Vitest + Playwright',
      enterprise: 'Multiple Next.js apps split by domain (admin BFF / user BFF) + edge caching + per-tenant theming',
    },
    limitations: [
      'BFF + frontend in same process (split for high-traffic per /admin/api-gateway/deep)',
      'Mermaid SSR-blind (diagrams not in initial HTML)',
      'No per-tenant theming yet',
    ],
    projectFit: [
      'services/frontend/app/* — Next.js App Router pages',
      'services/frontend/components/UniversalDeepDive.tsx — universal framework',
      'services/frontend/components/DeepDiveCrossRefs.tsx — §49 compose footer',
      'services/frontend/styles/variables.css — design tokens',
      'services/frontend/lib/sidecar.ts — BFF helper layer',
    ],
    interviewLine: 'Next.js App Router unifies SSR + RSC + BFF in one process. Server components by default; client components where interactivity demands it. Vanilla CSS + design tokens; Mermaid lazy-loaded client-side. The bet is single-process integration over 5-framework cohabitation; survives until horizontal scaling demands BFF/UI split.',
    implementationSteps: [
      { step: 'App Router structure', logic: 'app/<route>/page.tsx file-system routing; nested layouts; loading.tsx + error.tsx per route.' },
      { step: 'Server-first', logic: 'Default to Server Components; "use client" only when state/effects/handlers require it.' },
      { step: 'Design tokens', logic: 'styles/variables.css defines color/space/typography; never inline hex.' },
      { step: 'BFF routes', logic: 'app/api/v1/<path>/route.ts with Zod validation + correlation_id.' },
      { step: 'Universal deep-dive framework', logic: 'components/UniversalDeepDive.tsx + Topic type; consistent shape across all deep-dives.' },
      { step: 'Compose footer', logic: 'DeepDiveCrossRefs renders 3-7 refs per page; §49 compliance.' },
      { step: 'Drill the page', logic: 'drill_*_deep_dive locks structure (universal fields + footer + sidebar entry).' },
    ],
    codeExample: {
      language: 'typescript',
      code: `// services/frontend/app/admin/<topic>/deep/page.tsx — canonical pattern
'use client';

import DeepDiveCrossRefs from '../../../../components/DeepDiveCrossRefs';
import UniversalDeepDive, { type Topic } from '../../../../components/UniversalDeepDive';

const TOPICS: Topic[] = [
  {
    slug: 'topic-id',
    title: '1. Topic title',
    status: 'shipped' | 'partial' | 'planned',
    coreConcept: '...',
    problem: '...',
    // ... 17 more fields per the universal framework
    flowchart: \`flowchart LR
  a --> b\`,
    sequence: \`sequenceDiagram
  participant A
  A->>A: do thing\`,
  },
];

export default function MyDeepPage() {
  return (
    <>
      <div className="page-header">
        <h1 className="section-title">My deep dive</h1>
      </div>
      {TOPICS.map((t) => <UniversalDeepDive key={t.slug} t={t} />)}
      <DeepDiveCrossRefs refs={REFS_PLACEHOLDER} />
    </>
  );
}`,
    },
    starStory: {
      situation: 'Admin pages were drifting in shape, depth, and cross-reference patterns. New deep-dives were creating their own structures; auditors had no canonical query.',
      task: 'A universal framework that every deep-dive uses, plus a compose-footer pattern that surfaces dependencies between pages.',
      action: 'UniversalDeepDive component + Topic type with 20 canonical fields. DeepDiveCrossRefs for compose footer. Per-page drill locks the structure. Sidebar.tsx is the registry.',
      result: 'Every /admin/<topic>/deep page has identical structure; compose-footer makes the dependency graph greppable; drills lock the contract per page. New deep-dives ship in 1 iteration.',
    },
    interviewTraps: [
      'Defaulting to "use client" everywhere (kills SSR benefits + bundle size)',
      'Inline styles for layout (defeats design-token canonical surface)',
      'BFF routes without Zod validation (injection surface)',
    ],
    finalScript: 'Next.js App Router as the frontend stack: SSR + RSC + BFF in one process, vanilla CSS + design tokens, Mermaid client-side. The discipline — server-first, design tokens canonical, BFF Zod-validated — is what makes a single Next.js process scale to a feature-rich admin platform. When traffic forces split, the BFF logic ports to NGINX + Go behind unchanged contracts.',
  },
  {
    slug: 'backend-services',
    title: '2. Backend services (Python + FastAPI fleet)',
    status: 'shipped',
    coreConcept: 'A polyglot-but-mostly-Python backend fleet under services/. Each service is a thin FastAPI app + numbered SQL migrations + connection-pooled PG / Redis / Neo4j clients. Services are stateless where possible; state lives in PG (orchestrator project memory), SQLite (sidecar event memory), Redis (cache), Neo4j (graph). Services discover each other via compose DNS in dev, k8s service DNS in prod.',
    problem: 'Backends accrete: one Flask app, then a FastAPI service, then an async one, each with different config/auth/observability. Without a service template, every new service costs 2 days of boilerplate + 2 weeks of operational catch-up.',
    whyThisApproach: 'FastAPI + numbered migrations + Pydantic config + class-based services with constructor injection is the global §1-§3 template. Every service follows the same shape; new-service onboarding is 1 day. Stateful services own their schema via migrations; stateless services scale horizontally. Polyglot allowed (Go for gateway, future) but Python is the default.',
    whenToUse: ['New backend service in this project (default to FastAPI template)', 'Async I/O paths (FastAPI excels)', 'OpenAPI-spec-driven contracts', 'Heavy LLM / RAG / ML use cases (Python ecosystem)'],
    whenNotToUse: ['Latency-critical sub-ms paths (Go or Rust)', 'CPU-heavy parallel workloads (Rust / C++)', 'Pure stateless edge functions (Cloudflare Workers / Deno)'],
    input: 'request body (Pydantic) + repo-injected dependencies + correlation_id',
    process: [
      'FastAPI route handler receives request',
      'Pydantic schema validates body; rejects malformed early',
      'Depends() factories inject repo + service instances (DI)',
      'Service class executes business logic; repo handles all SQL',
      'Domain exceptions raised in service → mapped to HTTP via error_handlers',
      'Response shaped via response_model Pydantic class',
      'Audit row written + correlation_id in JSON log',
    ],
    output: 'Validated response with canonical error envelope.',
    flowchart: `flowchart LR
  bff[BFF] -->|JSON| api[FastAPI router]
  api -->|Pydantic| valid[Schema check]
  valid --> svc[Service class]
  svc --> repo[Repo]
  repo --> db[(Postgres / SQLite / Neo4j / Redis)]
  svc --> resp[Pydantic response]
  resp --> bff`,
    sequence: `sequenceDiagram
  autonumber
  participant BFF as BFF
  participant API as FastAPI router
  participant SVC as Service class
  participant Repo as Repo
  participant DB as Database
  BFF->>API: POST /events
  API->>API: Pydantic validate
  API->>SVC: service.create(model)
  SVC->>Repo: insert(record)
  Repo->>DB: SQL
  DB-->>Repo: row
  Repo-->>SVC: model
  SVC-->>API: response model
  API-->>BFF: JSON envelope`,
    alternatives: [
      { name: 'Flask', tradeoff: 'Simpler; sync only; no Pydantic-first; weaker OpenAPI' },
      { name: 'Django', tradeoff: 'Full-stack; ORM-heavy; overkill for service-per-domain' },
      { name: 'Go', tradeoff: 'Faster; less ML ecosystem; allowed for gateway tier per /admin/api-gateway/deep' },
    ],
    challenges: [
      'Migration discipline (numbered SQL only; never edit deployed migrations)',
      'Connection pool tuning per service',
      'Async vs sync routing (FastAPI is async-native; sync routes block event loop)',
      'Cross-service correlation_id propagation',
      'Operational consistency (every service must support health probe + structured log)',
    ],
    edgeCases: [
      { case: 'Service needs both PG + Neo4j', solution: 'Two repo classes; both injected via Depends(); transaction boundary per repo' },
      { case: 'Service needs LLM call', solution: 'Inject LLM client; per-call timeout + circuit breaker; cost trace' },
      { case: 'Service needs to call another service', solution: 'http_client lib with correlation_id propagation + retry budget' },
    ],
    failureModes: [
      { mode: 'Service OOM under load', detect: 'k8s OOMKilled events', recover: 'Tune pod memory; investigate caching; add backpressure' },
      { mode: 'Migration drift', detect: '_migrations table inconsistent across instances', recover: 'Apply remaining migrations; coordinate via blue-green deploy' },
      { mode: 'Connection pool exhaustion', detect: 'TimeoutError on PG connect', recover: 'Tune pool size; investigate slow queries; cache' },
    ],
    monitoring: [
      'documind_<svc>_request_duration_seconds_p95',
      'documind_<svc>_request_total{status_code}',
      'documind_<svc>_db_pool_size{state}',
      'OTel spans per route + repo call',
    ],
    testing: [
      'Per-service unit tests with isolated tmp DB (per global §8)',
      'drill_*_deep_dive locks per-service contract',
      'Integration tests in mcp/tests/ exercising real services',
    ],
    security: [
      'API key middleware (env-driven; per global §4.1)',
      'Pydantic validates all input; no raw dict acceptance',
      'SQL parameterized only (never f-string); per global §4.5',
      'CORS restrictive (no wildcard origins)',
      'Audit row per privileged action (governance §38)',
    ],
    scaling: [
      '10x: single replica per service; PG WAL + Redis pool',
      '100x: horizontal scale stateless services; PG read replicas; Redis sharded',
      '1000x: per-tenant service instances; cross-region replication',
      'Cost driver: PG connection count + LLM token cost; pool tuning + caching',
    ],
    maturity: {
      mvp: 'Single Python file per service; SQLite; ad-hoc routes',
      production: '12-service fleet (orchestrator, sidecar, inference, ingestion, retrieval, identity, governance, finops, evaluation, observability, gateway, frontend) + class-based services + numbered migrations + structured logging',
      enterprise: 'Per-tenant service replicas + cross-region failover + saga compensation + service mesh + canary deploys',
    },
    limitations: [
      'Single Postgres instance (no read replicas yet)',
      'Compose-only deployment (k8s migration is roadmap)',
      'No saga / compensation for distributed-transaction failures',
    ],
    projectFit: [
      'services/agent-orchestrator-svc/ — agent plan + memory + approvals',
      'services/sidecar-advisor/ — council advice + ratings',
      'services/inference-svc/ — LLM call + RAG retrieval',
      'services/ingestion-svc/ — document chunking + embedding',
      'services/retrieval-svc/ — vector + graph retrieval',
      'services/identity-svc/ — JWT + LDAP sync',
      'services/governance-svc/ — audit + policy',
      'services/finops-svc/ — cost tracking',
      'services/evaluation-svc/ — model + prompt eval',
      'services/observability-svc/ — OTel collector + dashboards',
    ],
    interviewLine: 'Backend is a 12-service Python fleet, each FastAPI + Pydantic + numbered migrations + class-based services with constructor injection. Service template is the global §1-§3 spec; new-service onboarding is 1 day. Polyglot allowed (Go for gateway tier) but Python default.',
    implementationSteps: [
      { step: 'Service skeleton', logic: 'main.py + core/{config,exceptions,middleware,auth} + repos/ + services/ + routers/' },
      { step: 'Numbered migrations', logic: 'migrations/NNN_*.sql; runner tracks via _migrations table; idempotent.' },
      { step: 'Pydantic config', logic: 'BaseSettings with env prefix; no os.environ.get scattered.' },
      { step: 'DI everywhere', logic: 'Depends() factories for repos + services; never imports of globals.' },
      { step: 'Class-based services', logic: 'Constructor injection; raise domain exceptions (not HTTPException).' },
      { step: 'Repo per table-group', logic: 'ALL SQL lives in repos; routers stay HTTP-only.' },
      { step: 'Drill the service', logic: 'Per-service drill locks contract end-to-end.' },
    ],
    codeExample: {
      language: 'python',
      code: `# services/agent-orchestrator-svc/app/main.py — service shape
from fastapi import FastAPI, Depends
from .core.config import get_settings, Settings
from .core.dependencies import get_postgres_store
from .postgres_store import PostgresStore
from .service import OrchestratorService
from .models import CreateProjectRequest, ProjectResponse

app = FastAPI(title="agent-orchestrator-svc")

def get_orchestrator_service(
    settings: Settings = Depends(get_settings),
    store: PostgresStore = Depends(get_postgres_store),
) -> OrchestratorService:
    return OrchestratorService(settings=settings, store=store)

@app.post("/projects", response_model=ProjectResponse, status_code=201)
async def create_project(
    req: CreateProjectRequest,
    svc: OrchestratorService = Depends(get_orchestrator_service),
) -> ProjectResponse:
    project = svc.create_project(req)  # raises NotFoundError / ValidationError
    return ProjectResponse.from_model(project)`,
    },
    starStory: {
      situation: 'New backend services were taking 2 days of boilerplate + 2 weeks of operational catch-up. Each service had different config, error handling, logging shape; auditors had to learn each from scratch.',
      task: 'A canonical service template (global §1-§3) that makes new-service onboarding 1 day instead of weeks.',
      action: 'Codified the service skeleton: core/config, core/exceptions, core/middleware, core/auth, repos/, services/, routers/. Pydantic config + numbered migrations + class-based services + DI. 12 services follow the same shape.',
      result: 'New-service onboarding: 1 day. Auditors read one service, know all 12. Operational concerns (auth, logging, error envelope, correlation_id) are solved once at template level.',
    },
    interviewTraps: [
      'Routes containing SQL (violates global §3 layering)',
      'HTTPException raised in service (couples business logic to HTTP)',
      'Module-level mutable state (caches/maps must be instance attributes)',
    ],
    finalScript: 'Backend is a 12-service Python fleet, each shaped by the same template: FastAPI + Pydantic + numbered migrations + class-based services with constructor injection. The discipline — no SQL in routers, no HTTPException in services, no global mutable state — is what makes 12 services cohabit operationally. New-service onboarding is 1 day; auditors learn one service, know all twelve.',
  },
];

export default function StackArchitectureDeepPage() {
  return (
    <>
      <div className="page-header">
        <div className="page-header-copy">
          <h1 className="section-title">Stack architecture deep dive</h1>
          <p className="page-subtitle">
            Two surfaces — Next.js frontend (SSR + RSC + BFF + design tokens)
            and 12-service Python backend fleet (FastAPI + Pydantic +
            numbered migrations + class-based services) — explained through
            the universal 20-dimension framework.
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
          { href: '/admin/techstack', label: 'Tech stack overview', why: 'this page details Next.js + Python; techstack page indexes the broader tooling inventory' },
          { href: '/admin/api-gateway/deep', label: 'API gateway', why: 'BFF routes are the gateway today; this page details the BFF layer the gateway tier slots in front of' },
          { href: '/admin/microservices/deep', label: 'Microservices deep-dive', why: '12-service backend is the microservices substrate; resilience patterns live there' },
          { href: '/admin/principles/deep', label: 'Engineering principles', why: 'global §1-§3 template + §47 17-factor + SOLID — backend service shape is principles applied' },
          { href: '/admin/checklist/deep#governance-ops-checklist', label: 'Governance gate', why: 'service template enforces audit + correlation_id + structured log — release prerequisites per §38' },
        ]}
      />
    </>
  );
}
