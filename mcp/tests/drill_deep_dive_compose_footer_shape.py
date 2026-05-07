#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: every services/frontend/app/admin/*/deep/page.tsx ships a
§49-compliant compose footer.

CLAUDE.md §49 declares the compose-footer pattern: every deep-dive
page must end with a `<DeepDiveCrossRefs refs={[...]} />` panel
listing 3-7 entries that name this page's closest neighbours, each
with a one-sentence WHY.

The companion drill drill_composes_with_docs_exist (Phase 6Y, b7fdf8f)
locks the same contract for markdown DOCS that have a `## Composes
with` section. This drill locks the same idea at the TSX page level:
component imported, component rendered, refs array between 3 and 7,
each ref carries href+label+why, no self-links, no relative paths.

Eight steps. Six negative assertions.

  1. POSITIVE: discover every deep-dive page; require at least 30
     pages so the drill can't trivially pass by deleting the
     directory.
  2. NEGATIVE: every page imports DeepDiveCrossRefs. Without the
     import, the JSX use is a build error.
  3. NEGATIVE: every page renders <DeepDiveCrossRefs ... refs={...}>.
     Importing the component but not rendering it ships dead code.
  4. NEGATIVE: every footer's refs array contains between 3 and 7
     entries (the §49 cap on either end). 0-2 = leaf node;
     8+ = link soup.
  5. NEGATIVE: every ref entry carries all three required keys
     (href, label, why). The WHY is the §49 contract — without it
     the entry is unfindable in the dependency graph.
  6. NEGATIVE: no ref href self-links to the current page's own
     /admin/<topic>/deep route. Self-links waste a slot.
  7. NEGATIVE: every ref href starts with '/' (an absolute admin
     route). Relative paths break Next.js Link routing on deep
     pages.
  8. POSITIVE: emit per-page entry count for drift visibility (so
     operators can spot pages drifting toward the 7-entry cap).

Run: python3 mcp/tests/drill_deep_dive_compose_footer_shape.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEEP_GLOB = "services/frontend/app/admin/*/deep/page.tsx"

# Floor: drills shouldn't trivially pass by deleting the directory.
# The current count is 35; we set the floor to 30 to allow legitimate
# consolidation while still requiring substantive coverage.
MIN_PAGES = 30
MIN_REFS = 3
MAX_REFS = 7

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


def _topic_route(page_path: Path) -> str:
    """For services/frontend/app/admin/<topic>/deep/page.tsx return
    /admin/<topic>/deep. Used to detect self-links."""
    parts = page_path.parts
    # Find 'admin' anchor and walk forward.
    if "admin" not in parts:
        return ""
    i = parts.index("admin")
    # parts[i+1] = topic (or topic-prefix); deep is parts[-2]
    if i + 2 >= len(parts):
        return ""
    topic = "/".join(parts[i + 1 : -1])
    return f"/admin/{topic}"


def _refs_block(body: str) -> str:
    """Return the source between the first refs={[ and its matching ]}.

    The block may contain nested braces and quoted strings with braces;
    we use a depth counter that respects backtick / single / double
    quotes so we don't bail early on `Foo { bar }` inside a string.
    """
    m = re.search(r"refs=\{\[", body)
    if not m:
        return ""
    start = m.end()
    depth = 1  # we just consumed the opening "["; track []
    brace_depth = 0  # track {} nesting separately
    i = start
    in_str: str | None = None
    while i < len(body):
        ch = body[i]
        prev = body[i - 1] if i > 0 else ""
        if in_str:
            # Inside a string; only the matching delimiter (unescaped) closes it.
            if ch == in_str and prev != "\\":
                in_str = None
        else:
            if ch in ("'", '"', "`"):
                in_str = ch
            elif ch == "{":
                brace_depth += 1
            elif ch == "}":
                brace_depth -= 1
            elif ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    return body[start:i]
        i += 1
    return ""  # unterminated


def _entries(refs_block: str) -> list[str]:
    """Split refs block into individual entry strings (one per
    object literal). Returns the inner content of each `{ ... }`
    object, brace-balanced and string-aware."""
    entries: list[str] = []
    i = 0
    while i < len(refs_block):
        ch = refs_block[i]
        if ch == "{":
            # Walk to matching closing brace, respecting strings.
            depth = 1
            j = i + 1
            in_str: str | None = None
            while j < len(refs_block) and depth > 0:
                cj = refs_block[j]
                pj = refs_block[j - 1] if j > 0 else ""
                if in_str:
                    if cj == in_str and pj != "\\":
                        in_str = None
                else:
                    if cj in ("'", '"', "`"):
                        in_str = cj
                    elif cj == "{":
                        depth += 1
                    elif cj == "}":
                        depth -= 1
                j += 1
            if depth == 0:
                entries.append(refs_block[i + 1 : j - 1])
            i = j
        else:
            i += 1
    return entries


def _href_value(entry: str) -> str | None:
    """Extract the href value from an entry string. Returns None
    when missing; returns the raw quoted-content otherwise."""
    m = re.search(
        r"href:\s*"
        r"(?:'((?:\\.|[^'\\])*)'"
        r"|\"((?:\\.|[^\"\\])*)\")",
        entry,
        re.DOTALL,
    )
    if not m:
        return None
    return m.group(1) if m.group(1) is not None else m.group(2)


