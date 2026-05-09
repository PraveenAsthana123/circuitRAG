"""Always-on CLI agent council.

Usage:
    python -m agent_cli.main

REPL commands:
    >>> <free text>           run a council session
    >>> show history          last 20 sessions
    >>> show history <id>     details of one session
    >>> rollback <RB_id>      restore previous state (where applicable)
    >>> help                  this list
    >>> exit | quit           leave

Composes safety_store + approval_agent + agent_cli.orchestrator.
"""
from __future__ import annotations

import json
import sys

from agent_cli.agents.cli_logger import log
from agent_cli.orchestrator import run_council
from safety_store import RollbackError, get_by_rollback_id, list_history, rollback

HELP = """\
Commands:
  <free text>                ask the council
  show history               last 20 sessions
  show history <history_id>  details of one session
  rollback <RB_id>           rollback (uncommon for CLI sessions)
  help                       this list
  exit | quit                leave
"""


def cmd_show_history(args: list[str]) -> int:
    if not args:
        rows = list_history(entity_type="agent_cli_session", limit=20)
        if not rows:
            print("(no sessions yet)")
            return 0
        for r in rows:
            short = r.action.upper()
            print(f"  {r.created_at}  {r.history_id}  {short:25s}  rb={r.rollback_id}")
        return 0
    target = args[0]
    matches = [r for r in list_history(limit=500) if r.history_id == target]
    if not matches:
        print(f"no history record id={target}")
        return 1
    print(json.dumps({
        "history_id": matches[0].history_id,
        "entity_type": matches[0].entity_type,
        "entity_id": matches[0].entity_id,
        "action": matches[0].action,
        "actor": matches[0].actor,
        "approved_by": matches[0].approved_by,
        "reason": matches[0].reason,
        "rollback_id": matches[0].rollback_id,
        "rollback_until": matches[0].rollback_until,
        "old_value": matches[0].old_value,
        "new_value": matches[0].new_value,
        "created_at": matches[0].created_at,
    }, indent=2))
    return 0


def cmd_rollback(args: list[str]) -> int:
    if not args:
        print("usage: rollback <RB_id>")
        return 1
    rb_id = args[0]
    record = get_by_rollback_id(rb_id)
    if record is None:
        print(f"unknown rollback_id={rb_id}")
        return 1
    print(f"about to rollback history_id={record.history_id} "
          f"(action={record.action} entity={record.entity_type}/{record.entity_id})")
    confirm = input("type 'yes' to confirm: ").strip().lower()
    if confirm != "yes":
        print("aborted")
        return 0
    try:
        new_record = rollback(rb_id, actor="cli_user", note="manual via REPL")
    except RollbackError as e:
        log("blocked", f"rollback denied: {e}")
        return 1
    log("history", f"rolled back; new history_id={new_record.history_id}")
    return 0


def repl() -> int:
    print("🚀 agent_cli — Ollama Agent Council  (type 'help' or 'exit')")
    while True:
        try:
            line = input(">>> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not line:
            continue
        low = line.lower()
        if low in ("exit", "quit"):
            return 0
        if low == "help":
            print(HELP)
            continue
        if low.startswith("show history"):
            args = line.split()[2:]
            cmd_show_history(args)
            continue
        if low.startswith("rollback "):
            args = line.split()[1:]
            cmd_rollback(args)
            continue

        # Free-text → run council
        result = run_council(line)
        print()
        print("=" * 60)
        print(result.final_answer)
        print("=" * 60)
        print(result.short())
        print()


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    if argv:
        # Non-interactive single-shot: `python -m agent_cli.main "build foo"`
        text = " ".join(argv)
        result = run_council(text)
        print(result.final_answer)
        print()
        print(result.short())
        return 0
    return repl()


if __name__ == "__main__":
    sys.exit(main())
