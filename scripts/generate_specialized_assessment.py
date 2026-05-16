#!/usr/bin/env python3
"""
Specialized assessment generator — frontend OR backend profile.

Produces a profile-specific 25-section production assessment Markdown
report that complements the generic FOLDER_REPORT.md. Use this when
the folder has frontend-specific concerns (state mgmt, routing,
accessibility, F12 console, bundle size, etc.) or backend-specific
concerns (API standards, DB transactions, caching, observability,
AI/RAG, etc.) that the generic template doesn't drill into.

Output filename:
  --profile frontend → <folder>/FRONTEND_ASSESSMENT_REPORT.md
  --profile backend  → <folder>/BACKEND_ASSESSMENT_REPORT.md

Auto-detected metadata varies by profile:
  frontend → React/Next.js version, TS/TSX files, components,
             package.json deps, build tool (next/vite/webpack)
  backend  → FastAPI/Express/Go runtime, DB libs, async/sync,
             external HTTP clients, AI/LLM deps, OTel wiring

Reviewer fills Status (check/X/warn/TBD) / Notes / Risk / Recommendation
per row. Skeleton starts with TBD per global honesty rule (never claim
10/10 without evidence).

Usage:
  python3 scripts/generate_specialized_assessment.py \\
      --folder services/frontend --profile frontend --reviewer "X" --force

  python3 scripts/generate_specialized_assessment.py \\
      --folder services/inference-svc --profile backend --reviewer "X" --force

  python3 scripts/generate_specialized_assessment.py \\
      --batch all --profile auto --reviewer "X" --force
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
IGNORE = {"__pycache__", "node_modules", ".git", ".venv", ".venv-redteam",
          "dist", "build", ".next", ".loop", ".archive-shims", ".tools",
          "mlruns", "data"}


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except (PermissionError, OSError):
        return ""


def _is_ignored(path: Path) -> bool:
    return bool(set(path.parts) & IGNORE)


def _count_ext(folder: Path, ext: str) -> int:
    return sum(1 for p in folder.rglob(f"*{ext}") if not _is_ignored(p))


def _git_authors(folder: Path) -> str:
    try:
        r = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "shortlog", "-sn",
             "--no-merges", "HEAD", "--",
             str(folder.relative_to(REPO_ROOT)) if folder.is_relative_to(REPO_ROOT) else "."],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode != 0:
            return "(git unavailable)"
        lines = [line.strip() for line in r.stdout.split("\n") if line.strip()][:4]
        return ", ".join(lines) or "(none)"
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return "(git unavailable)"


def detect_profile(folder: Path) -> str:
    """Auto-detect frontend vs backend from folder contents."""
    pkg_json = folder / "package.json"
    if pkg_json.exists():
        body = _read(pkg_json)
        if any(k in body for k in ('"next"', '"react"', '"vite"', '"vue"', '"svelte"')):
            return "frontend"
    if _count_ext(folder, ".tsx") > 0 or _count_ext(folder, ".jsx") > 0:
        return "frontend"
    if (folder / "app").is_dir() and (folder / "package.json").exists():
        return "frontend"
    return "backend"


# ---- Auto-detection ------------------------------------------------------

@dataclass
class FrontendFacts:
    framework: str = ""
    ts_files: int = 0
    tsx_files: int = 0
    jsx_files: int = 0
    has_app_router: bool = False
    has_pages_router: bool = False
    has_components: bool = False
    has_zod: bool = False
    has_swr: bool = False
    has_react_query: bool = False
    has_tailwind: bool = False
    has_playwright: bool = False
    has_vitest: bool = False
    has_storybook: bool = False
    deps_count: int = 0
    git_authors: str = ""
    loc: int = 0


@dataclass
class BackendFacts:
    runtime: str = ""
    py_files: int = 0
    go_files: int = 0
    has_fastapi: bool = False
    has_uvicorn: bool = False
    has_pydantic: bool = False
    db_libs: List[str] = field(default_factory=list)
    queue_libs: List[str] = field(default_factory=list)
    cache_libs: List[str] = field(default_factory=list)
    http_libs: List[str] = field(default_factory=list)
    ai_libs: List[str] = field(default_factory=list)
    obs_libs: List[str] = field(default_factory=list)
    auth_libs: List[str] = field(default_factory=list)
    async_funcs: int = 0
    has_dockerfile: bool = False
    has_pyproject: bool = False
    has_go_mod: bool = False
    test_files: int = 0
    git_authors: str = ""
    loc: int = 0


def _grep_any(folder: Path, patterns: List[str], exts: tuple = (".py",)) -> bool:
    rgx = re.compile("|".join(re.escape(p) for p in patterns))
    for ext in exts:
        for p in folder.rglob(f"*{ext}"):
            if _is_ignored(p):
                continue
            if rgx.search(_read(p)):
                return True
    return False


def _loc(folder: Path) -> int:
    total = 0
    for p in folder.rglob("*"):
        if not p.is_file() or _is_ignored(p):
            continue
        if p.suffix not in {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".sh"}:
            continue
        total += sum(1 for line in _read(p).split("\n") if line.strip())
    return total


def introspect_frontend(folder: Path) -> FrontendFacts:
    f = FrontendFacts(
        ts_files=_count_ext(folder, ".ts"),
        tsx_files=_count_ext(folder, ".tsx"),
        jsx_files=_count_ext(folder, ".jsx"),
        has_app_router=(folder / "app").is_dir(),
        has_pages_router=(folder / "pages").is_dir(),
        has_components=(folder / "components").is_dir(),
        git_authors=_git_authors(folder),
        loc=_loc(folder),
    )
    pkg = folder / "package.json"
    if pkg.exists():
        body = _read(pkg)
        if '"next"' in body:
            f.framework = "Next.js"
        elif '"react"' in body:
            f.framework = "React (SPA)"
        elif '"vue"' in body:
            f.framework = "Vue"
        elif '"svelte"' in body:
            f.framework = "Svelte"
        elif '"vite"' in body:
            f.framework = "Vite"
        f.has_zod = '"zod"' in body
        f.has_swr = '"swr"' in body
        f.has_react_query = '"@tanstack/react-query"' in body or '"react-query"' in body
        f.has_tailwind = '"tailwindcss"' in body
        f.has_playwright = '"@playwright/test"' in body or '"playwright"' in body
        f.has_vitest = '"vitest"' in body
        f.has_storybook = '"storybook"' in body or '"@storybook' in body
        f.deps_count = body.count('"@') + body.count('"react"')
    return f


def introspect_backend(folder: Path) -> BackendFacts:
    b = BackendFacts(
        py_files=_count_ext(folder, ".py"),
        go_files=_count_ext(folder, ".go"),
        has_dockerfile=(folder / "Dockerfile").exists(),
        has_pyproject=(folder / "pyproject.toml").exists(),
        has_go_mod=(folder / "go.mod").exists(),
        git_authors=_git_authors(folder),
        loc=_loc(folder),
    )
    if b.py_files > 0 and b.go_files == 0:
        b.runtime = f"Python ({b.py_files} files)"
    elif b.go_files > 0 and b.py_files == 0:
        b.runtime = f"Go ({b.go_files} files)"
    elif b.py_files > 0 and b.go_files > 0:
        b.runtime = f"Mixed (Python {b.py_files} + Go {b.go_files})"
    else:
        b.runtime = "Unknown"

    if _grep_any(folder, ["fastapi", "FastAPI"], (".py",)):
        b.has_fastapi = True
    if _grep_any(folder, ["uvicorn"], (".py",)):
        b.has_uvicorn = True
    if _grep_any(folder, ["pydantic", "BaseModel", "BaseSettings"], (".py",)):
        b.has_pydantic = True

    db_patterns = {
        "asyncpg": ["asyncpg"],
        "psycopg": ["psycopg"],
        "SQLAlchemy": ["sqlalchemy", "sessionmaker"],
        "Redis": ["aioredis", "redis"],
        "Qdrant": ["qdrant_client"],
        "Elasticsearch": ["elasticsearch"],
        "Neo4j": ["neo4j"],
    }
    for label, patterns in db_patterns.items():
        if _grep_any(folder, patterns, (".py", ".go")):
            b.db_libs.append(label)
    queue_patterns = {
        "Kafka": ["aiokafka", "kafka-python", "confluent_kafka"],
        "Redis Streams": ["xadd", "XREAD"],
        "RabbitMQ": ["aio_pika", "pika"],
    }
    for label, patterns in queue_patterns.items():
        if _grep_any(folder, patterns, (".py",)):
            b.queue_libs.append(label)
    cache_patterns = {
        "Redis": ["aioredis"],
        "lru_cache": ["@lru_cache"],
    }
    for label, patterns in cache_patterns.items():
        if _grep_any(folder, patterns, (".py",)):
            b.cache_libs.append(label)
    http_patterns = {
        "httpx": ["import httpx", "from httpx"],
        "requests": ["import requests"],
        "aiohttp": ["import aiohttp"],
    }
    for label, patterns in http_patterns.items():
        if _grep_any(folder, patterns, (".py",)):
            b.http_libs.append(label)
    ai_patterns = {
        "LangChain": ["from langchain"],
        "LangGraph": ["from langgraph"],
        "OpenAI": ["from openai", "openai.OpenAI"],
        "Anthropic": ["anthropic.", "from anthropic"],
        "Ollama": ["ollama"],
        "Rebuff (PI defense)": ["rebuff"],
        "Ragas": ["from ragas", "import ragas"],
    }
    for label, patterns in ai_patterns.items():
        if _grep_any(folder, patterns, (".py",)):
            b.ai_libs.append(label)
    obs_patterns = {
        "OpenTelemetry": ["opentelemetry"],
        "Prometheus": ["prometheus_client", "start_http_server"],
        "structlog": ["structlog"],
        "JsonFormatter": ["JsonFormatter"],
    }
    for label, patterns in obs_patterns.items():
        if _grep_any(folder, patterns, (".py",)):
            b.obs_libs.append(label)
    auth_patterns = {
        "JWT": ["jwt.decode", "PyJWT", "jose"],
        "OAuth2": ["OAuth2", "oauthlib"],
        "Custom (Bearer)": ["Bearer "],
    }
    for label, patterns in auth_patterns.items():
        if _grep_any(folder, patterns, (".py",)):
            b.auth_libs.append(label)

    afn_count = 0
    for p in folder.rglob("*.py"):
        if _is_ignored(p):
            continue
        afn_count += len(re.findall(r"\basync def\b", _read(p)))
    b.async_funcs = afn_count

    b.test_files = (
        sum(1 for p in folder.rglob("test_*.py") if not _is_ignored(p))
        + sum(1 for p in folder.rglob("*_test.py") if not _is_ignored(p))
        + sum(1 for p in folder.rglob("*_test.go") if not _is_ignored(p))
    )
    return b


# ---- Rendering -----------------------------------------------------------

def _checklist(title: str, items: List[str]) -> str:
    rows = "\n".join(f"| {i+1}. {c} | TBD | — | — | — |" for i, c in enumerate(items))
    return (
        f"### {title}\n\n"
        "| # / Item | Status | Notes | Risk (H/M/L) | Recommendation |\n"
        "|---|---|---|---|---|\n"
        f"{rows}\n\n"
    )


def render_frontend(f: FrontendFacts, folder: Path, reviewer: str, now: str) -> str:
    metadata = (
        "| Field | Value |\n|---|---|\n"
        f"| Folder | `{folder.relative_to(REPO_ROOT)}` |\n"
        f"| Profile | Frontend |\n"
        f"| Framework | {f.framework or 'Unknown'} |\n"
        f"| TS / TSX / JSX files | {f.ts_files} / {f.tsx_files} / {f.jsx_files} |\n"
        f"| App Router (Next.js) | {'yes' if f.has_app_router else 'no'} |\n"
        f"| Pages Router (Next.js) | {'yes' if f.has_pages_router else 'no'} |\n"
        f"| components/ dir | {'yes' if f.has_components else 'no'} |\n"
        f"| Zod | {'yes' if f.has_zod else 'no'} |\n"
        f"| SWR | {'yes' if f.has_swr else 'no'} |\n"
        f"| TanStack React Query | {'yes' if f.has_react_query else 'no'} |\n"
        f"| Tailwind | {'yes' if f.has_tailwind else 'no'} |\n"
        f"| Playwright (E2E) | {'yes' if f.has_playwright else 'no'} |\n"
        f"| Vitest | {'yes' if f.has_vitest else 'no'} |\n"
        f"| Storybook | {'yes' if f.has_storybook else 'no'} |\n"
        f"| Lines of code (rough) | {f.loc:,} |\n"
        f"| Git authors | {f.git_authors} |\n"
        f"| Reviewer | {reviewer} |\n"
        f"| Generated | {now} |\n\n"
    )
    sections = [
        ("1. Component architecture", [
            "Atomic / molecules / organisms / templates / pages convention applied?",
            "Server vs Client Components correctly split ('use client' only when needed)?",
            "Single-Responsibility per component (< 200 lines)?",
            "Props typed (no `any`)?",
            "No prop drilling > 2 levels (use context / composition)?",
        ]),
        ("2. State management", [
            "Local state (useState/useReducer) for component-local concerns?",
            "Server state via RSC (no client cache when server can fetch)?",
            "Global state minimal (Context only when truly cross-cutting)?",
            "External global state lib (zustand/redux) only if context too coarse?",
            "No state in module-level variables (causes hydration mismatch)?",
        ]),
        ("3. Routing (Next.js App Router)", [
            "File-system routing follows convention (`page.tsx` / `layout.tsx`)?",
            "Dynamic segments `[param]` typed?",
            "Loading states via `loading.tsx`?",
            "Error boundaries via `error.tsx`?",
            "404 via `not-found.tsx`?",
            "Parallel routes for tabs / modals?",
        ]),
        ("4. Data fetching", [
            "Server-side fetch with `next: { revalidate }` for cacheable data?",
            "Client-side fetch uses AbortController + cleanup?",
            "All client fetches in a centralized `services/api.ts`?",
            "Auth header injected automatically?",
            "Error envelope parsed consistently?",
            "Loading + empty + error states for every data fetch?",
        ]),
        ("5. Forms + validation", [
            f"Zod schemas for every form? {'(Zod present)' if f.has_zod else '(Zod missing)'}",
            "Server re-validates (never trust client validation)?",
            "Field-level error messages?",
            "Disable submit button on submission?",
            "Idempotency-Key header for POST?",
        ]),
        ("6. Accessibility (WCAG 2.1 AA)", [
            "Semantic HTML (button vs div with onClick)?",
            "ARIA labels for icon-only buttons?",
            "Keyboard navigation (Tab + Enter + Esc) works?",
            "Color contrast >= 4.5:1?",
            "Focus indicators visible?",
            "Form labels associated (htmlFor)?",
            "Skip-to-content link?",
            "Screen reader tested?",
        ]),
        ("7. Performance - Core Web Vitals", [
            "LCP < 2.5 s (Largest Contentful Paint)?",
            "FID < 100 ms (First Input Delay)?",
            "CLS < 0.1 (Cumulative Layout Shift)?",
            "TTFB < 800 ms (Time to First Byte)?",
            "INP < 200 ms (Interaction to Next Paint)?",
        ]),
        ("8. Bundle size + lazy loading", [
            "Initial JS bundle (gzip) < 200 KB?",
            "Lazy-loaded routes via `next/dynamic`?",
            "Images via `next/image` (auto-srcset)?",
            "Fonts via `next/font` (no CLS)?",
            "Tree-shaking working (no unused imports)?",
            "source-map-explorer audit clean?",
        ]),
        ("9. Security", [
            "No raw-HTML rendering without an HTML sanitizer (e.g. DOMPurify)?",
            "CSP header set (no unsafe-eval)?",
            "HttpOnly + Secure + SameSite cookies?",
            "OAuth flow uses PKCE?",
            "Tokens stored in HttpOnly cookie (not localStorage)?",
            "Secrets NEVER bundled (no NEXT_PUBLIC_* secrets)?",
        ]),
        ("10. Auth flow", [
            "Auth-required routes wrapped in middleware?",
            "Token refresh handled silently?",
            "Logout clears all client state?",
            "Tenant context resolved at layout level?",
        ]),
        ("11. Error boundaries + fallback UI", [
            "Top-level `app/global-error.tsx`?",
            "Per-route `error.tsx`?",
            "User-friendly message (no stack trace)?",
            "Retry button + report-error link?",
        ]),
        ("12. Loading + skeleton states", [
            "Every async data fetch has a loading state?",
            "Skeletons match the final UI shape (no layout shift)?",
            "Suspense boundaries strategically placed?",
        ]),
        ("13. F12 console hygiene", [
            "Zero console errors in production?",
            "Zero React warnings?",
            "No `console.log` in committed code (use logger)?",
            "Network tab: no 4xx / 5xx on happy path?",
            "Network tab: no CORS errors?",
        ]),
        ("14. SEO + meta + structured data", [
            "Title + meta description per route?",
            "Open Graph tags (og:image, og:title)?",
            "Twitter card tags?",
            "Structured data (JSON-LD)?",
            "Sitemap + robots.txt?",
        ]),
        ("15. Internationalization (i18n)", [
            "i18n library configured (next-intl / react-intl)?",
            "All user-facing strings extracted?",
            "RTL support tested?",
            "Date / number / currency locale-aware?",
        ]),
        ("16. Microfrontend (if applicable)", [
            "Module Federation configured (if multi-team)?",
            "Shell + remote contract documented?",
            "Shared deps deduped (single React instance)?",
            "Independent deploy possible?",
        ]),
        ("17. Build + deployment", [
            "Build clean (no warnings)?",
            "Bundle analyzed pre-deploy?",
            "CDN (Vercel / CloudFront / Fastly)?",
            "Cache-Control headers set?",
            "Service worker / PWA (if applicable)?",
        ]),
        ("18. Testing", [
            f"Vitest unit tests? {'(present)' if f.has_vitest else '(absent)'}",
            f"Playwright E2E tests? {'(present)' if f.has_playwright else '(absent)'}",
            "Component tests with React Testing Library?",
            "Accessibility tests (axe-core)?",
            "Visual regression tests?",
            "Coverage >= 60%?",
        ]),
        ("19. Observability", [
            "Web Vitals reported to backend?",
            "Error tracker (Sentry / custom)?",
            "Page-view analytics?",
            "Custom events for key flows?",
        ]),
        ("20. AI / UX (if applicable)", [
            "Streaming LLM responses (SSE)?",
            "Citations rendered inline with source links?",
            "Confidence score shown when low?",
            "Hallucination flag surfaced?",
            "Stop-generation button?",
            "Token-budget indicator?",
        ]),
        ("21. Browser compatibility", [
            "Target browsers documented (latest 2 versions)?",
            "Polyfills for older targets?",
            "Tested in Chrome / Firefox / Safari / Edge?",
            "Mobile Safari + Chrome Android tested?",
        ]),
        ("22. Component documentation", [
            f"Storybook present? {'(yes)' if f.has_storybook else '(no)'}",
            "Component props documented?",
            "Usage examples for shared components?",
        ]),
        ("23. Production readiness gates", [
            "Lighthouse score >= 90 (all categories)?",
            "axe-core scan clean?",
            "Bundle size budget met?",
            "Zero blocker accessibility issues?",
            "Privacy policy + cookie banner?",
        ]),
        ("24. Common frontend mistakes (avoid)", [
            "useEffect without cleanup (memory leak)?",
            "fetch without AbortController (race condition)?",
            "Re-renders on every prop change (missing memo)?",
            "Lists without `key` prop?",
            "Inline functions / objects in props (re-render every parent render)?",
            "Direct DOM manipulation outside refs?",
        ]),
        ("25. Sign-off", [
            "Tech Lead reviewed",
            "UX / Design reviewed (accessibility + visual)",
            "Security reviewed (CSP + secrets + auth flow)",
            "Performance reviewed (Lighthouse + Web Vitals)",
            "QA reviewed (E2E + cross-browser)",
            "Product approved",
        ]),
    ]
    body = "".join(_checklist(t, items) for t, items in sections)
    return (
        f"# Frontend Assessment - `{folder.name}`\n\n"
        f"**Profile:** Frontend (auto-detected: {f.framework or 'unknown'})\n"
        f"**Generated:** {now}\n"
        f"**Reviewer:** {reviewer}\n\n"
        f"> 25-section frontend-specific production assessment. Reviewer "
        f"fills Status / Notes / Risk / Recommendation per row. Skeleton "
        f"starts with TBD per global honesty rule (never claim 10/10 without evidence).\n\n"
        f"---\n\n"
        f"## Metadata (auto-detected)\n\n"
        f"{metadata}"
        f"---\n\n"
        f"{body}"
        f"---\n\n"
        f"_Generated by `scripts/generate_specialized_assessment.py "
        f"--profile frontend`. Re-run after major changes._\n"
    )


def render_backend(b: BackendFacts, folder: Path, reviewer: str, now: str) -> str:
    metadata = (
        "| Field | Value |\n|---|---|\n"
        f"| Folder | `{folder.relative_to(REPO_ROOT)}` |\n"
        f"| Profile | Backend |\n"
        f"| Runtime | {b.runtime} |\n"
        f"| Has FastAPI | {'yes' if b.has_fastapi else 'no'} |\n"
        f"| Has Pydantic | {'yes' if b.has_pydantic else 'no'} |\n"
        f"| Has Uvicorn | {'yes' if b.has_uvicorn else 'no'} |\n"
        f"| Async functions | {b.async_funcs} |\n"
        f"| DB libs | {', '.join(b.db_libs) or '_(none)_'} |\n"
        f"| Queue libs | {', '.join(b.queue_libs) or '_(none)_'} |\n"
        f"| Cache libs | {', '.join(b.cache_libs) or '_(none)_'} |\n"
        f"| HTTP client libs | {', '.join(b.http_libs) or '_(none)_'} |\n"
        f"| AI / LLM libs | {', '.join(b.ai_libs) or '_(none)_'} |\n"
        f"| Observability libs | {', '.join(b.obs_libs) or '_(none)_'} |\n"
        f"| Auth libs | {', '.join(b.auth_libs) or '_(none)_'} |\n"
        f"| Test files | {b.test_files} |\n"
        f"| Dockerfile | {'yes' if b.has_dockerfile else 'no'} |\n"
        f"| pyproject.toml | {'yes' if b.has_pyproject else 'no'} |\n"
        f"| go.mod | {'yes' if b.has_go_mod else 'no'} |\n"
        f"| Lines of code (rough) | {b.loc:,} |\n"
        f"| Git authors | {b.git_authors} |\n"
        f"| Reviewer | {reviewer} |\n"
        f"| Generated | {now} |\n\n"
    )
    sections = [
        ("1. API standards", [
            "REST / gRPC choice documented?",
            "Versioned (`/api/v1/`)?",
            "OpenAPI spec auto-generated?",
            "kebab-case paths + snake_case JSON?",
            "Plural nouns for collection endpoints?",
        ]),
        ("2. Authentication & Authorization", [
            f"AuthN implemented? Detected: {', '.join(b.auth_libs) or 'NONE - flag risk'}",
            "AuthZ scope check at every endpoint?",
            "JWT rotation strategy?",
            "Tenant context resolved from token?",
            "Service-to-service mTLS?",
        ]),
        ("3. Request validation", [
            f"Pydantic / Zod for every request? Detected Pydantic: {b.has_pydantic}",
            "Field validators + type coercion?",
            "422 response with field-level details on failure?",
            "Request body size cap enforced?",
        ]),
        ("4. Error handling + envelope", [
            "Consistent `{detail, error_code, correlation_id}` envelope?",
            "No stack traces in user-facing errors?",
            "4xx vs 5xx correctly distinguished?",
            "Domain exceptions mapped to HTTP codes?",
        ]),
        ("5. Database", [
            f"DB libs: {', '.join(b.db_libs) or 'NONE'}",
            "RLS policies for multi-tenant?",
            "Migrations in expand -> migrate -> contract order?",
            "Indexes on every WHERE + ORDER BY column?",
            "Transactions narrow (no HTTP / LLM inside)?",
            "Connection pooling sized correctly?",
            "WAL mode for SQLite?",
        ]),
        ("6. Caching", [
            f"Cache libs: {', '.join(b.cache_libs) or 'NONE'}",
            "Per-tenant cache keys (no cross-tenant leak)?",
            "TTL strategy (no unbounded growth)?",
            "Invalidation on source change?",
            "Semantic cache for LLM (30-60% savings)?",
        ]),
        ("7. Queue / events", [
            f"Queue libs: {', '.join(b.queue_libs) or 'NONE'}",
            "Idempotent consumers (handle duplicates)?",
            "Dead letter queue?",
            "Event schema versioned + in registry?",
            "Outbox pattern for dual writes?",
        ]),
        ("8. Async + concurrency", [
            f"Async functions: {b.async_funcs}",
            "No blocking I/O inside `async def`?",
            "Timeouts on every external call?",
            "ThreadPool for CPU-bound work?",
            "Bulkhead isolation for hot paths?",
        ]),
        ("9. External clients (HTTP)", [
            f"HTTP client libs: {', '.join(b.http_libs) or 'NONE'}",
            "Circuit breaker around every external dep?",
            "Retry with exponential backoff + jitter?",
            "Timeouts (connect + read)?",
            "Connection pool reused (not per-request)?",
            "Fallback chain documented?",
        ]),
        ("10. Background workers", [
            "Workers managed by lifespan (not raw threads)?",
            "Error handling updates job status?",
            "Graceful shutdown on SIGTERM?",
            "Heartbeat / health probe?",
        ]),
        ("11. Logging", [
            f"Structured logging libs: {', '.join(b.obs_libs) or 'NONE'}",
            "JSON output (no print())?",
            "correlation_id + tenant_id + actor on every line?",
            "PII redaction (email, ssn, api_key)?",
            "No log inside hot loops (use counters)?",
        ]),
        ("12. Tracing (OpenTelemetry)", [
            f"OTel installed? {'OpenTelemetry' in b.obs_libs}",
            "Spans for every external call?",
            "Baggage propagated across services?",
            "Sampling configured (head + tail)?",
            "Exporter to Jaeger / Tempo?",
        ]),
        ("13. Metrics (RED + custom)", [
            f"Prometheus installed? {'Prometheus' in b.obs_libs}",
            "Rate / Errors / Duration (RED) per endpoint?",
            "Custom business metrics?",
            "Per-tenant labels (cost attribution)?",
            "Side-channel /metrics port (avoid app middleware)?",
        ]),
        ("14. Security", [
            "OWASP Top 10 reviewed?",
            "No secrets in code (gitleaks clean)?",
            "Secrets in Vault / env (not hardcoded)?",
            "Encryption at rest for sensitive columns?",
            "TLS 1.3 in transit?",
            "Rate limiting per tenant + per endpoint?",
            "Input length caps (DoS prevention)?",
        ]),
        ("15. Performance", [
            "p95 latency within SLO?",
            "No N+1 queries (verified by EXPLAIN ANALYZE)?",
            "Pagination on every list endpoint?",
            "Streaming for large responses?",
            "GZip middleware for JSON > 1 KB?",
        ]),
        ("16. Scalability", [
            "Service stateless (HPA-ready)?",
            "Database sharding strategy?",
            "Hot-tenant detection + isolation?",
            "Cache locality (sticky sessions if needed)?",
        ]),
        ("17. Reliability", [
            "Graceful degradation when downstream down?",
            "Circuit breaker per backend?",
            "Health probe (startup + liveness + readiness)?",
            "Rollback tested in staging?",
            "DR RTO/RPO per tier?",
        ]),
        ("18. Testing", [
            f"Test files detected: {b.test_files}",
            "Coverage >= 80% statements + 70% branches?",
            "Drill with >= 3 negative assertions per project policy?",
            "Integration tests against real DB (testcontainers)?",
            "Chaos test (DB down, LLM timeout, network partition)?",
        ]),
        ("19. Documentation", [
            "README current (regenerated by global readme generator)?",
            "FOLDER_REPORT.md present?",
            "OpenAPI spec linked?",
            "Runbook for common incidents?",
            "ADR for major design decisions?",
        ]),
        ("20. AI / LLM / RAG (if applicable)", [
            f"AI libs: {', '.join(b.ai_libs) or 'n/a'}",
            "Prompt versioning in registry?",
            "Embedding model versioned + re-embed on bump?",
            "Decision audit row per AI call?",
            "Citation grounding (every claim cited)?",
            "Fairness gate?",
            "Counterfactual generation for regulated decisions?",
            "Model card filed?",
        ]),
        ("21. Production gates", [
            "Code coverage >= 80%?",
            "Zero critical CVEs?",
            "p95 latency within SLO?",
            "No hardcoded secrets?",
            "No PII in logs?",
            "Pagination validated?",
            "N+1 query check passed?",
            "Rollback tested?",
        ]),
        ("22. Deployment", [
            "Helm chart maintained?",
            "Health probes configured?",
            "Canary deploy strategy?",
            "Feature flags for risky changes?",
            "Blue-green or rolling deploy?",
        ]),
        ("23. Observability dashboards", [
            "Grafana dashboard exists + linked?",
            "Alertmanager rules in place?",
            "On-call rotation defined (PagerDuty)?",
            "Runbook URL on alerts?",
        ]),
        ("24. Common backend mistakes (avoid)", [
            "SQL via f-string (use parameters)?",
            "Bare `except:` (use specific exceptions)?",
            "Blocking call in async (move to thread pool)?",
            "`print()` instead of logger?",
            "Module-level mutable state?",
            "Skipping tenant scope check on new endpoint?",
            "Caching across tenants?",
            "Silent fallback for failed external call (raise instead)?",
        ]),
        ("25. Sign-off", [
            "Tech Lead reviewed",
            "Security reviewed (STRIDE + OWASP)",
            "SRE reviewed (runbook + on-call)",
            "Architect reviewed (ADR + capacity)",
            "Compliance reviewed (audit log + retention)",
            "AI Owner reviewed (model card + audit row schema, if AI feature)",
        ]),
    ]
    body = "".join(_checklist(t, items) for t, items in sections)
    return (
        f"# Backend Assessment - `{folder.name}`\n\n"
        f"**Profile:** Backend ({b.runtime})\n"
        f"**Generated:** {now}\n"
        f"**Reviewer:** {reviewer}\n\n"
        f"> 25-section backend-specific production assessment. Reviewer "
        f"fills Status / Notes / Risk / Recommendation per row. Skeleton "
        f"starts with TBD per global honesty rule (never claim 10/10 without evidence).\n\n"
        f"---\n\n"
        f"## Metadata (auto-detected)\n\n"
        f"{metadata}"
        f"---\n\n"
        f"{body}"
        f"---\n\n"
        f"_Generated by `scripts/generate_specialized_assessment.py "
        f"--profile backend`. Re-run after major changes._\n"
    )


# ---- CLI ---------------------------------------------------------------

def _has_relevant_files(folder: Path) -> bool:
    for p in folder.rglob("*"):
        if not p.is_file() or _is_ignored(p):
            continue
        if p.suffix in {".py", ".go", ".ts", ".tsx", ".js", ".jsx"}:
            return True
    return False


def _batch_folders(name: str) -> List[Path]:
    out: List[Path] = []
    if name == "services":
        svc = REPO_ROOT / "services"
        if svc.is_dir():
            out = sorted(p for p in svc.iterdir()
                         if p.is_dir() and _has_relevant_files(p))
    elif name == "libs":
        libs = REPO_ROOT / "libs" / "py"
        if libs.is_dir():
            out = sorted(p for p in libs.iterdir()
                         if p.is_dir() and _has_relevant_files(p))
    elif name == "all":
        out = _batch_folders("services") + _batch_folders("libs")
    return out


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Generate frontend or backend-specific assessment Markdown report.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--folder", "-f", type=Path,
                   help="Single folder to assess.")
    g.add_argument("--batch", "-b", choices=["services", "libs", "all"],
                   help="Run on a named batch.")
    p.add_argument("--profile", choices=["frontend", "backend", "auto"],
                   default="auto",
                   help="Which profile to apply. 'auto' detects via package.json + .tsx files.")
    p.add_argument("--output", "-o", type=Path,
                   help="(single-folder only) custom output path.")
    p.add_argument("--reviewer", default="<Reviewer>")
    p.add_argument("--force", action="store_true")
    return p.parse_args()


def write_one(folder: Path, profile: str, reviewer: str, output: Path,
              force: bool) -> tuple[bool, str]:
    if not folder.is_dir():
        return False, f"not a directory: {folder}"
    actual_profile = detect_profile(folder) if profile == "auto" else profile
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    if actual_profile == "frontend":
        facts = introspect_frontend(folder)
        content = render_frontend(facts, folder, reviewer, now)
        fname = "FRONTEND_ASSESSMENT_REPORT.md"
    else:
        facts = introspect_backend(folder)
        content = render_backend(facts, folder, reviewer, now)
        fname = "BACKEND_ASSESSMENT_REPORT.md"
    out = output if output else folder / fname
    if out.exists() and not force:
        return False, f"SKIP (exists): {out}"
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(content, encoding="utf-8")
    except (PermissionError, OSError) as e:
        return False, f"FAIL {out}: {e}"
    return True, f"WROTE [{actual_profile}] {out} - {len(content):,} bytes"


def main() -> int:
    args = parse_args()
    targets = ([args.folder.resolve()] if args.folder
               else _batch_folders(args.batch))
    if not targets:
        print(f"ERROR: no targets for batch {args.batch}", file=sys.stderr)
        return 1
    summary = {"wrote": 0, "skip": 0, "fail": 0}
    for folder in targets:
        ok, msg = write_one(
            folder, args.profile, args.reviewer,
            args.output if (args.folder and args.output) else None,
            args.force,
        )
        mark = "OK" if ok else ("SKIP" if "SKIP" in msg else "FAIL")
        print(f"  [{mark}] {msg}")
        if ok:
            summary["wrote"] += 1
        elif "SKIP" in msg:
            summary["skip"] += 1
        else:
            summary["fail"] += 1
    print(f"\nSummary: {summary['wrote']} wrote, "
          f"{summary['skip']} skip, {summary['fail']} fail")
    if summary["fail"] > 0:
        return 1
    if args.folder and summary["skip"] > 0 and summary["wrote"] == 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
