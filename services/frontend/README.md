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
└── admin/page.tsx      # admin panels (placeholder)
```

## Run

```bash
# from /mnt/deepa/rag/services/frontend
cp .env.local.example .env.local
npm install          # pnpm i also works
npm run dev          # http://localhost:3000
```

The dev server proxies `/api/*` to the API gateway (default `http://localhost:8080`), so the browser stays same-origin.

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

## Scripts

```bash
npm run dev     # dev server
npm run build   # production build
npm run start   # run production bundle
npm run lint    # next lint (zero warnings)
npm run test    # vitest
```

## Why Next.js + vanilla CSS (and not Vite+React / Tailwind / CRA)

- Per global CLAUDE.md §14.1: Next.js is the default frontend stack.
- Server Components + file-system routing remove boilerplate.
- Vanilla CSS keeps the design tokens first-class and the dependency tree small.
- No Tailwind class soup — every layout decision has a named variable.
