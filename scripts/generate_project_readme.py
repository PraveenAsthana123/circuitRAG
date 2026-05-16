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
        "## 🏛 Architecture — C4 Model\n\n"
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
        section_quick_start(),
        section_architecture(folders),
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
