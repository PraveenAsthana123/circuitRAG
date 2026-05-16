#!/usr/bin/env python3
"""
Folder-level Manual Code Review Checklist generator.

Produces a 20-section Markdown report for a specific folder with the
"Enterprise Folder-Level" review template — covering folder purpose,
responsibility boundaries, architecture, dependencies, business logic,
code quality, DB / API / queue / event, security, performance, reliability,
observability, testing, DevOps, AI/LLM/RAG, production risks,
refactoring recommendations, summary, decision, and scoring.

Auto-detects (pre-fills Section 1 Metadata) from filesystem + git:
  - folder name + relative path
  - file count by extension
  - lines of code (rough)
  - detected runtime (Python / Go / Node / mixed)
  - detected DB dependencies (asyncpg / sqlalchemy / pg / redis / qdrant / neo4j)
  - detected external HTTP (httpx / requests / aiohttp / fetch)
  - detected queue (kafka / redis-stream)
  - detected AI/LLM (langchain / openai / anthropic / ollama)
  - top git committers (from git shortlog over the folder)
  - presence of README / Dockerfile / tests dir

Reviewer fills the Status / Notes / Risk / Recommendation columns.

Usage:
  python3 scripts/generate_folder_review_report.py --folder services/agent-orchestrator-svc/app
  python3 scripts/generate_folder_review_report.py --folder libs/py/documind_core --output review.md
  python3 scripts/generate_folder_review_report.py --folder . --reviewer "Praveen Asthana"

Exit codes:
  0 success
  1 output file exists (without --force) OR folder not found
  2 IO error during write
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Tuple


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ChecklistItem:
    """One auditable check inside a sub-section."""
    item: str
    notes_hint: str = ""  # Optional hint shown in Notes column placeholder


@dataclass(frozen=True)
class ReviewQuestion:
    """One reviewer-prompt question. Observation + Risk filled in by reviewer."""
    question: str


@dataclass(frozen=True)
class TableSpec:
    """Generic data table with title, headers, optional sample rows + blanks."""
    title: str
    headers: List[str]
    sample_rows: List[List[str]] = field(default_factory=list)
    blank_rows: int = 3


# ---------------------------------------------------------------------------
# Auto-detection from filesystem + git
# ---------------------------------------------------------------------------

DB_PATTERNS = {
    "Postgres (asyncpg)": r"\basyncpg\b",
    "Postgres (psycopg)": r"\bpsycopg\b",
    "SQLAlchemy": r"\bsqlalchemy\b",
    "Redis": r"\bredis\b|\baioredis\b",
    "Qdrant": r"\bqdrant_client\b",
    "Neo4j": r"\bneo4j\b",
    "Elasticsearch": r"\belasticsearch\b",
    "MongoDB": r"\bpymongo\b|\bmotor\b",
}

HTTP_PATTERNS = {
    "httpx": r"\bhttpx\b",
    "requests": r"^\s*import requests\b|^\s*from requests\b",
    "aiohttp": r"\baiohttp\b",
    "node-fetch / fetch": r"\bnode-fetch\b|\bfetch\(",
}

QUEUE_PATTERNS = {
    "Kafka (aiokafka)": r"\baiokafka\b",
    "Kafka (kafka-python)": r"\bkafka\b.*Producer|KafkaConsumer",
    "Redis Streams": r"\bxadd\b|\bxread\b",
    "Celery": r"\bcelery\b",
    "RQ": r"\brq\b.*Queue",
}

AI_PATTERNS = {
    "LangChain": r"\blangchain\b",
    "LangGraph": r"\blanggraph\b",
    "OpenAI SDK": r"^\s*import openai\b|^\s*from openai\b",
    "Anthropic SDK": r"\banthropic\b",
    "Ollama client": r"\bollama_client\b|ollama\.AsyncClient",
    "Rebuff (prompt injection)": r"\brebuff\b",
    "Ragas": r"\bragas\b",
    "Giskard": r"\bgiskard\b",
}


def _grep_imports(folder: Path, patterns: dict[str, str]) -> List[str]:
    """Returns sorted unique labels of patterns matched in any file under folder."""
    hits: set[str] = set()
    for path in folder.rglob("*.py"):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except (PermissionError, OSError):
            continue
        for label, pat in patterns.items():
            if re.search(pat, text, re.MULTILINE):
                hits.add(label)
    # Also scan .ts / .tsx / .go files for fetch / queue patterns
    for ext in (".ts", ".tsx", ".go"):
        for path in folder.rglob(f"*{ext}"):
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except (PermissionError, OSError):
                continue
            for label, pat in patterns.items():
                if re.search(pat, text, re.MULTILINE):
                    hits.add(label)
    return sorted(hits)


def _file_inventory(folder: Path) -> dict[str, int]:
    """Returns count of files grouped by extension."""
    counts: dict[str, int] = {}
    for path in folder.rglob("*"):
        if path.is_file() and not _is_ignored(path):
            ext = path.suffix or "(no ext)"
            counts[ext] = counts.get(ext, 0) + 1
    return counts


def _is_ignored(path: Path) -> bool:
    """Skip common noise dirs."""
    parts = set(path.parts)
    return bool(parts & {"__pycache__", "node_modules", ".git", ".venv", "dist", "build", ".next"})


def _rough_loc(folder: Path) -> int:
    """Rough lines of code count (non-blank lines, source files only)."""
    total = 0
    code_ext = {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".java", ".rs", ".sh"}
    for path in folder.rglob("*"):
        if not path.is_file() or _is_ignored(path) or path.suffix not in code_ext:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except (PermissionError, OSError):
            continue
        total += sum(1 for line in text.split("\n") if line.strip())
    return total


def _detect_runtime(file_counts: dict[str, int]) -> str:
    """Heuristic: which runtime dominates the folder?"""
    py = file_counts.get(".py", 0)
    ts = file_counts.get(".ts", 0) + file_counts.get(".tsx", 0)
    js = file_counts.get(".js", 0) + file_counts.get(".jsx", 0)
    go = file_counts.get(".go", 0)
    runtimes = []
    if py > 0: runtimes.append(f"Python ({py} files)")
    if ts + js > 0: runtimes.append(f"TypeScript/JS ({ts + js} files)")
    if go > 0: runtimes.append(f"Go ({go} files)")
    return " · ".join(runtimes) if runtimes else "unknown"


def _git_owners(folder: Path, repo_root: Path, max_authors: int = 5) -> str:
    """Top git committers over the folder (relative to repo_root)."""
    rel = str(folder.relative_to(repo_root)) if folder.is_relative_to(repo_root) else str(folder)
    try:
        r = subprocess.run(
            ["git", "-C", str(repo_root), "shortlog", "-sn", "--no-merges", "HEAD", "--", rel],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode != 0:
            return "(git unavailable)"
        lines = [line.strip() for line in r.stdout.split("\n") if line.strip()][:max_authors]
        return ", ".join(lines) or "(no commits)"
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return "(git unavailable)"


def _has(folder: Path, name: str) -> str:
    """Returns 'Yes' / 'No' for presence of a file/dir at any depth."""
    return "Yes" if any(folder.rglob(name)) else "No"


def autodetect_metadata(folder: Path, repo_root: Path) -> dict[str, str]:
    """Build the Section 1 metadata table — pre-fills as much as possible."""
    file_counts = _file_inventory(folder)
    loc = _rough_loc(folder)
    return {
        "Folder Name": folder.name,
        "Relative Path": str(folder.relative_to(repo_root)) if folder.is_relative_to(repo_root) else str(folder),
        "Absolute Path": str(folder),
        "Runtime Detected": _detect_runtime(file_counts),
        "File Count": str(sum(file_counts.values())),
        "Lines of Code (rough)": f"{loc:,}",
        "README present": _has(folder, "README*"),
        "Dockerfile present": _has(folder, "Dockerfile"),
        "Tests dir present": "Yes" if any(folder.rglob("tests")) else "No",
        "Top Git Contributors": _git_owners(folder, repo_root),
        "External DB Dependencies (detected)": ", ".join(_grep_imports(folder, DB_PATTERNS)) or "(none detected)",
        "External HTTP Dependencies (detected)": ", ".join(_grep_imports(folder, HTTP_PATTERNS)) or "(none detected)",
        "Queue / Event Dependencies (detected)": ", ".join(_grep_imports(folder, QUEUE_PATTERNS)) or "(none detected)",
        "AI / LLM Dependencies (detected)": ", ".join(_grep_imports(folder, AI_PATTERNS)) or "(none detected)",
    }


# ---------------------------------------------------------------------------
# Markdown rendering helpers
# ---------------------------------------------------------------------------

def _md_escape(cell: str) -> str:
    return cell.replace("|", "\\|").replace("\n", " ") if cell else ""


def render_kv_table(title: str, kv: dict[str, str]) -> str:
    """Two-column key/value table (Metadata section)."""
    rows = "\n".join(f"| {k} | {_md_escape(v)} |" for k, v in kv.items())
    return f"### {title}\n\n| Field | Value |\n|---|---|\n{rows}\n"


def render_checklist(items: List[ChecklistItem]) -> str:
    """Standard 3-column checklist: Check / Status / Notes."""
    header = "| Check | Status | Notes |\n|---|---|---|\n"
    rows = "\n".join(f"| {_md_escape(it.item)} | — | {_md_escape(it.notes_hint) or '—'} |" for it in items)
    return header + rows + "\n"


def render_questions(questions: List[ReviewQuestion]) -> str:
    """4-column question table: Question / Observation / Risk."""
    header = "| Question | Observation | Risk |\n|---|---|---|\n"
    rows = "\n".join(f"| {_md_escape(q.question)} | — | — |" for q in questions)
    return header + rows + "\n"


def render_data_table(spec: TableSpec) -> str:
    """Generic table with sample rows + blank rows for reviewer to fill."""
    header_row = "| " + " | ".join(spec.headers) + " |"
    sep_row = "|" + "|".join(["---"] * len(spec.headers)) + "|"
    body: List[str] = []
    for row in spec.sample_rows:
        body.append("| " + " | ".join(_md_escape(c) for c in row) + " |")
    for _ in range(spec.blank_rows):
        body.append("| " + " | ".join(["—"] * len(spec.headers)) + " |")
    return f"#### {spec.title}\n\n{header_row}\n{sep_row}\n" + "\n".join(body) + "\n"


# ---------------------------------------------------------------------------
# 20 sections of the review template
# ---------------------------------------------------------------------------

def section_header_and_metadata(folder: Path, repo_root: Path, reviewer: str) -> str:
    """Title block + Section 1 Folder Review Metadata (auto-detected)."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    metadata = autodetect_metadata(folder, repo_root)
    # Add the reviewer-fillable fields:
    metadata = {
        **metadata,
        "Reviewer": reviewer,
        "Review Date": now,
        "Service/Module": "_TBD by reviewer_",
        "Business Domain": "_TBD by reviewer_",
        "Risk Level": "_Critical / High / Medium / Low_",
        "Production Critical": "_Yes / No_",
    }
    return (
        f"# 🚀 Enterprise Folder-Level Manual Code Review\n\n"
        f"**Folder under review:** `{metadata['Relative Path']}`\n"
        f"**Generated:** {now}\n\n"
        "> Purpose: folder-level production review · architecture validation · "
        "business logic · security · scalability · integration · performance · "
        "production readiness.\n\n"
        "> Intended audience: Staff Engineers · Principal Engineers · Tech Leads · "
        "Enterprise Architects · SRE · AI Platform Teams · Security Review Teams.\n\n"
        "---\n\n"
        "## 📁 Folder Review Metadata\n\n"
        + render_kv_table("Auto-detected + reviewer-supplied", metadata)
        + "\n"
    )


