#!/usr/bin/env python3
"""
Folder-level ADVANCED README generator.

Produces README.md per folder built to make the folder UNDERSTANDABLE without
reading a single source file. Auto-detects everything that can be inferred:

  * File inventory with absolute paths, docstrings, classes, functions, LOC
  * Import graph (how files in this folder link to each other)
  * Cross-folder integration (which other repo folders this depends on)
  * API endpoints with method + route + handler file + line
  * DB call sites + queries
  * Test cases (test function names + docstrings)
  * Concurrency / cache / AI deps / smells / longest functions
  * Git contributors

Then renders a deep README with:

  * 0  Auto-detected facts
  * 1  Purpose (business + technical)
  * 2  File inventory (paths + roles + summary)
  * 3  C4 model (L1 Context, L2 Container, L3 Component, L4 Code)
  * 4  Code sequence — how files link (import graph + mermaid)
  * 5  Flowchart — request lifecycle
  * 6  API endpoints — IPO table per endpoint
  * 7  Sequence diagram per endpoint
  * 8  Database layer
  * 9  Code quality + complexity
  * 10 Security review
  * 11 Performance review
  * 12 Reliability & observability
  * 13 Test cases (detected + checklist)
  * 14 Logging & monitoring
  * 15 LLM / GenAI / RAG (if AI deps detected)
  * 16 SOLID + microservice principles
  * 17 Integration with other folders
  * 18 Debugging guide
  * 19 Production gates
  * 20 Final score + sign-off

Default output: <folder>/README.md (use --force to overwrite).

Usage:
  python3 scripts/generate_folder_report.py --folder services/inference-svc
  python3 scripts/generate_folder_report.py --batch services --force
  python3 scripts/generate_folder_report.py --batch python --force
"""
from __future__ import annotations

import argparse
import ast
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
IGNORE_DIRS = {
    "__pycache__", "node_modules", ".git", ".venv", ".venv-redteam",
    "dist", "build", ".next", ".loop", ".archive-shims", ".tools",
    "mlruns", "data",
}
CODE_EXTS = {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".java", ".rs", ".sh"}


# ─── Auto-detection ────────────────────────────────────────────────────

API_DECORATOR_PATTERNS = [
    (r"@app\.(get|post|put|delete|patch|head|options)\(", "FastAPI app"),
    (r"@router\.(get|post|put|delete|patch|head|options)\(", "FastAPI router"),
    (r"app\.(get|post|put|delete|patch)\(", "Express/Next.js"),
    (r"\.HandleFunc\(", "Go net/http"),
    (r"\.GET\(|\.POST\(|\.PUT\(|\.DELETE\(", "Gin/Echo"),
]

API_ENDPOINT_PYTHON = re.compile(
    r'@(?:app|router)\.(get|post|put|delete|patch|head|options)'
    r'\(\s*["\']([^"\']+)["\']',
    re.MULTILINE,
)

DB_CALL_PATTERNS = [
    (r"\.execute\s*\(", "execute"),
    (r"\.fetch\w*\s*\(", "fetch/fetchall/fetchrow"),
    (r"\.query\s*\(", "ORM query"),
    (r"session\.(add|delete|commit|rollback)", "SQLAlchemy session"),
    (r"\.insert\s*\(|\.update\s*\(|\.delete\s*\(", "ORM CRUD"),
    (r"\.find\(|\.insert_one|\.update_one", "MongoDB"),
]

SANITIZATION_PATTERNS = [
    (r"class \w+\(BaseModel\)", "Pydantic BaseModel"),
    (r"@validator|@field_validator", "Pydantic validator"),
    (r"\bz\.object\(", "Zod (TS)"),
    (r"\bescape\(|sanitize\(", "Manual escape"),
]

SMELL_PATTERNS = [
    (r"http://localhost:\d+", "hardcoded localhost URL"),
    (r"password\s*=\s*['\"][^'\"]+['\"]", "hardcoded password literal"),
    (r"api_key\s*=\s*['\"][^'\"]{8,}['\"]", "hardcoded API key literal"),
    (r"\bTODO\b|\bFIXME\b|\bHACK\b|\bXXX\b", "TODO/FIXME marker"),
]

CONCURRENCY_PATTERNS = {
    "asyncio (async/await)": r"\basync def\b|\bawait \b",
    "threading": r"\bthreading\.|\bThread\(",
    "multiprocessing": r"\bmultiprocessing\.|\bProcess\(",
    "concurrent.futures": r"\bThreadPoolExecutor\b|\bProcessPoolExecutor\b",
    "Lock / RLock": r"\b(Lock|RLock|Semaphore)\(\)",
}

CACHE_PATTERNS = {
    "redis": r"\bredis\b|\baioredis\b",
    "in-memory @lru_cache": r"@lru_cache\b|@cache\b",
    "functools.cache": r"functools\.cache\b",
}

DB_LIB_PATTERNS = {
    "asyncpg": r"\basyncpg\b",
    "psycopg": r"\bpsycopg\b",
    "SQLAlchemy": r"\bsqlalchemy\b|\bsessionmaker\b",
    "Tortoise ORM": r"\btortoise\b",
    "Prisma": r"\bprisma\b",
    "Redis": r"\bredis\b",
    "Qdrant": r"\bqdrant_client\b",
    "Neo4j": r"\bneo4j\b",
    "Elasticsearch": r"\belasticsearch\b",
    "MongoDB (pymongo)": r"\bpymongo\b",
    "Kafka (aiokafka)": r"\baiokafka\b|\bkafka\b",
}

AI_PATTERNS = {
    "LangChain": r"\blangchain\b",
    "LangGraph": r"\blanggraph\b",
    "OpenAI SDK": r"\bopenai\b",
    "Anthropic SDK": r"\banthropic\b",
    "Ollama": r"\bollama\b",
    "Rebuff (PI defense)": r"\brebuff\b",
    "Ragas": r"\bragas\b",
    "Giskard": r"\bgiskard\b",
    "DeepEval": r"\bdeepeval\b",
    "OpenTelemetry GenAI": r"opentelemetry.*genai|otel.*llm",
}


@dataclass
class FileEntry:
    rel: str                      # path relative to folder
    abs: str                      # absolute path
    doc: str                      # first line of module docstring
    classes: int
    functions: int
    async_functions: int
    lines: int
    imports: List[str]            # internal + project imports
    role: str                     # auto-inferred (router / service / repo / etc.)


@dataclass
class Endpoint:
    method: str
    route: str
    file: str
    line: int


@dataclass
class TestCase:
    name: str
    file: str
    line: int
    doc: str


