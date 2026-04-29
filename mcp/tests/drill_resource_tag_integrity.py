#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: every drill's # RESOURCES: tag honestly reflects what the
drill imports.

Resource tags drive the run_drills.py scheduler. A drill tagged
'readonly' / 'none' MUST be safe to run in tier-1 (zero-infra
sweeps before commit, CI without docker-compose). A drill that
imports asyncpg, qdrant_client, or playwright but tags itself
readonly will mysteriously fail in CI without dependencies, or
worse — pass locally because the dev box has them but break a
fresh-checkout colleague.

This drill catches the dangerous direction: import → tag. If a
drill imports an infrastructure module, it MUST be tagged with
the matching resource. The reverse direction (tag → import) is
NOT enforced because PG / MCP / inference access often goes
through project-internal wrappers (documind_core.repos.*, etc.)
where the asyncpg import is one level deeper. The tag is the
operator's claim about runtime requirements; the import is
deterministic evidence of those requirements.

Eight steps. Five negative assertions.

  1. POSITIVE: discover drills (>= 100 floor — drill cannot
     trivially pass by deleting the directory).
  2. NEGATIVE: drills importing asyncpg / psycopg / psycopg2
     MUST be tagged 'pg'. Tagged-readonly + uses-asyncpg = the
     specific regression we lock against.
  3. NEGATIVE: drills importing qdrant_client MUST be tagged
     'qdrant'. Vector DB access in a readonly drill = the same
     regression pattern.
  4. NEGATIVE: drills importing playwright MUST be tagged
     'playwright' OR 'frontend' (frontend tag subsumes browser
     automation since you cannot exercise the frontend without
     it).
  5. NEGATIVE: readonly / none drills MUST NOT import any
     infrastructure module from the watch-list (asyncpg,
     psycopg, qdrant_client, playwright). The readonly tier is
     "pure-Python AST inspection only"; an infra import here
     contradicts the tier definition.
  6. NEGATIVE: drills tagged with an MCP namespace
     (mcp_hr / mcp_itsm / mcp_drills) MUST reference the
     namespace's URL env var OR import from the mcp module.
     Otherwise the tag is operator wishful thinking, not
     enforced behaviour.
  7. POSITIVE: emit per-tag drill count distribution.
  8. POSITIVE: emit infra-import distribution (which drills use
     which infra module — operator visibility on resource
     coupling).

Run: python3 mcp/tests/drill_resource_tag_integrity.py
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DRILLS_DIR = REPO / "mcp" / "tests"

MIN_DRILLS = 100

# (import_name, allowed_tag_set). The drill MUST be tagged with at
# least one tag from the set when the import_name appears.
# Multiple import names with the same allowed set are listed once
# per import.
TAG_REQUIREMENT = {
    "asyncpg": {"pg"},
    "psycopg": {"pg"},
    "psycopg2": {"pg"},
    "qdrant_client": {"qdrant"},
    "playwright": {"playwright", "frontend"},
}

# Tags that mean "no infrastructure". A drill with one of these
# tags must NOT import any infra module.
INFRA_FREE_TAGS = {"readonly", "none"}

# MCP namespace tags + their evidence patterns. The drill must
# contain at least one of these source-string markers, OR have a
# transitive-access tag (inference / retrieval / ingestion) which
# indicates the drill reaches MCP through a service that does.
# A drill tagged "inference mcp_hr" is honestly declaring "this
# drill needs both inference-svc AND mcp_hr alive" — even if its
# own code only talks to inference-svc directly.
MCP_NAMESPACE_EVIDENCE = {
    "mcp_hr": ("MCP_HR_URL", "from mcp", "8090", ":8090", "/mcp/hr"),
    "mcp_itsm": ("MCP_ITSM_URL", "from mcp", "8091", ":8091", "/mcp/itsm"),
    "mcp_drills": ("MCP_DRILLS_URL", "from mcp", "8092", ":8092", "/mcp/drills"),
}
# Tags that mean "I reach MCP transitively through a service".
TRANSITIVE_ACCESS_TAGS = {"inference", "retrieval", "ingestion"}

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


def _resource_tags(source: str) -> set[str]:
    """Parse the # RESOURCES: header line. Tags can be space-separated;
    sub-scoped tags like 'mcp_hr:read' collapse to base 'mcp_hr'."""
    m = re.search(r"^#\s*RESOURCES:\s*(.+)$", source, re.MULTILINE)
    if not m:
        return set()
    return {tok.split(":")[0] for tok in m.group(1).strip().split()}


def _readonly_subscoped_tags(source: str) -> set[str]:
    """Return the set of base tags that are declared with a ':read'
    sub-scope (e.g. 'mcp_hr:read' -> {'mcp_hr'}). Read sub-scope
    declares 'I'm a transitive consumer; I don't drive this surface
    directly' — exempts the tag from the direct-evidence check."""
    m = re.search(r"^#\s*RESOURCES:\s*(.+)$", source, re.MULTILINE)
    if not m:
        return set()
    out: set[str] = set()
    for tok in m.group(1).strip().split():
        if ":read" in tok:
            out.add(tok.split(":")[0])
    return out