def section_2_folder_purpose() -> str:
    items = [
        ChecklistItem("Folder responsibility is clear", "What is the one-line purpose?"),
        ChecklistItem("Single responsibility followed", "Does the folder have one cohesive reason to exist?"),
        ChecklistItem("Business purpose documented"),
        ChecklistItem("README exists"),
        ChecklistItem("README is updated", "Within last 90 days"),
        ChecklistItem("Ownership defined", "CODEOWNERS or README header"),
        ChecklistItem("Dependency boundaries defined", "Public vs internal API explicit"),
        ChecklistItem("Folder naming meaningful", "kebab/snake-case consistent with project convention"),
    ]
    return "## 1. Folder Purpose Review\n\n### Checklist\n\n" + render_checklist(items) + "\n"


def section_3_responsibility_boundary() -> str:
    questions = [
        ReviewQuestion("What is this folder responsible for?"),
        ReviewQuestion("What should NOT exist here?"),
        ReviewQuestion("Is business logic leaking from another layer?"),
        ReviewQuestion("Is DB logic mixed with controller/UI logic?"),
        ReviewQuestion("Is orchestration happening in wrong layer?"),
        ReviewQuestion("Are responsibilities duplicated elsewhere?"),
    ]
    return "## 2. Responsibility Boundary Review\n\n### Questions\n\n" + render_questions(questions) + "\n"


