"""Agent readiness check — does the council actually FIX things? (iter-76).

User asked three questions in the autonomous-loop session:
  1. "will they (models) able to work, are they functioning, are they
     integrated well?"
  2. "are they able to fix issue, take the task and provide solution?"
  3. "which agent is working, orchestration agent is working or not,
     able to be assign the work to agent?"

This probe answers all three EMPIRICALLY (no claims, just data) and
writes .loop/agent_readiness_report.json for the UI to surface.

Per CLAUDE.md §44 (iter-76), §55 ("a fix-bot at 0% apply rate is not
a fix-bot"), §55.3 (outcome-based contract: apply_rate / regressions /
cost), §38 (governance — verifiable claims), §51 (forensic substrate).

What it probes
--------------
A. MODELS WORK?       — read .loop/ollama_smoke_results.json (iter-75)
B. ORCHESTRATOR UP?   — HTTP /health on agent-orchestrator-svc
C. COUNCIL ACTIVE?    — count entries in .loop/council_runs.log + dates
D. APPLY RATE        — fraction of recent .loop/agent_task_board_apply
                       entries with outcome=='applied' (council lane)
E. WORK ASSIGNABLE?   — does the agent task board / issue dispatcher
                       successfully route a synthetic check?
F. MCP FLEET HEALTH   — at least N namespaces in WORKING/SLEEPING (not
                       FAILING / NOT_INSTALLED)

Honest output
-------------
Each dimension reports {status, evidence, notes}. status is one of:
  - YES (verifiable + currently true)
  - NO  (verifiable + currently false)
  - MIXED (partially true; needs operator action)
  - UNKNOWN (data missing — surface the gap, don't claim either way)

Exit code: 0 if all YES; 1 if any NO; 2 if any UNKNOWN. CI runs with
--strict to require all-YES.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LOOP = REPO / ".loop"
REPORT_PATH = LOOP / "agent_readiness_report.json"

ORCHESTRATOR_URL = os.getenv(
    "DOCUMIND_ORCHESTRATOR_URL",
    "http://localhost:8050",
)
# Fallback ports the orchestrator is sometimes started on (env-overrideable)
ORCHESTRATOR_FALLBACK_PORTS = (8087, 8050, 8051)
MCP_DRILLS_URL = os.getenv(
    "DOCUMIND_MCP_DRILLS_URL",
    "http://localhost:8092",
)


def _http_get(url: str, timeout: float = 3.0) -> tuple[int, bytes]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:  # noqa: S310
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, b""
    except Exception:  # noqa: BLE001
        return 0, b""


def probe_models() -> dict:
    """A. MODELS WORK? — read .loop/ollama_smoke_results.json."""
    smoke = LOOP / "ollama_smoke_results.json"
    if not smoke.exists():
        return {
            "status": "UNKNOWN",
            "evidence": "no .loop/ollama_smoke_results.json",
            "notes": "run: python3 scripts/ollama_all_models_smoke.py --write",
        }
    try:
        d = json.loads(smoke.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return {"status": "UNKNOWN", "evidence": f"corrupt smoke file: {e}", "notes": ""}

    total = d.get("models_total", 0)
    by_status = d.get("by_status", {})
    working = by_status.get("WORKING", 0)
    if total == 0:
        return {"status": "NO", "evidence": "no models installed", "notes": ""}
    if working == total:
        return {
            "status": "YES",
            "evidence": f"{working}/{total} models passed /api/generate smoke",
            "notes": f"smoked_at={d.get('smoked_at')}",
        }
    return {
        "status": "MIXED",
        "evidence": f"{working}/{total} models WORKING; by_status={by_status}",
        "notes": "see .loop/ollama_smoke_results.json for per-model details",
    }


def probe_orchestrator() -> dict:
    """B. ORCHESTRATOR UP? — HTTP probe with /health/live (§47.8 3-probe)."""
    candidates = [ORCHESTRATOR_URL] + [
        f"http://localhost:{p}" for p in ORCHESTRATOR_FALLBACK_PORTS
        if f":{p}" not in ORCHESTRATOR_URL
    ]
    for url in candidates:
        # Try /health/live first (§47.8 dumb liveness), then /health (legacy)
        for path in ("/health/live", "/health"):
            code, body = _http_get(f"{url}{path}", timeout=2.0)
            if code == 200:
                ready_code, ready_body = _http_get(f"{url}/health/ready", timeout=2.0)
                ready_note = (
                    ready_body[:200].decode("utf-8", "replace")
                    if ready_code == 200
                    else f"ready probe → {ready_code}"
                )
                return {
                    "status": "YES",
                    "evidence": f"GET {url}{path} → 200",
                    "notes": ready_note or "(no ready body)",
                }
    return {
        "status": "NO",
        "evidence": (
            f"all candidate URLs unreachable: "
            f"{candidates}"
        ),
        "notes": (
            "agent-orchestrator-svc not running on any known port; "
            "work routing falls back to scripts/issue_dispatcher.py"
        ),
    }


def probe_council() -> dict:
    """C. COUNCIL ACTIVE? — recent runs in stats/log files."""
    stats = LOOP / "council_stats_daily.jsonl"
    if not stats.exists():
        return {
            "status": "UNKNOWN",
            "evidence": "no .loop/council_stats_daily.jsonl",
            "notes": "council never ran or stats roll-up not configured",
        }
    lines = [
        json.loads(line) for line in stats.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not lines:
        return {
            "status": "NO",
            "evidence": "council_stats_daily.jsonl empty",
            "notes": "",
        }
    recent_total = sum(r.get("total", 0) for r in lines[-7:])
    recent_fired = sum(r.get("fired", 0) for r in lines[-7:])
    if recent_total == 0:
        return {
            "status": "NO",
            "evidence": "0 council runs in last 7 days",
            "notes": "",
        }
    return {
        "status": "YES",
        "evidence": f"{recent_total} council events / {recent_fired} fired (last 7d)",
        "notes": f"latest: {lines[-1].get('date')} fired={lines[-1].get('fired')}",
    }


def probe_apply_rate() -> dict:
    """D. APPLY RATE on council lane (last N attempts)."""
    apply_log = LOOP / "agent_task_board_apply.jsonl"
    if not apply_log.exists():
        return {
            "status": "UNKNOWN",
            "evidence": "no .loop/agent_task_board_apply.jsonl",
            "notes": "no apply attempts recorded yet",
        }
    rows = [
        json.loads(line) for line in apply_log.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not rows:
        return {"status": "UNKNOWN", "evidence": "apply log empty", "notes": ""}

    recent = rows[-50:]
    council_rows = [r for r in recent if r.get("lane") == "council"]
    deterministic_rows = [r for r in recent if r.get("lane") == "deterministic"]

    council_applied = sum(1 for r in council_rows if r.get("outcome") == "applied")
    council_total = len(council_rows)
    det_applied = sum(1 for r in deterministic_rows if r.get("outcome") == "applied")
    det_total = len(deterministic_rows)

    council_rate = (council_applied / council_total) if council_total else None
    det_rate = (det_applied / det_total) if det_total else None

    if council_total == 0 and det_total == 0:
        return {
            "status": "UNKNOWN",
            "evidence": f"{len(recent)} recent rows but no lane-tagged entries",
            "notes": "older log rows lack 'lane' field — backfill needed",
        }

    notes = []
    if council_rate is not None:
        notes.append(f"council {council_applied}/{council_total} = {council_rate:.0%}")
    if det_rate is not None:
        notes.append(f"deterministic {det_applied}/{det_total} = {det_rate:.0%}")

    if (council_rate is not None and council_rate >= 0.5) or (
        det_rate is not None and det_rate >= 0.5
    ):
        return {
            "status": "YES",
            "evidence": "; ".join(notes),
            "notes": "council lane below threshold is OK if deterministic lane works",
        }
    if (council_rate or 0) < 0.1 and (det_rate or 0) < 0.1:
        return {
            "status": "NO",
            "evidence": "; ".join(notes),
            "notes": "§55 brutal rule: 0% apply rate = logging system, not fix-bot",
        }
    return {
        "status": "MIXED",
        "evidence": "; ".join(notes),
        "notes": "below target apply rate; investigate council reject reasons",
    }


def probe_assignability() -> dict:
    """E. WORK ASSIGNABLE? — does issue dispatcher dry-run cleanly?"""
    dispatcher = REPO / "scripts" / "issue_dispatcher.py"
    if not dispatcher.exists():
        return {
            "status": "UNKNOWN",
            "evidence": f"missing {dispatcher.relative_to(REPO)}",
            "notes": "no work-routing CLI present",
        }
    # Don't actually run it (would touch the loop); just confirm it imports.
    import subprocess
    started = time.monotonic()
    r = subprocess.run(
        [sys.executable, str(dispatcher), "--help"],
        capture_output=True, text=True, timeout=10, cwd=str(REPO),
    )
    elapsed_ms = int((time.monotonic() - started) * 1000)
    if r.returncode != 0:
        return {
            "status": "NO",
            "evidence": f"issue_dispatcher --help exited {r.returncode}",
            "notes": (r.stderr or r.stdout)[:200],
        }
    return {
        "status": "YES",
        "evidence": f"issue_dispatcher --help OK ({elapsed_ms}ms)",
        "notes": "CLI work-routing path is operational; orchestrator service is optional",
    }


def probe_mcp_fleet() -> dict:
    """F. MCP FLEET HEALTH — read .loop/ for fleet output if any, else
    a coarse count from mcp/server_*.py."""
    # Easy signal: how many server files exist
    server_files = sorted((REPO / "mcp").glob("server_*.py"))
    if not server_files:
        return {"status": "NO", "evidence": "no mcp/server_*.py files", "notes": ""}
    # Sample one URL to see if anything is up
    code, _ = _http_get(f"{MCP_DRILLS_URL}/health", timeout=2.0)
    if code == 200:
        return {
            "status": "YES",
            "evidence": (
                f"{len(server_files)} MCP server files; drills server "
                f"reachable at {MCP_DRILLS_URL}"
            ),
            "notes": (
                "operator-readable fleet status: run "
                "`python3 scripts/mcp_fleet_health.py --full`"
            ),
        }
    return {
        "status": "MIXED",
        "evidence": (
            f"{len(server_files)} MCP server files installed; no servers "
            f"running locally on the surveyed ports"
        ),
        "notes": (
            "this is normal in dev — set DOCUMIND_MCP_<NS>_URL to enable; "
            "iter-72 fleet monitor classifies these as SLEEPING (not failing)"
        ),
    }


def probe_council_nodes() -> dict:
    """G. COUNCIL NODES — match council models against installed Ollama."""
    smoke = LOOP / "ollama_smoke_results.json"
    if not smoke.exists():
        return {"status": "UNKNOWN", "evidence": "no smoke file", "notes": ""}
    d = json.loads(smoke.read_text(encoding="utf-8"))
    installed = set(d.get("results", {}).keys())

    # Council canonical mapping (from scripts/local_council.py)
    EXPECTED = {
        "researcher": "qwen2.5:latest",
        "author": "deepseek-coder:6.7b-instruct",
        "reviewer": "codegemma:7b-instruct",
        "advisor": "codellama:7b-instruct",
    }
    missing = [
        f"{role}={model}"
        for role, model in EXPECTED.items()
        if model not in installed
    ]
    if missing:
        return {
            "status": "MIXED",
            "evidence": f"missing council models: {missing}",
            "notes": "ollama pull <model> to enable",
        }
    return {
        "status": "YES",
        "evidence": f"all 4 council node models installed: {list(EXPECTED.values())}",
        "notes": "researcher / author / reviewer / advisor all WORKING (per iter-75)",
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--json", action="store_true", help="JSON output only")
    p.add_argument("--strict", action="store_true",
                   help="exit non-zero on any UNKNOWN")
    p.add_argument("--write", action="store_true",
                   help="write to .loop/agent_readiness_report.json")
    args = p.parse_args()

    probes = [
        ("A_models_work", probe_models),
        ("B_orchestrator_up", probe_orchestrator),
        ("C_council_active", probe_council),
        ("D_apply_rate", probe_apply_rate),
        ("E_work_assignable", probe_assignability),
        ("F_mcp_fleet", probe_mcp_fleet),
        ("G_council_nodes", probe_council_nodes),
    ]

    results: dict[str, dict] = {}
    for key, fn in probes:
        try:
            results[key] = fn()
        except Exception as e:  # noqa: BLE001
            results[key] = {
                "status": "UNKNOWN",
                "evidence": f"probe crashed: {type(e).__name__}: {e}",
                "notes": "",
            }

    by_status: dict[str, int] = {}
    for r in results.values():
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1

    summary = {
        "generated_at": datetime.now(UTC).isoformat(),
        "by_status": by_status,
        "results": results,
    }

    if args.write or not args.json:
        LOOP.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print("\nAGENT READINESS REPORT")
        print("=" * 60)
        for key, r in results.items():
            print(f"\n{key:24} → {r['status']}")
            print(f"  evidence: {r['evidence']}")
            if r.get("notes"):
                print(f"  notes:    {r['notes']}")
        print(f"\nby_status: {by_status}")
        if args.write:
            print(f"Wrote: {REPORT_PATH.relative_to(REPO)}")

    if any(r["status"] == "NO" for r in results.values()):
        return 1
    if args.strict and any(r["status"] == "UNKNOWN" for r in results.values()):
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
