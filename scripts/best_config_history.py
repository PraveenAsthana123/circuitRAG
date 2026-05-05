"""Best-config history reader — Stage-1 audit-trail surface (per §38 + §51).

Reads .loop/best_config_history.jsonl (append-only, one row per
promotion gate evaluation) and projects an operator-facing summary:
how many promotions in the last N days, how many rejections, which
gates fired most often, what the latest decision was.

The history file is the SINGLE forensic record per §51 — every
promotion attempt is recorded whether it succeeded OR failed. This
script is the read-side projection.

CONTRACT:
  - load_history(path) → list[dict]
  - summarize(rows, days=7) → HistorySummary
  - latest(rows) → dict | None
  - is_available() / status()
  - CLI: python3 scripts/best_config_history.py --days 7

OPERATOR FLOW:
  1. promotion gate (scripts/promote_best_config.py) appends rows
  2. operator runs THIS script to see what happened recently
  3. dashboard can call summarize() to render a status panel

NEVER raises on missing/malformed file — returns empty summary
(§47 fail-safe). Stage-1 default-deny via env flag.

COMPOSES WITH:
    scripts/promote_best_config.py — writes rows
    scripts/best_config_loader.py   — reads the current best_config
    docs/architecture/six-plane-audit-2026-05-04.md — control plane
    §38 (governance), §47 (fail-safe), §51 (forensic substrate)
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

BEST_CONFIG_HISTORY_ENABLED = os.getenv("BEST_CONFIG_HISTORY_ENABLED", "").strip() == "1"
BEST_CONFIG_HISTORY_PATH = os.getenv(
    "BEST_CONFIG_HISTORY_PATH",
    ".loop/best_config_history.jsonl",
)


class BestConfigHistoryDisabled(RuntimeError):
    """Raised when force-required reader is invoked but env unset."""


@dataclass
class HistorySummary:
    """Aggregate view of recent promotion-gate decisions."""
    window_days: int = 7
    total_attempts: int = 0
    promoted: int = 0
    rejected: int = 0
    skipped: int = 0
    gates_failed_counts: dict[str, int] = field(default_factory=dict)
    latest_decision: dict[str, Any] | None = None
    earliest_ts: float = 0.0
    latest_ts: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def is_available() -> bool:
    """Stage-1 default-deny check."""
    return BEST_CONFIG_HISTORY_ENABLED


def status() -> dict[str, Any]:
    """Operator status surface."""
    p = Path(BEST_CONFIG_HISTORY_PATH)
    return {
        "stage": 1,
        "enabled_env": BEST_CONFIG_HISTORY_ENABLED,
        "available": is_available(),
        "history_path": str(p),
        "history_exists": p.exists(),
        "history_size_bytes": p.stat().st_size if p.exists() else 0,
        "next_stage": (
            "Stage-2 — surface summarize() output via "
            "/api/v1/health/best-config-history on inference-svc + "
            "retrieval-svc; dashboard renders a 'promotion timeline' panel"
        ),
    }


def load_history(path: str | None = None) -> list[dict[str, Any]]:
    """Read the JSONL history file. §47 fail-safe: returns [] on
    missing/malformed file rather than raising."""
    p = Path(path or BEST_CONFIG_HISTORY_PATH)
    if not p.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        with p.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    log.warning("malformed history row: %s", exc)
                    continue
    except Exception as exc:
        log.warning("history read failed: %s", exc)
        return []
    return rows


def latest(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Return the most recent decision row by decided_at_ts."""
    if not rows:
        return None
    return max(rows, key=lambda r: float(r.get("decided_at_ts", 0.0)))


def summarize(rows: list[dict[str, Any]], *, days: int = 7) -> HistorySummary:
    """Build a window-bounded summary. Negative `days` → all rows."""
    cutoff = 0.0 if days < 0 else time.time() - (days * 86400)
    windowed = [r for r in rows if float(r.get("decided_at_ts", 0.0)) >= cutoff]

    summary = HistorySummary(window_days=days)
    summary.total_attempts = len(windowed)
    if not windowed:
        return summary

    timestamps = [float(r.get("decided_at_ts", 0.0)) for r in windowed]
    summary.earliest_ts = min(timestamps)
    summary.latest_ts = max(timestamps)

    for r in windowed:
        promoted_flag = bool(r.get("promoted", False))
        reason = str(r.get("reason", ""))
        if promoted_flag:
            summary.promoted += 1
        elif "skipped" in reason.lower():
            summary.skipped += 1
        else:
            summary.rejected += 1

        # Tally gate failures
        for gate in r.get("gates_failed", []) or []:
            # Strip the threshold value to count gate types
            # e.g. "pass_rate=0.30 < min=0.50" → "pass_rate"
            key = gate.split("=", 1)[0].strip() if "=" in gate else gate
            summary.gates_failed_counts[key] = summary.gates_failed_counts.get(key, 0) + 1

    summary.latest_decision = latest(windowed)
    return summary


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", default=None, help="Override history path")
    parser.add_argument("--days", type=int, default=7,
                        help="Window in days (negative = all rows)")
    parser.add_argument("--json", action="store_true",
                        help="Emit JSON instead of human-readable")
    args = parser.parse_args()

    print("scripts/best_config_history.py — Stage-1 audit-trail reader")
    print(f"Stage-1 opt-in via BEST_CONFIG_HISTORY_ENABLED=1")
    print()
    print(json.dumps(status(), indent=2))
    print()

    if not is_available():
        print("Reader disabled. Set BEST_CONFIG_HISTORY_ENABLED=1 to summarize.")
        sys.exit(0)

    rows = load_history(args.path)
    summary = summarize(rows, days=args.days)
    if args.json:
        print(json.dumps(summary.as_dict(), indent=2))
    else:
        print(f"=== best_config promotion history (last {args.days}d) ===")
        print(f"  total attempts: {summary.total_attempts}")
        print(f"  promoted:       {summary.promoted}")
        print(f"  rejected:       {summary.rejected}")
        print(f"  skipped:        {summary.skipped}")
        if summary.gates_failed_counts:
            print(f"  gates failed by type:")
            for gate, n in sorted(summary.gates_failed_counts.items(), key=lambda x: -x[1]):
                print(f"    {gate}: {n}")
        if summary.latest_decision:
            ld = summary.latest_decision
            print(f"\n  latest decision:")
            print(f"    promoted: {ld.get('promoted')}")
            print(f"    reason:   {ld.get('reason', '?')}")
            print(f"    config:   {ld.get('raw_winner_signature', '?')}")
    sys.exit(0)