def section_4_architecture_design() -> str:
    soc = [
        ChecklistItem("Controller only handles request/response"),
        ChecklistItem("Business logic separated"),
        ChecklistItem("Repository/data access separated"),
        ChecklistItem("DTO/model separation exists"),
        ChecklistItem("Utility/helper separation exists"),
        ChecklistItem("Middleware isolated properly"),
        ChecklistItem("Prompt logic isolated (AI systems)"),
        ChecklistItem("Queue/event handling isolated"),
    ]
    solid = [
        ChecklistItem("Single Responsibility", "Per-class / per-module"),
        ChecklistItem("Open/Closed", "Add features by extension, not modification"),
        ChecklistItem("Liskov Substitution", "Subclasses honor contracts"),
        ChecklistItem("Interface Segregation", "No fat interfaces"),
        ChecklistItem("Dependency Inversion", "Depend on abstractions"),
    ]
    extens = [
        ChecklistItem("Easy to extend safely"),
        ChecklistItem("No hardcoded workflow"),
        ChecklistItem("Reusable components used"),
        ChecklistItem("Shared logic centralized"),
        ChecklistItem("No overengineering"),
        ChecklistItem("No god class/service"),
        ChecklistItem("No giant controller"),
    ]
    return (
        "## 3. Architecture & Design Review\n\n"
        "### Separation of Concerns\n\n" + render_checklist(soc) + "\n"
        "### SOLID Principles\n\n" + render_checklist(solid) + "\n"
        "### Design & Extensibility\n\n" + render_checklist(extens) + "\n"
    )


