#!/usr/bin/env python3
"""Run a set of drills, capture pass/fail per drill, write status JSON.

Closes the rule-1 gap from Phase 4B. The post-commit hook reads
.loop/last_drill_outcome.json to decide whether the latest commit
broke a drill; this script populates that file.

Output format:

    {
      "timestamp": "2026-04-28T10:15:32+00:00",
      "failed_drills": ["drill_x", "drill_y"],
      "total_drills": 29,
      "per_drill": {
        "drill_x": {"passed": false, "error": "exit 1: ..."},
        "drill_y": {"passed": false, "error": "timeout > 60.0s"},
        "drill_a": {"passed": true,  "error": null},
        ...
      }
    }

Operator usage:

    # Run every tier-1 drill and write status:
    python3 scripts/write_drill_status.py

    # Only readonly-tagged drills (faster):
    python3 scripts/write_drill_status.py --only-readonly

    # Custom timeout per drill:
    python3 scripts/write_drill_status.py --timeout 120

CI usage: exits 1 if any drill failed, so a wrapper job can fail
on red. Local loop usage: the loop pipes through write_drill_status.py
before each commit so the post-commit hook has fresh data.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_STATUS_PATH = REPO / ".loop" / "last_drill_outcome.json"

# Match run_drills.py's interpreter resolution. Drills like
# drill_tool_catalog_ttl import from `mcp` which needs documind_core
# on PYTHONPATH PLUS runtime deps (httpx, asyncpg). Resolution order
# prefers the venv that actually HAS the deps. Currently that's the
# legacy /tmp/documind-venv (set up earlier in the project lifetime);
# the project-resident .venv at $REPO/.venv exists but doesn't yet
# carry every drill dep. Operator can flip the order via PYTHON_BIN
# env once .venv is fully populated.
def _resolve_py_bin() -> str:
    override = os.environ.get("PYTHON_BIN")
    if override and Path(override).exists():
        return override
    legacy = Path("/tmp/documind-venv/bin/python")
    if legacy.exists():
        return str(legacy)
    repo_venv = REPO / ".venv" / "bin" / "python"
    if repo_venv.exists():
        return str(repo_venv)
    return sys.executable


PY_BIN = _resolve_py_bin()

log = logging.getLogger("write_drill_status")


@dataclass(frozen=True)
class DrillResult:
    """One drill's outcome."""

    name: str
    passed: bool
    error: str | None
    duration_s: float


def run_drill(
    drill_path: Path,
    *,
    timeout_s: float = 60.0,
    cwd: Path | None = None,
) -> DrillResult:
    """Run a single drill via subprocess. Returns the outcome.

    Never raises - subprocess errors / timeouts / file-not-found
    are captured as DrillResult.error so the caller can keep
    iterating across other drills.
    """
    import time
    cwd = cwd or REPO
    name = drill_path.stem
    t0 = time.monotonic()
    # Match run_drills.py's env: PYTHONPATH=REPO so drills that
    # `from mcp import ...` or `from documind_core import ...`
    # resolve correctly. PY_BIN points at the dev venv (where
    # documind_core lives) when available.
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO) + os.pathsep + env.get("PYTHONPATH", "")
    try:
        result = subprocess.run(
            [PY_BIN, str(drill_path)],
            capture_output=True,
            text=True,
            timeout=timeout_s,
            cwd=str(cwd),
            env=env,
        )
        duration = time.monotonic() - t0
        if result.returncode == 0:
            return DrillResult(name=name, passed=True, error=None, duration_s=duration)
        # Capture the tail of stderr (or stdout) for triage
        err_excerpt = (result.stderr or result.stdout or "")[-300:].strip()
        return DrillResult(
            name=name,
            passed=False,
            error=f"exit {result.returncode}: {err_excerpt}",
            duration_s=duration,
        )
    except subprocess.TimeoutExpired:
        return DrillResult(
            name=name,
            passed=False,
            error=f"timeout > {timeout_s:.1f}s",
            duration_s=timeout_s,
        )
    except FileNotFoundError as exc:
        return DrillResult(
            name=name,
            passed=False,
            error=f"file not found: {exc}",
            duration_s=time.monotonic() - t0,
        )
    except OSError as exc:
        return DrillResult(
            name=name,
            passed=False,
            error=f"OSError: {exc}",
            duration_s=time.monotonic() - t0,
        )


def is_readonly_drill(drill_path: Path) -> bool:
    """A drill is 'readonly' (tier 1) if its second line is the
    canonical resource tag '# RESOURCES: readonly'."""
    try:
        with drill_path.open() as f:
            lines = [next(f) for _ in range(3)]
        return any(ln.strip() == "# RESOURCES: readonly" for ln in lines)
    except (OSError, StopIteration):
        return False


def write_drill_status(
    drill_paths: list[Path],
    *,
    status_path: Path = DEFAULT_STATUS_PATH,
    timeout_s: float = 60.0,
) -> dict:
    """Run every drill in `drill_paths`, write the status JSON.
    Returns the status dict."""
    timestamp = datetime.now(UTC).isoformat(timespec="seconds")
    per_drill: dict[str, dict] = {}
    failed: list[str] = []

    for path in drill_paths:
        result = run_drill(path, timeout_s=timeout_s)
        per_drill[result.name] = {
            "passed": result.passed,
            "error": result.error,
            "duration_s": round(result.duration_s, 3),
        }
        if not result.passed:
            failed.append(result.name)
            log.warning(
                "drill_failed name=%s error=%s",
                result.name, (result.error or "")[:120],
            )

    status = {
        "timestamp": timestamp,
        "failed_drills": failed,
        "total_drills": len(drill_paths),
        "per_drill": per_drill,
    }
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(json.dumps(status, indent=2) + "\n")
    return status


def cli() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--status-path",
        default=str(DEFAULT_STATUS_PATH),
        help="where to write the JSON status file",
    )
    parser.add_argument(
        "--glob",
        default="mcp/tests/drill_*.py",
        help="glob (relative to repo root) for drills",
    )
    parser.add_argument(
        "--only-readonly", action="store_true",
        help="only run drills tagged '# RESOURCES: readonly'",
    )
    parser.add_argument(
        "--timeout", type=float, default=60.0,
        help="per-drill timeout in seconds",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    drill_paths = sorted((REPO).glob(args.glob))
    if args.only_readonly:
        drill_paths = [p for p in drill_paths if is_readonly_drill(p)]

    if not drill_paths:
        log.warning(
            "no drills matched glob=%r only_readonly=%s",
            args.glob, args.only_readonly,
        )

    status = write_drill_status(
        drill_paths,
        status_path=Path(args.status_path),
        timeout_s=args.timeout,
    )

    # Operator-visible summary on stderr
    n_pass = status["total_drills"] - len(status["failed_drills"])
    print(
        f"[drill_status] {n_pass}/{status['total_drills']} passed; "
        f"{len(status['failed_drills'])} failed; "
        f"wrote {args.status_path}",
        file=sys.stderr,
    )
    if status["failed_drills"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(cli())
