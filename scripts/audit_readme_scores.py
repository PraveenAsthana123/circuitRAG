#!/usr/bin/env python3
"""
Aggregate README audit-checklist scores across every folder in the repo.

Walks every README.md under services/, libs/py/, mcp/, and top-level
Python folders. For each, parses the 10×10 audit-checklist grid (added
by section_audit_checklist in scripts/generate_folder_report.py),
sums the per-row scores (10 / 5 / 0 / TBD), and emits an
operator-readable dashboard.

Outputs:
  * stdout: aggregate table + per-folder breakdown
  * --json:  machine-readable JSON for CI / dashboards
  * --html:  static HTML page for the frontend admin/readme-audit
              deep-dive

Honesty contract per §57.7:
  - **Auto-locked rows** (10/10 with drill-evidence link) — these are
    deterministically produced by the generator and verified by
    `mcp/tests/drill_readme_generator.py`. Count them as 10/10.
  - **TBD rows** — DO NOT count as ✓. They contribute 0 to the
    "achieved score" but inflate the "ceiling score". The gap is
    visible.
  - Never silently roll TBD → ✓. Operator must edit the README with
    evidence to claim the points.

Usage:
  python3 scripts/audit_readme_scores.py
  python3 scripts/audit_readme_scores.py --json
  python3 scripts/audit_readme_scores.py --html docs/audit-dashboard.html
  python3 scripts/audit_readme_scores.py --threshold 80
  python3 scripts/audit_readme_scores.py --only services/
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
IGNORE_DIRS = {"__pycache__", "node_modules", ".git", ".venv", ".venv-redteam",
               "dist", "build", ".next", ".loop", ".archive-shims", ".tools",
               "mlruns", "data"}

# Row-scoring patterns inside the audit-checklist tables
# Each row: | N | text | SCORE | evidence |
ROW_SCORE_RE = re.compile(
    r"^\|\s*\d+\s*\|.*?\|\s*(\*\*?\s*(10|5|0)\s*\*\*?|TBD|✓|⚠|✗)\s*\|",
    re.MULTILINE,
)

# Category headings inside the checklist
CATEGORY_RE = re.compile(r"^### (\d+)\. (.+?) \(10 rows\)", re.MULTILINE)


@dataclass
class CategoryScore:
    name: str
    achieved: int = 0       # sum of locked + reviewer-filled scores
    ceiling: int = 100      # always 10 rows × 10 max = 100 per category
    tbd_count: int = 0      # rows still TBD
    auto_locked_count: int = 0


@dataclass
class FolderScore:
    rel_path: str
    abs_path: str
    readme_size: int = 0
    section_count: int = 0
    categories: List[CategoryScore] = field(default_factory=list)
    total_achieved: int = 0
    total_ceiling: int = 1000  # 10 categories × 100 = 1000
    total_tbd: int = 0
    total_auto_locked: int = 0
    pass_threshold: bool = False
    has_audit_checklist: bool = False


def parse_score_token(token: str) -> Optional[int]:
    """Parse '10' / '**10**' / 'TBD' / '✓' / '⚠' / '✗' into 0-10 or None for TBD."""
    t = token.replace("*", "").strip()
    if t == "TBD":
        return None
    if t in {"✓", "10"}:
        return 10
    if t == "⚠" or t == "5":
        return 5
    if t in {"✗", "0"}:
        return 0
    if t.isdigit():
        v = int(t)
        return v if 0 <= v <= 10 else None
    return None


def parse_readme(readme_path: Path) -> FolderScore:
    """Parse one README's audit-checklist + return aggregate scores."""
    text = readme_path.read_text(encoding="utf-8", errors="ignore")
    rel = str(readme_path.parent.relative_to(REPO_ROOT)) if readme_path.parent.is_relative_to(REPO_ROOT) else str(readme_path.parent)
    score = FolderScore(
        rel_path=rel,
        abs_path=str(readme_path),
        readme_size=len(text),
        section_count=text.count("\n## "),
    )
    if "## 📋 Reporting + Audit Checklist" not in text:
        return score
    score.has_audit_checklist = True

    # Find category sections
    # Each category block runs until the next "### " or "### Aggregate" line.
    # Approach: split text by "### " headings, then for each that matches
    # "<N>. <name> (10 rows)", parse score tokens in the rows.
    category_starts = list(CATEGORY_RE.finditer(text))
    for i, m in enumerate(category_starts):
        cat_num = int(m.group(1))
        cat_name = m.group(2).strip()
        start = m.end()
        end = (category_starts[i + 1].start()
               if i + 1 < len(category_starts) else len(text))
        # Also stop at "### Aggregate" or the next "## " section
        agg_pos = text.find("### Aggregate", start)
        if 0 < agg_pos < end:
            end = agg_pos
        next_h2 = text.find("\n## ", start)
        if 0 < next_h2 < end:
            end = next_h2
        block = text[start:end]
        cat = CategoryScore(name=f"{cat_num}. {cat_name}")
        for row in ROW_SCORE_RE.finditer(block):
            token = row.group(1)
            v = parse_score_token(token)
            if v is None:
                cat.tbd_count += 1
            else:
                cat.achieved += v
                if "**" in token or token.strip() == "✓":
                    cat.auto_locked_count += 1
        score.categories.append(cat)
        score.total_achieved += cat.achieved
        score.total_tbd += cat.tbd_count
        score.total_auto_locked += cat.auto_locked_count

    return score