def section_5_dependency_review() -> str:
    direction = [
        ChecklistItem("No circular dependency"),
        ChecklistItem("Correct layer imports"),
        ChecklistItem("No controller → DB direct access"),
        ChecklistItem("No UI → repository shortcut"),
        ChecklistItem("No shared mutable state misuse"),
    ]
    api = [
        ChecklistItem("Public interfaces clearly defined"),
        ChecklistItem("Internal files hidden properly", "Leading underscore / private subpackage"),
        ChecklistItem("Unsafe cross-folder access avoided"),
        ChecklistItem("Shared modules versioned correctly"),
    ]
    return (
        "## 4. Dependency Review\n\n"
        "### Dependency Direction\n\n" + render_checklist(direction) + "\n"
        "### Public vs Private APIs\n\n" + render_checklist(api) + "\n"
    )


def section_6_business_logic() -> str:
    logic = [
        ChecklistItem("Logic matches business requirement"),
        ChecklistItem("No duplicated business rules"),
        ChecklistItem("Edge cases handled"),
        ChecklistItem("Negative scenarios handled"),
        ChecklistItem("Null/empty handling correct"),
        ChecklistItem("State transition valid"),
        ChecklistItem("No hidden side effects"),
        ChecklistItem("Idempotency handled"),
    ]
    side_effects = TableSpec(
        title="Side Effect Analysis",
        headers=["Side Effect", "Exists", "Safe?", "Notes"],
        sample_rows=[
            ["DB write", "—", "—", "—"],
            ["Queue publish", "—", "—", "—"],
            ["External API call", "—", "—", "—"],
            ["File write", "—", "—", "—"],
            ["Cache update", "—", "—", "—"],
            ["Notification/email", "—", "—", "—"],
            ["AI model invocation", "—", "—", "—"],
        ],
        blank_rows=0,
    )
    return (
        "## 5. Business Logic Review\n\n"
        "### Logic Validation\n\n" + render_checklist(logic) + "\n"
        + render_data_table(side_effects) + "\n"
    )


def section_7_code_quality() -> str:
    readability = [
        ChecklistItem("Meaningful variable names"),
        ChecklistItem("Meaningful function names"),
        ChecklistItem("Meaningful class names"),
        ChecklistItem("No misleading naming"),
        ChecklistItem("Small focused methods", "≤ 50 lines per function"),
        ChecklistItem("Low nesting complexity", "≤ 4 levels"),
        ChecklistItem("Easy to understand flow"),
    ]
    clean = [
        ChecklistItem("No dead code"),
        ChecklistItem("No commented code"),
        ChecklistItem("No debug logs"),
        ChecklistItem("No magic numbers"),
        ChecklistItem("No hardcoded configs"),
        ChecklistItem("Constants extracted"),
        ChecklistItem("Duplicate logic avoided"),
    ]
    complexity = TableSpec(
        title="Complexity",
        headers=["Metric", "Observation"],
        sample_rows=[
            ["Cyclomatic complexity", "—"],
            ["Long methods (>50 lines)", "—"],
            ["Giant classes (>500 lines)", "—"],
            ["Excessive conditions", "—"],
            ["Recursive risks", "—"],
        ],
        blank_rows=0,
    )
    return (
        "## 6. Code Quality Review\n\n"
        "### Readability\n\n" + render_checklist(readability) + "\n"
        "### Clean Code\n\n" + render_checklist(clean) + "\n"
        + render_data_table(complexity) + "\n"
    )