@dataclass
class FolderFacts:
    name: str
    rel_path: str
    abs_path: Path
    file_count: int = 0
    py_files: int = 0
    ts_files: int = 0
    go_files: int = 0
    sh_files: int = 0
    loc: int = 0
    classes: int = 0
    functions: int = 0
    async_functions: int = 0
    api_endpoints: List[Endpoint] = field(default_factory=list)
    api_summary: List[Tuple[str, int]] = field(default_factory=list)
    db_calls: List[Tuple[str, int]] = field(default_factory=list)
    db_libs: List[str] = field(default_factory=list)
    sanitization: List[str] = field(default_factory=list)
    smells: Dict[str, int] = field(default_factory=dict)
    concurrency: List[str] = field(default_factory=list)
    cache: List[str] = field(default_factory=list)
    ai_deps: List[str] = field(default_factory=list)
    tests_dir: bool = False
    test_file_count: int = 0
    test_cases: List[TestCase] = field(default_factory=list)
    has_dockerfile: bool = False
    has_pyproject: bool = False
    has_go_mod: bool = False
    has_package_json: bool = False
    git_contributors: str = ""
    purpose: str = ""
    longest_functions: List[Tuple[int, str, str]] = field(default_factory=list)
    files: List[FileEntry] = field(default_factory=list)
    integrations: Dict[str, int] = field(default_factory=dict)  # other-folder → import-count
    external_deps: Dict[str, int] = field(default_factory=dict)  # third-party → import-count


def _is_ignored(path: Path) -> bool:
    return bool(set(path.parts) & IGNORE_DIRS)


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except (PermissionError, OSError):
        return ""


def _count_pattern(folder: Path, pattern: str,
                   exts: tuple = (".py", ".ts", ".tsx", ".js", ".go")) -> int:
    rgx = re.compile(pattern, re.MULTILINE)
    n = 0
    for ext in exts:
        for path in folder.rglob(f"*{ext}"):
            if _is_ignored(path):
                continue
            n += len(rgx.findall(_read(path)))
    return n


def _detect_patterns(folder: Path, patterns: dict) -> List[str]:
    hits: set[str] = set()
    for ext in (".py", ".ts", ".tsx", ".js", ".go"):
        for path in folder.rglob(f"*{ext}"):
            if _is_ignored(path):
                continue
            text = _read(path)
            for label, pat in patterns.items():
                if re.search(pat, text, re.MULTILINE):
                    hits.add(label)
    return sorted(hits)


def _infer_role(rel_path: str, doc: str) -> str:
    p = rel_path.lower()
    if any(s in p for s in ("router", "route", "endpoint", "controller", "api")):
        return "🌐 HTTP router / API endpoints"
    if any(s in p for s in ("service", "usecase", "use_case")):
        return "🧠 business service / use-case"
    if any(s in p for s in ("repo", "repository", "dao", "store")):
        return "💾 repository / data access"
    if any(s in p for s in ("model", "schema", "dto")):
        return "📋 data model / schema"
    if any(s in p for s in ("client", "adapter", "gateway")):
        return "🔌 external service adapter"
    if any(s in p for s in ("middleware", "interceptor", "filter")):
        return "🪝 middleware / interceptor"
    if any(s in p for s in ("config", "settings")):
        return "⚙ config / settings"
    if any(s in p for s in ("util", "helper", "common")):
        return "🛠 utility / helper"
    if any(s in p for s in ("main", "app", "__init__", "cmd")):
        return "🚀 entry point / app bootstrap"
    if any(s in p for s in ("test_", "_test")):
        return "🧪 test"
    if any(s in p for s in ("agent", "tool", "executor")):
        return "🤖 agent / tool"
    if doc:
        return "📄 module"
    return "📄 module"


def _python_file_entries(folder: Path) -> List[FileEntry]:
    entries: List[FileEntry] = []
    for path in sorted(folder.rglob("*.py")):
        if _is_ignored(path):
            continue
        text = _read(path)
        if not text:
            continue
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        doc = (ast.get_docstring(tree) or "").strip().split("\n")[0][:140]
        classes = sum(1 for n in tree.body if isinstance(n, ast.ClassDef))
        fns = sum(1 for n in tree.body if isinstance(n, ast.FunctionDef))
        afns = sum(1 for n in tree.body if isinstance(n, ast.AsyncFunctionDef))
        imports: List[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module)
        rel = str(path.relative_to(folder))
        entries.append(FileEntry(
            rel=rel,
            abs=str(path),
            doc=doc,
            classes=classes,
            functions=fns,
            async_functions=afns,
            lines=len(text.split("\n")),
            imports=imports,
            role=_infer_role(rel, doc),
        ))
    return entries


def _python_ast_stats(folder: Path) -> tuple[int, int, int, List[tuple]]:
    classes = 0
    fns = 0
    afns = 0
    long_fns: List[tuple] = []
    for path in folder.rglob("*.py"):
        if _is_ignored(path):
            continue
        text = _read(path)
        if not text:
            continue
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                classes += 1
            elif isinstance(node, ast.AsyncFunctionDef):
                afns += 1
                fns += 1
                if hasattr(node, "end_lineno") and node.end_lineno:
                    lines = node.end_lineno - node.lineno + 1
                    long_fns.append((lines, f"{path.relative_to(folder)}:{node.lineno}", node.name))
            elif isinstance(node, ast.FunctionDef):
                fns += 1
                if hasattr(node, "end_lineno") and node.end_lineno:
                    lines = node.end_lineno - node.lineno + 1
                    long_fns.append((lines, f"{path.relative_to(folder)}:{node.lineno}", node.name))
    long_fns.sort(reverse=True)
    return classes, fns, afns, long_fns[:5]


def _file_count(folder: Path) -> dict[str, int]:
    out: dict[str, int] = {}
    for path in folder.rglob("*"):
        if path.is_file() and not _is_ignored(path):
            ext = path.suffix or "(no ext)"
            out[ext] = out.get(ext, 0) + 1
    return out


def _loc(folder: Path) -> int:
    total = 0
    for path in folder.rglob("*"):
        if not path.is_file() or _is_ignored(path) or path.suffix not in CODE_EXTS:
            continue
        text = _read(path)
        total += sum(1 for line in text.split("\n") if line.strip())
    return total


def _git_contributors(folder: Path) -> str:
    rel = str(folder.relative_to(REPO_ROOT)) if folder.is_relative_to(REPO_ROOT) else str(folder)
    try:
        r = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "shortlog", "-sn", "--no-merges", "HEAD", "--", rel],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode != 0:
            return "(git unavailable)"
        lines = [line.strip() for line in r.stdout.split("\n") if line.strip()][:4]
        return ", ".join(f"`{l}`" for l in lines) or "(no commits)"
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return "(git unavailable)"


def _smell_count(folder: Path) -> dict:
    out: dict[str, int] = {}
    for pat, label in SMELL_PATTERNS:
        n = _count_pattern(folder, pat)
        if n:
            out[label] = n
    return out


def _purpose_from_docstring(folder: Path) -> str:
    for candidate in ("app/main.py", "main.py", "__init__.py",
                      "cmd/main.go", "src/index.ts", "src/index.js"):
        p = folder / candidate
        if not p.exists():
            continue
        text = _read(p)
        m = re.search(r'^"""(.+?)"""', text, re.DOTALL | re.MULTILINE)
        if m:
            return m.group(1).strip().split("\n")[0][:200]
        m = re.search(r"^// (.+)$", text, re.MULTILINE)
        if m:
            return m.group(1)[:200]
    return ""


