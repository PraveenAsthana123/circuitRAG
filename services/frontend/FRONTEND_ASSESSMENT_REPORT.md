# Frontend Assessment - `frontend`

**Profile:** Frontend (auto-detected: Next.js)
**Generated:** 2026-05-16 22:59 UTC
**Reviewer:** Praveen Asthana

> 25-section frontend-specific production assessment. Reviewer fills Status / Notes / Risk / Recommendation per row. Skeleton starts with TBD per global honesty rule (never claim 10/10 without evidence).

---

## Metadata (auto-detected)

| Field | Value |
|---|---|
| Folder | `services/frontend` |
| Profile | Frontend |
| Framework | Next.js |
| TS / TSX / JSX files | 214 / 132 / 0 |
| App Router (Next.js) | yes |
| Pages Router (Next.js) | no |
| components/ dir | yes |
| Zod | yes |
| SWR | no |
| TanStack React Query | no |
| Tailwind | no |
| Playwright (E2E) | yes |
| Vitest | yes |
| Storybook | no |
| Lines of code (rough) | 150,632 |
| Git authors | 194	PraveenAsthana123, 4	Praveen |
| Reviewer | Praveen Asthana |
| Generated | 2026-05-16 22:59 UTC |

---

### 1. Component architecture

| # / Item | Status | Notes | Risk (H/M/L) | Recommendation |
|---|---|---|---|---|
| 1. Atomic / molecules / organisms / templates / pages convention applied? | TBD | — | — | — |
| 2. Server vs Client Components correctly split ('use client' only when needed)? | TBD | — | — | — |
| 3. Single-Responsibility per component (< 200 lines)? | TBD | — | — | — |
| 4. Props typed (no `any`)? | TBD | — | — | — |
| 5. No prop drilling > 2 levels (use context / composition)? | TBD | — | — | — |

### 2. State management

| # / Item | Status | Notes | Risk (H/M/L) | Recommendation |
|---|---|---|---|---|
| 1. Local state (useState/useReducer) for component-local concerns? | TBD | — | — | — |
| 2. Server state via RSC (no client cache when server can fetch)? | TBD | — | — | — |
| 3. Global state minimal (Context only when truly cross-cutting)? | TBD | — | — | — |
| 4. External global state lib (zustand/redux) only if context too coarse? | TBD | — | — | — |
| 5. No state in module-level variables (causes hydration mismatch)? | TBD | — | — | — |

### 3. Routing (Next.js App Router)

| # / Item | Status | Notes | Risk (H/M/L) | Recommendation |
|---|---|---|---|---|
| 1. File-system routing follows convention (`page.tsx` / `layout.tsx`)? | TBD | — | — | — |
| 2. Dynamic segments `[param]` typed? | TBD | — | — | — |
| 3. Loading states via `loading.tsx`? | TBD | — | — | — |
| 4. Error boundaries via `error.tsx`? | TBD | — | — | — |
| 5. 404 via `not-found.tsx`? | TBD | — | — | — |
| 6. Parallel routes for tabs / modals? | TBD | — | — | — |

### 4. Data fetching

| # / Item | Status | Notes | Risk (H/M/L) | Recommendation |
|---|---|---|---|---|
| 1. Server-side fetch with `next: { revalidate }` for cacheable data? | TBD | — | — | — |
| 2. Client-side fetch uses AbortController + cleanup? | TBD | — | — | — |
| 3. All client fetches in a centralized `services/api.ts`? | TBD | — | — | — |
| 4. Auth header injected automatically? | TBD | — | — | — |
| 5. Error envelope parsed consistently? | TBD | — | — | — |
| 6. Loading + empty + error states for every data fetch? | TBD | — | — | — |

### 5. Forms + validation

| # / Item | Status | Notes | Risk (H/M/L) | Recommendation |
|---|---|---|---|---|
| 1. Zod schemas for every form? (Zod present) | TBD | — | — | — |
| 2. Server re-validates (never trust client validation)? | TBD | — | — | — |
| 3. Field-level error messages? | TBD | — | — | — |
| 4. Disable submit button on submission? | TBD | — | — | — |
| 5. Idempotency-Key header for POST? | TBD | — | — | — |

### 6. Accessibility (WCAG 2.1 AA)

| # / Item | Status | Notes | Risk (H/M/L) | Recommendation |
|---|---|---|---|---|
| 1. Semantic HTML (button vs div with onClick)? | TBD | — | — | — |
| 2. ARIA labels for icon-only buttons? | TBD | — | — | — |
| 3. Keyboard navigation (Tab + Enter + Esc) works? | TBD | — | — | — |
| 4. Color contrast >= 4.5:1? | TBD | — | — | — |
| 5. Focus indicators visible? | TBD | — | — | — |
| 6. Form labels associated (htmlFor)? | TBD | — | — | — |
| 7. Skip-to-content link? | TBD | — | — | — |
| 8. Screen reader tested? | TBD | — | — | — |