def section_8_database() -> str:
    db_mapping = TableSpec(
        title="DB Call Mapping",
        headers=["File", "Function", "Query Type", "Query Count", "Risk"],
        blank_rows=5,
    )
    query = [
        ChecklistItem("No N+1 query issue"),
        ChecklistItem("Proper indexing used"),
        ChecklistItem("No full table scan"),
        ChecklistItem("Batch operations used"),
        ChecklistItem("Pagination implemented"),
        ChecklistItem("Connection pooling configured"),
        ChecklistItem("Query timeout configured"),
    ]
    transaction = [
        ChecklistItem("Correct transaction boundary"),
        ChecklistItem("Rollback handling exists"),
        ChecklistItem("Partial update prevention"),
        ChecklistItem("Deadlock prevention"),
        ChecklistItem("Isolation level appropriate"),
        ChecklistItem("Distributed transaction safe"),
    ]
    schema = [
        ChecklistItem("Proper normalization"),
        ChecklistItem("Constraints exist"),
        ChecklistItem("Migration backward compatible"),
        ChecklistItem("Soft delete strategy exists"),
        ChecklistItem("Multi-tenant isolation correct"),
        ChecklistItem("Data archival strategy exists"),
    ]
    return (
        "## 7. Database Review\n\n"
        + render_data_table(db_mapping) + "\n"
        "### Query Review\n\n" + render_checklist(query) + "\n"
        "### Transaction Review\n\n" + render_checklist(transaction) + "\n"
        "### Schema Review\n\n" + render_checklist(schema) + "\n"
    )


def section_9_api_integration() -> str:
    api = [
        ChecklistItem("Proper HTTP methods"),
        ChecklistItem("Proper status codes", "200 / 201 / 204 / 400 / 401 / 404 / 409 / 422 / 429 / 5xx"),
        ChecklistItem("Validation implemented", "Pydantic / Zod / JSON Schema"),
        ChecklistItem("Standard error response", "{detail, error_code, correlation_id}"),
        ChecklistItem("Versioning strategy exists", "/api/v1/..."),
        ChecklistItem("Pagination implemented"),
        ChecklistItem("Rate limiting exists"),
        ChecklistItem("Idempotency supported", "X-Idempotency-Key header"),
    ]
    api_mapping = TableSpec(
        title="API Call Mapping",
        headers=["API", "Timeout", "Retry", "Fallback", "Circuit Breaker", "Risk"],
        blank_rows=5,
    )
    queue = [
        ChecklistItem("Retry policy exists"),
        ChecklistItem("DLQ exists"),
        ChecklistItem("Duplicate event handling"),
        ChecklistItem("Event schema versioned"),
        ChecklistItem("Backpressure handling exists"),
        ChecklistItem("Queue overflow handling exists"),
    ]
    return (
        "## 8. API & Integration Review\n\n"
        "### API Review\n\n" + render_checklist(api) + "\n"
        + render_data_table(api_mapping) + "\n"
        "### Queue/Event Review\n\n" + render_checklist(queue) + "\n"
    )


def section_10_security() -> str:
    authn = [
        ChecklistItem("Authentication validated"),
        ChecklistItem("RBAC implemented"),
        ChecklistItem("ABAC implemented"),
        ChecklistItem("Unauthorized access blocked"),
        ChecklistItem("Session/token validation safe"),
        ChecklistItem("Multi-tenant isolation safe"),
    ]
    owasp = [
        ChecklistItem("SQL injection prevented"),
        ChecklistItem("XSS prevented"),
        ChecklistItem("CSRF prevented"),
        ChecklistItem("SSRF prevented"),
        ChecklistItem("File upload safe"),
        ChecklistItem("Path traversal prevented"),
        ChecklistItem("Prompt injection prevented"),
    ]
    secrets = [
        ChecklistItem("No secrets in code"),
        ChecklistItem("No secrets in logs"),
        ChecklistItem("Vault/secret manager used"),
        ChecklistItem("Env variables safe"),
        ChecklistItem("Secret rotation strategy exists"),
    ]
    pii = [
        ChecklistItem("PII masked in logs"),
        ChecklistItem("Encryption in transit"),
        ChecklistItem("Encryption at rest"),
        ChecklistItem("GDPR compliance considered"),
        ChecklistItem("Audit logs exist"),
        ChecklistItem("Data retention policy exists"),
    ]
    return (
        "## 9. Security Review\n\n"
        "### Authentication & Authorization\n\n" + render_checklist(authn) + "\n"
        "### OWASP Review\n\n" + render_checklist(owasp) + "\n"
        "### Secret Management\n\n" + render_checklist(secrets) + "\n"
        "### Sensitive Data Review\n\n" + render_checklist(pii) + "\n"
    )