def _is_ignored(path: Path) -> bool:
    parts = path.parts
    if any(part in IGNORE_DIRS for part in parts):
        return True
    # Any .venv* virtualenv
    if any(part.startswith(".venv") for part in parts):
        return True
    # Any site-packages
    if "site-packages" in parts:
        return True
    return False


def discover_readmes(roots: List[Path] = None) -> List[Path]:
    """Find every README.md in the repo (respecting IGNORE_DIRS)."""
    if roots is None:
        roots = [REPO_ROOT]
    found: List[Path] = []
    for root in roots:
        for p in root.rglob("README.md"):
            if _is_ignored(p):
                continue
            found.append(p)
    return sorted(set(found))


def render_dashboard(scores: List[FolderScore], threshold: int) -> str:
    """Render plaintext dashboard."""
    lines = []
    lines.append("═" * 92)
    lines.append("  README AUDIT SCOREBOARD — Folder-Readme Standard §58 + Audit Checklist")
    lines.append("═" * 92)
    lines.append(f"  Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append(f"  Threshold for production: ≥ {threshold} / 100 per folder")
    lines.append(f"  Total READMEs analyzed: {len(scores)}")
    auditable = [s for s in scores if s.has_audit_checklist]
    lines.append(f"  With audit checklist: {len(auditable)} ({100 * len(auditable) // max(len(scores), 1)}%)")
    lines.append("─" * 92)
    lines.append(
        f"  {'Folder':<46} {'KB':>5} {'Sec':>4} {'Score':>7} {'TBD':>5} {'Lock':>5} {'Pass':>5}"
    )
    lines.append("─" * 92)

    aggregate_achieved = 0
    aggregate_ceiling = 0
    aggregate_tbd = 0
    aggregate_locked = 0
    passing = 0

    for s in sorted(scores, key=lambda x: x.rel_path):
        pct = (100 * s.total_achieved // max(s.total_ceiling, 1)) if s.has_audit_checklist else 0
        s.pass_threshold = pct >= threshold and s.has_audit_checklist
        if s.pass_threshold:
            passing += 1
        marker = "✓" if s.pass_threshold else (" " if s.has_audit_checklist else "·")
        score_str = f"{s.total_achieved}/{s.total_ceiling}" if s.has_audit_checklist else "no audit"
        tbd_str = str(s.total_tbd) if s.has_audit_checklist else "—"
        lock_str = str(s.total_auto_locked) if s.has_audit_checklist else "—"
        path_disp = s.rel_path if len(s.rel_path) <= 46 else "..." + s.rel_path[-43:]
        lines.append(
            f"  {marker} {path_disp:<44} "
            f"{s.readme_size // 1024:>5} "
            f"{s.section_count:>4} "
            f"{score_str:>7} "
            f"{tbd_str:>5} "
            f"{lock_str:>5} "
            f"{'PASS' if s.pass_threshold else (str(pct) + '%' if s.has_audit_checklist else 'n/a'):>5}"
        )
        if s.has_audit_checklist:
            aggregate_achieved += s.total_achieved
            aggregate_ceiling += s.total_ceiling
            aggregate_tbd += s.total_tbd
            aggregate_locked += s.total_auto_locked

    lines.append("─" * 92)
    if aggregate_ceiling > 0:
        agg_pct = 100 * aggregate_achieved // aggregate_ceiling
        lines.append(f"  AGGREGATE  achieved={aggregate_achieved}  "
                     f"ceiling={aggregate_ceiling}  "
                     f"({agg_pct}%)  "
                     f"TBD={aggregate_tbd}  "
                     f"auto-locked={aggregate_locked}")
        lines.append(f"  PASS RATE  {passing}/{len(auditable)} folders "
                     f"({100 * passing // max(len(auditable), 1)}%) meet ≥{threshold}/1000 threshold")
    lines.append("═" * 92)

    # Honesty footer per §57.7
    lines.append("")
    lines.append("Honesty footer (§57.7):")
    lines.append("  * 'achieved'  = sum of locked (auto-verified) + reviewer-filled scores")
    lines.append("  * 'ceiling'   = 10 categories × 10 rows × 10 max = 1000 per folder")
    lines.append("  * 'TBD'       = rows awaiting reviewer evidence (NOT counted as ✓)")
    lines.append("  * 'auto-locked' = rows pre-scored 10/10 by the generator")
    lines.append("  * To raise a folder's score: open its README, find the TBD rows,")
    lines.append("    fill with ✓ (10) / ⚠ (5) / ✗ (0) AND link the evidence in the next column.")
    lines.append("    Never overwrite TBD with ✓ without rerunnable evidence.")
    return "\n".join(lines)


def render_json(scores: List[FolderScore]) -> str:
    """Emit machine-readable JSON."""
    return json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "folder_count": len(scores),
        "folders": [asdict(s) for s in scores],
        "aggregate": {
            "achieved": sum(s.total_achieved for s in scores if s.has_audit_checklist),
            "ceiling": sum(s.total_ceiling for s in scores if s.has_audit_checklist),
            "tbd": sum(s.total_tbd for s in scores if s.has_audit_checklist),
            "auto_locked": sum(s.total_auto_locked for s in scores if s.has_audit_checklist),
            "passing": sum(1 for s in scores if s.pass_threshold),
            "audited": sum(1 for s in scores if s.has_audit_checklist),
        },
    }, indent=2, default=str)


