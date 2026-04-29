#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: services/agent-orchestrator-svc/ structural contract.

The agent-orchestrator-svc was added in commit 5dfeb9c (G-1, parallel-
tool-authored, 25 files / 2120 insertions) without an autonomous-loop
drill. That ships a §43 discipline gap: every code commit needs a
drill with at least one negative assertion, and the service shipped
without one.

This drill closes the gap. It locks the service's structural surface
without testing live behaviour (live tests need Postgres + Ollama;
those belong in resourced-tier drills).

Eight steps. Six negative assertions.

  1. POSITIVE: service directory exists at the canonical path with
     all required files (Dockerfile, requirements.txt, app/main.py,
     app/agent_registry.py, app/agents.py, app/service.py,
     app/ollama_client.py, app/policy.py, app/postgres_store.py).
     Without these, the service can't boot.
  2. NEGATIVE: AgentRoleSpec catalog has at least 3 distinct
     role_types (coder, reviewer, advisor — the ADR-016 parallel-
     agent council shape). A registry with only 1 role_type means
     the council collapsed to a single agent and the parallel-agent
     allocation pattern is broken.
  3. NEGATIVE: every AgentRoleSpec entry has non-empty model AND
     prompt_template AND description. A spec missing any of these
     ships a "ghost role" — appears in the registry but cannot
     actually be invoked.
  4. NEGATIVE: ollama_client.OllamaClient takes base_url as a
     constructor parameter — no hardcoded http://localhost:11434.
     Hardcoded URLs break multi-environment deploy + Ollama Cloud
     routing.
  5. NEGATIVE: policy.py exports evaluate_approval_reasons. This
     is the gate function the service calls before any agent
     action; missing it means policy is bypassed.
  6. NEGATIVE: postgres_store.py uses parameterized queries only
     (no f-string SQL). Locks against the SQL-injection regression
     of CLAUDE.md §3 ("f-string in SQL").
  7. NEGATIVE: requirements.txt pins each dependency (every
     non-comment, non-blank line contains a version specifier).
     Unpinned deps mean the prod build is non-reproducible.
  8. POSITIVE: emit role catalog + file inventory for drift
     visibility (so operators can see when the registry expands).

Run: python3 mcp/tests/drill_agent_orchestrator_structure.py
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SVC = REPO / "services" / "agent-orchestrator-svc"

REQUIRED_FILES = (
    "Dockerfile",
    "requirements.txt",
    "app/main.py",
    "app/agent_registry.py",
    "app/agents.py",
    "app/service.py",
    "app/ollama_client.py",
    "app/policy.py",
    "app/postgres_store.py",
)

REQUIRED_ROLE_TYPES = ("coder", "reviewer", "advisor")

GREEN = "\033[32m"
RED = "\033[31m"
BOLD = "\033[1m"
NC = "\033[0m"


def ok(msg: str) -> None:
    print(f"  {GREEN}{msg}{NC}")


def fail(msg: str) -> None:
    print(f"  {RED}x {msg}{NC}")
    raise SystemExit(1)


def step(title: str) -> None:
    print(f"\n{BOLD}-- {title} --{NC}")