### 7. Performance - Core Web Vitals

| # / Item | Status | Notes | Risk (H/M/L) | Recommendation |
|---|---|---|---|---|
| 1. LCP < 2.5 s (Largest Contentful Paint)? | TBD | — | — | — |
| 2. FID < 100 ms (First Input Delay)? | TBD | — | — | — |
| 3. CLS < 0.1 (Cumulative Layout Shift)? | TBD | — | — | — |
| 4. TTFB < 800 ms (Time to First Byte)? | TBD | — | — | — |
| 5. INP < 200 ms (Interaction to Next Paint)? | TBD | — | — | — |

### 8. Bundle size + lazy loading

| # / Item | Status | Notes | Risk (H/M/L) | Recommendation |
|---|---|---|---|---|
| 1. Initial JS bundle (gzip) < 200 KB? | TBD | — | — | — |
| 2. Lazy-loaded routes via `next/dynamic`? | TBD | — | — | — |
| 3. Images via `next/image` (auto-srcset)? | TBD | — | — | — |
| 4. Fonts via `next/font` (no CLS)? | TBD | — | — | — |
| 5. Tree-shaking working (no unused imports)? | TBD | — | — | — |
| 6. source-map-explorer audit clean? | TBD | — | — | — |

### 9. Security

| # / Item | Status | Notes | Risk (H/M/L) | Recommendation |
|---|---|---|---|---|
| 1. No raw-HTML rendering without an HTML sanitizer (e.g. DOMPurify)? | TBD | — | — | — |
| 2. CSP header set (no unsafe-eval)? | TBD | — | — | — |
| 3. HttpOnly + Secure + SameSite cookies? | TBD | — | — | — |
| 4. OAuth flow uses PKCE? | TBD | — | — | — |
| 5. Tokens stored in HttpOnly cookie (not localStorage)? | TBD | — | — | — |
| 6. Secrets NEVER bundled (no NEXT_PUBLIC_* secrets)? | TBD | — | — | — |

### 10. Auth flow

| # / Item | Status | Notes | Risk (H/M/L) | Recommendation |
|---|---|---|---|---|
| 1. Auth-required routes wrapped in middleware? | TBD | — | — | — |
| 2. Token refresh handled silently? | TBD | — | — | — |
| 3. Logout clears all client state? | TBD | — | — | — |
| 4. Tenant context resolved at layout level? | TBD | — | — | — |

### 11. Error boundaries + fallback UI

| # / Item | Status | Notes | Risk (H/M/L) | Recommendation |
|---|---|---|---|---|
| 1. Top-level `app/global-error.tsx`? | TBD | — | — | — |
| 2. Per-route `error.tsx`? | TBD | — | — | — |
| 3. User-friendly message (no stack trace)? | TBD | — | — | — |
| 4. Retry button + report-error link? | TBD | — | — | — |

### 12. Loading + skeleton states

| # / Item | Status | Notes | Risk (H/M/L) | Recommendation |
|---|---|---|---|---|
| 1. Every async data fetch has a loading state? | TBD | — | — | — |
| 2. Skeletons match the final UI shape (no layout shift)? | TBD | — | — | — |
| 3. Suspense boundaries strategically placed? | TBD | — | — | — |

### 13. F12 console hygiene

| # / Item | Status | Notes | Risk (H/M/L) | Recommendation |
|---|---|---|---|---|
| 1. Zero console errors in production? | TBD | — | — | — |
| 2. Zero React warnings? | TBD | — | — | — |
| 3. No `console.log` in committed code (use logger)? | TBD | — | — | — |
| 4. Network tab: no 4xx / 5xx on happy path? | TBD | — | — | — |
| 5. Network tab: no CORS errors? | TBD | — | — | — |

### 14. SEO + meta + structured data

| # / Item | Status | Notes | Risk (H/M/L) | Recommendation |
|---|---|---|---|---|
| 1. Title + meta description per route? | TBD | — | — | — |
| 2. Open Graph tags (og:image, og:title)? | TBD | — | — | — |
| 3. Twitter card tags? | TBD | — | — | — |
| 4. Structured data (JSON-LD)? | TBD | — | — | — |
| 5. Sitemap + robots.txt? | TBD | — | — | — |

### 15. Internationalization (i18n)

| # / Item | Status | Notes | Risk (H/M/L) | Recommendation |
|---|---|---|---|---|
| 1. i18n library configured (next-intl / react-intl)? | TBD | — | — | — |
| 2. All user-facing strings extracted? | TBD | — | — | — |
| 3. RTL support tested? | TBD | — | — | — |
| 4. Date / number / currency locale-aware? | TBD | — | — | — |

### 16. Microfrontend (if applicable)

