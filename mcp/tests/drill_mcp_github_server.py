# RESOURCES: readonly
"""
Drill: mcp/server_github.py — read-only Stage-1 contract.

Per CLAUDE.md §43 (drill discipline; ≥3 negatives), §44 (autonomous-loop
ONE-thing-per-iter; iter-68 ships the most-critical missing AI SDLC tool),
§45.4 (no checkbox flips without code), §47 (architecture: each MCP server
owns ONE namespace), §47.6 (security: read-only Stage-1; PR comment /
issue create / merge are externally-visible mutations — separate ADR
per ADR-028 pattern).

Locks (positive):
  L1. mcp/server_github.py exists + canonical structure
  L2. TOOLS list has all 6 expected tool names
  L3. all 6 tools side_effects='read' + scope='github:read'
  L4. Repo slug regex enforces owner/name shape
  L5. Path validator blocks .. / leading / + null bytes (path traversal)
  L6. inference-svc mcp_spec wires DOCUMIND_MCP_GITHUB_URL

Locks (negative — ≥3 per §43):
  N1. 0 write tools (no PR comment / issue create / merge — write
      surface ships separately per ADR-028 pattern)
  N2. Repo allow-list enforced when set: GITHUB_ALLOWED_REPOS narrows
      what agents can read even if the token has broader access
  N3. Query validator rejects DDL/DML keywords (defense-in-depth even
      though GitHub search doesn't execute SQL)
  N4. Path traversal blocked (.., /etc/, null bytes)
  N5. Live-or-stub pattern; agents see available:False on missing token
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SERVER = REPO / "mcp" / "server_github.py"
INFERENCE_MAIN = REPO / "services" / "inference-svc" / "app" / "main.py"

GREEN = "\033[32m"
RED = "\033[31m"
BOLD = "\033[1m"
NC = "\033[0m"


def step(t: str) -> None:
    print(f"\n{BOLD}── {t} ──{NC}")


def ok(m: str) -> None:
    print(f"  {GREEN}✓ {m}{NC}")


def fail(m: str) -> None:
    print(f"  {RED}✗ {m}{NC}")
    raise SystemExit(1)


def main() -> int:
    if not SERVER.exists():
        fail(f"missing: {SERVER.relative_to(REPO)}")
    if not INFERENCE_MAIN.exists():
        fail(f"missing: {INFERENCE_MAIN.relative_to(REPO)}")

    src = SERVER.read_text(encoding="utf-8")
    inf_src = INFERENCE_MAIN.read_text(encoding="utf-8")

    sys.path.insert(0, str(REPO))
    try:
        from mcp import server_github as mod  # type: ignore[import-not-found]
    except Exception as exc:  # noqa: BLE001
        fail(f"server module failed to import: {exc}")

    # ------------------------------------------------------------------
    # Step 1 — POSITIVE: canonical structure
    # ------------------------------------------------------------------
    step("1. server_github.py has canonical structure")
    for marker in ("TOOLS", "_validate_repo_slug", "_validate_path",
                   "_validate_query", "_allowed_repos", "_live_or_stub"):
        if marker not in src:
            fail(f"server missing canonical symbol: {marker}")
    ok("source has TOOLS + 4 validators + allow-list + _live_or_stub")

    # ------------------------------------------------------------------
    # Step 2 — POSITIVE: 6 expected tool names
    # ------------------------------------------------------------------
    step("2. TOOLS list has all 6 expected tool names")
    expected = (
        "github.repo_get_file",
        "github.pr_lookup",
        "github.pr_search",
        "github.issue_lookup",
        "github.issue_search",
        "github.code_search",
    )
    missing = [t for t in expected if f'"name": "{t}"' not in src]
    if missing:
        fail(f"TOOLS missing: {missing}")
    ok(f"all {len(expected)} GitHub tools advertised")

    # ------------------------------------------------------------------
    # Step 3 — POSITIVE: all read-only with github:read scope
    # ------------------------------------------------------------------
    step("3. all 6 tools side_effects='read' + scope='github:read'")
    read_count = src.count('"side_effects": "read"')
    if read_count != len(expected):
        fail(f"expected {len(expected)} read tools; got {read_count}")
    if src.count('"github:read"') < len(expected):
        fail("not every tool requires 'github:read' scope")
    ok(f"{len(expected)} read tools / 0 write tools / uniform scope")

    # ------------------------------------------------------------------
    # Step 4 — POSITIVE: repo slug regex
    # ------------------------------------------------------------------
    step("4. _validate_repo_slug accepts canonical owner/name")
    good_slugs = ("anthropic/claude-code", "user/repo", "OrgX/Repo.Name")
    for slug in good_slugs:
        if mod._validate_repo_slug(slug) != slug:
            fail(f"repo slug {slug!r} unexpectedly rejected")
    ok(f"{len(good_slugs)} canonical slugs accepted")

    # ------------------------------------------------------------------
    # Step 5 — POSITIVE: path validator accepts canonical paths
    # ------------------------------------------------------------------
    step("5. _validate_path accepts canonical paths")
    good_paths = ("README.md", "src/foo/bar.py", "a-b_c.tsx")
    for p in good_paths:
        if mod._validate_path(p) != p:
            fail(f"canonical path {p!r} unexpectedly rejected")
    ok("canonical paths accepted")

    # ------------------------------------------------------------------
    # Step 6 — POSITIVE: inference-svc wires DOCUMIND_MCP_GITHUB_URL
    # ------------------------------------------------------------------
    step("6. inference-svc mcp_spec wires DOCUMIND_MCP_GITHUB_URL")
    if "DOCUMIND_MCP_GITHUB_URL" not in inf_src:
        fail("inference-svc missing DOCUMIND_MCP_GITHUB_URL hook")
    if not re.search(r'\(\s*"github"\s*,\s*os\.getenv\("DOCUMIND_MCP_GITHUB_URL"', inf_src):
        fail("inference-svc mcp_spec doesn't have ('github', getenv(...)) tuple")
    ok("inference-svc wired with empty default (operator opt-in)")

    # ------------------------------------------------------------------
    # Step 7 — NEGATIVE: 0 write tools
    # ------------------------------------------------------------------
    step("7. NEGATIVE: 0 write tools (Stage-1 read-only)")
    write_count = src.count('"side_effects": "write"')
    if write_count != 0:
        fail(f"server has {write_count} write tool(s) — Stage-1 lock broken")
    ok("0 write tools (PR comment / issue create / merge ship separately)")

    # ------------------------------------------------------------------
    # Step 8 — NEGATIVE: repo allow-list enforced when set
    # ------------------------------------------------------------------
    step("8. NEGATIVE: GITHUB_ALLOWED_REPOS narrows reachable repos")
    import os as _os  # noqa: PLC0415
    saved = _os.environ.pop("GITHUB_ALLOWED_REPOS", None)
    try:
        # With allow-list set to one repo, others must 403
        _os.environ["GITHUB_ALLOWED_REPOS"] = "approved/repo"
        try:
            mod._validate_repo_slug("other/repo")
            fail("repo outside allow-list wrongly accepted")
        except Exception as exc:
            detail = getattr(exc, "detail", {})
            if not (isinstance(detail, dict) and detail.get("code") == "repo_not_allowed"):
                fail(f"wrong error code; got {detail}")
        # Allow-listed repo passes
        if mod._validate_repo_slug("approved/repo") != "approved/repo":
            fail("allow-listed repo wrongly rejected")
    finally:
        _os.environ.pop("GITHUB_ALLOWED_REPOS", None)
        if saved is not None:
            _os.environ["GITHUB_ALLOWED_REPOS"] = saved
    ok("allow-list enforced; non-allow-listed repos return 403")

    # ------------------------------------------------------------------
    # Step 9 — NEGATIVE: DDL/DML in query rejected
    # ------------------------------------------------------------------
    step("9. NEGATIVE: query validator rejects DDL/DML keywords")
    # GitHub search rejects WRITE-shape keywords (DROP/DELETE/INSERT/
    # UPDATE/TRUNCATE/EXECUTE/UNION). Read-shape keywords like SELECT
    # are allowed — they're legitimate search terms in a code repo.
    bad_queries = (
        "DROP TABLE users",
        "test DELETE pattern",
        "INSERT INTO foo",
        "x UNION y",
        "TRUNCATE TABLE x",
    )
    rejections = 0
    for q in bad_queries:
        try:
            mod._validate_query(q)
            fail(f"query validator wrongly accepted: {q!r}")
        except Exception:
            rejections += 1
    if rejections != len(bad_queries):
        fail(f"only {rejections}/{len(bad_queries)} bad queries rejected")
    ok(f"all {len(bad_queries)} DDL/DML-shaped queries rejected")

    # ------------------------------------------------------------------
    # Step 10 — NEGATIVE: path traversal blocked
    # ------------------------------------------------------------------
    step("10. NEGATIVE: path traversal blocked (../, leading /, null bytes)")
    bad_paths = (
        "../etc/passwd",
        "/etc/passwd",
        "src/../../../secret",
        "file\x00.txt",
        "x" * 600,  # over length cap
    )
    rejections = 0
    for p in bad_paths:
        try:
            mod._validate_path(p)
            fail(f"path validator wrongly accepted: {p[:30]!r}")
        except Exception:
            rejections += 1
    if rejections != len(bad_paths):
        fail(f"only {rejections}/{len(bad_paths)} traversal attempts blocked")
    ok(f"all {len(bad_paths)} path-traversal attempts blocked")

    # ------------------------------------------------------------------
    # Step 11 — NEGATIVE: live_or_stub pattern; available:False shape
    # ------------------------------------------------------------------
    step("11. NEGATIVE: missing GITHUB_TOKEN → available:False shape")
    saved = _os.environ.pop("GITHUB_TOKEN", None)
    try:
        result = mod._pr_lookup_impl({"repo": "anthropic/claude-code", "number": 1})
        if result.get("available") is not False:
            fail(f"missing token didn't yield available:False; got {result}")
        if "GITHUB_TOKEN" not in result.get("reason", ""):
            fail(f"reason should mention GITHUB_TOKEN; got {result.get('reason')!r}")
    finally:
        if saved is not None:
            _os.environ["GITHUB_TOKEN"] = saved
    ok("missing token → available:False with explanatory reason")

    print(f"\n{GREEN}{BOLD}ALL 11 STEPS PASSED (6 positive + 5 negative){NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