def _str_value(node: ast.AST) -> str:
    """Extract a string from a Constant node, or return the unparsed
    source for everything else (which lets us assert non-empty on
    multi-line concatenated templates without invoking any sandbox-
    risky helpers)."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    # Strings built via concatenation (e.g. multi-line prompt templates):
    # report their unparsed length as a proxy for "non-empty content".
    src = ast.unparse(node)
    return src if src else ""


def _all_role_specs(registry_path: Path) -> list[dict[str, str]]:
    """Walk the AST of agent_registry.py and return one dict per
    AgentRoleSpec(...) keyword call. We don't import the module; we
    inspect the source tree only."""
    tree = ast.parse(registry_path.read_text())
    specs: list[dict[str, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        callee_name = ""
        if isinstance(node.func, ast.Name):
            callee_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            callee_name = node.func.attr
        if callee_name != "AgentRoleSpec":
            continue
        kw_map: dict[str, str] = {}
        for kw in node.keywords:
            if kw.arg is None:
                continue
            kw_map[kw.arg] = _str_value(kw.value)
        specs.append(kw_map)
    return specs


def main() -> int:
    step("1. POSITIVE: service directory + required files exist")
    if not SVC.is_dir():
        fail(f"{SVC} not a directory")
    missing = [f for f in REQUIRED_FILES if not (SVC / f).is_file()]
    if missing:
        fail(f"missing required files: {missing}")
    ok(f"all {len(REQUIRED_FILES)} required files present at {SVC.relative_to(REPO)}")

    registry_path = SVC / "app" / "agent_registry.py"

    step("2. NEGATIVE: AgentRoleSpec catalog has at least 3 distinct role_types")
    specs = _all_role_specs(registry_path)
    if not specs:
        fail("no AgentRoleSpec(...) calls found in agent_registry.py")
    # Filter to literal-string role_types only. The registry has a
    # forwarder call (`role_type=spec.role_type` inside a copy
    # constructor) whose AST-unparsed source is "spec.role_type" —
    # not a real role definition. Real role types are simple lowercase
    # identifiers without dots / underscores at the start.
    role_types = {
        s.get("role_type")
        for s in specs
        if "role_type" in s
        and s["role_type"]
        and "." not in s["role_type"]
        and not s["role_type"].startswith("_")
        and s["role_type"].isidentifier()
    }
    missing_types = [r for r in REQUIRED_ROLE_TYPES if r not in role_types]
    if missing_types:
        fail(
            f"required role_types missing: {missing_types}. "
            f"Saw: {sorted(t for t in role_types if t)}"
        )
    ok(
        f"{len(specs)} specs covering {len(role_types)} literal role_types: "
        f"{sorted(t for t in role_types if t)}"
    )

    step("3. NEGATIVE: every spec has non-empty model + prompt_template + description")
    ghost_roles: list[tuple[str, str]] = []
    for spec in specs:
        role_id = spec.get("role_id", "<unknown>")
        for required in ("model", "prompt_template", "description"):
            value = spec.get(required, "")
            if not value or len(value.strip()) < 1:
                ghost_roles.append((role_id, required))
    if ghost_roles:
        fail(f"specs with empty/missing fields: {ghost_roles[:5]}")
    ok(f"all {len(specs)} specs are fully populated (no ghost roles)")

    step("4. NEGATIVE: OllamaClient takes base_url constructor parameter")
    client_text = (SVC / "app" / "ollama_client.py").read_text()
    client_tree = ast.parse(client_text)
    init_found = False
    for node in ast.walk(client_tree):
        if isinstance(node, ast.FunctionDef) and node.name == "__init__":
            arg_names = [a.arg for a in node.args.args] + [
                a.arg for a in node.args.kwonlyargs
            ]
            if "base_url" in arg_names:
                init_found = True
                break
    if not init_found:
        fail("OllamaClient.__init__ does not accept base_url parameter")
    forbidden_literals = re.findall(
        r"\"http://(localhost|127\.0\.0\.1):\d+\"|'http://(localhost|127\.0\.0\.1):\d+'",
        client_text,
    )
    if forbidden_literals:
        fail(
            f"hardcoded localhost URL(s) in ollama_client.py: "
            f"{forbidden_literals[:3]}"
        )
    ok("OllamaClient takes base_url; no hardcoded localhost URL literals")

    step("5. NEGATIVE: policy.py exports evaluate_approval_reasons")
    policy_text = (SVC / "app" / "policy.py").read_text()
    if "def evaluate_approval_reasons" not in policy_text:
        fail("policy.evaluate_approval_reasons not defined")
    ok("policy.evaluate_approval_reasons is defined")

    step("6. NEGATIVE: postgres_store.py uses parameterized queries only")
    pg_text = (SVC / "app" / "postgres_store.py").read_text()
    fstring_sql = re.findall(
        r"\bexecute\s*\(\s*f[\"']",
        pg_text,
    )
    if fstring_sql:
        fail(
            f"f-string SQL detected in postgres_store.py "
            f"({len(fstring_sql)} instance(s)). Use parameterized queries."
        )
    concat_sql = re.findall(
        r"\bexecute\s*\(\s*[\"'][^\"']*[\"']\s*\+",
        pg_text,
    )
    if concat_sql:
        fail(
            f"string-concatenation SQL detected ({len(concat_sql)} instance(s))"
        )
    ok("no f-string or concatenation SQL in postgres_store.py")

    step("7. NEGATIVE: requirements.txt pins every dependency")
    req_lines = (SVC / "requirements.txt").read_text().splitlines()
    unpinned: list[str] = []
    for line in req_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        # Local editable installs are legitimate (e.g., '-e ../../libs/py').
        # They reference a path, not a versioned package, so the pin
        # contract doesn't apply.
        if stripped.startswith("-e ") or stripped.startswith("--editable "):
            continue
        head = stripped.split("#", 1)[0].strip()
        if not head:
            continue
        if not re.search(r"(==|~=|>=|<=|===|>|<)", head):
            unpinned.append(head)
    if unpinned:
        fail(
            f"unpinned dependency line(s): {unpinned[:5]}. "
            "Production build must be reproducible."
        )
    pinned_count = sum(
        1 for l in req_lines if l.strip() and not l.strip().startswith("#")
    )
    ok(f"{pinned_count} requirements lines, all pinned")

    step("8. POSITIVE: emit role catalog + file inventory")
    spec_summary = ", ".join(
        f"{s.get('role_id', '?')}({s.get('role_type', '?')})" for s in specs
    )
    ok(f"role catalog: {spec_summary}")
    ok(f"file inventory: {len(REQUIRED_FILES)} required files all present")

    print(f"\n{BOLD}{GREEN}{'=' * 50}{NC}")
    print(f"{BOLD}{GREEN}  ALL 8 ORCHESTRATOR-STRUCTURE STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}  (6 negative assertions: 2, 3, 4, 5, 6, 7){NC}")
    print(f"{BOLD}{GREEN}{'=' * 50}{NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