def _detect_endpoints(folder: Path) -> List[Endpoint]:
    out: List[Endpoint] = []
    for path in folder.rglob("*.py"):
        if _is_ignored(path):
            continue
        text = _read(path)
        if not text:
            continue
        for i, line in enumerate(text.split("\n"), 1):
            m = API_ENDPOINT_PYTHON.search(line)
            if m:
                out.append(Endpoint(
                    method=m.group(1).upper(),
                    route=m.group(2),
                    file=str(path.relative_to(folder)),
                    line=i,
                ))
    return out


def _detect_test_cases(folder: Path) -> List[TestCase]:
    out: List[TestCase] = []
    test_paths: List[Path] = []
    for pat in ("test_*.py", "*_test.py"):
        test_paths.extend(folder.rglob(pat))
    for path in sorted(set(test_paths)):
        if _is_ignored(path):
            continue
        text = _read(path)
        if not text:
            continue
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
                doc = (ast.get_docstring(node) or "").strip().split("\n")[0][:120]
                out.append(TestCase(
                    name=node.name,
                    file=str(path.relative_to(folder)),
                    line=node.lineno,
                    doc=doc,
                ))
    return out


def _other_repo_folders() -> List[str]:
    """Top-level repo folders that count as 'internal' (vs third-party)."""
    out: List[str] = []
    for p in REPO_ROOT.iterdir():
        if p.is_dir() and not p.name.startswith(".") and p.name not in {"node_modules"}:
            out.append(p.name)
    return out


def _classify_imports(files: List[FileEntry], folder: Path) -> tuple[Dict[str, int], Dict[str, int]]:
    """Returns (internal_repo_folder_hits, external_dep_hits)."""
    repo_folders = set(_other_repo_folders())
    folder_name = folder.name
    repo_folders.discard(folder_name)
    internal: Dict[str, int] = {}
    external: Dict[str, int] = {}
    for fe in files:
        for imp in fe.imports:
            top = imp.split(".")[0]
            if top in {"app", "documind_core", "documind", "libs", "mcp", "scripts"}:
                key = imp.split(".")[0] + "/" + (imp.split(".")[1] if "." in imp else "")
                internal[key.rstrip("/")] = internal.get(key.rstrip("/"), 0) + 1
            elif top in repo_folders:
                internal[top] = internal.get(top, 0) + 1
            elif top in {"os", "sys", "re", "json", "time", "datetime", "logging",
                         "pathlib", "typing", "dataclasses", "collections", "asyncio",
                         "functools", "itertools", "subprocess", "argparse", "io",
                         "uuid", "hashlib", "math", "random", "ast", "enum",
                         "contextlib", "abc", "copy", "warnings", "traceback",
                         "inspect", "string", "tempfile", "shutil", "socket",
                         "threading", "multiprocessing", "queue", "concurrent"}:
                # stdlib — skip
                continue
            elif top.startswith("__"):
                continue
            else:
                external[top] = external.get(top, 0) + 1
    return internal, external


def introspect(folder: Path) -> FolderFacts:
    counts = _file_count(folder)
    classes, fns, afns, long_fns = _python_ast_stats(folder)
    files = _python_file_entries(folder)
    internal, external = _classify_imports(files, folder)
    endpoints = _detect_endpoints(folder)

    # Summary tuples for backwards compatibility
    api_summary: List[Tuple[str, int]] = []
    for pat, label in API_DECORATOR_PATTERNS:
        n = _count_pattern(folder, pat)
        if n:
            api_summary.append((label, n))

    facts = FolderFacts(
        name=folder.name,
        rel_path=str(folder.relative_to(REPO_ROOT)) if folder.is_relative_to(REPO_ROOT) else str(folder),
        abs_path=folder,
        file_count=sum(counts.values()),
        py_files=counts.get(".py", 0),
        ts_files=counts.get(".ts", 0) + counts.get(".tsx", 0),
        go_files=counts.get(".go", 0),
        sh_files=counts.get(".sh", 0),
        loc=_loc(folder),
        classes=classes,
        functions=fns,
        async_functions=afns,
        longest_functions=long_fns,
        api_endpoints=endpoints,
        api_summary=api_summary,
        db_calls=[(label, _count_pattern(folder, pat)) for pat, label in DB_CALL_PATTERNS if _count_pattern(folder, pat) > 0],
        db_libs=_detect_patterns(folder, DB_LIB_PATTERNS),
        sanitization=_detect_patterns(folder, dict((label, pat) for pat, label in [(p, l) for p, l in SANITIZATION_PATTERNS])),
        smells=_smell_count(folder),
        concurrency=_detect_patterns(folder, CONCURRENCY_PATTERNS),
        cache=_detect_patterns(folder, CACHE_PATTERNS),
        ai_deps=_detect_patterns(folder, AI_PATTERNS),
        tests_dir=any(folder.rglob("tests")),
        test_file_count=len(list(folder.rglob("test_*.py"))) + len(list(folder.rglob("*_test.py"))) + len(list(folder.rglob("*_test.go"))),
        test_cases=_detect_test_cases(folder),
        has_dockerfile=(folder / "Dockerfile").exists(),
        has_pyproject=(folder / "pyproject.toml").exists(),
        has_go_mod=(folder / "go.mod").exists(),
        has_package_json=(folder / "package.json").exists(),
        git_contributors=_git_contributors(folder),
        purpose=_purpose_from_docstring(folder),
        files=files,
        integrations=internal,
        external_deps=external,
    )
    return facts


# ─── Markdown rendering ────────────────────────────────────────────────

def _kv_row(k: str, v: str) -> str:
    return f"| {k} | {v} |"


def _checklist(items: List[tuple]) -> str:
    rows = "\n".join(f"| {chk} | — | {hint or '—'} |" for chk, hint in items)
    return "| Check | Status (✓/✗/⚠) | Notes |\n|---|---|---|\n" + rows + "\n"


def header(f: FolderFacts, now: str) -> str:
    role_tag = ""
    if "services/" in f.rel_path:
        role_tag = "🧩 **Service**"
    elif "libs/" in f.rel_path:
        role_tag = "📚 **Library**"
    elif "mcp/" in f.rel_path:
        role_tag = "🔌 **MCP**"
    elif "scripts" in f.rel_path:
        role_tag = "🔧 **Scripts**"
    elif "docs" in f.rel_path:
        role_tag = "📖 **Docs**"
    elif "infra" in f.rel_path:
        role_tag = "🏗 **Infra**"

    return (
        f"# 📦 `{f.name}` — Advanced README\n\n"
        f"{role_tag}  ·  **Path:** `{f.rel_path}`  ·  **Generated:** {now}\n\n"
        f"> {f.purpose or '_Purpose not detected from docstrings — reviewer to fill._'}\n\n"
        f"This README is **auto-generated** by [`scripts/generate_folder_report.py`]"
        f"(../../scripts/generate_folder_report.py). It explains what this folder "
        f"does, every file inside it, how the files link to each other, every API "
        f"endpoint, every database call, every test case, and the production "
        f"controls (security / reliability / performance / observability). "
        f"Re-run after major changes.\n\n"
        f"---\n"
    )


