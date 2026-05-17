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
    """Auto-detect frontend / backend / database from folder contents."""
    pkg_json = folder / "package.json"
    if pkg_json.exists():
        body = _read(pkg_json)
        if any(k in body for k in ('"next"', '"react"', '"vite"', '"vue"', '"svelte"')):
            return "frontend"
    if _count_ext(folder, ".tsx") > 0 or _count_ext(folder, ".jsx") > 0:
        return "frontend"
    if (folder / "app").is_dir() and (folder / "package.json").exists():
        return "frontend"
    # Database: dominant signals = migrations dir, .sql files, repo/store names
    if ((folder / "migrations").is_dir()
            or (folder / "schemas").is_dir() and _count_ext(folder, ".sql") > 0
            or _count_ext(folder, ".sql") > 3
            or folder.name in {"migrations", "repositories", "db", "database",
                               "schemas", "alembic", "flyway"}):
        return "database"
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


@dataclass
class DatabaseFacts:
    runtime: str = ""
    sql_files: int = 0
    migration_files: int = 0
    has_migrations_dir: bool = False
    has_schema_dir: bool = False
    has_alembic: bool = False
    has_flyway: bool = False
    has_rls: bool = False
    has_jsonb: bool = False
    has_partition: bool = False
    has_index_concurrent: bool = False
    has_foreign_keys: bool = False
    db_engines: List[str] = field(default_factory=list)
    orm_libs: List[str] = field(default_factory=list)
    has_pyproject: bool = False
    git_authors: str = ""
    loc: int = 0


def introspect_database(folder: Path) -> DatabaseFacts:
    b = DatabaseFacts(
        sql_files=_count_ext(folder, ".sql"),
        has_migrations_dir=(folder / "migrations").is_dir(),
        has_schema_dir=(folder / "schemas").is_dir(),
        has_alembic=(folder / "alembic.ini").exists() or (folder / "alembic").is_dir(),
        has_flyway=any(folder.rglob("flyway.conf")),
        has_pyproject=(folder / "pyproject.toml").exists(),
        git_authors=_git_authors(folder),
        loc=_loc(folder),
    )
    b.migration_files = sum(
        1 for p in folder.rglob("*.sql")
        if not _is_ignored(p) and ("migration" in str(p).lower()
                                   or "_initial" in p.name
                                   or re.match(r"\d{3,4}_", p.name))
    )
    b.runtime = (
        "PostgreSQL (SQL files)" if b.sql_files > 0
        else "ORM / migrations folder" if b.has_migrations_dir
        else "Unknown"
    )
    # Detect engines via .sql / .py contents
    # NOTE: _grep_any() re.escapes its patterns, so use plain substrings here.
    eng_patterns = {
        "PostgreSQL": ["CREATE EXTENSION", "SERIAL,", "jsonb", "ON CONFLICT",
                       " RETURNING ", "::text", "::int"],
        "MySQL": ["AUTO_INCREMENT", "UNSIGNED"],
        "SQLite": ["PRAGMA ", "AUTOINCREMENT", "INTEGER PRIMARY KEY"],
        "MongoDB": ["db.collection(", "find_one(", "insert_one("],
    }
    for engine, patterns in eng_patterns.items():
        for pat in patterns:
            if _grep_any(folder, [pat], (".sql", ".py")):
                b.db_engines.append(engine)
                break
    b.db_engines = sorted(set(b.db_engines))
    # ORM libs
    orm_patterns = {
        "SQLAlchemy": ["sqlalchemy", "sessionmaker"],
        "asyncpg (raw)": ["asyncpg"],
        "psycopg": ["psycopg"],
        "Tortoise": ["tortoise"],
        "Prisma": ["prisma"],
        "Alembic (migration)": ["alembic"],
    }
    for label, patterns in orm_patterns.items():
        if _grep_any(folder, patterns, (".py",)):
            b.orm_libs.append(label)
    # Pattern detection in SQL files
    sql_blob = ""
    for p in folder.rglob("*.sql"):
        if _is_ignored(p):
            continue
        sql_blob += _read(p)[:50000]  # cap reads
    b.has_rls = "ROW LEVEL SECURITY" in sql_blob or "ENABLE ROW LEVEL" in sql_blob
    b.has_jsonb = "jsonb" in sql_blob.lower()
    b.has_partition = "PARTITION BY" in sql_blob
    b.has_index_concurrent = "CREATE INDEX CONCURRENTLY" in sql_blob
    b.has_foreign_keys = "FOREIGN KEY" in sql_blob or "REFERENCES " in sql_blob
    return b


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


