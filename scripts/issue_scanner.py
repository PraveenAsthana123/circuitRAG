#!/usr/bin/env python3
"""Issue scanner — produces .loop/issue_checklist.jsonl from real signal sources.

Sources scanned (deterministic — not LLM-based):
  1. ruff   (Python lint)              — always
  2. mypy   (Python type errors)       — opt-in via --include-mypy

Each issue gets:
  - id (stable)
  - severity (LOW / MED / HIGH per rule code)
  - difficulty (easy = autofix; medium = local model; hard = human review)
  - assigned_to (which tool / model / human handles it)
  - fix_available (only ruff issues can be auto-fixed)

Output: .loop/issue_checklist.jsonl  (one JSON per line)

The checklist is the input to scripts/issue_dispatcher.py which routes
each issue to its assignee. Per global §43 + §38, every fix attempt
runs the relevant drill before commit and writes an audit row.

Usage:
    python3 scripts/issue_scanner.py
    python3 scripts/issue_scanner.py --include-security  # include S* codes (manual review)
    python3 scripts/issue_scanner.py --include-mypy       # add mypy type errors
    python3 scripts/issue_scanner.py --mypy-targets libs/py/documind_core  # custom mypy roots

Locked by mcp/tests/drill_issue_dispatcher_format.py.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CHECKLIST = REPO / ".loop" / "issue_checklist.jsonl"

# Rule code → (severity, difficulty, assignee).
# - easy/ruff:autofix: ruff --fix handles deterministically
# - medium/<local-model>: small model proposes diff; drill verifies
# - hard/human-review: needs judgment (security, naming conventions)
RULE_ROUTING: dict[str, tuple[str, str, str]] = {
    # Import sort + unused imports — fully auto
    "I001": ("LOW", "easy", "ruff:autofix"),
    "F401": ("LOW", "easy", "ruff:autofix"),
    "F403": ("LOW", "easy", "ruff:autofix"),
    # pyupgrade — auto
    "UP017": ("LOW", "easy", "ruff:autofix"),
    "UP037": ("LOW", "easy", "ruff:autofix"),
    "UP041": ("LOW", "easy", "ruff:autofix"),
    "UP042": ("LOW", "easy", "ruff:autofix"),
    # whitespace — auto
    "W291": ("LOW", "easy", "ruff:autofix"),
    "W292": ("LOW", "easy", "ruff:autofix"),
    "W293": ("LOW", "easy", "ruff:autofix"),
    # Line length — local model can split
    "E501": ("LOW", "medium", "deepseek-coder:6.7b-instruct"),
    # Module-level import not at top — local model can decide
    "E402": ("MED", "medium", "deepseek-coder:6.7b-instruct"),
    # Comparison style — local model
    "E711": ("LOW", "medium", "deepseek-coder:6.7b-instruct"),
    "E712": ("LOW", "medium", "deepseek-coder:6.7b-instruct"),
    # Simplifications — local model
    "SIM102": ("LOW", "medium", "deepseek-coder:6.7b-instruct"),
    "SIM114": ("LOW", "medium", "deepseek-coder:6.7b-instruct"),
    # Naming conventions — judgment call; codegemma handles it
    "N806": ("LOW", "medium", "codegemma:7b-instruct"),
    "N814": ("LOW", "medium", "codegemma:7b-instruct"),
    "N999": ("LOW", "medium", "codegemma:7b-instruct"),
    # Security — HUMAN REVIEW. Never let a model auto-fix S* without operator sign-off.
    "S110": ("HIGH", "hard", "human-review"),
    "S603": ("HIGH", "hard", "human-review"),
    "S607": ("HIGH", "hard", "human-review"),
    "S608": ("HIGH", "hard", "human-review"),
}

# Mypy error code → (severity, difficulty, assignee).
# Mypy errors cannot be auto-fixed (no equivalent of ruff --fix). All
# routing is manual: local model proposes diff, drill verifies.
# Anything not in the table defaults to ("MED", "hard", "human-review").
MYPY_ROUTING: dict[str, tuple[str, str, str]] = {
    # Most common — None assigned to non-Optional, return type drift.
    # Local model proposes type-narrowing or Optional annotation.
    "assignment": ("MED", "medium", "deepseek-coder:6.7b-instruct"),
    "operator": ("MED", "medium", "deepseek-coder:6.7b-instruct"),
    "arg-type": ("MED", "medium", "deepseek-coder:6.7b-instruct"),
    "return-value": ("MED", "medium", "deepseek-coder:6.7b-instruct"),
    "no-any-return": ("LOW", "medium", "codegemma:7b-instruct"),
    "var-annotated": ("LOW", "medium", "codegemma:7b-instruct"),
    "type-arg": ("LOW", "medium", "codegemma:7b-instruct"),
    # Could be a real bug masquerading as a type error — operator review.
    "attr-defined": ("HIGH", "hard", "human-review"),
    "name-defined": ("HIGH", "hard", "human-review"),
    "call-arg": ("HIGH", "hard", "human-review"),
    # Annotation-only fixes — small model handles.
    "annotation-unchecked": ("LOW", "medium", "codegemma:7b-instruct"),
    "no-untyped-def": ("LOW", "medium", "codegemma:7b-instruct"),
    "no-untyped-call": ("LOW", "medium", "codegemma:7b-instruct"),
}


def make_id(filename: str, code: str, line: int, source: str = "ruff") -> str:
    short = filename.rsplit("/", 1)[-1]
    return f"{source}-{code}-{short}-L{line}"


# mypy line shape:
#   <path>:<line>: error: <message>  [<code>]
#   <path>:<line>: note: <message>      (skipped)
_MYPY_LINE_RE = re.compile(
    r"^(?P<file>[^:]+):(?P<line>\d+):\s*error:\s*(?P<msg>.*?)\s*\[(?P<code>[a-z][a-z0-9-]+)\]\s*$"
)


def _resolve_mypy() -> str:
    venv = REPO / ".venv" / "bin" / "mypy"
    if venv.exists():
        return str(venv)
    import shutil
    found = shutil.which("mypy")
    if found:
        return found
    raise RuntimeError("mypy not found in .venv/bin or PATH; install: pip install mypy")


def scan_mypy(targets: list[str]) -> list[dict]:
    """Run mypy + parse the human-readable output. mypy has no JSON
    output mode; we regex-parse `<file>:<line>: error: <msg>  [<code>]`.

    No --output-format=json because mypy doesn't support it as of 1.20.
    """
    mypy = _resolve_mypy()
    cmd = [
        mypy,
        "--ignore-missing-imports",
        "--no-error-summary",
        "--no-color-output",
        *targets,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO)
    # mypy exits 1 when issues exist; exit 2 = real failure (config error).
    if proc.returncode not in (0, 1):
        # Don't raise — mypy may fail on partial source; surface and skip.
        print(f"[scan_mypy] WARNING mypy returned {proc.returncode}: {proc.stderr[:300]}")
    out = []
    for line in proc.stdout.splitlines():
        m = _MYPY_LINE_RE.match(line)
        if not m:
            continue
        code = m.group("code")
        severity, difficulty, assignee = MYPY_ROUTING.get(
            code, ("MED", "hard", "human-review")
        )
        filename = m.group("file").replace(str(REPO) + "/", "")
        line_no = int(m.group("line"))
        out.append(
            {
                "id": make_id(filename, code, line_no, source="mypy"),
                "source": "mypy",
                "severity": severity,
                "difficulty": difficulty,
                "assigned_to": assignee,
                "file": filename,
                "line": line_no,
                "col": 0,
                "code": code,
                "message": m.group("msg")[:200],
                "fix_available": False,  # mypy has no autofix
            }
        )
    return out


def scan_ruff(targets: list[str], include_security: bool = False) -> list[dict]:
    cmd = [".venv/bin/ruff", "check", *targets, "--output-format=json"]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO)
    # ruff exits 1 when issues exist; that is normal.
    if proc.returncode not in (0, 1):
        raise RuntimeError(f"ruff failed: {proc.stderr}")
    issues = json.loads(proc.stdout) if proc.stdout.strip() else []
    out = []
    for issue in issues:
        code = issue.get("code", "UNKNOWN")
        if not include_security and code.startswith("S"):
            continue
        severity, difficulty, assignee = RULE_ROUTING.get(
            code, ("MED", "hard", "human-review")
        )
        filename = issue.get("filename", "").replace(str(REPO) + "/", "")
        line = issue.get("location", {}).get("row", 0)
        out.append(
            {
                "id": make_id(filename, code, line),
                "source": "ruff",
                "severity": severity,
                "difficulty": difficulty,
                "assigned_to": assignee,
                "file": filename,
                "line": line,
                "col": issue.get("location", {}).get("column", 0),
                "code": code,
                "message": (issue.get("message", "") or "")[:200],
                "fix_available": issue.get("fix") is not None,
            }
        )
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--include-security", action="store_true")
    parser.add_argument("--include-mypy", action="store_true",
                        help="add mypy type errors to the checklist (slow)")
    parser.add_argument("--targets", nargs="*", default=["services"])
    parser.add_argument("--mypy-targets", nargs="*",
                        default=["libs/py/documind_core"],
                        help="paths mypy scans (default: libs/py/documind_core)")
    args = parser.parse_args()

    issues = scan_ruff(args.targets, include_security=args.include_security)
    if args.include_mypy:
        try:
            mypy_issues = scan_mypy(args.mypy_targets)
            issues.extend(mypy_issues)
        except RuntimeError as e:
            print(f"[scan_mypy] SKIP: {e}")

    CHECKLIST.parent.mkdir(parents=True, exist_ok=True)
    with CHECKLIST.open("w") as f:
        for issue in issues:
            f.write(json.dumps(issue) + "\n")

    by_difficulty: dict[str, int] = {}
    by_assignee: dict[str, int] = {}
    for x in issues:
        by_difficulty[x["difficulty"]] = by_difficulty.get(x["difficulty"], 0) + 1
        by_assignee[x["assigned_to"]] = by_assignee.get(x["assigned_to"], 0) + 1

    summary = {
        "total": len(issues),
        "by_difficulty": by_difficulty,
        "by_assignee": by_assignee,
    }
    print(json.dumps(summary, indent=2))
    print(f"\nWrote {len(issues)} issues to {CHECKLIST.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