def section_0_facts(f: FolderFacts) -> str:
    api_total = len(f.api_endpoints)
    db_total = sum(n for _, n in f.db_calls)
    smell_table = "\n".join(f"| {k} | {v} |" for k, v in f.smells.items())
    smell_block = (
        "#### Smells detected (grep heuristics — verify manually)\n\n"
        "| Smell | Count |\n|---|---|\n" + smell_table + "\n"
        if smell_table else "#### Smells detected\n\n_(no smells detected by grep)_\n"
    )
    long_fn_table = "\n".join(
        f"| `{loc}` | `{name}` | {lines} |" for lines, loc, name in f.longest_functions
    )
    long_fn_block = (
        "#### Longest functions (top 5)\n\n"
        "| Location | Name | Lines |\n|---|---|---|\n" + long_fn_table + "\n"
        if long_fn_table else "#### Longest functions\n\n_(no Python functions found)_\n"
    )
    return (
        f"## 🔎 Section 0 — Auto-Detected Facts\n\n"
        f"| Metric | Value |\n|---|---|\n"
        f"{_kv_row('Folder', f'`{f.rel_path}`')}\n"
        f"{_kv_row('Total files', str(f.file_count))}\n"
        f"{_kv_row('Python files', str(f.py_files))}\n"
        f"{_kv_row('TypeScript/JS files', str(f.ts_files))}\n"
        f"{_kv_row('Go files', str(f.go_files))}\n"
        f"{_kv_row('Shell scripts', str(f.sh_files))}\n"
        f"{_kv_row('Lines of code', f'{f.loc:,}')}\n"
        f"{_kv_row('Python classes', str(f.classes))}\n"
        f"{_kv_row('Python functions', str(f.functions))}\n"
        f"{_kv_row('Async functions', str(f.async_functions))}\n"
        f"{_kv_row('Total API endpoints', str(api_total))}\n"
        f"{_kv_row('Total DB call sites', str(db_total))}\n"
        f"{_kv_row('DB / Storage libs', ', '.join(f.db_libs) or '_(none)_')}\n"
        f"{_kv_row('Concurrency primitives', ', '.join(f.concurrency) or '_(none)_')}\n"
        f"{_kv_row('Caching primitives', ', '.join(f.cache) or '_(none)_')}\n"
        f"{_kv_row('Input validation', ', '.join(f.sanitization) or '_(NONE — flag risk)_')}\n"
        f"{_kv_row('AI / LLM deps', ', '.join(f.ai_deps) or '_(none)_')}\n"
        f"{_kv_row('Test files', str(f.test_file_count))}\n"
        f"{_kv_row('Detected test cases', str(len(f.test_cases)))}\n"
        f"{_kv_row('Tests dir present', '✅' if f.tests_dir else '❌ — flag')}\n"
        f"{_kv_row('Dockerfile', '✅' if f.has_dockerfile else '❌')}\n"
        f"{_kv_row('pyproject.toml', '✅' if f.has_pyproject else '❌')}\n"
        f"{_kv_row('go.mod', '✅' if f.has_go_mod else '❌')}\n"
        f"{_kv_row('package.json', '✅' if f.has_package_json else '❌')}\n"
        f"{_kv_row('Top git contributors', f.git_contributors)}\n\n"
        f"{long_fn_block}\n"
        f"{smell_block}\n"
    )


def section_1_purpose(f: FolderFacts) -> str:
    return (
        "## 1. Purpose — Business + Technical\n\n"
        "### Business problem this folder solves\n\n"
        f"> _Reviewer to fill: {f.purpose or 'one paragraph describing the business need'}_\n\n"
        "### Technical contract this folder exposes\n\n"
        "> _Reviewer to fill: API surface, events emitted, data persisted, downstream consumers._\n\n"
        "### Out-of-scope (what this folder does NOT do)\n\n"
        "> _Reviewer to fill: explicit non-goals — prevents scope creep at review time._\n\n"
    )


def section_2_file_inventory(f: FolderFacts) -> str:
    if not f.files:
        return "## 2. File Inventory\n\n_No Python files detected._\n\n"
    rows = []
    for fe in f.files:
        doc = fe.doc or "_(no docstring)_"
        rows.append(
            f"| `{fe.rel}` | {fe.role} | {fe.classes} | {fe.functions + fe.async_functions} | "
            f"{fe.lines} | {doc} |"
        )
    paths_block = "\n".join(f"- `{fe.abs}`" for fe in f.files)
    return (
        "## 2. File Inventory\n\n"
        "Every Python file in this folder, with role / classes / functions / LOC / "
        "first docstring line. Full absolute paths listed below the table for "
        "easy `cat`-ability.\n\n"
        "| Relative path | Role (inferred) | Classes | Functions | LOC | Summary |\n"
        "|---|---|---|---|---|---|\n"
        + "\n".join(rows) + "\n\n"
        "### Absolute paths (clickable)\n\n"
        + paths_block + "\n\n"
    )


def section_3_c4_model(f: FolderFacts) -> str:
    """C4 L1 Context, L2 Container, L3 Component, L4 Code."""
    # L1 Context — show the folder in its system context.
    ctx_lines = ["flowchart LR", f"    Caller([External Caller]) --> This[\"{f.name}\"]"]
    for other in list(f.integrations.keys())[:6]:
        ctx_lines.append(f"    This --> {other.replace('/', '_').replace('-', '_')}[{other}]")
    ctx = "\n".join(ctx_lines)

    # L2 Container — show the folder's external dependencies.
    cont_lines = ["flowchart TB", f"    subgraph {f.name}", "        Code[Source Code]"]
    if f.db_libs:
        cont_lines.append("    end")
        for i, db in enumerate(f.db_libs):
            slug = re.sub(r"\W", "_", db)
            cont_lines.append(f"    Code --> DB_{i}[(\"{db}\")]")
    else:
        cont_lines.append("    end")
    if f.ai_deps:
        for i, ai in enumerate(f.ai_deps):
            cont_lines.append(f"    Code --> AI_{i}{{{{LLM: {ai}}}}}")
    cont = "\n".join(cont_lines)

    # L3 Component — files grouped by role.
    comp_lines = ["flowchart TB"]
    role_groups: Dict[str, List[str]] = {}
    for fe in f.files:
        role_groups.setdefault(fe.role, []).append(fe.rel)
    for role, files_in_role in role_groups.items():
        slug = re.sub(r"\W", "_", role)[:30]
        comp_lines.append(f"    subgraph {slug}[\"{role}\"]")
        for rel in files_in_role[:6]:
            slug_f = re.sub(r"\W", "_", rel)
            comp_lines.append(f"        {slug_f}[\"{rel}\"]")
        if len(files_in_role) > 6:
            comp_lines.append(f"        more_{slug}[\"... +{len(files_in_role) - 6} more\"]")
        comp_lines.append("    end")
    comp = "\n".join(comp_lines)

    # L4 Code — top 5 longest functions.
    code_lines = ["flowchart TB"]
    if f.longest_functions:
        for lines, loc, name in f.longest_functions:
            slug = re.sub(r"\W", "_", f"{loc}_{name}")[:40]
            code_lines.append(f"    {slug}[\"{name} ({lines} lines)<br/>{loc}\"]")
    else:
        code_lines.append("    none[No Python functions detected]")
    code = "\n".join(code_lines)

    return (
        "## 3. C4 Model — Context / Container / Component / Code\n\n"
        "### Level 1 — System Context\n\n"
        "_Where does this folder sit in the broader system?_\n\n"
        f"```mermaid\n{ctx}\n```\n\n"
        "### Level 2 — Container\n\n"
        "_What external dependencies does this folder talk to?_\n\n"
        f"```mermaid\n{cont}\n```\n\n"
        "### Level 3 — Component\n\n"
        "_Internal files grouped by inferred role._\n\n"
        f"```mermaid\n{comp}\n```\n\n"
        "### Level 4 — Code (top hotspots)\n\n"
        "_Longest functions — these are the most likely refactor candidates._\n\n"
        f"```mermaid\n{code}\n```\n\n"
    )


