#!/usr/bin/env python3
"""Issue dispatcher — routes each issue from the checklist to its assignee.

Reads .loop/issue_checklist.jsonl. For each issue:
  - assignee == ruff:autofix → run `ruff --fix --select <code>` on the file
  - assignee == <ollama-model> → POST to localhost:11434/api/generate with
    a structured prompt; receive a unified diff; print for review
    (NOT auto-applied — human or drill-gated apply is a separate step)
  - assignee == human-review → print the issue and skip

Writes audit row per attempt to .loop/issue_audit.jsonl.

Per the operator-only safety gate: --apply is required to actually mutate
files. By default this is a dry-run that shows what would happen.

Usage:
    # dry-run: show what each lane would do
    python3 scripts/issue_dispatcher.py

    # apply only ruff autofix lane (deterministic, safe)
    python3 scripts/issue_dispatcher.py --apply --only ruff:autofix

    # send one specific medium issue to its model and print proposal
    python3 scripts/issue_dispatcher.py --propose --id ruff-E501-policy.py-L21

Locked by mcp/tests/drill_issue_dispatcher_format.py.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import urllib.request

REPO = Path(__file__).resolve().parent.parent
CHECKLIST = REPO / ".loop" / "issue_checklist.jsonl"
AUDIT = REPO / ".loop" / "issue_audit.jsonl"
OLLAMA = "http://localhost:11434/api/generate"


def load_checklist() -> list[dict]:
    if not CHECKLIST.exists():
        print(f"missing {CHECKLIST.relative_to(REPO)}; run issue_scanner.py first")
        sys.exit(2)
    return [json.loads(line) for line in CHECKLIST.read_text().splitlines() if line.strip()]


def write_audit(row: dict) -> None:
    AUDIT.parent.mkdir(parents=True, exist_ok=True)
    row = {**row, "ts": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    with AUDIT.open("a") as f:
        f.write(json.dumps(row) + "\n")


def run_ruff_autofix(issues: list[dict], apply: bool) -> tuple[int, int]:
    """Apply ruff --fix to the union of files. Returns (attempted, fixed)."""
    files = sorted({i["file"] for i in issues})
    codes = sorted({i["code"] for i in issues})
    if not apply:
        print(f"  [DRY-RUN] would run: ruff check --fix --select {','.join(codes)} {' '.join(files)}")
        return len(issues), 0
    cmd = [
        ".venv/bin/ruff", "check", "--fix", "--select", ",".join(codes), *files,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO)
    fixed = proc.stdout.count("Fixed ") if proc.returncode in (0, 1) else 0
    write_audit({
        "lane": "ruff:autofix",
        "attempted": len(issues),
        "exit_code": proc.returncode,
        "stdout_tail": proc.stdout[-500:],
    })
    return len(issues), fixed


def call_ollama(model: str, prompt: str, timeout_s: int = 120) -> tuple[str, int]:
    """POST to local Ollama. Returns (response_text, eval_tokens)."""
    body = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.1, "num_ctx": 4096},
    }).encode()
    req = urllib.request.Request(OLLAMA, data=body, headers={"Content-Type": "application/json"})
    started = time.time()
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        data = json.loads(resp.read())
    return data.get("response", ""), data.get("eval_count", 0)


def propose_for_issue(issue: dict) -> None:
    """Send one issue to its assigned local model; print the proposal."""
    file_path = REPO / issue["file"]
    if not file_path.exists():
        print(f"  SKIP (file missing): {issue['file']}")
        return

    snippet = file_path.read_text(encoding="utf-8").splitlines()
    line_no = issue["line"]
    start = max(0, line_no - 5)
    end = min(len(snippet), line_no + 5)
    context = "\n".join(f"{i+1:4}: {snippet[i]}" for i in range(start, end))

    prompt = f"""You are a Python code-fix assistant. The linter found this issue:

  Rule: {issue['code']}
  Message: {issue['message']}
  File: {issue['file']}
  Line: {line_no}

Context (with line numbers):
```python
{context}
```

Propose ONE minimal unified-diff hunk that fixes this single issue. Do NOT
modify other lines. Output ONLY the diff in this format:

--- a/{issue['file']}
+++ b/{issue['file']}
@@ -<line>,<count> +<line>,<count> @@
 (unchanged context)
-(line to remove)
+(line to add)
 (unchanged context)

Diff:"""

    print(f"  Calling {issue['assigned_to']} ...")
    started = time.time()
    try:
        response, tokens = call_ollama(issue["assigned_to"], prompt)
    except Exception as e:
        print(f"  ERROR: {e}")
        write_audit({"id": issue["id"], "lane": issue["assigned_to"], "outcome": "error", "error": str(e)})
        return
    elapsed = time.time() - started
    print(f"  --- proposal ({tokens} tokens, {elapsed:.1f}s) ---")
    print(response[:1500])
    print(f"  --- end proposal ---")
    write_audit({
        "id": issue["id"],
        "lane": issue["assigned_to"],
        "model": issue["assigned_to"],
        "tokens": tokens,
        "latency_s": elapsed,
        "outcome": "proposed",
        "proposal": response[:2000],
    })


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="actually mutate files (default: dry-run)")
    parser.add_argument("--propose", action="store_true", help="invoke local model and print proposal")
    parser.add_argument("--only", help="filter by assignee")
    parser.add_argument("--id", help="run only this issue id")
    args = parser.parse_args()

    issues = load_checklist()

    if args.id:
        match = [i for i in issues if i["id"] == args.id]
        if not match:
            print(f"no issue with id={args.id}")
            return 2
        issue = match[0]
        if args.propose and issue["assigned_to"].startswith(("deepseek", "codegemma", "starcoder", "codellama", "qwen")):
            propose_for_issue(issue)
        else:
            print(json.dumps(issue, indent=2))
        return 0

    by_assignee: dict[str, list[dict]] = {}
    for i in issues:
        by_assignee.setdefault(i["assigned_to"], []).append(i)

    for assignee in sorted(by_assignee):
        if args.only and assignee != args.only:
            continue
        bucket = by_assignee[assignee]
        print(f"\n[{assignee}] {len(bucket)} issue(s)")
        if assignee == "ruff:autofix":
            attempted, fixed = run_ruff_autofix(bucket, apply=args.apply)
            print(f"  attempted={attempted} fixed={fixed}{' (dry-run)' if not args.apply else ''}")
        elif assignee == "human-review":
            for i in bucket[:3]:
                print(f"  HUMAN: {i['file']}:{i['line']} {i['code']} {i['message'][:80]}")
        else:
            print(f"  ({len(bucket)} medium issue(s) for {assignee} — use --propose --id <id> to invoke)")
            for i in bucket[:3]:
                print(f"    - {i['id']} ({i['file']}:{i['line']})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
