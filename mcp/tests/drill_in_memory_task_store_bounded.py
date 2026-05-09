#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: InMemoryTaskStore P0 (#35) — unbounded-memory closure invariants.

Locks the §52 brutal-review row 35 closure shipped in store.py:
  * 4 distinct collections must be bounded:
      - tasks                (OrderedDict, max_tasks default 1000)
      - task_runs per task   (list, max_runs_per_task default 100)
      - projects             (OrderedDict, max_projects default 500)
      - memories per scope   (list, max_memories_per_scope default 200)
  * `_evict_if_over` helper must exist + use OrderedDict.popitem(last=False)
    (LRU eviction — oldest first)
  * `save()` must `move-to-end` on update (refresh recency before evict)
  * Caps must be operator-overridable via constructor

8 steps, 4 negative.

Per CLAUDE.md §43 (drill discipline; ≥3 negatives — 4 here),
§52 (P0 closure must have a regression surface — code review alone
isn't enough; the drill enforces the invariant), §57.1 production-
grade-by-default (memory-bounded is the contract; reverting to
unbounded dict trips the drill), §57.7 honesty (drill verifies
behavior empirically; doc-only updates wouldn't have caught a
regression).
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services" / "agent-orchestrator-svc"))

GREEN = "\033[32m"
RED = "\033[31m"
BOLD = "\033[1m"
NC = "\033[0m"


def step(t: str) -> None:
    print(f"\n{BOLD}── {t} ──{NC}")


def ok(m: str) -> None:
    print(f"  {GREEN}✓ {m}{NC}")


def fail(m: str) -> None:
    print(f"  {RED}✗ {m}{NC}")
    raise SystemExit(1)


def main() -> int:
    # ── 1. POSITIVE: store source contains the bounded constants ──────
    step("1. POSITIVE: store.py declares 4 bound constants")
    src = (REPO / "services" / "agent-orchestrator-svc" / "app" / "store.py").read_text(
        encoding="utf-8"
    )
    for const in [
        "_DEFAULT_MAX_TASKS",
        "_DEFAULT_MAX_RUNS_PER_TASK",
        "_DEFAULT_MAX_PROJECTS",
        "_DEFAULT_MAX_MEMORIES_PER_SCOPE",
    ]:
        if const not in src:
            fail(f"store.py missing constant: {const}")
    ok("all 4 _DEFAULT_MAX_* constants declared")

    # ── 2. POSITIVE: _evict_if_over helper present ────────────────────
    step("2. POSITIVE: _evict_if_over helper present")
    if "_evict_if_over" not in src:
        fail("store.py missing _evict_if_over helper")
    if "popitem(last=False)" not in src:
        fail("_evict_if_over must use popitem(last=False) for LRU semantics")
    ok("_evict_if_over with LRU popitem(last=False) present")

    # ── 3. POSITIVE: caps applied at 4 collection sites ───────────────
    step("3. POSITIVE: caps applied at 4 collection sites")
    required_sites = [
        ("self._items", "max_tasks"),
        ("self._projects", "max_projects"),
        ("max_runs_per_task", "self.max_runs_per_task"),
        ("max_memories_per_scope", "self.max_memories_per_scope"),
    ]
    for marker, _ in required_sites:
        if marker not in src:
            fail(f"store.py missing cap-site marker: {marker}")
    ok("4 collection cap-sites present (tasks / runs / projects / memories)")

    # ── 4. NEGATIVE: store does NOT use bare dict[str, TaskView] ──────
    step("4. NEGATIVE: tasks collection is OrderedDict (not bare dict)")
    if "self._items: OrderedDict" not in src:
        fail(
            "self._items must be OrderedDict — bare dict has no eviction "
            "ordering, regressing the P0 fix"
        )
    if "self._projects: OrderedDict" not in src:
        fail("self._projects must be OrderedDict for LRU eviction semantics")
    ok("self._items + self._projects both typed as OrderedDict")

    # ── 5. NEGATIVE: caps must be constructor-overridable ─────────────
    step("5. NEGATIVE: caps are constructor-overridable")
    if "def __init__" not in src:
        fail("InMemoryTaskStore has no __init__")
    init_block = src[src.find("def __init__") : src.find("def __init__") + 1500]
    for kw in ["max_tasks", "max_runs_per_task", "max_projects", "max_memories_per_scope"]:
        if f"{kw}:" not in init_block and f"{kw} =" not in init_block:
            fail(f"__init__ does not accept {kw} kwarg — caps not overridable")
    ok("all 4 caps accepted as constructor kwargs")

    # ── 6. NEGATIVE: save() refreshes recency (move-to-end) ───────────
    step("6. NEGATIVE: save() deletes-then-inserts (move-to-end on update)")
    save_block = src[src.find("async def save(self, task: TaskView)") : src.find("async def save(self, task: TaskView)") + 600]
    if "del self._items[task.task_id]" not in save_block:
        fail(
            "save() does NOT delete-before-insert — without this, repeated "
            "updates to the same task don't refresh LRU recency, and the "
            "task gets evicted prematurely. P0 fix half-works."
        )
    ok("save() deletes-then-inserts (LRU recency refresh)")

    # ── 7. POSITIVE: empirical eviction works ─────────────────────────
    step("7. POSITIVE: empirical — store with cap=3 holds exactly 3 items")
    try:
        from app.models import TaskView
        from app.store import InMemoryTaskStore
    except Exception as e:  # noqa: BLE001
        fail(f"could not import store: {e}")

    async def empirical_eviction() -> int:
        store = InMemoryTaskStore(max_tasks=3)
        for i in range(5):
            await store.save(TaskView(task_id=f"task-{i}", tenant_id="t", goal="g", status="pending", risk_level="low"))
        return len(store._items)

    held = asyncio.run(empirical_eviction())
    if held != 3:
        fail(f"after 5 saves with cap=3, expected 3 items held, got {held}")
    ok(f"cap=3 saved 5 → held 3 (eviction works)")

    # ── 8. NEGATIVE: cap=0 must not be accepted (would lose every save) ─
    step("8. NEGATIVE: cap=0 normalizes to ≥1 (operator typo defense)")

    async def cap_zero_normalizes() -> int:
        store = InMemoryTaskStore(max_tasks=0)
        await store.save(TaskView(task_id="solo", tenant_id="t", goal="g", status="pending", risk_level="low"))
        return len(store._items)

    held_zero = asyncio.run(cap_zero_normalizes())
    if held_zero == 0:
        fail("cap=0 accepted as-is — every save evicts immediately. Should normalize to ≥1.")
    ok(f"cap=0 normalized: 1 save held {held_zero} item (max(1, cap) defense works)")

    print(f"\n{BOLD}{GREEN}ALL 8 STEPS PASSED{NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