def section_4_code_sequence(f: FolderFacts) -> str:
    """Import graph between files inside the folder."""
    if not f.files:
        return "## 4. Code Sequence — How Files Link\n\n_No Python files detected._\n\n"

    file_set = {fe.rel: fe for fe in f.files}
    # Build local edges: file → file (when one file's import resolves to another file in the folder).
    module_to_file: Dict[str, str] = {}
    for fe in f.files:
        # Convert "subpkg/foo.py" → "subpkg.foo"
        mod = fe.rel.replace("/", ".")
        if mod.endswith(".py"):
            mod = mod[:-3]
        if mod.endswith(".__init__"):
            mod = mod[: -len(".__init__")]
        module_to_file[mod] = fe.rel

    edges: List[Tuple[str, str]] = []
    for fe in f.files:
        for imp in fe.imports:
            for mod, target in module_to_file.items():
                if imp == mod or imp.endswith("." + mod) or imp.startswith(mod + "."):
                    if target != fe.rel:
                        edges.append((fe.rel, target))
                    break

    # Dedupe edges + count multiplicity for the table.
    edge_counts: Dict[Tuple[str, str], int] = {}
    for src, dst in edges:
        edge_counts[(src, dst)] = edge_counts.get((src, dst), 0) + 1

    if not edge_counts:
        mermaid = "flowchart LR\n    none[No internal imports detected — files are decoupled]"
        edge_table = "_No internal imports detected._\n"
    else:
        lines = ["flowchart LR"]
        for (src, dst), _n in edge_counts.items():
            slug_s = re.sub(r"\W", "_", src)[:40]
            slug_d = re.sub(r"\W", "_", dst)[:40]
            lines.append(f"    {slug_s}[\"{src}\"] --> {slug_d}[\"{dst}\"]")
        mermaid = "\n".join(lines)
        edge_table = "| From file | To file | Import-count |\n|---|---|---|\n"
        for (src, dst), n in sorted(edge_counts.items(), key=lambda kv: (-kv[1], kv[0])):
            edge_table += f"| `{src}` | `{dst}` | {n} |\n"

    return (
        "## 4. Code Sequence — How Files Link to Each Other\n\n"
        "**Import graph for files in this folder.** Reading order: start at any "
        "entry-point file (look for `🚀 entry point` role in the inventory above), "
        "then follow the arrows.\n\n"
        f"```mermaid\n{mermaid}\n```\n\n"
        "### Edge list\n\n"
        f"{edge_table}\n"
    )


def section_5_flowchart(f: FolderFacts) -> str:
    has_api = bool(f.api_endpoints)
    has_db = bool(f.db_libs)
    has_ai = bool(f.ai_deps)
    has_cache = bool(f.cache)

    lines = ["flowchart TD",
             "    Start([Request arrives]) --> Validate{{Validate input}}",
             "    Validate -- invalid --> Err400[400 Bad Request]",
             "    Validate -- ok --> Auth{{Auth + RBAC check}}",
             "    Auth -- denied --> Err401[401/403]",
             "    Auth -- ok --> Logic[Business logic]"]
    if has_cache:
        lines.extend([
            "    Logic --> CacheCheck{{Cache hit?}}",
            "    CacheCheck -- yes --> Return[Return cached]",
            "    CacheCheck -- no --> Compute[Compute / fetch]",
        ])
    else:
        lines.append("    Logic --> Compute[Compute / fetch]")
    if has_db:
        lines.append("    Compute --> DB[(Database)]")
        lines.append("    DB --> Compute")
    if has_ai:
        lines.append("    Compute --> LLM{{LLM / RAG call}}")
        lines.append("    LLM --> Compute")
    lines.extend([
        "    Compute --> Log[Emit log + metric + trace span]",
        "    Log --> Return2[Return response]",
        "    Err400 --> Log",
        "    Err401 --> Log",
    ])
    flow = "\n".join(lines)
    return (
        "## 5. Request Flowchart\n\n"
        "Generic request lifecycle for this folder. Branches that don't apply are "
        "auto-removed based on detected dependencies (DB / cache / LLM).\n\n"
        f"```mermaid\n{flow}\n```\n\n"
    )


def section_6_api_endpoints(f: FolderFacts) -> str:
    if not f.api_endpoints:
        return (
            "## 6. API Endpoints — Input / Process / Output\n\n"
            "_No HTTP endpoints detected via `@app.*` / `@router.*` decorators._\n\n"
        )
    rows = []
    for ep in f.api_endpoints:
        rows.append(
            f"| `{ep.method}` | `{ep.route}` | `{ep.file}:{ep.line}` | "
            f"_TBD_ | _TBD_ | _TBD_ |"
        )
    return (
        "## 6. API Endpoints — Input / Process / Output\n\n"
        f"**Detected endpoints:** {len(f.api_endpoints)}\n\n"
        "| Method | Route | Defined in | Input (schema) | Process (summary) | Output (schema) |\n"
        "|---|---|---|---|---|---|\n"
        + "\n".join(rows) + "\n\n"
        "_Reviewer fills the last three columns from the Pydantic models in the "
        "handler. Auto-extraction of Pydantic schemas is on the roadmap._\n\n"
    )


def section_7_sequence_diagrams(f: FolderFacts) -> str:
    if not f.api_endpoints:
        return (
            "## 7. Sequence Diagrams per Endpoint\n\n"
            "_No endpoints detected; sequence-diagram template intentionally omitted._\n\n"
        )
    # One generic sequence diagram + per-endpoint stubs (first 5 endpoints).
    generic = (
        "```mermaid\n"
        "sequenceDiagram\n"
        "  autonumber\n"
        "  participant Client\n"
        f"  participant API as {f.name}\n"
        "  participant MW as Middleware (auth + logging)\n"
        "  participant Svc as Business Service\n"
        "  participant DB as Database\n"
        "  Client->>API: HTTP request\n"
        "  API->>MW: pass through\n"
        "  MW-->>API: validated + auth ok\n"
        "  API->>Svc: call handler\n"
        "  Svc->>DB: read / write\n"
        "  DB-->>Svc: result\n"
        "  Svc-->>API: domain object\n"
        "  API-->>Client: JSON response\n"
        "  Note over API: emit log + metric + span\n"
        "```\n\n"
    )
    per_ep_blocks = ""
    for ep in f.api_endpoints[:5]:
        slug = re.sub(r"\W", "_", ep.route).strip("_") or "root"
        per_ep_blocks += (
            f"### `{ep.method} {ep.route}` ({ep.file}:{ep.line})\n\n"
            "```mermaid\n"
            "sequenceDiagram\n"
            "  autonumber\n"
            "  participant C as Client\n"
            f"  participant H as Handler ({ep.file}:{ep.line})\n"
            "  participant S as Service\n"
            "  participant D as DB / external\n"
            f"  C->>H: {ep.method} {ep.route}\n"
            "  H->>S: validated payload\n"
            "  S->>D: read/write\n"
            "  D-->>S: result\n"
            "  S-->>H: domain object\n"
            "  H-->>C: response\n"
            "```\n\n"
        )
    if len(f.api_endpoints) > 5:
        per_ep_blocks += f"_(+{len(f.api_endpoints) - 5} more endpoints — diagrams omitted for brevity.)_\n\n"

    return (
        "## 7. Sequence Diagrams per Endpoint\n\n"
        "### Generic flow (all endpoints)\n\n"
        + generic
        + "### Per-endpoint sequence stubs (top 5)\n\n"
        + per_ep_blocks
    )


