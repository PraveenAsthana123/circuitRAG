#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: documented cron references parse as valid crontab syntax.

Phase 6H closes operator copy-paste drift: the runbooks include
ready-to-paste cron examples, but a typo in the schedule, escaping,
or line-continuation shape would only show up when an operator tries
to install them on a real host.

This drill extracts the documented cron examples from:
  * docs/runbooks/autonomous-loop-cheatsheet.md
  * docs/runbooks/council-telemetry.md

Then it reconstructs the lines (including the multi-line 5X pipeline
example), writes them to a temporary crontab file, and asks the local
`crontab` implementation to syntax-check them. On this host the check
flag is `-n`; some distros use `-T`, so the drill supports either.

Eight steps. Six negative assertions.

  1. POSITIVE: both runbooks exist.
  2. NEGATIVE: cheatsheet has a ```cron block with ≥4 non-comment cron
     entries (snapshot, 2F prune, 6E prune, 5X pipeline).
  3. NEGATIVE: council-telemetry runbook has a ```cron block with the
     daily snapshot line and the 5X pipeline example.
  4. NEGATIVE: the three single-line cheatsheet cron entries match the
     expected canonical commands exactly.
  5. NEGATIVE: the multi-line 5X example round-trips into one single
     crontab line with schedule + command + flags intact, and does
     not require embedding the webhook secret inline.
  6. NEGATIVE: the local crontab syntax checker exists (`-n` or `-T`).
     Without this the drill would be a regex-only placebo.
  7. NEGATIVE: the reconstructed cron examples pass crontab syntax
     validation as a batch.
  8. POSITIVE: a deliberately broken cron line is rejected by the same
     syntax checker (proves step 7 is honest).

Run: python3 mcp/tests/drill_cron_reference_syntax.py
"""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CHEATSHEET = REPO / "docs" / "runbooks" / "autonomous-loop-cheatsheet.md"
TELEMETRY = REPO / "docs" / "runbooks" / "council-telemetry.md"

EXPECTED_SINGLE_LINES = {
    "5 0 * * * /mnt/deepa/rag/.venv/bin/python /mnt/deepa/rag/scripts/council_stats_snapshot.py",
    "0 4 * * 0 /mnt/deepa/rag/.venv/bin/python /mnt/deepa/rag/scripts/prune_council_runs.py --apply --vacuum",
    "30 4 * * 0 /mnt/deepa/rag/.venv/bin/python /mnt/deepa/rag/scripts/prune_loop_logs.py --apply",
}
EXPECTED_PIPELINE_PREFIX = "5 0 * * * /mnt/deepa/rag/scripts/run_filter_pipeline.sh"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _extract_cron_blocks(text: str) -> list[str]:
    blocks = re.findall(r"```cron\n(.*?)```", text, re.DOTALL)
    if not blocks:
        raise ValueError("no ```cron block found")
    return blocks


def _collapse_cron_lines(block: str) -> list[str]:
    lines: list[str] = []
    current = ""
    for raw in block.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        if line.lstrip().startswith("#"):
            continue
        if current:
            current += " " + line.strip()
        else:
            current = line.strip()
        if current.endswith("\\"):
            current = current[:-1].rstrip()
            continue
        lines.append(re.sub(r"\s+", " ", current).strip())
        current = ""
    if current:
        lines.append(re.sub(r"\s+", " ", current).strip())
    return lines


def _checker_flag() -> str | None:
    help_text = subprocess.run(
        ["crontab", "--help"],
        capture_output=True,
        text=True,
        timeout=5,
    )
    text = (help_text.stdout or "") + (help_text.stderr or "")
    if "-n" in text:
        return "-n"
    if "-T" in text:
        return "-T"
    return None


def _validate_crontab(lines: list[str], flag: str) -> bool:
    with tempfile.NamedTemporaryFile("w", delete=False) as tmp:
        tmp.write("\n".join(lines) + "\n")
        tmp_path = tmp.name
    try:
        result = subprocess.run(
            ["crontab", flag, tmp_path],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def main() -> int:
    # Step 1
    for path in (CHEATSHEET, TELEMETRY):
        if not path.exists():
            print(f"✗ step 1: missing runbook: {path}")
            return 1
    print("✓ step 1: both cron-carrying runbooks exist")

    # Step 2
    cheatsheet_lines: list[str] = []
    for block in _extract_cron_blocks(_read(CHEATSHEET)):
        cheatsheet_lines.extend(_collapse_cron_lines(block))
    if len(cheatsheet_lines) < 4:
        print(f"✗ step 2: cheatsheet cron block has {len(cheatsheet_lines)} entries, expected ≥4")
        return 1
    print(f"✓ step 2: cheatsheet cron block has {len(cheatsheet_lines)} entries")

    # Step 3
    telemetry_lines: list[str] = []
    for block in _extract_cron_blocks(_read(TELEMETRY)):
        telemetry_lines.extend(_collapse_cron_lines(block))
    if not any("council_stats_snapshot.py" in line for line in telemetry_lines):
        print("✗ step 3: telemetry runbook cron block missing snapshot line")
        return 1
    if not any("run_filter_pipeline.sh" in line for line in telemetry_lines):
        print("✗ step 3: telemetry runbook cron block missing pipeline line")
        return 1
    print("✓ step 3: telemetry runbook carries snapshot + pipeline cron examples")

    # Step 4
    singles = {line for line in cheatsheet_lines if "run_filter_pipeline.sh" not in line}
    if EXPECTED_SINGLE_LINES - singles:
        print(f"✗ step 4: missing canonical single-line cron entries: {sorted(EXPECTED_SINGLE_LINES - singles)}")
        return 1
    print("✓ step 4: canonical single-line cron entries match expected commands")

    # Step 5
    pipeline_lines = [line for line in cheatsheet_lines if "run_filter_pipeline.sh" in line]
    if len(pipeline_lines) != 1:
        print(f"✗ step 5: expected exactly 1 pipeline cron entry, found {len(pipeline_lines)}")
        return 1
    pipeline = pipeline_lines[0]
    required_fragments = [
        EXPECTED_PIPELINE_PREFIX,
        "--prometheus-out /var/lib/node_exporter/textfile/council.prom",
        "--webhook-format slack",
        '--alert-on "filtered>0.5"',
    ]
    missing = [frag for frag in required_fragments if frag not in pipeline]
    if missing:
        print(f"✗ step 5: pipeline cron entry missing fragments: {missing}")
        return 1
    if "--webhook " in pipeline:
        print("✗ step 5: pipeline cron entry still embeds webhook inline; env-file contract broken")
        return 1
    print("✓ step 5: multi-line 5X example collapses into one valid cron line")

    # Step 6
    flag = _checker_flag()
    if flag is None:
        print("✗ step 6: local crontab exposes neither -n nor -T syntax-check flag")
        return 1
    print(f"✓ step 6: local crontab syntax checker available via {flag}")

    # Step 7
    if not _validate_crontab(cheatsheet_lines, flag):
        print("✗ step 7: documented cron examples fail local crontab syntax check")
        return 1
    print("✓ step 7: documented cron examples pass local crontab syntax check")

    # Step 8
    broken = cheatsheet_lines[:]
    broken[0] = "bad bad * * * /mnt/deepa/rag/.venv/bin/python broken.py"
    if _validate_crontab(broken, flag):
        print("✗ step 8: deliberately broken cron line passed syntax check; validation dishonest")
        return 1
    print("✓ step 8: deliberately broken cron line is rejected by the same checker")

    print("\nALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
