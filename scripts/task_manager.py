"""Task management — Tier 5 #5.7.

Per CLAUDE.md §50 + §55. Unified Kanban-shape task board across
HUMAN and AGENT owners. Beyond the orchestrator's
`orchestration.agent_tasks` table (which is agent-only) and beyond
the `.loop/issue_checklist.jsonl` (which is lint-issue-only), this
gives an operator-facing surface for:

  - Feature work scheduled to a human dev
  - Chore tasks (refactor; doc update; runbook)
  - Spike investigations (research questions; "look into X")
  - Agent-assigned work (research / code / review per Tier 1 #1.2 routing)

The shape is general so a future iter can wire it into the
orchestrator's DB-backed agent_tasks table for cross-system unity;
today: pure JSONL at `.loop/tasks.jsonl`.

§42 / §54 BOUNDARIES
====================

  - All persistence is local JSONL; no external service writes
  - Status transitions are append-only (audit trail preserved)
  - DAG validation rejects cycles in depends_on (a depends on b
    depends on a → reject at add time)
  - Pydantic extra='forbid' blocks PII contamination in task body

USAGE
=====

  python3 scripts/task_manager.py add "title" --owner praveen --priority high
  python3 scripts/task_manager.py add "title" --owner-type agent --owner researcher
  python3 scripts/task_manager.py list --owner praveen --status pending
  python3 scripts/task_manager.py update <id> --status in_progress
  python3 scripts/task_manager.py update <id> --status done
  python3 scripts/task_manager.py board   # Kanban-shape view across all tasks

Drilled by mcp/tests/drill_task_manager.py.
"""

from __future__ import annotations

import argparse
import datetime
import uuid
from collections import defaultdict
from pathlib import Path
from typing import ClassVar, Literal

from pydantic import BaseModel, Field, ValidationError

REPO = Path(__file__).resolve().parent.parent
TASKS_LOG = REPO / ".loop" / "tasks.jsonl"


OwnerType = Literal["human", "agent"]
Status = Literal["pending", "in_progress", "blocked", "done", "cancelled"]
Priority = Literal["low", "medium", "high", "urgent"]


class Task(BaseModel):
    """One task on the unified board.

    JSONL-serializable. extra='forbid' prevents PII contamination
    via accidental kwargs.
    """

    id: str = Field(min_length=1, max_length=64,
                    pattern=r"^[a-z0-9][a-z0-9_-]*$",
                    description="kebab-case unique id")
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(default="", max_length=4000)
    owner_type: OwnerType = Field(description="human or agent")
    owner: str = Field(min_length=1, max_length=64,
                       pattern=r"^[a-z][a-z0-9_-]*$",
                       description="kebab/snake; human username OR agent name")
    status: Status = Field(default="pending")
    priority: Priority = Field(default="medium")
    depends_on: list[str] = Field(default_factory=list,
                                  description="task ids this blocks on")
    tags: list[str] = Field(default_factory=list)
    created_at: str = Field(description="ISO 8601 UTC")
    updated_at: str = Field(description="ISO 8601 UTC")

    model_config: ClassVar[dict] = {"extra": "forbid"}


def now_iso() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat()


def _load_tasks() -> list[Task]:
    if not TASKS_LOG.exists():
        return []
    out: list[Task] = []
    for line in TASKS_LOG.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            out.append(Task.model_validate_json(line))
        except ValidationError:
            continue  # tolerate forward-compat schema drift
    return out


def _detect_cycle(tasks: list[Task], new_task: Task | None = None) -> str | None:
    """Walk the depends_on graph; return cycle path string OR None."""
    all_tasks = list(tasks)
    if new_task is not None:
        all_tasks = [t for t in tasks if t.id != new_task.id] + [new_task]
    by_id = {t.id: t for t in all_tasks}
    state: dict[str, str] = {}  # id → "white"|"gray"|"black"

    def visit(node: str, path: list[str]) -> str | None:
        if node not in by_id:
            return None  # unknown dep ids treated as terminal
        color = state.get(node, "white")
        if color == "black":
            return None
        if color == "gray":
            return " → ".join(path + [node])
        state[node] = "gray"
        for dep in by_id[node].depends_on:
            cyc = visit(dep, path + [node])
            if cyc:
                return cyc
        state[node] = "black"
        return None

    for tid in by_id:
        cyc = visit(tid, [])
        if cyc:
            return cyc
    return None


def _save_task(task: Task) -> None:
    TASKS_LOG.parent.mkdir(parents=True, exist_ok=True)
    # JSONL append; no rewrite.
    with TASKS_LOG.open("a", encoding="utf-8") as fh:
        fh.write(task.model_dump_json() + "\n")