def _imports(source: str) -> set[str]:
    """Top-level import names via AST (deterministic; not regex)."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module.split(".")[0])
    return names


def main() -> int:
    step("1. POSITIVE: discover drills (>= MIN_DRILLS floor)")
    drills = sorted(DRILLS_DIR.glob("drill_*.py"))
    if len(drills) < MIN_DRILLS:
        fail(
            f"only {len(drills)} drills discovered; floor is {MIN_DRILLS}. "
            "Drill cannot trivially pass by deleting the catalog."
        )
    ok(f"discovered {len(drills)} drills")

    drill_data: list[tuple[Path, set[str], set[str]]] = []
    for d in drills:
        src = d.read_text()
        drill_data.append((d, _resource_tags(src), _imports(src)))

    step("2. NEGATIVE: drills importing asyncpg/psycopg MUST be tagged 'pg'")
    pg_imports = {"asyncpg", "psycopg", "psycopg2"}
    pg_violations: list[tuple[str, list[str], list[str]]] = []
    for d, tags, imps in drill_data:
        used_pg = imps & pg_imports
        if used_pg and "pg" not in tags:
            pg_violations.append((d.name, sorted(used_pg), sorted(tags)))
    if pg_violations:
        fail(
            f"{len(pg_violations)} drill(s) import pg client but missing "
            f"'pg' tag: {pg_violations[:3]}"
        )
    ok(f"every drill that imports asyncpg/psycopg is tagged 'pg'")

    step("3. NEGATIVE: drills importing qdrant_client MUST be tagged 'qdrant'")
    qdrant_violations: list[tuple[str, list[str]]] = []
    for d, tags, imps in drill_data:
        if "qdrant_client" in imps and "qdrant" not in tags:
            qdrant_violations.append((d.name, sorted(tags)))
    if qdrant_violations:
        fail(
            f"{len(qdrant_violations)} drill(s) import qdrant_client but "
            f"missing 'qdrant' tag: {qdrant_violations[:3]}"
        )
    ok(f"every drill that imports qdrant_client is tagged 'qdrant'")

    step("4. NEGATIVE: drills importing playwright MUST be tagged 'playwright' OR 'frontend'")
    playwright_violations: list[tuple[str, list[str]]] = []
    for d, tags, imps in drill_data:
        if "playwright" in imps and not (tags & {"playwright", "frontend"}):
            playwright_violations.append((d.name, sorted(tags)))
    if playwright_violations:
        fail(
            f"{len(playwright_violations)} drill(s) import playwright but "
            f"missing 'playwright'/'frontend' tag: {playwright_violations[:3]}"
        )
    ok(f"every drill that imports playwright is tagged 'playwright' or 'frontend'")

    step("5. NEGATIVE: readonly/none drills MUST NOT import any infra module")
    watch_list = pg_imports | {"qdrant_client", "playwright"}
    infra_in_readonly: list[tuple[str, list[str], list[str]]] = []
    for d, tags, imps in drill_data:
        if not (tags & INFRA_FREE_TAGS):
            continue
        leaked = imps & watch_list
        if leaked:
            infra_in_readonly.append((d.name, sorted(tags), sorted(leaked)))
    if infra_in_readonly:
        fail(
            f"{len(infra_in_readonly)} readonly/none drill(s) import infra "
            f"modules: {infra_in_readonly[:3]}. Readonly tier must stay "
            "infra-free."
        )
    ok(f"no readonly/none drill imports asyncpg/qdrant_client/playwright")

    step("6. NEGATIVE: MCP-namespace-tagged drills MUST reference the namespace's evidence (URL env or mcp import)")
    mcp_violations: list[tuple[str, str, list[str]]] = []
    for d, tags, imps in drill_data:
        src = d.read_text()
        # Transitive-access tags satisfy the MCP-evidence
        # requirement once for ALL MCP namespace tags on the drill.
        # That's the right shape: a drill claiming "inference +
        # mcp_hr" declares the dependency tree honestly even if its
        # own code only talks to inference-svc.
        has_transitive = bool(tags & TRANSITIVE_ACCESS_TAGS)
        # ':read' sub-scoped tags are explicitly transitive consumers.
        readonly_subs = _readonly_subscoped_tags(src)
        for ns_tag, evidence in MCP_NAMESPACE_EVIDENCE.items():
            if ns_tag not in tags:
                continue
            if has_transitive:
                continue
            if ns_tag in readonly_subs:
                continue
            has_direct_evidence = any(token in src for token in evidence)
            if not has_direct_evidence:
                mcp_violations.append((d.name, ns_tag, sorted(tags)))
    if mcp_violations:
        fail(
            f"{len(mcp_violations)} MCP-tagged drill(s) lack evidence of the "
            f"namespace: {mcp_violations[:3]}. Tag {{ns}} requires URL env "
            "or `from mcp` import."
        )
    ok(f"every MCP-namespace-tagged drill references the namespace")

    step("7. POSITIVE: emit per-tag drill count distribution")
    tag_counts: dict[str, int] = {}
    for _, tags, _ in drill_data:
        for tag in tags:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
    if "readonly" not in tag_counts and "none" not in tag_counts:
        # Defensive: catalog shouldn't be empty of readonly drills.
        fail("catalog has no readonly/none drills — sanity check failed")
    summary = ", ".join(
        f"{t}:{tag_counts[t]}" for t in sorted(tag_counts, key=lambda k: -tag_counts[k])
    )
    ok(f"tag distribution: {summary}")

    step("8. POSITIVE: emit infra-import distribution")
    import_counts: dict[str, int] = {}
    for _, _, imps in drill_data:
        for imp in imps & watch_list:
            import_counts[imp] = import_counts.get(imp, 0) + 1
    if import_counts:
        imp_summary = ", ".join(
            f"{i}:{import_counts[i]}" for i in sorted(import_counts)
        )
        ok(f"infra-import distribution: {imp_summary}")
    else:
        ok("no drill in catalog imports any infra module from watch-list")

    print(f"\n{BOLD}{GREEN}{'=' * 50}{NC}")
    print(f"{BOLD}{GREEN}  ALL 8 RESOURCE-TAG-INTEGRITY STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}  (5 negative assertions: 2, 3, 4, 5, 6){NC}")
    print(f"{BOLD}{GREEN}{'=' * 50}{NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