def main() -> int:
    step("1. POSITIVE: discover deep-dive pages (>= MIN_PAGES floor)")
    pages = sorted(REPO.glob(DEEP_GLOB))
    if len(pages) < MIN_PAGES:
        fail(
            f"only {len(pages)} deep-dive pages discovered; "
            f"floor is {MIN_PAGES}. Drill cannot pass trivially "
            "by deleting the admin/* directory."
        )
    ok(f"discovered {len(pages)} deep-dive pages")

    page_bodies = {p: p.read_text() for p in pages}

    step("2. NEGATIVE: every page imports DeepDiveCrossRefs")
    missing_import = [
        p.relative_to(REPO)
        for p, body in page_bodies.items()
        if "import DeepDiveCrossRefs" not in body
    ]
    if missing_import:
        fail(
            f"{len(missing_import)} page(s) missing DeepDiveCrossRefs "
            f"import: {missing_import[:5]}"
        )
    ok(f"all {len(pages)} pages import DeepDiveCrossRefs")

    step("3. NEGATIVE: every page renders <DeepDiveCrossRefs ... refs={...}>")
    missing_render = [
        p.relative_to(REPO)
        for p, body in page_bodies.items()
        if "<DeepDiveCrossRefs" not in body
    ]
    if missing_render:
        fail(
            f"{len(missing_render)} page(s) imported but did not "
            f"render the component: {missing_render[:5]}"
        )
    missing_refs = [
        p.relative_to(REPO)
        for p, body in page_bodies.items()
        if "refs=" not in body
    ]
    if missing_refs:
        fail(
            f"{len(missing_refs)} page(s) render component without "
            f"refs prop: {missing_refs[:5]}"
        )
    ok(f"all {len(pages)} pages render DeepDiveCrossRefs with refs={{...}}")

    step("4. NEGATIVE: every footer has between MIN_REFS and MAX_REFS entries")
    out_of_bounds: list[tuple[str, int]] = []
    page_counts: dict[Path, int] = {}
    for p, body in page_bodies.items():
        block = _refs_block(body)
        if not block:
            out_of_bounds.append((str(p.relative_to(REPO)), 0))
            continue
        entries = _entries(block)
        n = len(entries)
        page_counts[p] = n
        if n < MIN_REFS or n > MAX_REFS:
            out_of_bounds.append((str(p.relative_to(REPO)), n))
    if out_of_bounds:
        fail(
            f"{len(out_of_bounds)} page(s) outside [{MIN_REFS},{MAX_REFS}] "
            f"refs: {out_of_bounds[:5]}"
        )
    ok(
        f"all {len(pages)} pages have refs count in "
        f"[{MIN_REFS},{MAX_REFS}]"
    )

    step("5. NEGATIVE: every ref entry has href + label + why")
    schema_violations: list[tuple[str, str]] = []
    for p, body in page_bodies.items():
        block = _refs_block(body)
        for entry in _entries(block):
            for required in ("href:", "label:", "why:"):
                if required not in entry:
                    schema_violations.append(
                        (str(p.relative_to(REPO)), required.rstrip(":"))
                    )
                    break
    if schema_violations:
        fail(
            f"{len(schema_violations)} entries missing required keys: "
            f"{schema_violations[:5]}"
        )
    ok("every ref entry has href + label + why")

    step("6. NEGATIVE: no ref href self-links to the current page's route")
    self_links: list[tuple[str, str]] = []
    for p, body in page_bodies.items():
        own_route = _topic_route(p)  # e.g. /admin/sidecar/deep
        block = _refs_block(body)
        for entry in _entries(block):
            href = _href_value(entry)
            if href is None:
                continue
            if href == own_route or href.startswith(own_route + "#"):
                self_links.append((str(p.relative_to(REPO)), href))
    if self_links:
        fail(
            f"{len(self_links)} self-links found "
            f"(refs to the page's own route): {self_links[:5]}"
        )
    ok(f"no self-links across {len(pages)} pages")

    step("7. NEGATIVE: every ref href starts with '/' (absolute admin route)")
    relative_paths: list[tuple[str, str]] = []
    for p, body in page_bodies.items():
        block = _refs_block(body)
        for entry in _entries(block):
            href = _href_value(entry)
            if href is None:
                continue
            if not href.startswith("/"):
                relative_paths.append((str(p.relative_to(REPO)), href))
    if relative_paths:
        fail(
            f"{len(relative_paths)} relative href(s) found "
            f"(must start with '/'): {relative_paths[:5]}"
        )
    ok("every href is an absolute path")

    step("8. POSITIVE: emit per-page entry count distribution")
    distribution: dict[int, int] = {}
    for n in page_counts.values():
        distribution[n] = distribution.get(n, 0) + 1
    bucket_summary = ", ".join(
        f"{n}refs:{distribution[n]}" for n in sorted(distribution)
    )
    ok(f"distribution across {len(pages)} pages — {bucket_summary}")

    print(f"\n{BOLD}{GREEN}{'=' * 50}{NC}")
    print(f"{BOLD}{GREEN}  ALL 8 COMPOSE-FOOTER-SHAPE STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}  (6 negative assertions: 2, 3, 4, 5, 6, 7){NC}")
    print(f"{BOLD}{GREEN}{'=' * 50}{NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