def add_task(
    *,
    title: str,
    owner_type: OwnerType = "human",
    owner: str,
    body: str = "",
    priority: Priority = "medium",
    depends_on: list[str] | None = None,
    tags: list[str] | None = None,
    task_id: str | None = None,
) -> Task:
    """Append a new task. Validates DAG before save (rejects cycles)."""
    task = Task(
        id=task_id or f"task-{uuid.uuid4().hex[:12]}",
        title=title,
        body=body,
        owner_type=owner_type,
        owner=owner,
        status="pending",
        priority=priority,
        depends_on=depends_on or [],
        tags=tags or [],
        created_at=now_iso(),
        updated_at=now_iso(),
    )
    existing = _load_tasks()
    cycle = _detect_cycle(existing, new_task=task)
    if cycle is not None:
        raise ValueError(f"depends_on would create a cycle: {cycle}")
    _save_task(task)
    return task


def update_status(task_id: str, new_status: Status) -> Task:
    """Append an updated row. Latest-row-wins semantics on read."""
    tasks = _load_tasks()
    target = next((t for t in tasks if t.id == task_id), None)
    if target is None:
        raise ValueError(f"task not found: {task_id}")
    updated = Task(
        id=target.id,
        title=target.title,
        body=target.body,
        owner_type=target.owner_type,
        owner=target.owner,
        status=new_status,
        priority=target.priority,
        depends_on=target.depends_on,
        tags=target.tags,
        created_at=target.created_at,
        updated_at=now_iso(),
    )
    _save_task(updated)
    return updated


def list_current_tasks() -> list[Task]:
    """Return latest version of each task (latest-row-wins)."""
    rows = _load_tasks()
    by_id: dict[str, Task] = {}
    for row in rows:
        by_id[row.id] = row  # later rows overwrite
    return list(by_id.values())


# ---------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------

def cmd_add(args: argparse.Namespace) -> int:
    try:
        task = add_task(
            title=args.title,
            owner_type=args.owner_type,
            owner=args.owner,
            body=args.body or "",
            priority=args.priority,
            depends_on=args.depends_on or [],
            tags=args.tags or [],
        )
    except (ValidationError, ValueError) as exc:
        print(f"x rejected: {exc}")
        return 1
    print(f"✓ added task {task.id}: {task.title}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    tasks = list_current_tasks()
    if args.owner:
        tasks = [t for t in tasks if t.owner == args.owner]
    if args.status:
        tasks = [t for t in tasks if t.status == args.status]
    if not tasks:
        print("(no tasks match)")
        return 0
    for t in sorted(tasks, key=lambda t: (t.priority, t.updated_at)):
        print(f"  {t.id:<24} [{t.status:<11}] [{t.priority:<6}] [{t.owner_type}/{t.owner}] {t.title[:80]}")
    return 0


def cmd_update(args: argparse.Namespace) -> int:
    try:
        task = update_status(args.id, args.status)
    except ValueError as exc:
        print(f"x rejected: {exc}")
        return 1
    print(f"✓ {task.id} → status={task.status}")
    return 0


def cmd_board(_args: argparse.Namespace) -> int:
    tasks = list_current_tasks()
    by_status: dict[str, list[Task]] = defaultdict(list)
    for t in tasks:
        by_status[t.status].append(t)
    print("=== TASK BOARD ===")
    for status in ("pending", "in_progress", "blocked", "done", "cancelled"):
        items = by_status.get(status, [])
        print(f"\n  {status.upper()} ({len(items)})")
        for t in items[:10]:
            print(f"    {t.id:<24} [{t.priority:<6}] [{t.owner_type}/{t.owner}] {t.title[:70]}")
        if len(items) > 10:
            print(f"    ... +{len(items) - 10} more")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="task_manager.py", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_add = sub.add_parser("add", help="add a task")
    p_add.add_argument("title")
    p_add.add_argument("--body", default="")
    p_add.add_argument("--owner-type", choices=["human", "agent"], default="human")
    p_add.add_argument("--owner", required=True)
    p_add.add_argument("--priority", choices=["low", "medium", "high", "urgent"], default="medium")
    p_add.add_argument("--depends-on", nargs="*", default=[])
    p_add.add_argument("--tags", nargs="*", default=[])
    p_add.set_defaults(func=cmd_add)

    p_ls = sub.add_parser("list", help="list tasks (latest-row-wins)")
    p_ls.add_argument("--owner", default=None)
    p_ls.add_argument("--status", default=None,
                      choices=["pending", "in_progress", "blocked", "done", "cancelled"])
    p_ls.set_defaults(func=cmd_list)

    p_up = sub.add_parser("update", help="update task status")
    p_up.add_argument("id")
    p_up.add_argument("--status", required=True,
                      choices=["pending", "in_progress", "blocked", "done", "cancelled"])
    p_up.set_defaults(func=cmd_update)

    p_bd = sub.add_parser("board", help="Kanban-shape board view")
    p_bd.set_defaults(func=cmd_board)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
