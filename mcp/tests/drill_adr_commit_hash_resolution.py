#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: every ADR commit-hash reference resolves via git rev-parse.

Per §47.3 ADRs are immutable references; their References tables
cite specific commits (e.g. "Phase 6F | `1fac9b1` | ADR-015"). If
those commits get rebased away, force-pushed over, or otherwise
rewritten, the ADR ends up pointing into a void — operator can't
trace the architectural decision back to actual code.

This drill walks every `docs/architecture/adr/*.md`, extracts every
backtick-quoted hex hash of length ≥7 (the standard git short-hash
shape), and verifies each resolves via `git rev-parse --verify
<hash>^{commit}`. Catches drift before operators hit it during a
post-incident archeology session.

Eight steps. Six negative assertions.

  1. POSITIVE: ADR directory exists with ≥10 ADRs (sanity — the
     repo isn't empty; the drill has something to check).
  2. NEGATIVE: every backtick-hex-7+ hash resolves via git rev-parse.
     If any doesn't, the ADR points to a non-existent commit (rebase
     drift, force-push damage, or typo).
  3. NEGATIVE: bogus hash "deadbeefcafe1" does NOT resolve. Sanity
     check the resolution mechanism — without this, a regex bug
     could silently report all-green.
  4. NEGATIVE: ADRs WITH a "## References" section cite ≥1 commit
     hash. An ADR with References as a section but zero commit
     citations is a structural smell (the section exists for a
     reason; populate it).
  5. NEGATIVE: ADR-014 + ADR-015 each cite ≥1 commit (these are
     the autonomous-loop session's load-bearing ADRs; both have
     References tables that must connect to the actual commits
     that landed the architecture).
  6. NEGATIVE: ADRs are sequentially numbered with no gaps. Per
     §47.3 ADR numbering is monotonic + gap-free; missing 008 (or
     having 008 after 014) means architectural decisions got
     dropped or reordered without operator awareness.
  7. NEGATIVE: non-hash backtick strings (e.g. `KNOWN_MISSING`,
     `iso_week`) do NOT match the hash regex. The pattern must
     be tight enough to avoid false positives that would confuse
     the rev-parse step.
  8. POSITIVE: end-to-end — sample the most recently committed
     hash from any ADR, verify it appears in `git log --all`
     output (defense-in-depth: rev-parse passes for short-hash
     prefixes; log-output catch confirms the actual commit).

Run: python3 mcp/tests/drill_adr_commit_hash_resolution.py
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ADR_DIR = REPO / "docs" / "architecture" / "adr"

# Backtick-quoted hex string of 7-12 chars. Tight enough to avoid
# false positives on words like `iso_week` or `KNOWN_MISSING`. The
# 7-char minimum is git's standard short-hash length; 12 is the
# longest a sensible operator would write inline.
_HASH_RE = re.compile(r"`([0-9a-f]{7,12})`")