def section_11_performance() -> str:
    general = [
        ChecklistItem("No blocking operations"),
        ChecklistItem("Async processing used"),
        ChecklistItem("Parallel processing used"),
        ChecklistItem("Large file streaming used"),
        ChecklistItem("Large payload avoided"),
        ChecklistItem("Proper batching exists"),
    ]
    memory = [
        ChecklistItem("No memory leak risk"),
        ChecklistItem("Large object retention avoided"),
        ChecklistItem("Proper cleanup exists"),
        ChecklistItem("Cache eviction strategy exists"),
    ]
    caching = [
        ChecklistItem("Cache strategy defined"),
        ChecklistItem("TTL configured"),
        ChecklistItem("Cache invalidation exists"),
        ChecklistItem("Tenant-safe cache keys"),
        ChecklistItem("Cache stampede prevention"),
    ]
    concurrency = [
        ChecklistItem("Thread safety validated"),
        ChecklistItem("Race condition prevented"),
        ChecklistItem("Deadlock prevention exists"),
        ChecklistItem("Optimistic locking used"),
        ChecklistItem("Queue concurrency safe"),
    ]
    return (
        "## 10. Performance Review\n\n"
        "### General Performance\n\n" + render_checklist(general) + "\n"
        "### Memory Review\n\n" + render_checklist(memory) + "\n"
        "### Caching Review\n\n" + render_checklist(caching) + "\n"
        "### Concurrency Review\n\n" + render_checklist(concurrency) + "\n"
    )


def section_12_reliability() -> str:
    failure = [
        ChecklistItem("Retry implemented", "Bounded; exponential backoff + jitter"),
        ChecklistItem("Timeout configured", "On every external call"),
        ChecklistItem("Circuit breaker implemented"),
        ChecklistItem("Graceful degradation exists"),
        ChecklistItem("Fallback response exists"),
        ChecklistItem("Infinite retry avoided"),
    ]
    dr = [
        ChecklistItem("Backup strategy exists"),
        ChecklistItem("Multi-region awareness"),
        ChecklistItem("RPO documented"),
        ChecklistItem("RTO documented"),
        ChecklistItem("Failover strategy tested"),
    ]
    return (
        "## 11. Reliability & Resilience Review\n\n"
        "### Failure Handling\n\n" + render_checklist(failure) + "\n"
        "### Disaster Recovery\n\n" + render_checklist(dr) + "\n"
    )


def section_13_observability() -> str:
    logging = [
        ChecklistItem("Structured logging", "JSON formatter"),
        ChecklistItem("Correlation ID exists"),
        ChecklistItem("Sensitive data masked"),
        ChecklistItem("Log level correct"),
        ChecklistItem("No excessive logging"),
    ]
    monitoring = [
        ChecklistItem("Metrics exposed", "RED: rate / errors / duration"),
        ChecklistItem("SLA/SLO defined"),
        ChecklistItem("Alerts configured"),
        ChecklistItem("Health checks exist", "/health/live + /health/ready"),
        ChecklistItem("Dashboard exists"),
    ]
    tracing = [
        ChecklistItem("OpenTelemetry ready"),
        ChecklistItem("Distributed tracing enabled"),
        ChecklistItem("Trace propagation exists"),
        ChecklistItem("Cross-service tracing works"),
    ]
    return (
        "## 12. Observability Review\n\n"
        "### Logging\n\n" + render_checklist(logging) + "\n"
        "### Monitoring\n\n" + render_checklist(monitoring) + "\n"
        "### Tracing\n\n" + render_checklist(tracing) + "\n"
    )


def section_14_testing() -> str:
    unit = [
        ChecklistItem("Happy path tested"),
        ChecklistItem("Negative path tested"),
        ChecklistItem("Edge cases tested"),
        ChecklistItem("Mocking correct"),
        ChecklistItem("Critical logic covered"),
    ]
    integration = [
        ChecklistItem("DB integration tested"),
        ChecklistItem("API integration tested"),
        ChecklistItem("Queue integration tested"),
        ChecklistItem("External dependency tested"),
    ]
    coverage = TableSpec(
        title="Coverage",
        headers=["Metric", "Value"],
        sample_rows=[
            ["Unit Test Coverage", "—"],
            ["Critical Logic Coverage", "—"],
            ["Integration Coverage", "—"],
            ["E2E Coverage", "—"],
        ],
        blank_rows=0,
    )
    return (
        "## 13. Testing Review\n\n"
        "### Unit Testing\n\n" + render_checklist(unit) + "\n"
        "### Integration Testing\n\n" + render_checklist(integration) + "\n"
        + render_data_table(coverage) + "\n"
    )


def section_15_devops() -> str:
    cicd = [
        ChecklistItem("Pipeline automated"),
        ChecklistItem("Security scan exists"),
        ChecklistItem("Test gate exists"),
        ChecklistItem("Rollback automation exists"),
        ChecklistItem("Blue/Green deployment supported"),
        ChecklistItem("Canary deployment supported"),
    ]
    k8s = [
        ChecklistItem("Non-root container"),
        ChecklistItem("Resource limits configured"),
        ChecklistItem("Health probes configured"),
        ChecklistItem("Secret mounting secure"),
        ChecklistItem("Autoscaling configured"),
    ]
    return (
        "## 14. DevOps & Deployment Review\n\n"
        "### CI/CD Review\n\n" + render_checklist(cicd) + "\n"
        "### Container/Kubernetes Review\n\n" + render_checklist(k8s) + "\n"
    )


