# DocuMind Frontend — Next.js 14 + vanilla CSS

Next.js (App Router) with plain vanilla CSS. No Tailwind, no CSS-in-JS, no Material/Chakra.

## Layout

- **Left sidebar** (dark, 240px, fixed) — nav
- **Right content** (white bg, flex-fill, scrollable)
- **Topbar** (dark, tenant pill + admin link)

Design tokens live in `styles/variables.css`. Components reference them; no hardcoded hex / px for layout.

## Routes

```
app/
├── layout.tsx          # shell: sidebar + topbar + content
├── page.tsx            # / → redirects to /ask
├── error.tsx           # route-level error boundary
├── loading.tsx         # default suspense fallback
├── upload/page.tsx     # upload a PDF/DOCX/TXT/MD/HTML
├── documents/page.tsx  # list tenant's documents
├── ask/page.tsx        # query the RAG pipeline
├── admin/page.tsx      # operator dashboard (live health, prompts, tools, upstreams)
├── admin/monitoring    # monitoring + runtime status + operations map
├── admin/techstack     # installed vs pending tool catalog
├── admin/sidecar       # sidecar advisor events + ratings + drill-down
├── admin/sidecar/telemetry  # council telemetry surface
├── admin/forensics     # trace → draft → audit → HITL reconstruction
├── admin/agentic       # agentic task submission + policy simulation
├── admin/agentic/control-plane # normalized project/task/approval/memory chain
└── app-meta/           # frontend-owned local routes (not proxied to gateway)
```

## Operator/admin surfaces

These are the main operational routes exposed by the frontend today:

- `/admin`
  - primary operator dashboard
  - health, breakers, prompts, tools, upstreams, build info, trace-link panel
- `/admin/monitoring`
  - monitoring + technical operations map
  - live service/runtime status
  - running/unhealthy services
  - resource consumers from local Docker stats
  - observability links for Grafana / Prometheus / Alertmanager / Jaeger
  - local stack inventory including node-exporter and cAdvisor
  - agent activity summary
- `/admin/techstack`
  - installed vs pending tool inventory
- `/admin/sidecar`
  - advisor events, live ratings, search/filter/pagination
- `/admin/sidecar/[eventId]`
  - event drill-down with reviewer metadata
- `/admin/sidecar/telemetry`
  - council histogram / telemetry surface
- `/admin/forensics`
  - trace → draft → audit → HITL reconstruction
- `/admin/agentic`
  - bounded task/project creation and policy simulation
- `/admin/agentic/control-plane`
  - normalized plan rows, task runs, approvals, memories

## Frontend-owned local routes

Not every route in this app should proxy to the backend gateway.

Current local runtime routes:

- `/app-meta/build-info`
  - current frontend build identity
- `/app-meta/runtime-status`
  - local compose/runtime status
  - Docker service states
  - Docker stats resource usage
  - Ollama systemd status

Also kept local under App Router APIs:

- `/api/v1/tts`
- `/api/v1/sidecar/*`

Everything else under `/api/*` is still rewritten to the gateway.

## Run

```bash
# from /mnt/deepa/rag/services/frontend
cp .env.local.example .env.local
npm install          # pnpm i also works
npm run dev          # http://localhost:3000
```

The dev server proxies most `/api/*` traffic to the API gateway (default `http://localhost:8080`), so the browser stays same-origin.

Exception:

- frontend-owned routes stay local:
  - `/api/v1/tts`
  - `/api/v1/sidecar/*`
  - `/app-meta/*`

## Environment

- `NEXT_PUBLIC_API_BASE_URL` — gateway origin (browser-visible, public)
- `NEXT_PUBLIC_DEMO_TENANT_ID` — inserted as `X-Tenant-ID` on every request

Never put secrets under `NEXT_PUBLIC_*` — those ship to the browser.

## API client

`lib/api.ts` is the ONE place any code makes HTTP calls. It:

- Attaches `X-Tenant-ID` + `X-Correlation-ID` per request
- Parses the standard error envelope (`{detail, error_code, correlation_id}`) into `ApiError`
- Enforces a 30s default timeout (120s for upload / ask)
- Accepts an external `AbortSignal` so components can cancel in-flight calls on unmount

Don't fetch from components directly.

It also now wraps local runtime/operator surfaces such as:

- `frontendBuildInfo()`
- `frontendRuntimeStatus()`
- `healthDetailed()`
- `healthTools()`
- `healthPrompts()`
- `healthUpstreams()`
- `healthTechstack()`
- agentic read/write endpoints

## Scripts

```bash
npm run dev     # dev server
npm run build   # production build
npm run start   # run production bundle
npm run lint    # next lint (zero warnings)
npm run test    # vitest
```

## Current-state notes

Be explicit about these:

- this frontend is no longer just upload/documents/ask
- it now acts as the main operator shell for monitoring, sidecar, forensics, and agentic control-plane work
- several admin/deep-dive pages are educational/reference surfaces
- several other admin pages are live operational surfaces

Practical split:

- **live operational UI:** `/admin*`, `/app-meta/*`, sidecar routes, monitoring, techstack, agentic control-plane
- **reference/explainer UI:** many `admin/*/deep` routes and `tools/*` routes

## Why Next.js + vanilla CSS (and not Vite+React / Tailwind / CRA)

- Per global CLAUDE.md §14.1: Next.js is the default frontend stack.
- Server Components + file-system routing remove boilerplate.
- Vanilla CSS keeps the design tokens first-class and the dependency tree small.
- No Tailwind class soup — every layout decision has a named variable.