def _git_resolves(hash_str: str) -> bool:
    """Return True if `git rev-parse --verify <hash>^{commit}`
    succeeds — i.e. the hash unambiguously identifies a commit
    in the local repo."""
    rc = subprocess.call(
        ["git", "rev-parse", "--verify", f"{hash_str}^{{commit}}"],
        cwd=str(REPO),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return rc == 0


def main() -> int:
    # ── Step 1: POSITIVE — ADR dir + count ──
    if not ADR_DIR.exists():
        print(f"✗ step 1: {ADR_DIR} missing")
        return 1
    # Only NNN-*.md files; skip README.md and other meta files in the dir.
    adrs = sorted(
        p for p in ADR_DIR.glob("*.md")
        if re.match(r"^\d{3}-", p.name)
    )
    if len(adrs) < 10:
        print(f"✗ step 1: only {len(adrs)} ADRs found, expected ≥10")
        return 1
    print(f"✓ step 1: {len(adrs)} ADRs found in canonical dir")

    # ── Step 2: NEGATIVE — every hash resolves ──
    broken = []
    total_hashes = 0
    for adr in adrs:
        body = adr.read_text()
        hashes = set(_HASH_RE.findall(body))
        for h in hashes:
            total_hashes += 1
            if not _git_resolves(h):
                broken.append((adr.name, h))
    if broken:
        print(f"✗ step 2: {len(broken)} ADR commit refs don't resolve "
              f"(rebase / force-push / typo drift): {broken[:3]}")
        return 1
    print(f"✓ step 2: all {total_hashes} backtick-hashes resolve via git rev-parse")

    # ── Step 3: NEGATIVE — bogus hash sanity check ──
    if _git_resolves("deadbeefcafe1"):
        print("✗ step 3: bogus hash 'deadbeefcafe1' resolved; resolution "
              "mechanism broken — step 2's all-green is meaningless")
        return 1
    print("✓ step 3: bogus hash correctly fails to resolve (mechanism honest)")

    # ── Step 4: NEGATIVE — ADRs with References cite ≥1 commit ──
    refless = []
    for adr in adrs:
        body = adr.read_text()
        if "## References" not in body:
            continue  # ADR may legitimately have no References section
        # Extract just the References section (multi-line; until
        # next ## heading or EOF)
        m = re.search(r"## References(.*?)(?=\n## |\Z)", body, re.DOTALL)
        refs_text = m.group(1) if m else ""
        if not _HASH_RE.search(refs_text):
            refless.append(adr.name)
    if refless:
        print(f"✗ step 4: {len(refless)} ADRs have ## References but zero "
              f"commit citations: {refless}")
        return 1
    print(f"✓ step 4: every ADR with ## References cites ≥1 commit")

    # ── Step 5: NEGATIVE — ADR-014 + ADR-015 each have ≥1 hash ──
    session_adrs = ["014-autonomous-loop-architecture.md",
                    "015-ratchet-pattern-for-discipline-drift.md"]
    for name in session_adrs:
        path = ADR_DIR / name
        if not path.exists():
            print(f"✗ step 5: session ADR {name} missing")
            return 1
        body = path.read_text()
        hashes = set(_HASH_RE.findall(body))
        if len(hashes) < 1:
            print(f"✗ step 5: {name} cites zero commits; load-bearing "
                  "ADRs must connect to landed code")
            return 1
    print(f"✓ step 5: ADR-014 + ADR-015 both cite commits "
          "(architectural lineage preserved)")

    # ── Step 6: NEGATIVE — sequential numbering, no gaps ──
    # Per §47.3 ADR numbering is monotonic + gap-free. Missing 008
    # (or 014 jumping to 016) means an architectural decision got
    # dropped or never landed; operators reviewing the catalog by
    # number wouldn't see the gap.
    numbers = []
    for adr in adrs:
        m = re.match(r"^(\d{3})-", adr.name)
        if not m:
            print(f"✗ step 6: ADR filename {adr.name!r} doesn't match NNN-* shape")
            return 1
        numbers.append(int(m.group(1)))
    numbers.sort()
    expected = list(range(numbers[0], numbers[-1] + 1))
    if numbers != expected:
        gaps = sorted(set(expected) - set(numbers))
        print(f"✗ step 6: ADR numbering has gaps: missing {gaps}")
        return 1
    print(f"✓ step 6: ADRs sequentially numbered {numbers[0]:03d}..{numbers[-1]:03d} "
          "(no gaps)")

    # ── Step 7: NEGATIVE — non-hash backtick strings excluded ──
    non_hash_examples = ["KNOWN_MISSING", "iso_week", "ADR-014",
                         "council_runs", "main"]
    false_positives = [s for s in non_hash_examples if _HASH_RE.match(f"`{s}`")]
    if false_positives:
        print(f"✗ step 7: regex false-positives on {false_positives}; "
              "would confuse step 2's rev-parse check")
        return 1
    print(f"✓ step 7: regex correctly rejects {len(non_hash_examples)} "
          "non-hash backtick strings")

    # ── Step 8: POSITIVE — sample resolves in git log ──
    # Pick any hash from ADR-015 (newest). Confirm it appears in
    # `git log --oneline --all`. Defense in depth: rev-parse passes
    # for prefixes; log-grep confirms the commit truly exists.
    adr_015 = (ADR_DIR / "015-ratchet-pattern-for-discipline-drift.md").read_text()
    sample_hashes = list(set(_HASH_RE.findall(adr_015)))
    if not sample_hashes:
        print("✗ step 8: ADR-015 has no hashes to sample")
        return 1
    sample = sample_hashes[0]
    log_out = subprocess.run(
        ["git", "log", "--oneline", "--all"],
        cwd=str(REPO), capture_output=True, text=True, timeout=10.0,
    )
    if log_out.returncode != 0:
        print(f"✗ step 8: git log failed: {log_out.stderr}")
        return 1
    if sample not in log_out.stdout:
        print(f"✗ step 8: hash {sample!r} resolves via rev-parse but "
              "doesn't appear in git log --all (orphaned ref?)")
        return 1
    print(f"✓ step 8: end-to-end — hash {sample!r} found in git log --all")

    print("\nALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
