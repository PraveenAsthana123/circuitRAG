#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: every doc cited in a `Composes with` section exists on disk.

Several operator-facing docs end with a `## Composes with` footer that
links the current document to policy, ADR, and runbook context. Those
footers are useful only if the cited docs are real. This drill locks
that contract without caring about UI routes or other non-doc prose.

  1. discover markdown files that contain a `## Composes with` section
  2. NEGATIVE: every discovered file yields at least one backticked
     reference in the compose footer
  3. NEGATIVE: every cited doc path resolves on disk
  4. NEGATIVE: any cited doc glob/range matches at least one real doc
  5. NEGATIVE: every resolved cited-doc target is a markdown / policy
     doc file
  6. POSITIVE: emit exact source -> target mappings for drift debugging

Run: python3 mcp/tests/drill_composes_with_docs_exist.py
"""
from __future__ import annotations

import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
DOCS = REPO / "docs"
HOME = pathlib.Path.home()
MARKDOWN_GLOBS = ("*.md", "*.mdx")

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


def _compose_section(text: str) -> str:
    match = re.search(r"^## Composes with\s*$([\s\S]*?)(?=^## |\Z)", text, re.MULTILINE)
    return match.group(1).strip() if match else ""


def _extract_doc_refs(section: str) -> list[str]:
    refs: list[str] = []
    for token in re.findall(r"`([^`]+)`", section):
        if "/" not in token and not token.endswith(".md"):
            continue
        if token.startswith("/admin/"):
            continue
        if ".md" in token or ".mdx" in token or token.endswith("CLAUDE.md"):
            refs.append(token)
    return refs


def _extract_all_refs(section: str) -> list[str]:
    return [token for token in re.findall(r"`([^`]+)`", section) if "/" in token]


def _resolve_ref(raw: str) -> list[pathlib.Path]:
    ref = raw.strip()
    if ref.startswith("~/"):
        expanded = HOME / ref[2:]
    elif ref.startswith("/"):
        expanded = pathlib.Path(ref)
    else:
        expanded = REPO / ref

    # Support the retrospective shorthand `014..019-*.md`.
    range_match = re.search(r"/(\d{3})\.\.(\d{3})-\*\.md$", str(expanded))
    if range_match:
        start = int(range_match.group(1))
        end = int(range_match.group(2))
        parent = expanded.parent
        matches: list[pathlib.Path] = []
        for n in range(start, end + 1):
            matches.extend(sorted(parent.glob(f"{n:03d}-*.md")))
        return matches

    if any(ch in str(expanded) for ch in "*?[]"):
        return sorted(expanded.parent.glob(expanded.name))

    return [expanded]


def main() -> int:
    step("1. discover markdown files with a `Composes with` section")
    sources = sorted(
        path for glob in MARKDOWN_GLOBS for path in DOCS.rglob(glob)
        if "## Composes with" in path.read_text()
    )
    if not sources:
        fail("no markdown files with a `Composes with` section found")
    ok(f"found {len(sources)} docs with compose footers")

    step("2. NEGATIVE: every discovered file yields at least one backticked reference")
    sections = {path: _compose_section(path.read_text()) for path in sources}
    all_refs = {path: _extract_all_refs(section) for path, section in sections.items()}
    extracted = {path: _extract_doc_refs(section) for path, section in sections.items()}
    missing_refs = [str(path.relative_to(REPO)) for path, refs in all_refs.items() if not refs]
    if missing_refs:
        fail(f"compose footer has no backticked refs: {missing_refs}")
    ok("every compose footer yields at least one backticked reference")

    step("3. NEGATIVE: every referenced path resolves on disk")
    unresolved: list[str] = []
    resolved_pairs: list[tuple[str, str]] = []
    for source, refs in extracted.items():
        for raw in refs:
            matches = _resolve_ref(raw)
            if not matches or not all(path.exists() for path in matches):
                unresolved.append(f"{source.relative_to(REPO)} -> {raw}")
                continue
            for match in matches:
                resolved_pairs.append((str(source.relative_to(REPO)), str(match)))
    if unresolved:
        fail(f"unresolved compose refs: {unresolved}")
    ok(f"resolved {len(resolved_pairs)} source -> target mappings")

    step("4. NEGATIVE: any glob/range reference matches at least one real doc")
    empty_patterns: list[str] = []
    for source, refs in extracted.items():
        for raw in refs:
            if ".." not in raw and not any(ch in raw for ch in "*?[]"):
                continue
            matches = _resolve_ref(raw)
            if not matches:
                empty_patterns.append(f"{source.relative_to(REPO)} -> {raw}")
    if empty_patterns:
        fail(f"compose globs/ranges matched nothing: {empty_patterns}")
    ok("every glob/range reference matches at least one doc")

    step("5. NEGATIVE: every resolved target is a markdown / policy doc file")
    bad_targets = []
    for source, target in resolved_pairs:
        path = pathlib.Path(target)
        if path.suffix not in {".md", ".mdx"}:
            bad_targets.append(f"{source} -> {target}")
    if bad_targets:
        fail(f"non-doc targets found in compose footer: {bad_targets}")
    ok("all resolved compose targets are markdown/policy docs")

    step("6. POSITIVE: exact mappings are emitted for drift debugging")
    for source, target in resolved_pairs:
        print(f"  {source} -> {target}")
    ok("exact mappings printed")

    print(f"\n{BOLD}{GREEN}{'=' * 50}{NC}")
    print(f"{BOLD}{GREEN}  ALL 6 COMPOSES-WITH DOC STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}  (4 negative assertions: 2, 3, 4, 5){NC}")
    print(f"{BOLD}{GREEN}{'=' * 50}{NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
