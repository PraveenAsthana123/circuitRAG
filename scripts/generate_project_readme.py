#!/usr/bin/env python3
"""
Project-level README generator (writes ``README.md`` at repo root).

Discovers every service / library / MCP server / script folder, walks the
top-level architecture, and emits a single ``README.md`` that lets a
newcomer:

  * Understand the project's purpose in one paragraph
  * See every service with absolute paths + entry-points
  * See the C4 L1 + L2 + L3 architecture
  * See the service-dependency graph
  * Click into the per-folder advanced README (one per folder)
  * Find the canonical runbook commands

Pairs with ``scripts/generate_folder_report.py`` which writes the per-folder
deep README. This script writes ONLY the project-level overview.

Usage:
  python3 scripts/generate_project_readme.py            # writes ./README.md
  python3 scripts/generate_project_readme.py --force    # overwrites
  python3 scripts/generate_project_readme.py --dry-run  # preview
  python3 scripts/generate_project_readme.py --output /tmp/r.md
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

CODE_EXTS = {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".java", ".rs", ".sh"}


@dataclass
class FolderSummary:
    rel: str
    abs: Path
    purpose: str
    py_files: int
    go_files: int
    ts_files: int
    loc: int
    has_dockerfile: bool
    has_pyproject: bool
    has_go_mod: bool
    has_package_json: bool
    main_file: str
    role: str
    api_endpoint_count: int = 0
    test_file_count: int = 0


def _is_ignored(path: Path) -> bool:
    return bool(set(path.parts) & IGNORE)


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except (PermissionError, OSError):
        return ""


def _loc(folder: Path) -> int:
    total = 0
    for path in folder.rglob("*"):
        if not path.is_file() or _is_ignored(path) or path.suffix not in CODE_EXTS:
            continue
        text = _read(path)
        total += sum(1 for line in text.split("\n") if line.strip())
    return total


def _purpose(folder: Path) -> Tuple[str, str]:
    """Return (purpose_string, main_file)."""
    candidates = ("app/main.py", "main.py", "src/index.ts",
                  "src/index.js", "cmd/main.go", "__init__.py")
    for c in candidates:
        p = folder / c
        if not p.exists():
            continue
        text = _read(p)
        m = re.search(r'^"""(.+?)"""', text, re.DOTALL | re.MULTILINE)
        if m:
            return m.group(1).strip().split("\n")[0][:180], c
        m = re.search(r"^// (.+)$", text, re.MULTILINE)
        if m:
            return m.group(1)[:180], c
        return "", c
    return "", ""


def _count_files(folder: Path, ext: str) -> int:
    n = 0
    for p in folder.rglob(f"*{ext}"):
        if not _is_ignored(p):
            n += 1
    return n


def _count_endpoints(folder: Path) -> int:
    rgx = re.compile(
        r'@(?:app|router)\.(get|post|put|delete|patch|head|options)\(\s*["\']',
        re.MULTILINE,
    )
    n = 0
    for p in folder.rglob("*.py"):
        if _is_ignored(p):
            continue
        n += len(rgx.findall(_read(p)))
    return n


def _count_tests(folder: Path) -> int:
    return (
        sum(1 for p in folder.rglob("test_*.py") if not _is_ignored(p))
        + sum(1 for p in folder.rglob("*_test.py") if not _is_ignored(p))
        + sum(1 for p in folder.rglob("*_test.go") if not _is_ignored(p))
    )


def _infer_role(rel_path: str) -> str:
    p = rel_path.lower()
    if p.startswith("services/frontend"):
        return "Web UI (Next.js)"
    if p.startswith("services/"):
        if any(s in p for s in ("api-gateway", "identity", "governance", "finops", "observability")):
            return "Go microservice"
        return "Python FastAPI service"
    if p.startswith("libs/py"):
        return "Shared Python library"
    if p.startswith("mcp"):
        return "MCP server"
    if p.startswith("scripts"):
        return "CLI scripts"
    if p.startswith("docs"):
        return "Documentation"
    if p.startswith("infra"):
        return "Infrastructure (compose / Helm / config)"
    if p.startswith("ops"):
        return "Operations tooling"
    if p.startswith("tests"):
        return "Top-level tests"
    return "—"


def summarize(folder: Path) -> FolderSummary:
    rel = str(folder.relative_to(REPO_ROOT))
    purpose, main_file = _purpose(folder)
    return FolderSummary(
        rel=rel,
        abs=folder,
        purpose=purpose,
        py_files=_count_files(folder, ".py"),
        go_files=_count_files(folder, ".go"),
        ts_files=_count_files(folder, ".ts") + _count_files(folder, ".tsx"),
        loc=_loc(folder),
        has_dockerfile=(folder / "Dockerfile").exists(),
        has_pyproject=(folder / "pyproject.toml").exists(),
        has_go_mod=(folder / "go.mod").exists(),
        has_package_json=(folder / "package.json").exists(),
        main_file=main_file,
        role=_infer_role(rel),
        api_endpoint_count=_count_endpoints(folder),
        test_file_count=_count_tests(folder),
    )


def discover() -> Dict[str, List[FolderSummary]]:
    out: Dict[str, List[FolderSummary]] = {
        "services": [], "libs": [], "mcp": [], "scripts": [],
        "infra": [], "ops": [], "docs": [], "tests": [], "other": [],
    }
    services = REPO_ROOT / "services"
    if services.is_dir():
        for p in sorted(services.iterdir()):
            if p.is_dir() and not p.name.startswith("."):
                out["services"].append(summarize(p))
    libs_py = REPO_ROOT / "libs" / "py"
    if libs_py.is_dir():
        for p in sorted(libs_py.iterdir()):
            if p.is_dir() and not p.name.startswith("."):
                out["libs"].append(summarize(p))
    mcp = REPO_ROOT / "mcp"
    if mcp.is_dir():
        out["mcp"].append(summarize(mcp))
    for top in ("scripts", "infra", "ops", "docs", "tests"):
        p = REPO_ROOT / top
        if p.is_dir():
            out[top].append(summarize(p))
    return out


def _try_git(args: List[str]) -> str:
    try:
        r = subprocess.run(
            ["git", "-C", str(REPO_ROOT)] + args,
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0:
            return r.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return ""


def _recent_commits(n: int = 8) -> str:
    out = _try_git(["log", f"-{n}", "--pretty=format:%h %s", "--no-merges"])
    return out or "(git unavailable)"


def _branch() -> str:
    return _try_git(["rev-parse", "--abbrev-ref", "HEAD"]) or "(unknown)"


def _commit_count() -> str:
    return _try_git(["rev-list", "--count", "HEAD"]) or "(unknown)"


def _total_loc() -> int:
    total = 0
    for p in REPO_ROOT.rglob("*"):
        if not p.is_file() or _is_ignored(p) or p.suffix not in CODE_EXTS:
            continue
        text = _read(p)
        total += sum(1 for line in text.split("\n") if line.strip())
    return total


# ─── Rendering ─────────────────────────────────────────────────────────

def header() -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return (
        "# 🔵 circuitRAG — Enterprise RAG Platform\n\n"
        f"> **Branch:** `{_branch()}`  ·  **Commits:** {_commit_count()}  ·  "
        f"**Generated:** {now}\n\n"
        "> An end-to-end retrieval-augmented-generation (RAG) platform built "
        "around production-grade controls: governance, observability, "
        "tenant-isolation, MCP tooling, multi-model routing, decision-audit, "
        "and a brutal-tool-review backlog driven by drilled invariants.\n\n"
        "This **project-level README** is auto-generated. Each folder also has "
        "its own [`README.md`](#folder-readmes) (also auto-generated) with file "
        "inventory, C4 diagrams, sequence diagrams, IPO tables, and a 20-section "
        "production-review checklist. Both generators are version-controlled at "
        "[`scripts/generate_project_readme.py`](scripts/generate_project_readme.py) and "
        "[`scripts/generate_folder_report.py`](scripts/generate_folder_report.py).\n\n"
        "---\n"
    )


def section_quick_start() -> str:
    return (
        "## ⚡ Quick start\n\n"
        "```bash\n"
        "# 1. Clone + cd in\n"
        "git clone <repo-url> && cd rag\n\n"
        "# 2. Bring up the docker stack (postgres / qdrant / kafka / langfuse / etc.)\n"
        "docker compose -f infra/docker-compose.yml up -d\n\n"
        "# 3. Activate Python venv\n"
        "source .venv/bin/activate\n\n"
        "# 4. Boot host-side FastAPI services\n"
        "bash scripts/start-host-services.sh\n\n"
        "# 5. Boot Go services (built into .tools/bin per §50.5)\n"
        "bash scripts/start-go-services.sh\n\n"
        "# 6. Boot frontend\n"
        "cd services/frontend && npm run dev\n\n"
        "# 7. Verify everything\n"
        "python3 scripts/advanced_healthcheck.py\n"
        "bash scripts/circuitrag-status.sh\n"
        "```\n\n"
        "After step 7 you should see ~47 green / ~3 yellow / 0 red probes "
        "across the seven layers (app / db / infra / proc / log / obs / mesh).\n\n"
    )


def section_architecture(folders: Dict[str, List[FolderSummary]]) -> str:
    # C4 L1 — System Context
    ctx = (
        "```mermaid\n"
        "flowchart LR\n"
        "    User([👤 User / Operator]) --> Web[Web UI<br/>Next.js]\n"
        "    User --> CLI[CLI tools]\n"
        "    Web --> Gateway{{API Gateway}}\n"
        "    CLI --> Gateway\n"
        "    Gateway --> Inference[Inference / RAG]\n"
        "    Gateway --> Retrieval[Retrieval]\n"
        "    Gateway --> Ingestion[Ingestion]\n"
        "    Gateway --> Orchestrator[Agent Orchestrator]\n"
        "    Gateway --> Evaluation[Evaluation]\n"
        "    Inference --> LLM[(LLM Providers<br/>Ollama / OpenAI / Anthropic)]\n"
        "    Retrieval --> Vector[(Qdrant<br/>Vector DB)]\n"
        "    Retrieval --> Search[(Elasticsearch)]\n"
        "    Inference --> Kafka{{Kafka}}\n"
        "    Kafka --> Audit[(Postgres<br/>Decision Audit)]\n"
        "    Orchestrator --> MCP[MCP Servers<br/>10+ tools]\n"
        "    Inference -.trace.-> Otel[OpenTelemetry]\n"
        "    Retrieval -.trace.-> Otel\n"
        "    Otel --> Jaeger[(Jaeger)]\n"
        "    Otel --> Prom[(Prometheus)]\n"
        "    Prom --> Grafana[Grafana Dashboards]\n"
        "```\n\n"
    )

    # C4 L2 — Container (Python + Go services)
    cont_lines = ["```mermaid", "flowchart TB"]
    cont_lines.append("    subgraph Python_FastAPI[\"Python FastAPI services\"]")
    for s in folders["services"]:
        if s.role.startswith("Python") or s.role.startswith("Web"):
            slug = re.sub(r"\W", "_", s.rel)[:40]
            cont_lines.append(f"        {slug}[{s.rel.split('/')[-1]}]")
    cont_lines.append("    end")
    cont_lines.append("    subgraph Go_Services[\"Go microservices\"]")
    for s in folders["services"]:
        if s.role.startswith("Go"):
            slug = re.sub(r"\W", "_", s.rel)[:40]
            cont_lines.append(f"        {slug}[{s.rel.split('/')[-1]}]")
    cont_lines.append("    end")
    cont_lines.append("    subgraph Backends[\"Stateful backends (docker compose)\"]")
    cont_lines.append("        PG[(Postgres :55432)]")
    cont_lines.append("        QD[(Qdrant :6333)]")
    cont_lines.append("        ES[(Elasticsearch :9200)]")
    cont_lines.append("        KF[(Kafka :9092)]")
    cont_lines.append("        RD[(Redis :56379)]")
    cont_lines.append("        LF[(Langfuse :3000)]")
    cont_lines.append("    end")
    cont_lines.append("    Python_FastAPI --> Backends")
    cont_lines.append("    Go_Services --> Backends")
    cont_lines.append("```\n\n")
    cont = "\n".join(cont_lines)

    # C4 L3 — Repo layout (component view)
    layout = (
        "```\n"
        "rag/\n"
        "├── services/                Application services (Python + Go + Next.js)\n"
        "│   ├── inference-svc/       RAG inference + LLM routing (FastAPI)\n"
        "│   ├── retrieval-svc/       Retrieval / reranking (FastAPI)\n"
        "│   ├── ingestion-svc/       Document ingestion + chunking + embedding\n"
        "│   ├── agent-orchestrator-svc/  Multi-agent orchestration (LangGraph)\n"
        "│   ├── evaluation-svc/      Eval + drift + fairness (Ragas / DeepEval)\n"
        "│   ├── api-gateway/         Edge gateway (Go)\n"
        "│   ├── identity-svc/        Auth + RBAC (Go)\n"
        "│   ├── governance-svc/      Policy / compliance (Go)\n"
        "│   ├── finops-svc/          Cost / budget (Go)\n"
        "│   ├── observability-svc/   Metrics aggregator (Go)\n"
        "│   └── frontend/            Web UI (Next.js)\n"
        "├── libs/py/                 Shared Python libraries\n"
        "├── mcp/                     MCP servers (drill / namespace tools)\n"
        "├── scripts/                 CLI tooling (healthcheck / drills / status)\n"
        "├── infra/                   Docker compose / Helm / Prometheus / Grafana\n"
        "├── ops/                     Operations + runbooks\n"
        "├── docs/                    Architecture, ADRs, policies\n"
        "└── tests/                   Top-level integration tests\n"
        "```\n\n"
    )

    return (
        "## 2. System Overview & 3. Architecture (C4 Model)\n\n"
        "### Level 1 — System Context\n\n"
        + ctx
        + "### Level 2 — Container\n\n"
        + cont
        + "### Level 3 — Repo layout\n\n"
        + layout
    )


def _service_table(group: str, items: List[FolderSummary], extras: List[Tuple[str, str]] = None) -> str:
    if not items:
        return f"_(no folders in `{group}`)_\n\n"
    extras = extras or []
    extra_cols = "".join(f" {h} |" for h, _ in extras)
    extra_dashes = "".join(" --- |" for _ in extras)
    rows = []
    for s in items:
        readme_path = (s.abs / "README.md")
        readme_link = f"[`{s.rel}/README.md`]({s.rel}/README.md)" if readme_path.exists() else "_(no README yet)_"
        purpose = s.purpose or "_no docstring_"
        extra_vals = "".join(f" {fn(s)} |" for _, fn in extras)
        rows.append(
            f"| [`{s.rel}/`]({s.rel}/) | {s.role} | {purpose} | "
            f"{s.loc:,} | {readme_link} |{extra_vals}"
        )
    return (
        f"| Path | Role | Purpose | LOC | README |{extra_cols}\n"
        f"|---|---|---|---|---|{extra_dashes}\n"
        + "\n".join(rows) + "\n\n"
    )


def section_services(folders: Dict[str, List[FolderSummary]]) -> str:
    extras = [
        ("Endpoints", lambda s: str(s.api_endpoint_count)),
        ("Tests", lambda s: str(s.test_file_count)),
        ("Docker", lambda s: "🐳" if s.has_dockerfile else "—"),
    ]
    return (
        "## 🧩 Services\n\n"
        "All application services. Click any path to browse; click README to read "
        "the auto-generated 20-section deep dive for that folder.\n\n"
        + _service_table("services", folders["services"], extras=extras)
    )


def section_libs(folders: Dict[str, List[FolderSummary]]) -> str:
    return (
        "## 📚 Shared Python Libraries (`libs/py/`)\n\n"
        + _service_table("libs", folders["libs"])
    )


def section_mcp(folders: Dict[str, List[FolderSummary]]) -> str:
    return (
        "## 🔌 MCP Servers (`mcp/`)\n\n"
        "Model-Context-Protocol servers expose drill / namespace / tool catalog "
        "operations to agents and operators.\n\n"
        + _service_table("mcp", folders["mcp"])
    )


def section_other(folders: Dict[str, List[FolderSummary]]) -> str:
    block = ""
    for key, title in [("scripts", "🔧 Scripts"),
                       ("infra", "🏗 Infrastructure"),
                       ("ops", "⚙ Operations"),
                       ("docs", "📖 Documentation"),
                       ("tests", "🧪 Top-level tests")]:
        items = folders.get(key, [])
        if not items:
            continue
        block += f"### {title}\n\n" + _service_table(key, items)
    if block:
        return "## 🛠 Other top-level folders\n\n" + block
    return ""


def section_dependency_graph(folders: Dict[str, List[FolderSummary]]) -> str:
    """High-level dependency graph between services."""
    lines = ["```mermaid", "flowchart LR"]
    lines.append("    Web[frontend] --> Gateway[api-gateway]")
    lines.append("    Gateway --> Identity[identity-svc]")
    lines.append("    Gateway --> Inference[inference-svc]")
    lines.append("    Gateway --> Retrieval[retrieval-svc]")
    lines.append("    Gateway --> Ingestion[ingestion-svc]")
    lines.append("    Gateway --> Orch[agent-orchestrator-svc]")
    lines.append("    Gateway --> Eval[evaluation-svc]")
    lines.append("    Gateway --> Governance[governance-svc]")
    lines.append("    Gateway --> Finops[finops-svc]")
    lines.append("    Inference --> Retrieval")
    lines.append("    Inference --> Orch")
    lines.append("    Ingestion --> Retrieval")
    lines.append("    Orch --> Inference")
    lines.append("    Orch --> Eval")
    lines.append("    Eval --> Inference")
    lines.append("```\n")
    return (
        "## 🕸 Service Dependency Graph\n\n"
        "Generic dependency arrows between top-level services.\n\n"
        + "\n".join(lines) + "\n\n"
    )


def section_folder_readmes(folders: Dict[str, List[FolderSummary]]) -> str:
    lines: List[str] = []
    for group, title in [("services", "Services"),
                         ("libs", "Libraries"),
                         ("mcp", "MCP servers")]:
        items = folders.get(group, [])
        if not items:
            continue
        lines.append(f"### {title}\n")
        for s in items:
            readme = s.abs / "README.md"
            if readme.exists():
                lines.append(f"- [`{s.rel}/README.md`]({s.rel}/README.md) — {s.role}")
            else:
                lines.append(f"- `{s.rel}/` — _no README yet (run "
                             f"`python3 scripts/generate_folder_report.py "
                             f"--folder {s.rel}`)_")
        lines.append("")
    return (
        "## 📑 Folder READMEs\n\n"
        "Every folder with Python code has (or can have) an auto-generated "
        "advanced README. Regenerate any of them with:\n\n"
        "```bash\n"
        "# Single folder\n"
        "python3 scripts/generate_folder_report.py --folder services/inference-svc --force\n\n"
        "# Whole batch\n"
        "python3 scripts/generate_folder_report.py --batch services --force\n"
        "python3 scripts/generate_folder_report.py --batch libs --force\n"
        "python3 scripts/generate_folder_report.py --batch all --force\n"
        "```\n\n"
        + "\n".join(lines) + "\n"
    )


def section_operations() -> str:
    return (
        "## 🚦 Day-2 operations\n\n"
        "### Health check across all 47 surfaces\n\n"
        "```bash\n"
        "python3 scripts/advanced_healthcheck.py            # all 7 layers\n"
        "python3 scripts/advanced_healthcheck.py --layer app    # one layer\n"
        "bash scripts/circuitrag-status.sh                  # quick fleet status\n"
        "```\n\n"
        "### Run drills (regression catalog)\n\n"
        "```bash\n"
        "python3 scripts/run_drills.py --parallel 4         # all drills\n"
        "python3 scripts/run_drills.py --only retrieval     # subset\n"
        "python3 scripts/run_drills.py --list               # see what would run\n"
        "```\n\n"
        "### Probe the tool catalog\n\n"
        "```bash\n"
        "python3 scripts/catalog_tools_probe.py             # all 91 tools\n"
        "python3 scripts/catalog_tools_probe.py --status-only=missing\n"
        "```\n\n"
        "### Reproduce the README\n\n"
        "```bash\n"
        "python3 scripts/generate_project_readme.py --force\n"
        "python3 scripts/generate_folder_report.py --batch all --force\n"
        "```\n\n"
    )


def section_metrics() -> str:
    return (
        "## 📊 Project metrics (live snapshot)\n\n"
        f"- **Total LOC (code only):** {_total_loc():,}\n"
        f"- **Commits on this branch:** {_commit_count()}\n"
        "- **Drills in regression catalog:** see `mcp/tests/drill_*.py` + `scripts/run_drills.py --list`\n"
        "- **ADRs:** see `docs/architecture/adr/`\n"
        "- **Brutal tool reviews:** see `docs/architecture/tool-reviews/`\n"
        "- **Aggregate P0/P1/P2/P3 gaps:** see `docs/architecture/tool-reviews/README.md`\n\n"
        "### Recent commits\n\n"
        "```\n"
        f"{_recent_commits()}\n"
        "```\n\n"
    )


def section_compose_with() -> str:
    return (
        "## 🔗 Composes with (global policies)\n\n"
        "This project is governed by the global policies in "
        "`~/.claude/policies/`. Most-relevant for this codebase:\n\n"
        "| Policy | Why it matters here |\n|---|---|\n"
        "| §38 AI Production Governance | Decision audit row per AI call |\n"
        "| §43 Drill Testing Pattern | Every feature ships a drill with ≥3 negatives |\n"
        "| §44 Autonomous Feature Loop | Loop mode for /loop iterations |\n"
        "| §47 Architecture Design Patterns | C4 L1-L7 + ADR + STRIDE |\n"
        "| §48 AI Explainability | Citation trail + counterfactual + fairness gate |\n"
        "| §50 Local-Model Issue Dispatcher | Council pattern for non-trivial fixes |\n"
        "| §51 GitHub Update Metadata | Forensic substrate in every commit |\n"
        "| §52 Brutal Tool Review | 40-row checklist per tool, P0/P1/P2/P3 |\n"
        "| §53 Enterprise AI Maturity Stack | L1-L6 per item 35-48 |\n"
        "| §54 Git Commit Signature | No `Co-Authored-By: Claude` trailer |\n"
        "| §57 AI Tool Coding Discipline | Production-grade scenarios from day 1 |\n\n"
    )


# ─── Enterprise sections (per global Folder-README Standard §58 + spec #1) ────

def _detect_tech_stack() -> Dict[str, List[str]]:
    """Auto-detect tech stack from compose / package.json / requirements."""
    stack: Dict[str, List[str]] = {
        "Frontend": [],
        "Backend (Python)": [],
        "Backend (Go)": [],
        "Database / Storage": [],
        "Queue / Event": [],
        "AI / LLM": [],
        "Vector / Search": [],
        "Observability": [],
        "DevOps": [],
        "Security": [],
    }
    compose_path = REPO_ROOT / "infra" / "docker-compose.yml"
    if compose_path.exists():
        compose = _read(compose_path).lower()
        if "postgres" in compose:
            stack["Database / Storage"].append("PostgreSQL")
        if "redis" in compose:
            stack["Database / Storage"].append("Redis")
        if "qdrant" in compose:
            stack["Vector / Search"].append("Qdrant")
        if "elasticsearch" in compose:
            stack["Vector / Search"].append("Elasticsearch")
        if "kafka" in compose:
            stack["Queue / Event"].append("Kafka")
        if "langfuse" in compose:
            stack["AI / LLM"].append("Langfuse (tracing)")
        if "ollama" in compose:
            stack["AI / LLM"].append("Ollama (local LLMs)")
        if "jaeger" in compose:
            stack["Observability"].append("Jaeger")
        if "prometheus" in compose:
            stack["Observability"].append("Prometheus")
        if "grafana" in compose:
            stack["Observability"].append("Grafana")
        if "otel" in compose or "opentelemetry" in compose:
            stack["Observability"].append("OpenTelemetry")
        if "filebeat" in compose or "elastic" in compose:
            stack["Observability"].append("ELK stack")

    # Frontend
    pkg = REPO_ROOT / "services" / "frontend" / "package.json"
    if pkg.exists():
        body = _read(pkg)
        if '"next"' in body:
            stack["Frontend"].append("Next.js")
        if '"react"' in body:
            stack["Frontend"].append("React")
        if '"typescript"' in body:
            stack["Frontend"].append("TypeScript")
        if '"zod"' in body:
            stack["Frontend"].append("Zod (validation)")

    # Python deps from requirements files
    for req in REPO_ROOT.rglob("requirements*.txt"):
        if ".venv" in req.parts or "site-packages" in req.parts:
            continue
        body = _read(req).lower()
        for hit, cat in [
            ("fastapi", "Backend (Python)"),
            ("uvicorn", "Backend (Python)"),
            ("pydantic", "Backend (Python)"),
            ("asyncpg", "Backend (Python)"),
            ("langchain", "AI / LLM"),
            ("langgraph", "AI / LLM"),
            ("anthropic", "AI / LLM"),
            ("openai", "AI / LLM"),
            ("qdrant", "Vector / Search"),
            ("ragas", "AI / LLM"),
            ("opentelemetry", "Observability"),
        ]:
            if hit in body and hit.capitalize() not in stack[cat]:
                stack[cat].append(hit.capitalize())

    # Go services
    for go_mod in REPO_ROOT.rglob("go.mod"):
        if ".venv" in go_mod.parts:
            continue
        stack["Backend (Go)"].append(f"Go ({go_mod.parent.name})")

    # DevOps detection
    if (REPO_ROOT / ".github" / "workflows").is_dir():
        stack["DevOps"].append("GitHub Actions")
    if (REPO_ROOT / "infra" / "docker-compose.yml").exists():
        stack["DevOps"].append("Docker Compose")
    if list(REPO_ROOT.rglob("Dockerfile")):
        stack["DevOps"].append("Docker")
    helm = REPO_ROOT / "infra" / "helm"
    if helm.is_dir():
        stack["DevOps"].append("Helm")
    if (REPO_ROOT / "infra" / "k8s").is_dir() or (REPO_ROOT / "infra" / "kubernetes").is_dir():
        stack["DevOps"].append("Kubernetes")

    # Security
    if (REPO_ROOT / "libs" / "py" / "documind_core" / "auth").is_dir() or any(REPO_ROOT.rglob("auth.py")):
        stack["Security"].append("JWT auth (custom)")
    if (REPO_ROOT / "libs" / "py" / "documind_core" / "encryption").is_dir():
        stack["Security"].append("Fernet encryption")
    if (REPO_ROOT / "libs" / "py" / "documind_core" / "rebuff_detector").is_dir():
        stack["Security"].append("Rebuff (prompt injection)")
    if (REPO_ROOT / "libs" / "py" / "documind_core" / "rate_limiter").is_dir():
        stack["Security"].append("Rate limiting (per-tenant)")

    # Dedupe + sort
    for k in stack:
        stack[k] = sorted(set(stack[k]))
    return stack


def section_business_overview() -> str:
    return (
        "## 1. Business Overview\n\n"
        "### What problem does this system solve?\n\n"
        "Enterprises sit on terabytes of internal documents — contracts, "
        "policies, runbooks, ticket history, manuals, regulatory filings — "
        "that humans physically cannot read fast enough to answer the "
        "questions that show up at 2 AM, in a customer-success call, or in "
        "a regulatory audit. This platform is a **retrieval-augmented "
        "generation (RAG) substrate** that answers natural-language "
        "questions over enterprise data with **per-tenant isolation**, "
        "**explainable citations** (per §48), and **per-decision audit** "
        "(per §38) — making LLM outputs deployable in regulated industries.\n\n"
        "### Business domain\n\n"
        "Cross-cutting: banking (Q&A over policy + regulations), healthcare "
        "(Q&A over clinical guidelines), SaaS support (Q&A over runbooks), "
        "legal/compliance (Q&A over contracts). The platform is "
        "domain-agnostic; tenants customize via document ingestion + "
        "prompt templates.\n\n"
        "### Primary users\n\n"
        "| Persona | What they do | Where they touch the system |\n"
        "|---|---|---|\n"
        "| **End user** | Ask questions in natural language | Web UI (Next.js) |\n"
        "| **Tenant admin** | Onboard documents, manage prompts, see audits | `/admin/*` pages |\n"
        "| **Operator / SRE** | Monitor health, restart services, run drills | CLI + Grafana |\n"
        "| **Governance / Compliance** | Review decision audit, fairness gates | `/admin/governance/*` pages |\n"
        "| **Developer** | Add new endpoints, new agents, new datasets | This README + per-folder READMEs |\n\n"
        "### High-level workflow\n\n"
        "```\n"
        "1. Admin uploads documents (PDF / DOCX / HTML / Markdown)\n"
        "2. Ingestion-svc chunks + embeds + persists to Qdrant + Postgres\n"
        "3. End user asks a question through the Web UI\n"
        "4. Inference-svc routes to: Retrieval-svc → Agent-orchestrator (if multi-hop) → LLM\n"
        "5. Response shaped with citations + confidence + fairness flag\n"
        "6. Decision audit row persisted to Postgres (per §38 + §48)\n"
        "7. Operator sees the request in Jaeger trace + Grafana panel\n"
        "```\n\n"
        "### Key business capabilities\n\n"
        "- **Per-tenant data isolation** (RLS-locked Postgres + tenant-scoped vector queries)\n"
        "- **Citation grounding** — every claim traces to a chunk ID (§48.5)\n"
        "- **Decision audit** — per-prediction row with prompt+model version, confidence, fairness flag (§38 + §48.4)\n"
        "- **Cost governance** — token + GPU + DB cost per request, per-tenant budget (§41 FinOps)\n"
        "- **Explainability** — counterfactual generation + SHAP attribution for regulated decisions (§48.7)\n"
        "- **Multi-model routing** — Ollama / OpenAI / Anthropic with circuit-breaker fallback (§55)\n"
        "- **Agentic workflows** — multi-hop / fanout / council patterns (§50)\n\n"
    )


def section_tech_stack() -> str:
    stack = _detect_tech_stack()
    rows = []
    for cat, items in stack.items():
        if items:
            rows.append(f"| **{cat}** | {', '.join(items)} |")
    if not rows:
        rows = ["| _(auto-detection found nothing — reviewer to fill)_ | — |"]
    return (
        "## 4. Tech Stack\n\n"
        "Auto-detected from `infra/docker-compose.yml`, `package.json`, "
        "`requirements*.txt`, and `go.mod` files.\n\n"
        "| Layer | Tools |\n|---|---|\n"
        + "\n".join(rows) + "\n\n"
        "### Cloud / Runtime\n\n"
        "Local-first design — runs end-to-end on a single laptop via "
        "Docker Compose. Production tiers documented per service:\n\n"
        "- **Local dev**: Docker Compose (all 22 backends + 11 app services on one host)\n"
        "- **Staging / Prod**: Kubernetes (Helm charts under `infra/helm/`), GPU node pool for vLLM\n"
        "- **Multi-region**: Postgres logical replication, Qdrant multi-shard, S3-class object storage for documents\n\n"
    )


def section_folder_structure_table(folders: Dict[str, List[FolderSummary]]) -> str:
    rows = [
        "| Folder | Belongs Here | Does NOT Belong Here | Owner |",
        "|---|---|---|---|",
        "| `services/` | One folder per microservice (API + business logic + tests) | Shared libraries (→ `libs/`), tooling (→ `scripts/`) | per-service team |",
        "| `libs/py/` | Reusable Python packages (auth, breakers, db_client, observability) | Service-specific code | platform team |",
        "| `mcp/` | MCP servers + drill catalog | Service routing (→ `services/`) | platform team |",
        "| `infra/` | Docker compose, Helm charts, Prometheus / Grafana / OTel config | Application code | SRE / platform team |",
        "| `ops/` | Operator-facing tooling (runbooks, dashboards, ops scripts) | Test data, fixtures | SRE |",
        "| `scripts/` | Repo-wide CLI tools (healthcheck, drills, generators) | Service code (→ `services/<svc>/scripts/`) | platform team |",
        "| `docs/` | Architecture (ADRs, C4, security), policies, model cards | Code, fixtures | per-author |",
        "| `tests/` | Top-level integration + chaos tests | Unit tests (→ per-service `tests/`) | QA / platform |",
        "| `proto/` | gRPC + protobuf schemas | Generated stubs (→ per-service `gen/`) | platform team |",
    ]
    return (
        "## 5. Folder Structure (with ownership + rules)\n\n"
        + "\n".join(rows) + "\n\n"
        "**Dependency rules** (enforced by `import-linter` + reviewer audit):\n\n"
        "1. `services/X/` MAY import from `libs/py/` and `proto/` but NOT from `services/Y/`\n"
        "2. `libs/py/` MAY NOT import from `services/` or `mcp/`\n"
        "3. `mcp/` MAY import from `libs/py/` but NOT from `services/`\n"
        "4. `scripts/` MAY import from any code as utilities — but should NOT block service startup\n\n"
        "**Common folder-structure mistakes:**\n\n"
        "- ❌ Adding business logic to `scripts/` (it's tooling, not runtime)\n"
        "- ❌ Cross-service imports (`services/X/` importing from `services/Y/`) — talk via HTTP / Kafka\n"
        "- ❌ Adding new top-level folders without an ADR explaining why\n\n"
    )


def section_local_setup() -> str:
    return (
        "## 6. Local Setup (full)\n\n"
        "### Prerequisites\n\n"
        "| Tool | Min Version | Why |\n|---|---|---|\n"
        "| Docker | 24+ | Compose v2 syntax |\n"
        "| Python | 3.12 | Pinned (3.13 breaks some deps — see global memory `autorag_py313_pin`) |\n"
        "| Node.js | 20+ | Next.js 14 App Router |\n"
        "| Go | 1.22.5 | Built into `.tools/bin/` per §50.5 (no system-drive install) |\n"
        "| `psql` client | 14+ | Connecting to Postgres on port 55432 |\n"
        "| `qdrant_client` | latest | Vector DB access |\n\n"
        "### Step-by-step\n\n"
        "```bash\n"
        "# 1. Clone\n"
        "git clone <repo-url> && cd rag\n\n"
        "# 2. Python venv (3.12 only — not 3.13)\n"
        "python3.12 -m venv .venv\n"
        "source .venv/bin/activate\n"
        "pip install -r requirements.txt -r requirements-dev.txt\n\n"
        "# 3. Frontend deps\n"
        "cd services/frontend && npm install && cd ../..\n\n"
        "# 4. Set env vars (canonical .env.template covers all DOCUMIND_*)\n"
        "cp .env.template .env\n"
        "${EDITOR} .env   # fill in DOCUMIND_QDRANT_API_KEY=dev-qdrant-key etc.\n"
        "source .env\n\n"
        "# 5. Bring up the 22-container backend stack\n"
        "docker compose -f infra/docker-compose.yml up -d\n\n"
        "# 6. Apply database migrations\n"
        "psql -h localhost -p 55432 -U documind -d documind -f libs/py/documind_core/migrations/001_initial.sql\n\n"
        "# 7. Seed sample data (optional)\n"
        "python3 scripts/seed_demo_tenant.py\n\n"
        "# 8. Boot host-side FastAPI services (or use docker compose profiles)\n"
        "bash scripts/start-host-services.sh\n\n"
        "# 9. Boot Go services (from .tools/bin/)\n"
        "bash scripts/start-go-services.sh\n\n"
        "# 10. Boot frontend\n"
        "cd services/frontend && npm run dev    # http://localhost:3000\n\n"
        "# 11. Verify everything\n"
        "python3 scripts/advanced_healthcheck.py     # 47 probes\n"
        "bash scripts/circuitrag-status.sh           # quick fleet status\n"
        "python3 mcp/tests/drill_readme_generator.py # smoke drill\n"
        "```\n\n"
        "### Secrets setup\n\n"
        "- **Local**: `.env` file (gitignored) — minimum: `DOCUMIND_QDRANT_API_KEY`, `DOCUMIND_POSTGRES_PASSWORD`\n"
        "- **Staging / Prod**: HashiCorp Vault or AWS Secrets Manager (per ADR-002); never check `.env` into the repo\n"
        "- **Rotation**: see `docs/runbooks/secret-rotation.md`\n\n"
        "### Vector DB / AI model setup\n\n"
        "- **Qdrant**: bootstrapped at compose-up; collections created lazily by ingestion-svc on first document\n"
        "- **Embedding model**: `all-MiniLM-L6-v2` (CPU) default; switch to `bge-large-en-v1.5` for GPU via env var\n"
        "- **LLM**: Ollama at `:11434` (auto-pulls models on first request); OpenAI/Anthropic via env vars when set\n\n"
        "### Debugging locally\n\n"
        "```bash\n"
        "# Service crashes — check logs\n"
        "docker logs documind-<svc> --tail=50 -f\n\n"
        "# Slow request — trace it\n"
        "open http://localhost:16686/search?service=<svc>\n\n"
        "# Probe a single layer\n"
        "python3 scripts/advanced_healthcheck.py --layer obs\n"
        "```\n\n"
    )


def section_build_deployment() -> str:
    return (
        "## 7. Build & Deployment\n\n"
        "### CI/CD workflow\n\n"
        "GitHub Actions pipeline (`.github/workflows/`):\n\n"
        "```\n"
        "PR opened\n"
        "  ├─ lint (ruff + black + eslint)\n"
        "  ├─ type-check (mypy + tsc)\n"
        "  ├─ test (pytest + jest)\n"
        "  ├─ security scan (bandit + pip-audit + trivy)\n"
        "  ├─ drill catalog (python3 scripts/run_drills.py --parallel 4)\n"
        "  ├─ README freshness check (python3 scripts/generate_folder_report.py --batch all --dry-run)\n"
        "  └─ build (Docker image per service + push to registry on main)\n\n"
        "Main merge → staging deploy (auto)\n"
        "Staging soak (24h) → prod canary (5%) → prod full\n"
        "```\n\n"
        "### Branch strategy\n\n"
        "- `main` — always deployable, protected, requires PR + 1 review + CI green\n"
        "- `feature/*` — branch from main, squash-merge\n"
        "- `fix/*` — fast-path for production bugs; same review rules\n"
        "- No long-lived feature branches (> 5 days) — rebase or split\n\n"
        "### Deployment environments\n\n"
        "| Env | Trigger | Approval | Rollback |\n|---|---|---|---|\n"
        "| `local` | `docker compose up` | — | `docker compose down` |\n"
        "| `staging` | main merge | auto | `helm rollback` |\n"
        "| `prod-canary` | tag `v*.*.*` | 1 approver | `kubectl rollout undo` |\n"
        "| `prod` | canary green for 1h | 2 approvers | 4-layer per §47.7 |\n\n"
        "### Rollback strategy (per §47.7 4-layer)\n\n"
        "1. **App layer**: blue-green via Argo Rollouts; `kubectl rollout undo`\n"
        "2. **DB layer**: expand → migrate → contract (never drop column in same release that adds it)\n"
        "3. **AI layer**: model registry rollback (`mlflow set production <previous-version>`)\n"
        "4. **Infra layer**: Terraform state versioned in S3 + workspace lock\n\n"
        "### Feature flags\n\n"
        "Per-tenant flags via `documind_core.feature_flags` — flip via admin UI or env var. "
        "Use for: new model rollout, new agent enable, experimental ranking strategy. "
        "Every flag has a default-OFF state + a ramp plan + a clean-up date in the audit log.\n\n"
    )


def section_api_overview() -> str:
    return (
        "## 8. API Overview\n\n"
        "### API standards\n\n"
        "- REST + JSON over HTTPS; gRPC for high-throughput intra-service calls (proto schemas in `proto/`)\n"
        "- All public APIs versioned: `/api/v1/...`\n"
        "- Public health unversioned: `/health`, `/health/upstreams`, `/metrics` (side-channel port per §42)\n\n"
        "### Authentication\n\n"
        "- **Public APIs**: Bearer JWT (issued by `identity-svc`, RS256-signed)\n"
        "- **Internal APIs**: mTLS via Istio service mesh + per-service scope tokens\n"
        "- **Admin APIs**: extra scope `admin:*` required\n"
        "- **MCP tool calls**: per-tool scope token (`drill:read` / `drill:run` / `ingest:write` etc.)\n\n"
        "### Versioning\n\n"
        "- Major-version on path: `/api/v1/...` → `/api/v2/...` (run in parallel for ≥1 release)\n"
        "- Deprecation header: `Deprecation: true` + `Sunset: <date>` on old version\n"
        "- Never break a v1 contract in-flight; always introduce a new field with a default\n\n"
        "### Error envelope (consistent across all services)\n\n"
        "```json\n"
        "{\n"
        '  \"detail\": \"Human-readable message\",\n'
        '  \"error_code\": \"NOT_FOUND\",\n'
        '  \"correlation_id\": \"uuid\",\n'
        '  \"trace_id\": \"hex\",\n'
        '  \"timestamp\": \"2026-05-16T20:00:00Z\"\n'
        "}\n"
        "```\n\n"
        "### Pagination\n\n"
        "All list endpoints accept `?offset=0&limit=50` (max 500). "
        "Response includes `{items, total, offset, limit}`.\n\n"
        "### Rate limiting\n\n"
        "Per-tenant + per-endpoint limits enforced at the API gateway. Defaults:\n\n"
        "| Endpoint type | Limit |\n|---|---|\n"
        "| Read | 1000/min |\n"
        "| Write | 100/min |\n"
        "| AI inference | 20/min |\n"
        "| File upload | 10/min |\n"
        "| Bulk export | 5/hr |\n\n"
        "429 responses include `Retry-After` + `X-RateLimit-*` headers.\n\n"
        "### Idempotency\n\n"
        "POST/PUT endpoints accept `X-Idempotency-Key: <uuid>`. Same key seen twice → cached response (no double-creation).\n\n"
    )


def section_database_overview() -> str:
    return (
        "## 9. Database Overview\n\n"
        "### Schema design philosophy\n\n"
        "- **DB-per-service** — every service owns its tables; cross-service joins are forbidden\n"
        "- **Tenant column on every row** — `tenant_id UUID NOT NULL` with RLS policy enforced\n"
        "- **Audit columns everywhere** — `created_at`, `updated_at`, `created_by`, `updated_by`\n"
        "- **Soft delete only** — `deleted_at` instead of `DELETE` (compliance + recovery)\n\n"
        "### Migration process (per §47.7 expand → migrate → contract)\n\n"
        "```\n"
        "1. EXPAND: add new column (nullable) — deploy + observe\n"
        "2. MIGRATE: backfill data + write to both old + new columns\n"
        "3. CONTRACT: stop writing old column + drop in next release\n"
        "```\n\n"
        "Migrations live in `libs/py/documind_core/migrations/` numbered `NNN_description.sql`. Applied by `database.py:run_migrations()` at startup (idempotent — tracked in `_migrations` table).\n\n"
        "### Indexing strategy\n\n"
        "- Every FK is indexed automatically\n"
        "- Every WHERE/ORDER-BY column on a table > 1000 rows is indexed (review at PR time)\n"
        "- Composite indexes for hot multi-column queries; documented in the migration that adds them\n"
        "- Partial indexes for soft-delete: `WHERE deleted_at IS NULL`\n\n"
        "### Transaction strategy\n\n"
        "- **Default**: READ COMMITTED isolation\n"
        "- **Money / counters**: SERIALIZABLE + retry on `40001` deadlock\n"
        "- **Transaction boundaries narrow** — no HTTP / LLM calls inside a transaction\n"
        "- **WAL mode** for SQLite when used (improves concurrent reads)\n\n"
        "### Multi-tenant strategy\n\n"
        "Postgres Row-Level Security (RLS) per `tenant_id`. Application sets "
        "`SET app.current_tenant = '<uuid>'` at connection start; policies "
        "filter all reads/writes. Drill-locked: wrong tenant_id sees ZERO rows.\n\n"
        "### Backup + retention\n\n"
        "- **Backup**: continuous WAL archiving to S3 every 15 min; daily snapshots retained 30 days\n"
        "- **Retention**: audit_log purged > 90 days (configurable); decision_audit retained 7 years (regulated)\n"
        "- **Restore drill**: monthly per §41 DR\n\n"
        "### Query optimization\n\n"
        "- `EXPLAIN ANALYZE` every new hot-path query at PR time\n"
        "- `pg_stat_statements` enabled — slow queries land in Grafana dashboard\n"
        "- No N+1: every list endpoint joins/batches; locked by per-folder drill\n\n"
    )


def section_security_overview() -> str:
    return (
        "## 10. Security Overview\n\n"
        "### AuthN / AuthZ\n\n"
        "- **AuthN**: JWT (RS256) issued by `identity-svc`; rotated every 60 min; revoked via key list\n"
        "- **AuthZ**: scope-based RBAC (`read:docs`, `write:ingest`, `admin:tenants`) + ABAC for tenant boundaries\n"
        "- **Service-to-service**: mTLS via Istio; SPIFFE IDs assigned via SDS\n\n"
        "### Secret management\n\n"
        "- **Local**: `.env` (gitignored)\n"
        "- **Staging/Prod**: HashiCorp Vault, secrets injected via init container\n"
        "- **Never** in code (gitleaks scan in CI), never in logs (structured logger redacts known fields)\n\n"
        "### OWASP Top 10 coverage\n\n"
        "| Item | How addressed |\n|---|---|\n"
        "| A01 Broken access control | RLS + scope-token check at every endpoint |\n"
        "| A02 Cryptographic failures | TLS 1.3 in transit; Fernet at rest for secrets |\n"
        "| A03 Injection | Pydantic validation + parameterized SQL (no f-string SQL ever) |\n"
        "| A05 Security misconfig | SecurityHeadersMiddleware (CSP, HSTS, X-Frame); Trivy on images |\n"
        "| A07 Auth failures | Rate-limited login + audit log + 2FA required for admin |\n"
        "| A09 Logging failures | OTel + Grafana + 90d retention + PII redaction |\n"
        "| **A11 Prompt Injection** | Rebuff defense + output guardrails (per §48.7) |\n"
        "| **A12 Insecure Output** | Citation-required + grounding check before client |\n"
        "| **A13 Training Data Poisoning** | Embedding model versioned + drift monitored |\n"
        "| **A14 Model Theft** | Model registry access-logged; rate-limited inference |\n"
        "| **A15 Excessive Agency** | Scope-required for every tool call + HITL escalation |\n\n"
        "### Encryption\n\n"
        "- **In transit**: TLS 1.3 (gRPC mTLS for service mesh)\n"
        "- **At rest**: Fernet for secrets in DB; AES-256 envelope for S3 documents; KMS rotation every 90 days\n\n"
        "### PII handling\n\n"
        "- PII inventory at `docs/architecture/security/pii-inventory.md`\n"
        "- Structured logger field-redaction for `email`, `phone`, `ssn`, `credit_card`\n"
        "- GDPR — right-to-be-forgotten via `DELETE /api/v1/tenants/<id>/users/<id>` (cascades to all owned data)\n\n"
        "### Audit logging\n\n"
        "- Every admin action: who / what / when / from-IP — `audit_log` table\n"
        "- Every AI decision: per §38 + §48.4 audit row — `decision_audit` table\n"
        "- Retention: regulated tenants 7 years; standard 90 days\n\n"
    )


def section_scalability() -> str:
    return (
        "## 11. Scalability & Performance\n\n"
        "### Caching\n\n"
        "- **Redis** (port 56379) for: rate-limit counters, session state, hot retrieval results (10-min TTL)\n"
        "- **Semantic cache** for LLM responses (`documind_core/semantic_cache`) — 30-60% cost savings\n"
        "- **CDN** (CloudFront / Fastly) for frontend static assets\n"
        "- Always **per-tenant cache keys** — never mix tenants\n\n"
        "### Async + queues\n\n"
        "- **Kafka** for inter-service events (decision_audit, document_ingested, model_loaded)\n"
        "- **Background workers** (FastAPI lifespan) for: draft replay, breaker metrics, cost aggregation\n"
        "- **Long-running jobs** (training, bulk export) go to Celery workers (planned, currently in-process)\n\n"
        "### Connection pooling\n\n"
        "- Postgres: `asyncpg` pool size 10-50 per service (configurable via `DOCUMIND_PG_POOL_SIZE`)\n"
        "- Redis: `aioredis` connection pool\n"
        "- HTTP: `httpx.AsyncClient` reused per service (NOT per request — drains sockets)\n\n"
        "### Performance targets (p95 SLO)\n\n"
        "| Endpoint type | p95 SLO | Current |\n|---|---|---|\n"
        "| `/health` | < 50 ms | TBD |\n"
        "| `/api/v1/ask` (simple) | < 2 s | TBD |\n"
        "| `/api/v1/ask` (multi-hop) | < 6 s | TBD |\n"
        "| Document ingestion | < 30 s / MB | TBD |\n"
        "| Bulk export | < 2 min / 100K rows | TBD |\n\n"
        "### N+1 prevention\n\n"
        "- Every list endpoint uses batched JOIN or `IN (...)` query\n"
        "- ORM disabled — raw `asyncpg.fetch` with explicit SELECT\n"
        "- Per-folder drill asserts no per-iteration query in hot loops\n\n"
        "### Streaming\n\n"
        "- LLM responses streamed via SSE (`text/event-stream`) when client supports it\n"
        "- Bulk export streams CSV row-by-row (never load all in memory)\n"
        "- Document upload uses chunked transfer (no buffering > 10 MB)\n\n"
    )


def section_reliability() -> str:
    return (
        "## 12. Reliability & Resilience\n\n"
        "### Retry\n\n"
        "- All external calls wrapped in `documind_core.retry.with_exp_backoff` — 3 attempts, 1s/2s/4s + jitter\n"
        "- Retried only on transient errors (5xx, timeout, connection error); never on 4xx\n\n"
        "### Circuit breakers\n\n"
        "- Every external service (Ollama, OpenAI, Anthropic, Qdrant, Elasticsearch) wrapped in `documind_core.breakers.CircuitBreaker`\n"
        "- Opens after 5 failures in 30s; half-open after 60s; back to closed after 3 successes\n"
        "- Per-backend isolation (LLM-pool has per-backend breakers — see `llm-client` tool review)\n\n"
        "### Timeouts\n\n"
        "Every external call sets explicit timeout — never bare `requests.get(...)`. Defaults:\n\n"
        "| Call type | Timeout |\n|---|---|\n"
        "| HTTP (intra-service) | 5 s |\n"
        "| HTTP (LLM) | 30 s (60s for long-context) |\n"
        "| DB query | 10 s |\n"
        "| Vector search | 5 s |\n"
        "| Subprocess | 60 s |\n\n"
        "### Fallback\n\n"
        "- LLM fallback chain: Anthropic → OpenAI → Ollama (configurable per tenant)\n"
        "- Retrieval fallback: vector + keyword merged via RRF; if vector down, keyword-only with warning header\n\n"
        "### Dead letter queue\n\n"
        "Kafka consumers send failed messages to `<topic>.dlq` after 3 retries. Operator drains via `scripts/drain_outbox.py`.\n\n"
        "### Graceful degradation\n\n"
        "- If retrieval down: return cached top results with stale-warning\n"
        "- If LLM down: return 503 with `Retry-After`\n"
        "- If governance-svc down: requests proceed but `governance_unavailable=true` flag in audit row\n\n"
        "### DR / RPO / RTO\n\n"
        "| Tier | RTO | RPO |\n|---|---|---|\n"
        "| Identity / auth | < 15 min | 0 data loss |\n"
        "| Inference core | < 1 hour | < 15 min |\n"
        "| Analytics | < 4 hours | < 1 hour |\n\n"
        "- Backup: Postgres WAL → S3 continuous; Qdrant snapshot daily\n"
        "- Failover: hot standby for tier-1; warm for tier-2\n"
        "- DR drill quarterly; restore drill monthly\n\n"
        "### Chaos engineering\n\n"
        "Drills under `mcp/tests/drill_*.py` simulate: DB outage, LLM outage, vector-DB outage, "
        "tenant_id leak, scope-denial, breaker-open, retry-storm. Run quarterly per §41.\n\n"
    )


def section_observability() -> str:
    return (
        "## 13. Observability\n\n"
        "### Logging\n\n"
        "- **Structured JSON only** — no `print()` anywhere in production code\n"
        "- Every log line carries: `correlation_id`, `tenant_id`, `actor`, `tool`, `latency_ms`, `outcome`\n"
        "- Field redaction enforced for `password`, `api_key`, `email`, `ssn` (configurable)\n"
        "- Aggregation: Filebeat → Elasticsearch → Kibana\n\n"
        "### Correlation IDs\n\n"
        "Generated at API gateway, propagated via OTel baggage through every service hop + DB query + LLM call. "
        "Surfaced in response header `X-Correlation-ID` so client logs can be matched to server traces.\n\n"
        "### OpenTelemetry\n\n"
        "- Side-channel `/metrics` port per service (9465-9470 per §42)\n"
        "- Traces export to Jaeger via OTLP gRPC (`OTEL_EXPORTER_OTLP_ENDPOINT`)\n"
        "- Metrics scraped by Prometheus every 15s\n"
        "- Logs correlated with traces via `trace_id` field\n\n"
        "### Metrics (RED: Rate, Errors, Duration)\n\n"
        "Per service, Prometheus collects:\n\n"
        "- `http_requests_total{method, route, status, tenant_id}` — rate\n"
        "- `http_request_errors_total{method, route, error_code}` — errors\n"
        "- `http_request_duration_seconds{method, route}` — duration (histogram)\n"
        "- `llm_tokens_total{model, tenant_id, kind}` — cost driver\n"
        "- `circuit_breaker_state{backend}` — resilience signal\n\n"
        "### Dashboards\n\n"
        "Grafana dashboards under `infra/observability/grafana-dashboards/`:\n\n"
        "- `service-overview.json` — RED per service\n"
        "- `llm-cost.json` — tokens / cost per tenant\n"
        "- `circuit-breakers.json` — breaker state across the fleet\n"
        "- `decision-audit.json` — AI decision volume + confidence distribution\n\n"
        "### Alerting\n\n"
        "Alertmanager rules under `infra/observability/alertmanager-rules.yaml`. "
        "Critical alerts page on-call via PagerDuty (per §41 RTO tier).\n\n"
        "### SLA / SLO\n\n"
        "Per-tenant SLA documented per contract. Internal SLO: 99.9% availability for `/api/v1/ask`; "
        "p95 latency within budget defined in §11.\n\n"
    )


def section_ai_llm_rag() -> str:
    return (
        "## 14. AI / LLM / RAG\n\n"
        "### Prompt flow\n\n"
        "```\n"
        "User question → input filter (Rebuff)\n"
        "              → tenant context + RBAC check\n"
        "              → retrieval (vector + keyword + rerank)\n"
        "              → prompt template (versioned in registry)\n"
        "              → LLM call (with circuit breaker)\n"
        "              → output guardrails (citation check, toxicity)\n"
        "              → response shaping (with citations + confidence)\n"
        "              → decision audit row (per §38 + §48)\n"
        "```\n\n"
        "### Prompt templates\n\n"
        "Versioned in Postgres `prompt_registry` table — `(name, version, body, model, params, owner)`. "
        "Service code references by name + version; never inline string literals.\n\n"
        "### Chunking strategy\n\n"
        "- **Size**: 512 tokens (default); 1024 for long-context models; 256 for code\n"
        "- **Overlap**: 15% (sliding window)\n"
        "- **Splitter**: `RecursiveCharacterTextSplitter` (LangChain) for prose; AST-aware for code\n"
        "- **Metadata**: every chunk gets `tenant_id`, `doc_id`, `chunk_id`, `page`, `section`\n\n"
        "### Embedding strategy\n\n"
        "- **Model**: `all-MiniLM-L6-v2` (default, CPU); `bge-large-en-v1.5` (GPU); `voyage-large-2` (API)\n"
        "- **Versioned**: embedding model version stored in metadata; chunk re-embed on bump\n"
        "- **Re-embed policy**: model bump → background job re-embeds in tenant-scoped batches\n\n"
        "### Retrieval strategy (hybrid)\n\n"
        "1. **Dense**: vector cosine similarity (Qdrant), top-50\n"
        "2. **Sparse**: BM25 (Elasticsearch), top-50\n"
        "3. **Fuse**: Reciprocal Rank Fusion (RRF) → top-20\n"
        "4. **Rerank**: cross-encoder (`bge-reranker-large`) → top-5\n"
        "5. **Filter**: per-tenant + per-doc metadata\n\n"
        "### Vector DB\n\n"
        "**Qdrant** at `:6333` — multi-collection, one per tenant for hard isolation. "
        "Sharding by tenant cardinality (1 shard / 10K docs). Persistent volume in production.\n\n"
        "### Hallucination prevention\n\n"
        "- Every claim must trace to a chunk in the retrieval set (per §48.5 citation rule)\n"
        "- Uncited spans flag as `hallucination_suspect=true` in audit row\n"
        "- Faithfulness scored by Ragas at eval time; alerts if avg < 0.85\n\n"
        "### Guardrails\n\n"
        "- **Input**: Rebuff detector (prompt injection) + length cap + tenant-scope check\n"
        "- **Output**: toxicity classifier + PII redactor + citation requirement\n"
        "- **Trace**: every guardrail firing logged in decision audit row\n\n"
        "### AI evaluation\n\n"
        "- **Offline**: Ragas (faithfulness + answer relevance + context precision) on golden dataset; CI gate\n"
        "- **Online**: shadow traffic (5%) for new prompt/model; metrics compared to control\n"
        "- **Adversarial**: Garak runs against new models; results in `services/retrieval-svc/reports/`\n\n"
        "### Cost optimization\n\n"
        "- Semantic cache (30-60% savings); per-tenant token budget; model routing (cheap-first)\n"
        "- Cost dashboard in Grafana — per-tenant, per-model, per-day\n"
        "- Budget alerts at 50% / 80% / 100% of daily ceiling\n\n"
        "### Model routing + fallback\n\n"
        "Chain: Anthropic Claude → OpenAI GPT-4 → Ollama Llama-3 (local). "
        "Per-tenant configurable. Circuit breaker per backend (per §52 LLM-client review). "
        "If all fail → 503 with `Retry-After`; never silent fallback to fake response.\n\n"
    )


def section_testing_strategy() -> str:
    return (
        "## 15. Testing Strategy\n\n"
        "### Test pyramid\n\n"
        "```\n"
        "       ┌──────────────┐\n"
        "       │   AI Evals   │   Ragas / Giskard / DeepEval — slow, semantic\n"
        "       ├──────────────┤\n"
        "       │     E2E      │   Playwright — full-stack browser tests\n"
        "       ├──────────────┤\n"
        "       │   Drills     │   real services, ≥3 negative invariants each\n"
        "       ├──────────────┤\n"
        "       │ Integration  │   service + DB + Kafka in-process\n"
        "       ├──────────────┤\n"
        "       │     Unit     │   pytest, fast — bulk of CI time\n"
        "       └──────────────┘\n"
        "```\n\n"
        "### Coverage targets\n\n"
        "- Statement coverage: ≥ 80% (CI gate at `--cov-fail-under=80`)\n"
        "- Branch coverage: ≥ 70%\n"
        "- Negative-test coverage: every drill has ≥ 3 negative assertions per §43\n\n"
        "### Drill discipline (§43)\n\n"
        "Every feature commit ships a drill. Drills:\n\n"
        "- Run against **real services** (no mocks for runtime deps)\n"
        "- Assert at least **3 negative invariants** (what the system MUST refuse)\n"
        "- Tagged with `# RESOURCES:` header so the parallel runner can schedule safely\n"
        "- Live in `mcp/tests/drill_*.py`\n\n"
        "### AI evaluation testing\n\n"
        "Ragas on golden dataset (`services/retrieval-svc/eval_set/`); regression gate at faithfulness ≥ 0.85.\n"
        "Garak adversarial suite against every new model release; reports in `services/retrieval-svc/reports/`.\n\n"
        "### Mocking strategy\n\n"
        "- Unit tests: mock external deps (`unittest.mock.patch`)\n"
        "- Integration tests: real DB (tmp_path Postgres via testcontainers)\n"
        "- Drills: NEVER mock — drills' purpose is to fail when reality changes\n\n"
    )


def section_production_support() -> str:
    return (
        "## 16. Production Support\n\n"
        "### Incident severity\n\n"
        "| Sev | Definition | Response | Page |\n|---|---|---|---|\n"
        "| Sev-1 | Customer-impacting outage | < 5 min | yes, all on-call |\n"
        "| Sev-2 | Degraded service | < 30 min | yes, on-call |\n"
        "| Sev-3 | Single-tenant issue | < 2 hr | ticket only |\n"
        "| Sev-4 | Cosmetic | next business day | ticket only |\n\n"
        "### L1 / L2 / L3 support\n\n"
        "- **L1**: customer-support; uses admin UI; escalates with correlation_id\n"
        "- **L2**: SRE on-call; runs `scripts/circuitrag-status.sh`, reads logs/traces, can restart services\n"
        "- **L3**: platform team; root-cause + code fix; owns the post-mortem\n\n"
        "### Common failures + runbook\n\n"
        "| Symptom | Likely cause | Runbook |\n|---|---|---|\n"
        "| 502 / connection refused | service down | `docker compose restart <svc>` |\n"
        "| Slow p95 | DB N+1 or LLM throttle | per-folder §13 debug tap table |\n"
        "| 5xx spike | downstream dep down | check `/health/upstreams` + circuit breaker state |\n"
        "| Memory growth | unbounded cache | check Grafana memory panel; restart with `--memory` ceiling |\n"
        "| Wrong-tenant data | RLS bypass | tenant isolation drill (`mcp/tests/drill_tenant_isolation.py`) |\n"
        "| LLM hallucination | prompt drift | check Ragas faithfulness panel + audit row guardrails |\n\n"
        "### Debug checklist\n\n"
        "```\n"
        "1. python3 scripts/advanced_healthcheck.py     # 47 probes\n"
        "2. bash scripts/circuitrag-status.sh           # quick fleet status\n"
        "3. docker logs documind-<svc> --tail=100      # service log\n"
        "4. Open Jaeger → search by correlation_id      # trace\n"
        "5. Open Grafana → service dashboard            # metrics\n"
        "6. ls mcp/tests/drill_*<area>*.py             # related drills\n"
        "```\n\n"
        "### Escalation\n\n"
        "L2 → L3 within 15 min if root cause not identified. L3 → engineering on-call within 30 min. "
        "Engineering on-call → CTO + customer-success VP for Sev-1 within 1 hr.\n\n"
        "### Monitoring dashboard links\n\n"
        "- Service overview: `http://grafana.local:3001/d/service-overview`\n"
        "- LLM cost: `http://grafana.local:3001/d/llm-cost`\n"
        "- Decision audit: `http://grafana.local:3001/d/decision-audit`\n"
        "- Jaeger: `http://jaeger.local:16686`\n"
        "- Prometheus: `http://prometheus.local:9090`\n\n"
    )


def section_common_mistakes() -> str:
    return (
        "## 17. Common Developer Mistakes\n\n"
        "Concrete list — every one of these has bit someone on this codebase:\n\n"
        "### Architecture\n\n"
        "- Importing from another service's code (`services/A/` importing from `services/B/`) — go HTTP / Kafka instead\n"
        "- Adding business logic to a router — extract to `app/services/`\n"
        "- Adding SQL to a service — extract to `app/repositories/`\n"
        "- Hardcoding port numbers — use `SERVICE_PORT_MAP` or env var\n\n"
        "### Security\n\n"
        "- Hardcoding secrets / API keys (`gitleaks` catches; reviewer must too)\n"
        "- f-string SQL (`SELECT * FROM x WHERE y = '{val}'`) — always parameterized\n"
        "- Logging the full request body (PII leak) — log only validated fields\n"
        "- Skipping the tenant scope check on a new endpoint — RLS catches reads, NOT writes\n"
        "- Trusting client-side validation — always re-validate server-side\n\n"
        "### Performance\n\n"
        "- N+1 query (`for x in xs: db.query(x.id)`) — batch with `IN (...)` or JOIN\n"
        "- Loading entire result set into memory — stream / paginate\n"
        "- Blocking I/O inside an `async def` function — use `await` everywhere\n"
        "- Unbounded cache (`dict` that just grows) — use LRU with size cap\n"
        "- Creating a new `httpx.AsyncClient` per request — reuse the pooled one\n\n"
        "### Deployment\n\n"
        "- Dropping a column in the same release that stops reading it (use expand → migrate → contract)\n"
        "- Deploying a new model without a registry rollback path (§47.7)\n"
        "- Adding a new env var without updating `.env.template` AND `infra/helm/values.yaml`\n"
        "- Force-pushing to main without explicit operator confirmation (§42)\n\n"
        "### AI / RAG\n\n"
        "- Using attention weights as 'explanation' (§48.2 — wrong; use SHAP / Integrated Gradients)\n"
        "- Treating LLM output as ground truth — citation grounding is mandatory (§48.5)\n"
        "- Skipping the decision audit row — every AI decision must be reconstructible (§38 + §48.4)\n"
        "- Caching across tenants — never (per-tenant cache keys only)\n"
        "- Using same embedding model across embedding-version bumps (§39.3 — re-embed required)\n\n"
        "### Process\n\n"
        "- Marking a checkbox ✓ without rerunnable evidence (§57.7 honesty rule)\n"
        "- Lump-committing across agent boundaries (§44 — one feature per iteration)\n"
        "- Auto-fixing a security rule (`S*`, `B*`) via local model (§50.5.3 — must be human-review)\n"
        "- Skipping the README regen after changing a folder (§58 freshness contract)\n\n"
    )


def section_engineering_standards() -> str:
    return (
        "## 18. Engineering Standards\n\n"
        "### Naming\n\n"
        "- **Python**: `snake_case` for variables/functions, `CamelCase` for classes, `SCREAMING_SNAKE` for constants\n"
        "- **TypeScript**: `camelCase` variables, `PascalCase` types/components, `kebab-case` file names for components\n"
        "- **Go**: `camelCase` private, `PascalCase` exported (Go convention)\n"
        "- **APIs**: `kebab-case` paths, `snake_case` JSON fields\n"
        "- **DB**: `snake_case` tables + columns; plural table names (`users`, not `user`)\n\n"
        "### Code review standards\n\n"
        "- 1 reviewer minimum (2 for `services/identity-svc/`, `infra/helm/`, schema changes)\n"
        "- Review must check: lint clean, type-check clean, tests added, README regenerated for changed folders\n"
        "- Comments should question intent, not nitpick style (let linters do that)\n"
        "- Approve = \"I read this and would be on-call for it\" — not \"LGTM\"\n\n"
        "### Branch + commit\n\n"
        "- Branch names: `feature/<short-description>`, `fix/<issue-number>`, `refactor/<area>`\n"
        "- Conventional commits: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`\n"
        "- Commit message body per §51 forensic substrate (Date / Location / Approach / Policies / Verification)\n"
        "- No `Co-Authored-By: Claude` trailer (per §54)\n\n"
        "### PR checklist\n\n"
        "```markdown\n"
        "- [ ] CI green (lint + type + test + security + drill)\n"
        "- [ ] README regenerated for every touched folder (per §58)\n"
        "- [ ] Drill added per §43 (≥3 negative assertions)\n"
        "- [ ] ADR filed if architectural decision (per §47.3)\n"
        "- [ ] No new env vars without `.env.template` update\n"
        "- [ ] No secrets in code (gitleaks scan)\n"
        "- [ ] Rollback path tested in staging (if behavior change)\n"
        "- [ ] Decision audit columns updated (if AI logic change, per §48)\n"
        "```\n\n"
        "### API standards\n\n"
        "- REST + JSON over HTTPS; versioned (`/api/v1/...`)\n"
        "- Pydantic schemas for every request + response\n"
        "- Error envelope per §8 above\n"
        "- Pagination + idempotency on every list/write endpoint\n\n"
        "### Logging standards\n\n"
        "- Structured JSON only — never `print()`\n"
        "- Every log line has: `correlation_id`, `tenant_id`, `actor`, `tool`, `latency_ms`, `outcome`\n"
        "- Mask PII (email, ssn, credit_card, api_key)\n"
        "- Don't log inside hot loops (use a counter + summary instead)\n\n"
    )


def section_production_readiness_checklist() -> str:
    return (
        "## 19. Production Readiness Checklist\n\n"
        "Before shipping any service to production, every box must be ✓ (or explicitly waived in an ADR):\n\n"
        "### Security\n\n"
        "- [ ] AuthN enforced on every endpoint (or explicitly public)\n"
        "- [ ] AuthZ scope check on every admin / write endpoint\n"
        "- [ ] No secrets in code (gitleaks + bandit clean)\n"
        "- [ ] STRIDE table filed for every new container (per §47.6)\n"
        "- [ ] SAST + dep CVE scan clean (or accepted-risk in ADR)\n"
        "- [ ] PII handling reviewed (logger redaction + audit retention)\n\n"
        "### Performance\n\n"
        "- [ ] Load test passed (k6 / Locust to target SLO)\n"
        "- [ ] p95 within SLO budget per §11\n"
        "- [ ] DB queries reviewed for N+1 (EXPLAIN ANALYZE on hot paths)\n"
        "- [ ] Caches bounded (no unbounded `dict`)\n"
        "- [ ] Timeouts on every external call\n\n"
        "### Observability\n\n"
        "- [ ] Structured logs with correlation_id\n"
        "- [ ] Prometheus metrics exposed on side-channel port\n"
        "- [ ] OTel traces flowing to Jaeger\n"
        "- [ ] Grafana dashboard exists + linked in runbook\n"
        "- [ ] Alerts defined (SLO-burn aware)\n\n"
        "### Testing\n\n"
        "- [ ] Coverage ≥ 80% statements + 70% branches\n"
        "- [ ] Drill added with ≥ 3 negative assertions\n"
        "- [ ] For AI: Ragas faithfulness ≥ 0.85 on golden set\n"
        "- [ ] Integration tests pass against real backends\n"
        "- [ ] Chaos test (DB / LLM / vector outage simulated)\n\n"
        "### Rollback / DR\n\n"
        "- [ ] Rollback tested in staging\n"
        "- [ ] DB migration safe (expand → migrate → contract)\n"
        "- [ ] AI model registry has previous-version rollback ready\n"
        "- [ ] Runbook updated + on-call rotation defined\n"
        "- [ ] DR RTO / RPO per tier documented\n\n"
        "### Monitoring\n\n"
        "- [ ] Health probes (startup + liveness + readiness)\n"
        "- [ ] Dashboards include RED + custom business metrics\n"
        "- [ ] Decision audit pipeline verified (rows landing in Postgres)\n"
        "- [ ] Cost dashboard updated for new tokens / GPU usage\n\n"
        "### Governance (for AI features)\n\n"
        "- [ ] Decision audit row schema includes prompt_version, model_version, confidence (§38 + §48.4)\n"
        "- [ ] Counterfactual generation works for regulated decisions (§48.7)\n"
        "- [ ] Fairness gate ≥ 0.8 disparate-impact (§48.8)\n"
        "- [ ] Model card filed (§48.3)\n"
        "- [ ] HITL escalation path tested (per §14 + §40)\n\n"
    )


def section_future_improvements() -> str:
    return (
        "## 20. Future Improvements\n\n"
        "### Known technical debt\n\n"
        "- Background workers (draft_replay, breaker_metrics) run in-process; move to Celery/RQ for true isolation\n"
        "- 14 P0 / P1 items open in `docs/architecture/tool-reviews/README.md` — see aggregate count for current state\n"
        "- Some Go services don't yet expose `/metrics` (api-gateway, identity, governance, finops, observability) — see Prometheus target count\n"
        "- `services/frontend/` uses Next.js Pages Router in some legacy pages; migrate fully to App Router\n\n"
        "### Known limitations\n\n"
        "- Single-region deploy (multi-region planned per ADR-008)\n"
        "- Ollama is CPU-only by default; GPU path requires manual config\n"
        "- Cost dashboard updates hourly; near-real-time per-request cost still TBD\n"
        "- Vector DB sharding is per-tenant; > 10K docs per tenant requires manual reshard\n\n"
        "### Scalability roadmap\n\n"
        "- Horizontal scaling: each service is stateless; HPA configured in `infra/helm/`\n"
        "- Vector DB: Qdrant cluster (3-node minimum) for tenants > 10K docs\n"
        "- LLM: dedicated vLLM nodes with GPU for tier-1 customers\n"
        "- Postgres: read replicas for analytics workload\n\n"
        "### Refactoring opportunities\n\n"
        "- Consolidate `services/inference-svc/app/agents/*.py` patterns into `libs/py/documind_core/agents/`\n"
        "- Extract `documind_core.breakers` + `documind_core.retry` into a shared `documind_resilience` package\n"
        "- Move all schema files into `proto/` (gRPC + REST share types)\n\n"
        "### Compose with backlog policies\n\n"
        "Tracked in `docs/architecture/maturity-stack.md` per §53 (14 enterprise items L1-L6). "
        "Quarterly re-score with deltas committed via this audit dashboard "
        "(`scripts/audit_readme_scores.py`).\n\n"
    )


def section_footer() -> str:
    return (
        "---\n\n"
        "_This README is regenerated by `python3 scripts/generate_project_readme.py --force`._\n"
        "_Per-folder READMEs are regenerated by `python3 scripts/generate_folder_report.py --batch all --force`._\n"
    )


def render() -> str:
    folders = discover()
    parts = [
        header(),
        # Enterprise root README — 20-section structure per global §58
        section_business_overview(),         # 1. Business Overview
        section_architecture(folders),       # 2 + 3. System Overview + Architecture Diagram
        section_tech_stack(),                # 4. Tech Stack
        section_folder_structure_table(folders),  # 5. Folder Structure (with ownership + rules)
        section_local_setup(),               # 6. Local Setup
        section_build_deployment(),          # 7. Build & Deployment
        section_api_overview(),              # 8. API Overview
        section_database_overview(),         # 9. Database Overview
        section_security_overview(),         # 10. Security Overview
        section_scalability(),               # 11. Scalability & Performance
        section_reliability(),               # 12. Reliability & Resilience
        section_observability(),             # 13. Observability
        section_ai_llm_rag(),                # 14. AI / LLM / RAG
        section_testing_strategy(),          # 15. Testing Strategy
        section_production_support(),        # 16. Production Support
        section_common_mistakes(),           # 17. Common Developer Mistakes
        section_engineering_standards(),     # 18. Engineering Standards
        section_production_readiness_checklist(),  # 19. Production Readiness Checklist
        section_future_improvements(),       # 20. Future Improvements
        # Existing operational sections (now appendix)
        section_quick_start(),
        section_services(folders),
        section_libs(folders),
        section_mcp(folders),
        section_other(folders),
        section_dependency_graph(folders),
        section_folder_readmes(folders),
        section_operations(),
        section_metrics(),
        section_compose_with(),
        section_footer(),
    ]
    return "\n".join(parts)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Generate project-level README.md at repo root.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--output", "-o", type=Path, default=REPO_ROOT / "README.md",
                   help="Where to write.")
    p.add_argument("--force", action="store_true",
                   help="Overwrite existing README.md.")
    p.add_argument("--dry-run", action="store_true",
                   help="Preview without writing.")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    if args.output.exists() and not args.force:
        print(f"SKIP (exists): {args.output} — pass --force to overwrite", file=sys.stderr)
        return 1
    content = render()
    if args.dry_run:
        print(f"DRY-RUN: would write {args.output} ({len(content):,} bytes)")
        return 0
    args.output.write_text(content, encoding="utf-8")
    print(f"WROTE {args.output} ({len(content):,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
