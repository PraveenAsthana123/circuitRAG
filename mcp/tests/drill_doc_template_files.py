# RESOURCES: readonly
"""
Drill: skeleton + prompt template files exist for all 20 doc types.

Per CLAUDE.md §43 (drill discipline; ≥3 negatives), §44 (autonomous-loop
ONE-thing-per-iter; iter-70 is the iter-69 follow-up — registry referenced
40 files; iter-70 ships them), §45.4 (no checkbox flips without code),
§47 + ADR-029 §Iter-by-iter.

Iter-69 shipped registry.yaml referencing 40 paths
(20 skeleton + 20 prompt). Iter-70 ships the files at those paths.
This drill verifies registry-vs-filesystem consistency.

Locks (positive):
  L1. All 40 files exist (one skeleton + one prompt per doc type)
  L2. Each skeleton has all 8 standard sections (Metadata / Use-Case /
      Doc-Specific / KPI Scoring / Reviewer Sign-Offs / Inter-Dept
      Feedback / Revision History / Approval)
  L3. Each prompt references the doc's owner_role + reviewer_roles
  L4. Each prompt cites the §38 governance hard constraints
      (no invented stakeholders / no invented regulators)

Locks (negative — ≥3 per §43):
  N1. Every registry path resolves to an existing non-empty file
      (catches a registry typo OR a builder-script regression)
  N2. Skeleton has NO 'TBD' / 'TODO' tokens in headings (TBD/TODO
      means the section is unspecified; reviewer can't score it)
  N3. Skeleton min_kpi placeholder rendered as concrete percent
      (a literal `{min_kpi}` left in the file means the format-string
      didn't fire — would surface in production as a confused reviewer)
  N4. Each prompt cites at LEAST 1 ADR (provenance lock; the prompt
      should ground the doc in the existing architecture)
  N5. Each skeleton's `Revision History` table has a header row but
      NO data rows (revision history starts empty; the LLM appends)
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

from doc_framework_registry import load_registry  # noqa: E402

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
    reg = load_registry()
    if len(reg.docs) != 20:
        fail(f"registry has {len(reg.docs)} docs; expected 20")

    # ------------------------------------------------------------------
    # Step 1 — POSITIVE: all 40 files exist
    # ------------------------------------------------------------------
    step("1. all 40 files exist (20 skeletons + 20 prompts)")
    missing: list[str] = []
    for d in reg.docs:
        for path_attr in ("template_path", "prompt_path"):
            p = REPO / getattr(d, path_attr)
            if not p.exists() or not p.is_file():
                missing.append(str(p.relative_to(REPO)))
    if missing:
        fail(f"{len(missing)} missing: {missing[:3]}")
    ok(f"all {len(reg.docs) * 2} files present")

    # ------------------------------------------------------------------
    # Step 2 — POSITIVE: each skeleton has 8 standard sections
    # ------------------------------------------------------------------
    step("2. each skeleton has all 8 standard sections")
    standard_sections = (
        "## 1. Metadata",
        "## 2. Business Use-Case",
        "## 3. Doc-Specific Sections",
        "## 4. KPI Scoring",
        "## 5. Reviewer Sign-Offs",
        "## 6. Inter-Department Feedback",
        "## 7. Revision History",
        "## 8. Approval",
    )
    for d in reg.docs:
        src = (REPO / d.template_path).read_text(encoding="utf-8")
        for sec in standard_sections:
            if sec not in src:
                fail(f"{d.doc_type}: skeleton missing section header {sec!r}")
    ok(f"all 20 skeletons have all 8 standard section headers")

    # ------------------------------------------------------------------
    # Step 3 — POSITIVE: each prompt references owner + reviewer roles
    # ------------------------------------------------------------------
    step("3. each prompt references the doc's owner + all reviewer roles")
    for d in reg.docs:
        src = (REPO / d.prompt_path).read_text(encoding="utf-8")
        if d.owner_role not in src:
            fail(f"{d.doc_type}: prompt doesn't reference owner_role {d.owner_role!r}")
        for r in d.reviewer_roles:
            if r not in src:
                fail(f"{d.doc_type}: prompt doesn't reference reviewer {r!r}")
    ok("all 20 prompts reference owner + reviewer roles")

    # ------------------------------------------------------------------
    # Step 4 — POSITIVE: each prompt cites §38 governance hard constraints
    # ------------------------------------------------------------------
    step("4. each prompt cites §38 governance constraints")
    for d in reg.docs:
        src = (REPO / d.prompt_path).read_text(encoding="utf-8")
        if "§38" not in src:
            fail(f"{d.doc_type}: prompt doesn't cite §38 governance")
        # Hard-constraint phrases reviewers can grep for
        if "DO NOT invent" not in src:
            fail(
                f"{d.doc_type}: prompt missing 'DO NOT invent' constraint "
                f"(prevents hallucinated stakeholders / regulators)"
            )
    ok("all 20 prompts cite §38 + hard constraints")

    # ------------------------------------------------------------------
    # Step 5 — NEGATIVE: registry path → existing non-empty file
    # ------------------------------------------------------------------
    step("5. NEGATIVE: every registry path → existing non-empty file")
    empties: list[str] = []
    for d in reg.docs:
        for path_attr in ("template_path", "prompt_path"):
            p = REPO / getattr(d, path_attr)
            if p.exists() and p.stat().st_size < 200:
                empties.append(f"{p.relative_to(REPO)} ({p.stat().st_size}B)")
    if empties:
        fail(f"empty/tiny files (likely format-string failure): {empties[:3]}")
    ok("all 40 files are ≥200B (real content rendered)")

    # ------------------------------------------------------------------
    # Step 6 — NEGATIVE: no TBD/TODO in skeleton section headings
    # ------------------------------------------------------------------
    step("6. NEGATIVE: skeletons have no TBD/TODO in section headings")
    bad: list[str] = []
    for d in reg.docs:
        src = (REPO / d.template_path).read_text(encoding="utf-8")
        # Section headings only — skip the body (TBD/TODO inside body
        # is fine; the LLM fills it in)
        for line in src.splitlines():
            if line.startswith("###") and ("TBD" in line or "TODO" in line):
                bad.append(f"{d.doc_type}: {line.strip()[:80]}")
                break
    if bad:
        fail(f"skeletons with TBD/TODO in headings: {bad[:3]}")
    ok("no TBD/TODO in skeleton section headings (all sections are concrete)")

    # ------------------------------------------------------------------
    # Step 7 — NEGATIVE: format-string placeholders fully rendered
    # ------------------------------------------------------------------
    step("7. NEGATIVE: skeleton format-string placeholders rendered")
    # Look for any {min_kpi} / {display_name} / {owner_role} that
    # leaked through — would mean the format-string didn't fire.
    leaked: list[str] = []
    for d in reg.docs:
        src = (REPO / d.template_path).read_text(encoding="utf-8")
        for placeholder in ("{min_kpi}", "{display_name}", "{owner_role}",
                            "{reviewer_roles}", "{sections}", "{kpi_table}"):
            if placeholder in src:
                leaked.append(f"{d.doc_type}: {placeholder}")
    if leaked:
        fail(f"unrendered placeholders: {leaked[:3]}")
    ok("all format-string placeholders fully rendered")

    # ------------------------------------------------------------------
    # Step 8 — NEGATIVE: each prompt cites ≥1 ADR
    # ------------------------------------------------------------------
    step("8. NEGATIVE: each prompt cites ≥1 ADR (provenance lock)")
    import re  # noqa: PLC0415
    for d in reg.docs:
        src = (REPO / d.prompt_path).read_text(encoding="utf-8")
        if not re.search(r"ADR-\d{3}", src):
            fail(f"{d.doc_type}: prompt cites no ADR")
    ok("all 20 prompts cite at least one ADR")

    # ------------------------------------------------------------------
    # Step 9 — NEGATIVE: revision history starts empty
    # ------------------------------------------------------------------
    step("9. NEGATIVE: each skeleton's Revision History starts empty")
    for d in reg.docs:
        src = (REPO / d.template_path).read_text(encoding="utf-8")
        # Find the Revision History section + its table
        rev_idx = src.find("## 7. Revision History")
        if rev_idx == -1:
            fail(f"{d.doc_type}: missing Revision History section")
        approval_idx = src.find("## 8.", rev_idx)
        rev_block = src[rev_idx:approval_idx if approval_idx > 0 else len(src)]
        # Header row is `| Version |...` — that's allowed.
        # Data rows would be like `| v1 |...` — must be 0.
        # Check by counting `|` rows that aren't header/separator.
        data_rows = [
            ln for ln in rev_block.splitlines()
            if ln.strip().startswith("|")
            and not ln.strip().startswith("| Version")
            and not ln.strip().startswith("|---")
            and "|" in ln.strip()[1:]
        ]
        if data_rows:
            fail(
                f"{d.doc_type}: Revision History has data rows in skeleton: "
                f"{data_rows[:1]}"
            )
    ok("all 20 skeletons start with empty Revision History (LLM appends)")

    print(f"\n{GREEN}{BOLD}ALL 9 STEPS PASSED (4 positive + 5 negative; 40 files){NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