def render_html(scores: List[FolderScore], threshold: int) -> str:
    """Render minimal static HTML dashboard."""
    rows = []
    for s in sorted(scores, key=lambda x: x.rel_path):
        pct = (100 * s.total_achieved // max(s.total_ceiling, 1)) if s.has_audit_checklist else 0
        marker = "✓ PASS" if s.pass_threshold else (f"{pct}%" if s.has_audit_checklist else "—")
        color = "#10b981" if s.pass_threshold else (
            "#f59e0b" if s.has_audit_checklist else "#94a3b8")
        score_str = (f"{s.total_achieved} / {s.total_ceiling}"
                     if s.has_audit_checklist else "no audit checklist")
        rows.append(
            f"<tr><td><code>{s.rel_path}</code></td>"
            f"<td>{s.readme_size // 1024} KB</td>"
            f"<td>{s.section_count}</td>"
            f"<td>{score_str}</td>"
            f"<td>{s.total_tbd if s.has_audit_checklist else '—'}</td>"
            f"<td>{s.total_auto_locked if s.has_audit_checklist else '—'}</td>"
            f"<td style='color:{color};font-weight:bold'>{marker}</td>"
            f"</tr>"
        )
    return f"""<!doctype html>
<html><head><meta charset="utf-8"/>
<title>README Audit Scoreboard</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; max-width: 1200px; margin: 2em auto; padding: 0 1em; }}
  h1 {{ border-bottom: 2px solid #333; padding-bottom: .5em; }}
  table {{ width: 100%; border-collapse: collapse; margin: 1em 0; }}
  th, td {{ padding: .4em .8em; text-align: left; border-bottom: 1px solid #e5e7eb; }}
  th {{ background: #f3f4f6; }}
  code {{ font-size: .9em; color: #1f2937; }}
  .footer {{ font-size: .85em; color: #6b7280; margin-top: 2em; }}
</style></head><body>
<h1>📋 README Audit Scoreboard</h1>
<p><strong>Generated:</strong> {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}<br/>
<strong>Threshold:</strong> ≥ {threshold} / 1000 for production-pass</p>
<table>
<thead><tr><th>Folder</th><th>Size</th><th>Sections</th><th>Score</th><th>TBD</th><th>Locked</th><th>Status</th></tr></thead>
<tbody>
{"".join(rows)}
</tbody>
</table>
<div class="footer">
  <p><strong>Honesty contract (§57.7):</strong> auto-locked rows are pre-scored 10/10 because the generator
  deterministically produces them AND the drill <code>mcp/tests/drill_readme_generator.py</code> verifies
  the invariants. TBD rows are NOT counted as ✓ — they're rows awaiting reviewer evidence.
  Edit the README to fill TBD with ✓ (10) / ⚠ (5) / ✗ (0) AND link evidence in the next column.</p>
</div>
</body></html>
"""


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Aggregate README audit-checklist scores across the repo.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--json", action="store_true",
                   help="Emit JSON to stdout (not the text dashboard).")
    p.add_argument("--html", type=Path,
                   help="Write HTML dashboard to this path.")
    p.add_argument("--threshold", type=int, default=80,
                   help="Per-folder pass threshold (% of 1000).")
    p.add_argument("--only", type=Path, action="append", default=[],
                   help="Only scan these subfolders (repeatable).")
    p.add_argument("--fail-under", type=int, default=0,
                   help="Exit code 1 if aggregate % < this value.")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    roots = [REPO_ROOT / p for p in args.only] if args.only else [REPO_ROOT]
    readmes = discover_readmes(roots)
    if not readmes:
        print("No READMEs found.", file=sys.stderr)
        return 1
    scores = [parse_readme(r) for r in readmes]

    if args.html:
        args.html.parent.mkdir(parents=True, exist_ok=True)
        args.html.write_text(render_html(scores, args.threshold), encoding="utf-8")
        print(f"WROTE {args.html}", file=sys.stderr)

    if args.json:
        print(render_json(scores))
    else:
        print(render_dashboard(scores, args.threshold))

    # Exit-code gate
    if args.fail_under > 0:
        total_achieved = sum(s.total_achieved for s in scores if s.has_audit_checklist)
        total_ceiling = sum(s.total_ceiling for s in scores if s.has_audit_checklist)
        if total_ceiling > 0:
            pct = 100 * total_achieved // total_ceiling
            if pct < args.fail_under:
                print(f"\nFAIL: aggregate {pct}% < threshold {args.fail_under}%",
                      file=sys.stderr)
                return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