def render_database(b: DatabaseFacts, folder: Path, reviewer: str, now: str) -> str:
    metadata = (
        "| Field | Value |\n|---|---|\n"
        f"| Folder | `{folder.relative_to(REPO_ROOT)}` |\n"
        f"| Profile | Database |\n"
        f"| Runtime | {b.runtime} |\n"
        f"| SQL files | {b.sql_files} |\n"
        f"| Migration files | {b.migration_files} |\n"
        f"| `migrations/` dir | {'yes' if b.has_migrations_dir else 'no'} |\n"
        f"| `schemas/` dir | {'yes' if b.has_schema_dir else 'no'} |\n"
        f"| Alembic detected | {'yes' if b.has_alembic else 'no'} |\n"
        f"| Flyway detected | {'yes' if b.has_flyway else 'no'} |\n"
        f"| ORM / DB client libs | {', '.join(b.orm_libs) or '_(none)_'} |\n"
        f"| Database engines (detected) | {', '.join(b.db_engines) or '_(none)_'} |\n"
        f"| Row-Level Security present | {'yes' if b.has_rls else 'no'} |\n"
        f"| JSONB column type used | {'yes' if b.has_jsonb else 'no'} |\n"
        f"| Partition tables | {'yes' if b.has_partition else 'no'} |\n"
        f"| `CREATE INDEX CONCURRENTLY` used | {'yes' if b.has_index_concurrent else 'no'} |\n"
        f"| Foreign keys defined | {'yes' if b.has_foreign_keys else 'no'} |\n"
        f"| Lines of code (rough) | {b.loc:,} |\n"
        f"| Git authors | {b.git_authors} |\n"
        f"| Reviewer | {reviewer} |\n"
        f"| Generated | {now} |\n\n"
    )
    sections = [
        ("1. Schema design", [
            f"Database engine documented? Detected: {', '.join(b.db_engines) or 'NONE'}",
            "Normalized to 3NF (no redundant columns)?",
            "Foreign keys defined?" + (f" Detected: {b.has_foreign_keys}"),
            "Surrogate vs natural keys decision documented?",
            "Timestamps (created_at, updated_at) on every mutable table?",
            "Soft-delete pattern (`deleted_at`) vs hard DELETE?",
            "Tenant_id column on every multi-tenant table?",
            "Schema versioned in source control?",
        ]),
        ("2. Migrations", [
            f"Migration files numbered + ordered? Detected: {b.migration_files} files",
            "Each migration is reversible (down.sql)?",
            "Migrations idempotent (safe to re-run)?",
            "Expand -> migrate -> contract pattern (never add+drop same release)?",
            f"Tool: Alembic ({b.has_alembic}) / Flyway ({b.has_flyway}) / custom?",
            "Migration applied via app startup OR explicit deploy step?",
            "Migration history tracked in `_migrations` table?",
            "Production-data backfills tested in staging?",
        ]),
        ("3. Indexing", [
            "Index on every foreign key?",
            "Index on every WHERE column on tables > 1000 rows?",
            "Index on ORDER BY column?",
            "Composite index for hot multi-column queries (column order matters)?",
            "Partial index for soft-delete (`WHERE deleted_at IS NULL`)?",
            f"`CREATE INDEX CONCURRENTLY` for production? Detected: {b.has_index_concurrent}",
            "Index bloat monitored (vacuum + analyze schedule)?",
            "Unused indexes audited periodically?",
        ]),
        ("4. Transactions (ACID)", [
            "Isolation level documented per use case (READ COMMITTED vs SERIALIZABLE)?",
            "Transaction boundaries narrow (no HTTP / LLM inside)?",
            "Rollback on exception?",
            "Retry on serialization failure (40001)?",
            "Pessimistic vs optimistic locking decision per table?",
            "Deadlock prevention (consistent lock order)?",
            "Savepoints used for nested transactions?",
        ]),
        ("5. Multi-tenant isolation", [
            f"Row-Level Security policies enabled? Detected: {b.has_rls}",
            "Tenant context set at connection (`SET app.current_tenant`)?",
            "Tenant-id column on every row?",
            "BYPASSRLS role isolated from app code?",
            "Wrong-tenant query returns ZERO rows (drill-locked)?",
            "Per-tenant connection pool limits?",
        ]),
        ("6. Connection pooling", [
            "Pool size sized per service (not unlimited)?",
            "Connection timeout configured?",
            "Idle connection eviction?",
            "PgBouncer / proxy in front of Postgres?",
            "Read replica routing for read-heavy workloads?",
            "Connection lifecycle managed by ORM (not raw)?",
        ]),
        ("7. Query optimization", [
            "EXPLAIN ANALYZE run on every new hot-path query?",
            "`pg_stat_statements` enabled?",
            "Slow query log in Grafana?",
            "No SELECT * (explicit columns)?",
            "No N+1 (batched IN/JOIN)?",
            "Pagination uses keyset (not OFFSET) for large tables?",
            "JOIN order verified for query planner?",
        ]),
        ("8. Concurrency + locking", [
            "Hot rows identified (FOR UPDATE strategy)?",
            "Lock wait timeout configured?",
            "Long transactions detected + alerted?",
            "Advisory locks for app-level coordination?",
            "VACUUM frequency tuned for high-write tables?",
        ]),
        ("9. Backup + recovery", [
            "Continuous WAL archiving to S3?",
            "Daily snapshots retained N days?",
            "Restore drill monthly (operator runs + measures RTO)?",
            "Backup encryption at rest (KMS)?",
            "Cross-region backup replication?",
            "Point-in-time recovery tested?",
        ]),
        ("10. Partitioning + sharding", [
            f"Partitioned tables? Detected: {b.has_partition}",
            "Partition pruning strategy documented?",
            "Sharding key chosen (avoid hot shards)?",
            "Resharding plan + tooling?",
            "Cross-shard queries minimized?",
        ]),
        ("11. Data types", [
            f"JSONB for flexible schema? Detected: {b.has_jsonb}",
            "ENUM vs lookup table decision documented?",
            "TIMESTAMPTZ (not TIMESTAMP) for all timestamps?",
            "UUID v4 vs v7 / ULID choice documented?",
            "DECIMAL for money (never FLOAT)?",
            "TEXT vs VARCHAR(N) decision (TEXT preferred in PG)?",
        ]),
        ("12. Data integrity", [
            "NOT NULL on every required column?",
            "CHECK constraints for business invariants?",
            "UNIQUE constraints for natural keys?",
            "Foreign key ON DELETE behavior chosen (CASCADE / SET NULL / RESTRICT)?",
            "Trigger usage minimized (logic in app code preferred)?",
        ]),
        ("13. Security", [
            "No DB credentials in code (Vault / env)?",
            "App role least-privileged (SELECT/INSERT/UPDATE only)?",
            "RLS enforced for all app queries?",
            "SQL injection prevented (parameterized queries everywhere)?",
            "Audit log for sensitive table changes?",
            "PII columns encrypted at rest (pgcrypto)?",
        ]),
        ("14. Performance monitoring", [
            "pg_stat_database scraped to Prometheus?",
            "Active connections + waiting count alerted?",
            "Replication lag alerted?",
            "Disk space alerted?",
            "Slow query alerted (> N seconds)?",
        ]),
        ("15. ORM hygiene (if applicable)", [
            f"ORM libs: {', '.join(b.orm_libs) or 'none — using raw SQL'}",
            "Lazy loading avoided in hot paths?",
            "Eager loading explicit (joinedload / selectinload)?",
            "Session lifecycle per request (not per process)?",
            "Bulk operations use batch APIs (not loop + single insert)?",
            "Raw SQL escape hatch documented for complex queries?",
        ]),
        ("16. Caching", [
            "Read-through cache (Redis) for hot rows?",
            "Cache invalidation on source row change?",
            "Per-tenant cache keys (no cross-tenant leak)?",
            "Materialized views for expensive aggregations?",
            "Cache stampede prevention (single flight)?",
        ]),
        ("17. Schema evolution + change mgmt", [
            "Schema change requires ADR?",
            "Schema diff visible in PR review?",
            "Production schema vs staging diff zero?",
            "Downstream consumer notified before schema change?",
            "Breaking schema changes versioned (additive only in v1)?",
        ]),
        ("18. Testing", [
            "Unit tests use real DB (testcontainers / docker)?",
            "Integration tests cover migration up + down?",
            "Drills assert RLS isolation (per project policy)?",
            "Property-based tests for invariants?",
            "Load tests at expected scale?",
        ]),
        ("19. Documentation", [
            "ER diagram in `docs/db/`?",
            "Data dictionary (column descriptions)?",
            "Migration changelog?",
            "Runbook for common DB incidents (replication lag, connection storm)?",
        ]),
        ("20. AI/RAG-specific (if applicable)", [
            "Vector column type (pgvector or external)?",
            "Embedding model version stored alongside vector?",
            "Re-embed strategy when model bumps?",
            "Per-tenant vector collection isolation?",
            "Hybrid retrieval index (BM25 + vector + metadata)?",
        ]),
        ("21. DR + RTO / RPO", [
            "RTO tier documented (< 15 min / < 1 hr / < 4 hr)?",
            "RPO documented (< 0 / < 15 min / < 1 hr)?",
            "Hot standby for tier-1?",
            "Failover drill quarterly?",
            "Cross-region DR for tier-1?",
        ]),
        ("22. Cost", [
            "Storage growth monitored + alerted?",
            "Index storage vs table storage ratio tracked?",
            "Cold data archived (S3 + table partition drop)?",
            "Read replica cost vs latency tradeoff documented?",
        ]),
        ("23. Common DB mistakes (avoid)", [
            "f-string SQL (use parameters)?",
            "Implicit transaction (rely on autocommit)?",
            "DROP COLUMN in same release that stops reading it?",
            "Missing index on hot-path WHERE column?",
            "Unbounded query without LIMIT?",
            "Synchronous DB call inside `async def`?",
            "Cross-tenant SELECT without WHERE tenant_id?",
        ]),
        ("24. Production gates", [
            "All migrations idempotent + reversible?",
            "Zero schema diff between staging and prod?",
            "Backup tested in last 30 days?",
            "p95 query latency within SLO?",
            "No table > 100M rows without partitioning plan?",
        ]),
        ("25. Sign-off", [
            "DBA reviewed",
            "Security reviewed (RLS + audit log)",
            "SRE reviewed (backup + DR)",
            "Tech Lead reviewed",
            "Data Engineer reviewed (lineage)",
        ]),
    ]
    body = "".join(_checklist(t, items) for t, items in sections)
    return (
        f"# Database Assessment - `{folder.name}`\n\n"
        f"**Profile:** Database ({b.runtime})\n"
        f"**Generated:** {now}\n"
        f"**Reviewer:** {reviewer}\n\n"
        f"> 25-section database-specific production assessment. Reviewer "
        f"fills Status / Notes / Risk / Recommendation per row. Skeleton "
        f"starts with TBD per global honesty rule.\n\n"
        f"---\n\n"
        f"## Metadata (auto-detected)\n\n"
        f"{metadata}"
        f"---\n\n"
        f"{body}"
        f"---\n\n"
        f"_Generated by `scripts/generate_specialized_assessment.py "
        f"--profile database`. Re-run after major changes._\n"
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
    p.add_argument("--profile", choices=["frontend", "backend", "database", "auto"],
                   default="auto",
                   help="Which profile to apply. 'auto' detects via package.json + .tsx + migrations/.")
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
    elif actual_profile == "database":
        facts = introspect_database(folder)
        content = render_database(facts, folder, reviewer, now)
        fname = "DATABASE_ASSESSMENT_REPORT.md"
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