def section_16_ai_llm() -> str:
    prompt = [
        ChecklistItem("Prompt injection handled", "Rebuff / output filter"),
        ChecklistItem("Output sanitization exists"),
        ChecklistItem("Prompt versioning exists"),
        ChecklistItem("Toxicity filtering exists"),
    ]
    rag = [
        ChecklistItem("Chunking strategy validated"),
        ChecklistItem("Embedding consistency validated"),
        ChecklistItem("Metadata filtering exists"),
        ChecklistItem("Citation grounding exists"),
        ChecklistItem("Hallucination prevention exists", "Ragas / Giskard scoring"),
        ChecklistItem("Token optimization exists"),
    ]
    return (
        "## 15. AI / LLM / RAG Review\n\n"
        "### Prompt Safety\n\n" + render_checklist(prompt) + "\n"
        "### RAG Review\n\n" + render_checklist(rag) + "\n"
    )


def section_17_production_risks() -> str:
    table = TableSpec(
        title="Production Risks",
        headers=["Risk", "Impact", "Severity", "Mitigation"],
        blank_rows=6,
    )
    return "## 16. Production Risks\n\n" + render_data_table(table) + "\n"


def section_18_refactoring() -> str:
    table = TableSpec(
        title="Refactoring Recommendations",
        headers=["Area", "Recommendation", "Priority"],
        blank_rows=6,
    )
    return "## 17. Refactoring Recommendations\n\n" + render_data_table(table) + "\n"


def section_19_final_summary() -> str:
    return (
        "## 18. Final Review Summary\n\n"
        "### Strengths\n\n"
        "1. _TBD_\n2. _TBD_\n3. _TBD_\n\n"
        "### Weaknesses\n\n"
        "1. _TBD_\n2. _TBD_\n3. _TBD_\n\n"
        "### Critical Risks\n\n"
        "1. _TBD_\n2. _TBD_\n\n"
        "### Immediate Fixes Needed\n\n"
        "1. _TBD_\n2. _TBD_\n\n"
    )


def section_20_decision_and_score() -> str:
    decision_table = (
        "| Decision | Meaning | Mark |\n"
        "|---|---|---|\n"
        "| Approve | Production-ready | [ ] |\n"
        "| Approve with comments | Minor issues only | [ ] |\n"
        "| Request changes | Must fix before merge | [ ] |\n"
        "| Block release | Critical production/security risk | [ ] |\n"
    )
    score = TableSpec(
        title="Production Readiness Score",
        headers=["Area", "Score (/10)"],
        sample_rows=[
            ["Architecture", "—"],
            ["Security", "—"],
            ["Performance", "—"],
            ["Reliability", "—"],
            ["Observability", "—"],
            ["Testing", "—"],
            ["Scalability", "—"],
            ["AI Safety", "—"],
            ["DevOps", "—"],
            ["Maintainability", "—"],
        ],
        blank_rows=0,
    )
    return (
        "## 19. Final Decision\n\n"
        + decision_table + "\n"
        "## 20. Production Readiness Score\n\n"
        + render_data_table(score) + "\n"
        "### Final Score\n\n"
        "| Metric | Value |\n|---|---|\n"
        "| Final Production Readiness Score | _TBD_ |\n"
        "| Total Score (/10) | _TBD_ / 10 |\n"
        "| Overall Risk | _Low / Medium / High / Critical_ |\n"
        "| Production Recommendation | **GO / CONDITIONAL GO / NO-GO** |\n\n"
        "### Sign-off\n\n"
        "| Role | Name | Date | Signature |\n"
        "|---|---|---|---|\n"
        "| Reviewer (Tech Lead) | — | — | — |\n"
        "| Security Reviewer | — | — | — |\n"
        "| SRE / Ops | — | — | — |\n"
        "| Owner (Manager) | — | — | — |\n\n"
        "---\n\n_End of folder review report._\n"
    )


# ---------------------------------------------------------------------------
# Report assembly
# ---------------------------------------------------------------------------