def section_8_database(f: FolderFacts) -> str:
    db_total = sum(n for _, n in f.db_calls)
    if not f.db_libs and db_total == 0:
        return "## 8. Database Layer\n\n_No DB libraries or call sites detected._\n\n"
    calls_table = (
        "| Pattern | Count |\n|---|---|\n"
        + "\n".join(f"| `{label}` | {n} |" for label, n in f.db_calls)
    )
    return (
        f"## 8. Database Layer\n\n"
        f"**DB / storage libraries:** {', '.join(f.db_libs) or '_(none)_'}\n\n"
        f"**Total DB call sites:** {db_total}\n\n"
        f"{calls_table}\n\n"
        "### Query Optimization checklist\n\n"
        + _checklist([
            ("Indexes on every WHERE / ORDER BY column", "EXPLAIN ANALYZE hot paths"),
            ("Full table scans avoided", ""),
            ("Batch operations used (not N writes in a loop)", ""),
            ("Parameterized queries (NEVER f-string SQL)", ""),
        ])
        + "\n### Transactions (ACID)\n\n"
        + _checklist([
            ("Transaction boundaries narrow (no HTTP / LLM inside)", ""),
            ("Rollback on exception", ""),
            ("Isolation level documented (READ COMMITTED / SERIALIZABLE)", ""),
            ("Deadlock prevention strategy", ""),
        ])
        + "\n### N+1 Query Findings (reviewer to fill)\n\n"
        + "| Endpoint / Function | Suspect Loop | Est. Queries / Request | Fix |\n"
        + "|---|---|---|---|\n"
        + "| — | — | — | — |\n\n"
    )


def section_9_code_quality(f: FolderFacts) -> str:
    return (
        "## 9. Code Quality + Complexity\n\n"
        "### Readability\n\n"
        + _checklist([
            ("Clear variable / function / class names", ""),
            ("No misleading naming (no `tmp` / `xyz` / `foo`)", ""),
            ("Small focused functions (≤ 50 lines)",
             f"{len([x for x in f.longest_functions if x[0] > 50])} > 50 lines (see Section 0)"),
            ("Avoid deeply nested conditions (≤ 4 levels)", ""),
        ])
        + "\n### Clean code\n\n"
        + _checklist([
            ("No dead / commented-out code", ""),
            ("No `print()` — use logger", ""),
            ("No hardcoded values", f"smell count: {sum(f.smells.values())}"),
            ("Constants extracted to a settings module", ""),
        ])
        + "\n### Complexity\n\n"
        + _checklist([
            ("Long methods broken down", ""),
            ("No overengineering (premature abstractions)", ""),
            ("Cyclomatic complexity ≤ 15 per function", "run `ruff complexity` or `radon`"),
        ])
        + "\n"
    )


def section_10_security(f: FolderFacts) -> str:
    return (
        "## 10. Security Review\n\n"
        "### Authentication & Authorization\n\n"
        + _checklist([
            ("Authentication implemented correctly", "Bearer / JWT / session"),
            ("Authorization (RBAC / ABAC) checks", "no client-side trust"),
            ("Tokens validated server-side every request", "rotate, expire, revoke"),
        ])
        + "\n### OWASP Top 10\n\n"
        + _checklist([
            ("Request validation present",
             f"sanitization: {', '.join(f.sanitization) or 'NONE'}"),
            ("SQL injection prevention",
             f"DB libs: {', '.join(f.db_libs) or 'n/a'} — parameterized queries only"),
            ("XSS / CSRF prevention", "output encoding / CSP / SameSite"),
            ("Path traversal prevention", "no user input concatenated to file paths"),
            ("Prompt injection prevention",
             "Rebuff / output filter" if f.ai_deps else "n/a — no AI deps"),
        ])
        + "\n### Secret Management\n\n"
        + _checklist([
            ("No secrets in code",
             f"smell count: {f.smells.get('hardcoded password literal', 0)} password literals, "
             f"{f.smells.get('hardcoded API key literal', 0)} api key literals"),
            ("Env vars / Vault used", "Pydantic BaseSettings or env reader"),
            ("Secret rotation strategy", "documented in runbook"),
        ])
        + "\n### Sensitive Data\n\n"
        + _checklist([
            ("PII masked in logs", "structured logger with field redaction"),
            ("Encryption in transit (TLS)", ""),
            ("Encryption at rest (DB / object store)", ""),
            ("GDPR — retention + right-to-be-forgotten", ""),
        ])
        + "\n"
    )


def section_11_performance(f: FolderFacts) -> str:
    return (
        "## 11. Performance Review\n\n"
        "### Memory\n\n"
        + _checklist([
            ("Large object retention avoided", ""),
            ("Streaming for large files / data", ""),
            ("Caches bounded (LRU / TTL)",
             f"caching: {', '.join(f.cache) or 'none'}"),
        ])
        + "\n### Concurrency\n\n"
        + _checklist([
            ("Thread safety validated",
             f"primitives: {', '.join(f.concurrency) or 'none'}"),
            ("Race conditions prevented", ""),
            ("Deadlocks avoided (lock ordering)", ""),
            ("Parallel processing where beneficial",
             f"{f.async_functions} async fns"),
        ])
        + "\n### Latency\n\n"
        + _checklist([
            ("External API calls batched / cached", ""),
            ("Timeouts on every external call", ""),
            ("No blocking I/O inside async functions", ""),
        ])
        + "\n"
    )


def section_12_reliability(f: FolderFacts) -> str:
    return (
        "## 12. Reliability & Observability\n\n"
        "### Failure Handling\n\n"
        + _checklist([
            ("Retry (bounded + exp backoff + jitter)", ""),
            ("Circuit breaker around external deps", ""),
            ("Graceful degradation", ""),
        ])
        + "\n### Timeout Handling\n\n"
        + _checklist([
            ("Timeout on every external call (HTTP / DB / subprocess)", ""),
            ("No infinite waits", ""),
        ])
        + "\n### Observability\n\n"
        + _checklist([
            ("Structured (JSON) logging",
             "correlation_id + tenant_id + request_id"),
            ("Metrics (RED: rate / errors / duration)", ""),
            ("Tracing (OpenTelemetry → Jaeger / Tempo)", ""),
            ("Baggage propagation across services", ""),
        ])
        + "\n"
    )


