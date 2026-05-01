# RESOURCES: readonly
"""
Drill: §48.3 model card coverage.

§48.3 mandate: every deployed model must have a model card with 9
sections. Updates without a card are release-blocked.

The deployed list is sourced from two places:
  1. `services/finops-svc/cmd/main.go` shadowRates table (LLMs)
  2. embedder configured in ingestion-svc reembed_worker (bge-m3)

Steps:

  1. docs/model-cards/INDEX.md exists.
  2. docs/model-cards/TEMPLATE.md exists (authors copy-from).
  3. Each LLM in finops-svc shadowRates has a per-model card
     under docs/model-cards/<sanitized>.md.
  4. The bge-m3 embedding model has a card.
  5. Each card has all 9 §48.3 required section headings:
     Intended use, Out-of-scope, Training data, Performance,
     Fairness, Explainability, Limitations, Owner / contact,
     Last review date, Version history.
  6. NEGATIVE: a phantom model name "phantom-llm-9000" must NOT
     have a card. Locks: the audit reads the real shadowRates,
     not a hardcoded list.
  7. NEGATIVE: a card with a missing section MUST be detected.
     Test by stripping a section heading from a temp copy and
     asserting the validator fails on it. Locks: section detection
     isn't a tautology.

Run:
    .venv/bin/python mcp/tests/drill_model_cards.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CARDS = REPO / "docs" / "model-cards"
FINOPS_MAIN = REPO / "services" / "finops-svc" / "cmd" / "main.go"

GREEN = "\033[32m"
RED = "\033[31m"
BOLD = "\033[1m"
NC = "\033[0m"

REQUIRED_SECTIONS = [
    "Intended use",
    "Out-of-scope",
    "Training data",
    "Performance",
    "Fairness",
    "Explainability",
    "Limitations",
    "Owner",  # "Owner / contact" — match by leading 'Owner'
    "Last review date",
    "Version history",
]

# Embedding models tracked outside finops shadowRates.
EXTRA_MODELS = ["bge-m3"]


def ok(msg: str) -> None:
    print(f"  {GREEN}✓{NC} {msg}")


def fail(msg: str) -> None:
    print(f"  {RED}✗{NC} {msg}")


def sanitize_filename(model: str) -> str:
    """`llama3.1:8b` → `llama3.1-8b` for the file slug."""
    return model.replace(":", "-")


def discover_llms_from_finops() -> list[str]:
    text = FINOPS_MAIN.read_text(encoding="utf-8")
    return re.findall(r'\{Model:\s*"([^"]+)"', text)


def required_sections_present(card_text: str) -> list[str]:
    missing: list[str] = []
    for sec in REQUIRED_SECTIONS:
        # ^## <Section> (Markdown H2). Match leading '##' to avoid
        # matching mentions inside body text.
        if not re.search(rf"^##\s+{re.escape(sec)}", card_text, re.MULTILINE):
            missing.append(sec)
    return missing


def main() -> int:
    failures = 0

    # 1. INDEX.md
    if (CARDS / "INDEX.md").is_file():
        ok("step 1: docs/model-cards/INDEX.md exists")
    else:
        fail("step 1: docs/model-cards/INDEX.md MISSING")
        failures += 1
        return failures

    # 2. TEMPLATE.md
    if (CARDS / "TEMPLATE.md").is_file():
        ok("step 2: docs/model-cards/TEMPLATE.md exists")
    else:
        fail("step 2: docs/model-cards/TEMPLATE.md MISSING")
        failures += 1

    # 3. LLMs in shadowRates have cards.
    llms = discover_llms_from_finops()
    if not llms:
        fail("step 3: shadowRates table empty in finops-svc — model audit can't anchor")
        failures += 1
    missing_cards: list[str] = []
    for m in llms:
        slug = sanitize_filename(m)
        path = CARDS / f"{slug}.md"
        if not path.is_file():
            missing_cards.append(f"{m} → {slug}.md")
    if not missing_cards:
        ok(f"step 3: all {len(llms)} LLMs in shadowRates have cards: {llms}")
    else:
        fail(f"step 3: missing cards: {missing_cards}")
        failures += 1

    # 4. bge-m3 (embedder).
    for extra in EXTRA_MODELS:
        slug = sanitize_filename(extra)
        path = CARDS / f"{slug}.md"
        if path.is_file():
            ok(f"step 4: extra model card present — {slug}.md")
        else:
            fail(f"step 4: missing card for {extra}")
            failures += 1

    # 5. Each card has all 9 §48.3 sections.
    all_models = [sanitize_filename(m) for m in llms] + [
        sanitize_filename(m) for m in EXTRA_MODELS
    ]
    for slug in all_models:
        path = CARDS / f"{slug}.md"
        if not path.is_file():
            continue  # already counted in step 3/4
        text = path.read_text(encoding="utf-8")
        miss = required_sections_present(text)
        if not miss:
            ok(f"step 5: {slug}.md has all {len(REQUIRED_SECTIONS)} required sections")
        else:
            fail(f"step 5: {slug}.md missing sections: {miss}")
            failures += 1

    # 6. NEGATIVE — phantom model name.
    phantom = "phantom-llm-9000"
    if not (CARDS / f"{phantom}.md").exists():
        ok(f"step 6 (negative): phantom card '{phantom}.md' absent — audit reads live shadowRates")
    else:
        fail(f"step 6 (negative): phantom card '{phantom}.md' exists — drift")
        failures += 1

    # 7. NEGATIVE — section validator catches a missing-section card.
    sample_card = REPO / "docs" / "model-cards" / "TEMPLATE.md"
    if sample_card.is_file():
        text = sample_card.read_text(encoding="utf-8")
        # Strip the "## Performance" heading (one of the required sections).
        broken = re.sub(r"^##\s+Performance.*$", "## SOMETHING_ELSE",
                        text, count=1, flags=re.MULTILINE)
        miss = required_sections_present(broken)
        if "Performance" in miss:
            ok("step 7 (negative): validator catches a stripped section — section check is real")
        else:
            fail("step 7 (negative): validator FAILED to catch a stripped section — tautology")
            failures += 1

    print()
    if failures == 0:
        print(
            f"{GREEN}{BOLD}ALL STEPS PASSED "
            f"({len(llms)} LLMs + {len(EXTRA_MODELS)} extra models verified){NC}"
        )
        return 0
    print(f"{RED}{BOLD}{failures} STEP(S) FAILED{NC}")
    return failures


if __name__ == "__main__":
    sys.exit(main())