def assemble_report(folder: Path, repo_root: Path, reviewer: str) -> str:
    """Concatenate all 20 sections in order."""
    sections = [
        section_header_and_metadata(folder, repo_root, reviewer),
        section_2_folder_purpose(),
        section_3_responsibility_boundary(),
        section_4_architecture_design(),
        section_5_dependency_review(),
        section_6_business_logic(),
        section_7_code_quality(),
        section_8_database(),
        section_9_api_integration(),
        section_10_security(),
        section_11_performance(),
        section_12_reliability(),
        section_13_observability(),
        section_14_testing(),
        section_15_devops(),
        section_16_ai_llm(),
        section_17_production_risks(),
        section_18_refactoring(),
        section_19_final_summary(),
        section_20_decision_and_score(),
    ]
    return "\n".join(sections)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a 20-section folder-level code review checklist (Markdown).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument(
        "--folder", "-f",
        type=Path,
        help="Single folder to review (relative or absolute).",
    )
    g.add_argument(
        "--batch", "-b",
        choices=["services", "libs", "mcp", "python", "all"],
        help="Run on a named batch of folders.",
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        help="(single-folder only) custom output path. "
             "Default for batch: <folder>/FOLDER_REPORT.md.",
    )
    parser.add_argument(
        "--reviewer",
        type=str, default="<Reviewer>",
        help="Reviewer name (printed in Metadata section).",
    )
    parser.add_argument(
        "--repo-root",
        type=Path, default=Path.cwd(),
        help="Repo root (for git ownership lookup). Default: CWD.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite the output file if it exists.",
    )
    return parser.parse_args()


def write_report(content: str, path: Path, force: bool) -> None:
    """Write the report with explicit error handling."""
    if path.exists() and not force:
        raise FileExistsError(
            f"{path} already exists. Pass --force to overwrite, "
            f"or choose a different --output."
        )
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    except PermissionError as exc:
        raise PermissionError(f"cannot write {path}: {exc}") from exc
    except OSError as exc:
        raise OSError(f"OS error writing {path}: {exc}") from exc


def _has_python(folder: Path) -> bool:
    for p in folder.rglob("*.py"):
        parts = set(p.parts)
        if not parts & {"__pycache__", "node_modules", ".git", ".venv",
                        ".venv-redteam", "dist", "build", ".next",
                        ".loop", ".archive-shims", ".tools", "mlruns", "data"}:
            return True
    return False


def _batch_folders(name: str, repo_root: Path) -> List[Path]:
    """Resolve a batch name to a list of folder Paths."""
    out: List[Path] = []
    if name == "services":
        svc = repo_root / "services"
        if svc.is_dir():
            out = sorted(p for p in svc.iterdir() if p.is_dir() and _has_python(p))
    elif name == "libs":
        libs = repo_root / "libs" / "py"
        if libs.is_dir():
            out = sorted(p for p in libs.iterdir() if p.is_dir() and _has_python(p))
    elif name == "mcp":
        mcp = repo_root / "mcp"
        if mcp.is_dir():
            out = [mcp]
    elif name == "python":
        for p in sorted(repo_root.iterdir()):
            if (p.is_dir() and not p.name.startswith(".")
                    and p.name not in {"node_modules"} and _has_python(p)):
                out.append(p)
    elif name == "all":
        out = (_batch_folders("services", repo_root)
               + _batch_folders("libs", repo_root)
               + _batch_folders("mcp", repo_root))
    return out


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    targets = ([args.folder.resolve()] if args.folder
               else _batch_folders(args.batch, repo_root))
    if not targets:
        print(f"ERROR: no target folders for batch {args.batch}", file=sys.stderr)
        return 1

    summary = {"wrote": 0, "skip": 0, "fail": 0}
    for folder in targets:
        if not folder.is_dir():
            print(f"  ✗ not a directory: {folder}", file=sys.stderr)
            summary["fail"] += 1
            continue

        if args.folder and args.output:
            output = args.output
        else:
            output = folder / "FOLDER_REPORT.md"

        try:
            report = assemble_report(folder, repo_root, args.reviewer)
            write_report(report, output, args.force)
        except FileExistsError as exc:
            print(f"  ⊘ SKIP (exists): {output}", file=sys.stderr)
            summary["skip"] += 1
            continue
        except (PermissionError, OSError) as exc:
            print(f"  ✗ FAIL {output}: {exc}", file=sys.stderr)
            summary["fail"] += 1
            continue

        sections = report.count("\n## ")
        print(f"  ✓ WROTE {output} — {len(report):,} bytes · ~{sections} sections")
        summary["wrote"] += 1

    print(f"\nSummary: {summary['wrote']} wrote · "
          f"{summary['skip']} skip · {summary['fail']} fail")
    # Single-folder mode: SKIP is a user-visible failure (they asked for the file).
    # Batch mode: SKIP is normal (some folders had reports; not a failure).
    if summary["fail"] > 0:
        return 1
    if args.folder and summary["skip"] > 0 and summary["wrote"] == 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