def section_13_tests(f: FolderFacts) -> str:
    if not f.test_cases:
        return (
            "## 13. Test Cases\n\n"
            f"**Test files detected:** {f.test_file_count}\n"
            "_No `test_*` functions parsed via AST. Either tests live "
            "elsewhere or names don't match the `test_*` convention._\n\n"
        )
    rows = "\n".join(
        f"| `{tc.name}` | `{tc.file}:{tc.line}` | {tc.doc or '_(no docstring)_'} |"
        for tc in f.test_cases
    )
    return (
        f"## 13. Test Cases\n\n"
        f"**Test files detected:** {f.test_file_count}\n"
        f"**Test functions parsed:** {len(f.test_cases)}\n\n"
        f"| Test name | Location | Purpose (from docstring) |\n"
        f"|---|---|---|\n{rows}\n\n"
        "### Coverage matrix (reviewer to fill)\n\n"
        "| Metric | Value | Min |\n|---|---|---|\n"
        "| Statement coverage | _TBD_ % | 80% |\n"
        "| Branch coverage | _TBD_ % | 70% |\n"
        "| Critical-path coverage | _TBD_ % | 100% |\n"
        "| Negative-test coverage | _TBD_ % | 80% |\n\n"
    )


def section_14_logging_monitoring(f: FolderFacts) -> str:
    return (
        "## 14. Logging & Monitoring\n\n"
        "### Logging\n\n"
        + _checklist([
            ("Structured (JSON) logs", ""),
            ("Correlation ID present", ""),
            ("No PII / secrets in log lines", ""),
            ("No excessive logging (no logs in hot loops)", ""),
        ])
        + "\n### Monitoring\n\n"
        + _checklist([
            ("Alerts defined (SLO-burn aware)", ""),
            ("Dashboards exist (Grafana)", ""),
            ("On-call playbook references", ""),
        ])
        + "\n"
    )


def section_15_llm(f: FolderFacts) -> str:
    if not f.ai_deps:
        return (
            "## 15. LLM / GenAI / RAG\n\n"
            "_No AI / LLM dependencies detected — section not applicable._\n\n"
        )
    return (
        f"## 15. LLM / GenAI / RAG\n\n"
        f"**Detected AI deps:** {', '.join(f.ai_deps)}\n\n"
        "### Prompt Safety\n\n"
        + _checklist([
            ("Prompt injection handling (input filter)",
             "Rebuff" if "Rebuff (PI defense)" in f.ai_deps else ""),
            ("Output sanitization", ""),
            ("Prompt versioning in registry", ""),
            ("Toxicity / bias filtering", ""),
        ])
        + "\n### RAG Quality\n\n"
        + _checklist([
            ("Chunking strategy validated (size + overlap)", ""),
            ("Embedding model versioned (re-embed on bump)", ""),
            ("Vector DB query optimized (recall@k measured)", ""),
            ("Metadata filtering exists (per-tenant)", ""),
        ])
        + "\n### Cost\n\n"
        + _checklist([
            ("Model fallback strategy defined", ""),
            ("Token usage minimized (cache / truncation)", ""),
            ("Per-tenant cost ceiling enforced", ""),
        ])
        + "\n### Explainability / Responsible AI\n\n"
        + _checklist([
            ("Citation / source grounding (every claim cited)", ""),
            ("Confidence scoring (Ragas / DeepEval)",
             "Ragas" if "Ragas" in f.ai_deps else ""),
            ("Decision audit row per prediction (§48)", ""),
            ("Fairness / bias checks", ""),
        ])
        + "\n"
    )


def section_16_principles() -> str:
    return (
        "## 16. SOLID + Microservice Principles\n\n"
        "### SOLID\n\n"
        + _checklist([
            ("S — Single Responsibility (one reason to change per class)", ""),
            ("O — Open/Closed (extend via composition, not modification)", ""),
            ("L — Liskov Substitution (subclasses honor contracts)", ""),
            ("I — Interface Segregation (no fat interfaces)", ""),
            ("D — Dependency Inversion (depend on abstractions)", ""),
        ])
        + "\n### Microservice\n\n"
        + _checklist([
            ("Single business capability", ""),
            ("Bounded context (no domain bleed)", ""),
            ("Independent deploy (no coupled releases)", ""),
            ("Resilience patterns (CB / retry / bulkhead)", ""),
        ])
        + "\n"
    )


def section_17_integration(f: FolderFacts) -> str:
    if not f.integrations and not f.external_deps:
        return (
            "## 17. Integration with Other Folders\n\n"
            "_No internal cross-folder imports or external deps detected. "
            "This folder appears to be a leaf node._\n\n"
        )
    internal_rows = "\n".join(
        f"| `{k}` | {v} | _reviewer-described_ |"
        for k, v in sorted(f.integrations.items(), key=lambda x: -x[1])
    ) or "| _(none)_ | — | — |"
    external_rows = "\n".join(
        f"| `{k}` | {v} |"
        for k, v in sorted(f.external_deps.items(), key=lambda x: -x[1])[:20]
    ) or "| _(none)_ | — |"

    return (
        "## 17. Integration with Other Folders\n\n"
        "### Internal — other folders in this repo\n\n"
        "| Folder / Module | Import-count | Purpose |\n"
        "|---|---|---|\n"
        f"{internal_rows}\n\n"
        "### External — third-party packages\n\n"
        "| Package | Import-count |\n"
        "|---|---|\n"
        f"{external_rows}\n\n"
    )


def section_18_debugging(f: FolderFacts) -> str:
    return (
        "## 18. Debugging Guide\n\n"
        "### Step-by-step when something breaks\n\n"
        "```\n"
        f"1. Tail logs:        tail -50 /tmp/{f.name}.log   (if host-side)\n"
        f"                     docker logs documind-{f.name} --tail=50   (if container)\n"
        f"2. Health probe:     curl http://localhost:<PORT>/health\n"
        f"3. Fleet probe:      python3 scripts/advanced_healthcheck.py --layer app\n"
        f"4. Trace:            Open Jaeger → search request_id → see span tree\n"
        f"5. Metrics:          Open Grafana → service dashboard → look for spike\n"
        f"6. Drill:            ls mcp/tests/drill_*{f.name}*.py and run\n"
        "```\n\n"
        "### Common failure modes\n\n"
        "| Symptom | Likely cause | Fix |\n|---|---|---|\n"
        "| 502 / connection refused | service down | check `circuitrag-status.sh` |\n"
        "| Slow p95 latency | DB N+1 or LLM throttle | Section 8 + Section 15 |\n"
        "| 5xx spike | downstream dep down | check `/health/upstreams` |\n"
        "| Memory growth | unbounded cache or closure leak | Section 11 |\n"
        "| Wrong-tenant data | RLS bypass | tenant isolation drill |\n\n"
    )