| # / Item | Status | Notes | Risk (H/M/L) | Recommendation |
|---|---|---|---|---|
| 1. Module Federation configured (if multi-team)? | TBD | — | — | — |
| 2. Shell + remote contract documented? | TBD | — | — | — |
| 3. Shared deps deduped (single React instance)? | TBD | — | — | — |
| 4. Independent deploy possible? | TBD | — | — | — |

### 17. Build + deployment

| # / Item | Status | Notes | Risk (H/M/L) | Recommendation |
|---|---|---|---|---|
| 1. Build clean (no warnings)? | TBD | — | — | — |
| 2. Bundle analyzed pre-deploy? | TBD | — | — | — |
| 3. CDN (Vercel / CloudFront / Fastly)? | TBD | — | — | — |
| 4. Cache-Control headers set? | TBD | — | — | — |
| 5. Service worker / PWA (if applicable)? | TBD | — | — | — |

### 18. Testing

| # / Item | Status | Notes | Risk (H/M/L) | Recommendation |
|---|---|---|---|---|
| 1. Vitest unit tests? (present) | TBD | — | — | — |
| 2. Playwright E2E tests? (present) | TBD | — | — | — |
| 3. Component tests with React Testing Library? | TBD | — | — | — |
| 4. Accessibility tests (axe-core)? | TBD | — | — | — |
| 5. Visual regression tests? | TBD | — | — | — |
| 6. Coverage >= 60%? | TBD | — | — | — |

### 19. Observability

| # / Item | Status | Notes | Risk (H/M/L) | Recommendation |
|---|---|---|---|---|
| 1. Web Vitals reported to backend? | TBD | — | — | — |
| 2. Error tracker (Sentry / custom)? | TBD | — | — | — |
| 3. Page-view analytics? | TBD | — | — | — |
| 4. Custom events for key flows? | TBD | — | — | — |

### 20. AI / UX (if applicable)

| # / Item | Status | Notes | Risk (H/M/L) | Recommendation |
|---|---|---|---|---|
| 1. Streaming LLM responses (SSE)? | TBD | — | — | — |
| 2. Citations rendered inline with source links? | TBD | — | — | — |
| 3. Confidence score shown when low? | TBD | — | — | — |
| 4. Hallucination flag surfaced? | TBD | — | — | — |
| 5. Stop-generation button? | TBD | — | — | — |
| 6. Token-budget indicator? | TBD | — | — | — |

### 21. Browser compatibility

| # / Item | Status | Notes | Risk (H/M/L) | Recommendation |
|---|---|---|---|---|
| 1. Target browsers documented (latest 2 versions)? | TBD | — | — | — |
| 2. Polyfills for older targets? | TBD | — | — | — |
| 3. Tested in Chrome / Firefox / Safari / Edge? | TBD | — | — | — |
| 4. Mobile Safari + Chrome Android tested? | TBD | — | — | — |

### 22. Component documentation

| # / Item | Status | Notes | Risk (H/M/L) | Recommendation |
|---|---|---|---|---|
| 1. Storybook present? (no) | TBD | — | — | — |
| 2. Component props documented? | TBD | — | — | — |
| 3. Usage examples for shared components? | TBD | — | — | — |

### 23. Production readiness gates

| # / Item | Status | Notes | Risk (H/M/L) | Recommendation |
|---|---|---|---|---|
| 1. Lighthouse score >= 90 (all categories)? | TBD | — | — | — |
| 2. axe-core scan clean? | TBD | — | — | — |
| 3. Bundle size budget met? | TBD | — | — | — |
| 4. Zero blocker accessibility issues? | TBD | — | — | — |
| 5. Privacy policy + cookie banner? | TBD | — | — | — |

### 24. Common frontend mistakes (avoid)

| # / Item | Status | Notes | Risk (H/M/L) | Recommendation |
|---|---|---|---|---|
| 1. useEffect without cleanup (memory leak)? | TBD | — | — | — |
| 2. fetch without AbortController (race condition)? | TBD | — | — | — |
| 3. Re-renders on every prop change (missing memo)? | TBD | — | — | — |
| 4. Lists without `key` prop? | TBD | — | — | — |
| 5. Inline functions / objects in props (re-render every parent render)? | TBD | — | — | — |
| 6. Direct DOM manipulation outside refs? | TBD | — | — | — |

### 25. Sign-off

| # / Item | Status | Notes | Risk (H/M/L) | Recommendation |
|---|---|---|---|---|
| 1. Tech Lead reviewed | TBD | — | — | — |
| 2. UX / Design reviewed (accessibility + visual) | TBD | — | — | — |
| 3. Security reviewed (CSP + secrets + auth flow) | TBD | — | — | — |
| 4. Performance reviewed (Lighthouse + Web Vitals) | TBD | — | — | — |
| 5. QA reviewed (E2E + cross-browser) | TBD | — | — | — |
| 6. Product approved | TBD | — | — | — |

---

_Generated by `scripts/generate_specialized_assessment.py --profile frontend`. Re-run after major changes._