def section_19_gates(f: FolderFacts) -> str:
    return (
        "## 19. Production Gates (hard pass/fail)\n\n"
        "| Gate | Target | Status | Evidence |\n|---|---|---|---|\n"
        "| Code coverage ≥ 80% | statements + branches | — | — |\n"
        "| Naming convention enforced | ruff / eslint | — | — |\n"
        "| Zero critical CVEs | Trivy / Bandit | — | — |\n"
        "| No hardcoded secrets | gitleaks | — | — |\n"
        f"| No memory leaks | bounded caches | — | smells: {sum(f.smells.values())} |\n"
        f"| No N+1 queries | hot paths reviewed | — | {sum(n for _, n in f.db_calls)} DB call sites |\n"
        f"| All APIs validated | Pydantic / Zod | — | sanitization: {', '.join(f.sanitization) or 'NONE'} |\n"
        "| Duplicate logic eliminated | DRY check | — | — |\n"
        "| Structured logging with correlation_id | — | — | — |\n"
        "| Distributed tracing wired | OpenTelemetry | — | — |\n"
        f"| For AI: prompt injection tested | Rebuff / Garak | — | {'AI deps present' if f.ai_deps else 'n/a'} |\n"
        f"| For AI: hallucination scoring ≥ 0.85 | Ragas faithfulness | — | {'yes' if 'Ragas' in f.ai_deps else 'n/a'} |\n\n"
    )


def section_20_final() -> str:
    return (
        "## 20. Final Production Readiness Score\n\n"
        "| Area | Score (/10) |\n|---|---|\n"
        "| Architecture | — |\n"
        "| Security | — |\n"
        "| Performance | — |\n"
        "| Reliability | — |\n"
        "| Observability | — |\n"
        "| Testing | — |\n"
        "| Scalability | — |\n"
        "| AI Safety | — |\n"
        "| DevOps | — |\n"
        "| Maintainability | — |\n"
        "| **Total** | **— / 100** |\n\n"
        "### Decision\n\n"
        "- [ ] **GO** — Production-ready (≥80, no failed gates)\n"
        "- [ ] **CONDITIONAL GO** — Ship with documented follow-ups (≥60)\n"
        "- [ ] **NO-GO** — Block release (any critical-red gate, or <60)\n\n"
        "### Critical blockers\n\n"
        "1. _TBD_\n\n"
        "### Follow-ups (post-ship)\n\n"
        "| ID | Description | Owner | Due |\n|---|---|---|---|\n"
        "| — | — | — | — |\n\n"
        "### Sign-off\n\n"
        "| Role | Name | Date | Signature |\n|---|---|---|---|\n"
        "| Tech Lead | — | — | — |\n"
        "| Security | — | — | — |\n"
        "| SRE | — | — | — |\n\n"
        "---\n\n"
        "_Generated by `scripts/generate_folder_report.py`. "
        "Re-run after major folder changes:_\n"
        "_`python3 scripts/generate_folder_report.py --folder <this-folder> --force`_\n"
    )


def render(f: FolderFacts) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    parts = [
        header(f, now),
        section_0_facts(f),
        section_1_purpose(f),
        section_2_file_inventory(f),
        section_3_c4_model(f),
        section_4_code_sequence(f),
        section_5_flowchart(f),
        section_6_api_endpoints(f),
        section_7_sequence_diagrams(f),
        section_8_database(f),
        section_9_code_quality(f),
        section_10_security(f),
        section_11_performance(f),
        section_12_reliability(f),
        section_13_tests(f),
        section_14_logging_monitoring(f),
        section_15_llm(f),
        section_16_principles(),
        section_17_integration(f),
        section_18_debugging(f),
        section_19_gates(f),
        section_20_final(),
    ]
    return "\n".join(parts)


# ─── Batch + CLI ───────────────────────────────────────────────────────

def _has_python(folder: Path) -> bool:
    for p in folder.rglob("*.py"):
        if not _is_ignored(p):
            return True
    return False


def _batch(name: str) -> List[Path]:
    if name == "services":
        return sorted(p for p in (REPO_ROOT / "services").iterdir()
                      if p.is_dir() and _has_python(p))
    if name == "libs":
        libs_root = REPO_ROOT / "libs" / "py"
        if not libs_root.exists():
            return []
        return sorted(p for p in libs_root.iterdir()
                      if p.is_dir() and _has_python(p))
    if name == "mcp":
        mcp_root = REPO_ROOT / "mcp"
        if not mcp_root.exists():
            return []
        return [mcp_root]
    if name == "python":
        # Every top-level dir with Python.
        out: List[Path] = []
        for p in REPO_ROOT.iterdir():
            if p.is_dir() and not p.name.startswith(".") and p.name not in {"node_modules"}:
                if _has_python(p):
                    out.append(p)
        return sorted(out)
    if name == "all":
        return _batch("services") + _batch("libs") + _batch("mcp")
    raise ValueError(f"unknown batch: {name}")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Generate per-folder advanced README.md.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--folder", "-f", type=Path,
                   help="Single folder (writes <folder>/README.md).")
    g.add_argument("--batch", "-b",
                   choices=["services", "libs", "mcp", "python", "all"],
                   help="Run on a named batch.")
    p.add_argument("--output", "-o", type=Path,
                   help="(single-folder only) custom output path.")
    p.add_argument("--filename", default="README.md",
                   help="Output filename (default README.md).")
    p.add_argument("--force", action="store_true",
                   help="Overwrite existing file.")
    p.add_argument("--dry-run", action="store_true",
                   help="Preview without writing.")
    return p.parse_args()


def write_one(folder: Path, output: Path, force: bool, dry: bool) -> tuple[bool, str]:
    if not folder.is_dir():
        return (False, f"not a directory: {folder}")
    if output.exists() and not force:
        return (False, f"SKIP (exists): {output}")
    facts = introspect(folder.resolve())
    content = render(facts)
    if dry:
        return (False,
                f"DRY-RUN: would write {output} "
                f"({len(content):,} bytes, {content.count(chr(10) + '## ')} sections)")
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(content, encoding="utf-8")
    except (PermissionError, OSError) as e:
        return (False, f"FAIL: {output} ({type(e).__name__}: {e})")
    return (True, f"WROTE {output} ({len(content):,} bytes)")


def main() -> int:
    args = parse_args()
    targets = [args.folder.resolve()] if args.folder else _batch(args.batch)
    if not targets:
        print("ERROR: no targets.", file=sys.stderr)
        return 1
    summary = {"wrote": 0, "skip": 0, "fail": 0}
    for folder in targets:
        out = args.output if (args.folder and args.output) else folder / args.filename
        ok, msg = write_one(folder, out, args.force, args.dry_run)
        mark = "✓" if ok else ("⊘" if "SKIP" in msg or "DRY-RUN" in msg else "✗")
        print(f"  {mark} {msg}")
        if ok:
            summary["wrote"] += 1
        elif "SKIP" in msg or "DRY-RUN" in msg:
            summary["skip"] += 1
        else:
            summary["fail"] += 1
    print(f"\nSummary: {summary['wrote']} wrote · "
          f"{summary['skip']} skip · {summary['fail']} fail")
    return 0 if summary["fail"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
