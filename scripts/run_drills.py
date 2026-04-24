#!/usr/bin/env python3
"""
run_drills.py — resource-aware parallel drill runner.

Most drills kill/restart shared services (MCP on :8090, inference on
:8084) — they can't run simultaneously. A minority are pure-read
(audit verifier, tenant span tags reading from Jaeger) and are safe
to parallelise with anything.

How scheduling works
====================

Each drill file MAY declare a set of shared resources it touches at
the top of the file, e.g.::

    # RESOURCES: mcp_hr inference pg

The runner reads that tag. If a drill has no tag, the default is
``{"mcp_hr", "inference", "pg"}`` — the safe "touches everything"
assumption, which serialises it against every other drill.

A drill starts only when ALL of its declared resources are free. A
free resource is one no currently-running drill has reserved. Simple
Python asyncio semaphores per resource implement the interlock.

Usage
=====

    scripts/run_drills.py                       # serial, all drills
    scripts/run_drills.py --parallel 4          # up to 4 concurrent
    scripts/run_drills.py --only trace audit    # filter by substring
    scripts/run_drills.py --list                # show tags, don't run
    scripts/run_drills.py --stop-on-fail        # abort on first failure

Exit code: 0 if every drill passed, 1 otherwise.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DRILL_DIR = REPO / "mcp" / "tests"
PY_BIN = os.getenv("PYTHON_BIN", "/tmp/documind-venv/bin/python")

RESOURCE_TAG_RE = re.compile(r"^#\s*RESOURCES\s*:\s*(.+)$", re.MULTILINE)
RESULT_RE = re.compile(r"ALL\s+(\d+)\s+.*STEPS\s+PASSED")

# Default (no tag): "touches everything with write-level exclusion."
# Safe — untagged drills serialise against every other drill.
DEFAULT_RESOURCES: frozenset[tuple[str, str]] = frozenset({
    ("mcp_hr", "write"),
    ("inference", "write"),
    ("pg", "write"),
})

GREEN = "\033[32m"; RED = "\033[31m"; YELLOW = "\033[33m"; BOLD = "\033[1m"; NC = "\033[0m"


@dataclass
class Drill:
    name: str
    path: Path
    # Set of (resource_name, mode) pairs. mode ∈ {"read", "write"}.
    # "read" drills sharing a resource can run concurrently; one
    # "write" drill excludes all other holders of that resource.
    resources: frozenset[tuple[str, str]]
    status: str = "pending"       # pending | running | passed | failed | skipped
    duration_s: float = 0.0
    steps_passed: int = 0
    exit_code: int | None = None
    tail: str = ""


def _parse_resource_tokens(tokens: list[str]) -> frozenset[tuple[str, str]]:
    """Turn a token list like ``['mcp_hr', 'inference:read']`` into
    ``{('mcp_hr','write'), ('inference','read')}``. Bare tokens
    default to write-level exclusion. ``:read`` modifier marks a
    shared lock."""
    out: set[tuple[str, str]] = set()
    for t in tokens:
        if ":" in t:
            name, _, mode = t.partition(":")
            mode = mode.strip().lower()
            if mode not in ("read", "write"):
                mode = "write"
            out.add((name.strip(), mode))
        else:
            out.add((t.strip(), "write"))
    return frozenset(out)


def _discover(filter_terms: list[str]) -> list[Drill]:
    drills: list[Drill] = []
    for path in sorted(DRILL_DIR.glob("drill_*.py")):
        name = path.stem
        if filter_terms and not any(t in name for t in filter_terms):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        m = RESOURCE_TAG_RE.search(text)
        if m:
            tokens = [t.strip() for t in m.group(1).split() if t.strip()]
            # "none" or "readonly" → empty set (parallel with everything)
            if tokens == ["none"] or tokens == ["readonly"]:
                resources: frozenset[tuple[str, str]] = frozenset()
            else:
                resources = _parse_resource_tokens(tokens)
        else:
            resources = DEFAULT_RESOURCES
        drills.append(Drill(name=name, path=path, resources=resources))
    return drills


class _ResourceTable:
    """Per-resource reader-count + writer-flag.

    Semantics: a resource held in "read" mode by any drill permits
    other "read" acquires on the same resource; a "write" acquire
    needs the resource to have ZERO holders (no readers, no writer).
    Classic read-write lock, per resource.

    Uses ``asyncio.Condition`` + predicate-wait; an ``Event`` has a
    clear/set race where a third acquire can clear the event between
    a release and a waiter's wake-up, parking waiters forever. Hit
    that bug first pass — the comment is the tombstone.
    """

    def __init__(self) -> None:
        # resource_name → {"readers": int, "writer": bool}
        self._state: dict[str, dict[str, int | bool]] = {}
        self._cond = asyncio.Condition()

    def _compatible(self, resources: frozenset[tuple[str, str]]) -> bool:
        for name, mode in resources:
            s = self._state.get(name)
            if s is None:
                continue
            if mode == "write":
                # Need zero holders.
                if s.get("writer") or (s.get("readers", 0) or 0) > 0:
                    return False
            else:  # read
                # Need no writer; other readers are fine.
                if s.get("writer"):
                    return False
        return True

    async def acquire(self, resources: frozenset[tuple[str, str]]) -> None:
        async with self._cond:
            await self._cond.wait_for(lambda: self._compatible(resources))
            for name, mode in resources:
                s = self._state.setdefault(name, {"readers": 0, "writer": False})
                if mode == "write":
                    s["writer"] = True
                else:
                    s["readers"] = (s.get("readers", 0) or 0) + 1

    async def release(self, resources: frozenset[tuple[str, str]]) -> None:
        async with self._cond:
            for name, mode in resources:
                s = self._state.get(name)
                if not s:
                    continue
                if mode == "write":
                    s["writer"] = False
                else:
                    s["readers"] = max(0, (s.get("readers", 0) or 0) - 1)
            self._cond.notify_all()


def _launch_and_wait(path: Path, env: dict[str, str]) -> tuple[int, str]:
    """Run a drill via subprocess.run (argv list, no shell). Blocks the
    current thread until the drill exits — callers invoke this inside
    ``asyncio.to_thread`` so multiple drills can run concurrently."""
    result = subprocess.run(
        [PY_BIN, str(path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
        check=False,
    )
    return result.returncode, result.stdout.decode(errors="replace")


async def _run_one(
    drill: Drill,
    table: _ResourceTable,
    max_concurrency: asyncio.Semaphore,
) -> None:
    async with max_concurrency:
        await table.acquire(drill.resources)
        try:
            drill.status = "running"
            t0 = time.monotonic()
            env = os.environ.copy()
            env["PYTHONPATH"] = str(REPO)
            def _fmt(rs: frozenset[tuple[str, str]]) -> str:
                if not rs:
                    return "(none)"
                return " ".join(
                    n if m == "write" else f"{n}:read" for n, m in sorted(rs)
                )
            print(
                f"{YELLOW}▶ {drill.name}{NC} resources={_fmt(drill.resources)}",
                flush=True,
            )
            drill.exit_code, text = await asyncio.to_thread(
                _launch_and_wait, drill.path, env,
            )
            drill.duration_s = time.monotonic() - t0
            m = RESULT_RE.search(text)
            drill.steps_passed = int(m.group(1)) if m else 0
            if drill.exit_code == 0 and m:
                drill.status = "passed"
                print(
                    f"{GREEN}✓ {drill.name}{NC} "
                    f"steps={drill.steps_passed} time={drill.duration_s:.1f}s",
                    flush=True,
                )
            else:
                drill.status = "failed"
                # Tail is useful for a quick look without re-running
                tail_lines = text.strip().splitlines()[-20:]
                drill.tail = "\n    ".join(tail_lines)
                print(
                    f"{RED}✗ {drill.name}{NC} "
                    f"exit={drill.exit_code} time={drill.duration_s:.1f}s",
                    flush=True,
                )
        finally:
            await table.release(drill.resources)


async def _run_all(
    drills: list[Drill], parallel: int, stop_on_fail: bool,
) -> int:
    table = _ResourceTable()
    sem = asyncio.Semaphore(max(1, parallel))
    tasks: list[asyncio.Task] = [
        asyncio.create_task(_run_one(d, table, sem)) for d in drills
    ]
    if stop_on_fail:
        # Watchdog: cancel the rest as soon as any one drill fails.
        async def _watchdog() -> None:
            while not all(t.done() for t in tasks):
                await asyncio.sleep(0.5)
                if any(d.status == "failed" for d in drills):
                    for t in tasks:
                        if not t.done():
                            t.cancel()
                    return
        tasks.append(asyncio.create_task(_watchdog()))
    await asyncio.gather(*tasks, return_exceptions=True)
    failed = [d for d in drills if d.status == "failed"]
    return 0 if not failed else 1


def _list(drills: list[Drill]) -> None:
    print(f"{BOLD}Discovered drills:{NC}")
    for d in drills:
        if not d.resources:
            r = "(none — pure reads)"
        else:
            r = " ".join(
                n if m == "write" else f"{n}:read"
                for n, m in sorted(d.resources)
            )
        print(f"  {d.name:<40}  resources: {r}")
    print(f"\n{len(drills)} drills.")


def _junit_xml(drills: list[Drill], elapsed: float) -> str:
    """Emit a minimal JUnit-XML document with one <testsuite> wrapping
    one <testcase> per drill. Sufficient for GitHub Actions
    test-reporter, Jenkins, and any JUnit consumer."""
    def _esc(s: str) -> str:
        return (
            s.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;")
             .replace('"', "&quot;")
             .replace("\n", "&#10;")
        )

    passed = sum(1 for d in drills if d.status == "passed")
    failed = sum(1 for d in drills if d.status == "failed")
    skipped = sum(1 for d in drills if d.status in ("pending", "skipped"))
    total = len(drills)

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            f'<testsuite name="documind-drills" tests="{total}" '
            f'failures="{failed}" skipped="{skipped}" '
            f'time="{elapsed:.3f}">'
        ),
    ]
    for d in drills:
        tags = " ".join(
            n if m == "write" else f"{n}:read" for n, m in sorted(d.resources)
        ) or "(none)"
        lines.append(
            f'  <testcase classname="drills" name="{_esc(d.name)}" '
            f'time="{d.duration_s:.3f}">'
        )
        lines.append('    <properties>')
        lines.append(f'      <property name="resources" value="{_esc(tags)}"/>')
        lines.append(f'      <property name="steps_passed" value="{d.steps_passed}"/>')
        ec = d.exit_code if d.exit_code is not None else ""
        lines.append(f'      <property name="exit_code" value="{ec}"/>')
        lines.append('    </properties>')
        if d.status == "failed":
            lines.append(
                f'    <failure message="exit {d.exit_code}" type="DrillFailure">'
                f'{_esc(d.tail)}</failure>'
            )
        elif d.status in ("pending", "skipped"):
            lines.append('    <skipped message="not run"/>')
        lines.append('  </testcase>')
    lines.append('</testsuite>')
    return "\n".join(lines) + "\n"


def _report(drills: list[Drill], elapsed: float) -> None:
    passed = [d for d in drills if d.status == "passed"]
    failed = [d for d in drills if d.status == "failed"]
    skipped = [d for d in drills if d.status in ("pending", "skipped")]
    total_steps = sum(d.steps_passed for d in passed)

    print(f"\n{BOLD}══════════════════════════════════════════════════════════{NC}")
    print(f"{BOLD}Result:{NC}  passed={len(passed)}  failed={len(failed)}  "
          f"skipped={len(skipped)}  steps={total_steps}  "
          f"wall={elapsed:.1f}s")
    if failed:
        print(f"\n{RED}Failures:{NC}")
        for d in failed:
            print(f"  ✗ {d.name}  exit={d.exit_code}  time={d.duration_s:.1f}s")
            print(f"    {d.tail}")


def main() -> int:
    p = argparse.ArgumentParser(description="Resource-aware parallel drill runner")
    p.add_argument("--parallel", type=int, default=1,
                   help="Max concurrent drills (default 1 = serial)")
    p.add_argument("--only", nargs="*", default=[],
                   help="Filter drills by substring match on the name")
    p.add_argument("--list", action="store_true",
                   help="List drills + resource tags, don't run")
    p.add_argument("--stop-on-fail", action="store_true",
                   help="Cancel remaining drills on first failure")
    p.add_argument(
        "--report",
        help=(
            "Emit a machine-readable report. Format: 'junit=<path>' writes "
            "JUnit XML. Multiple uses stack (e.g. --report junit=file.xml)."
        ),
    )
    args = p.parse_args()

    drills = _discover(args.only)
    if not drills:
        print(f"{RED}No drills match filter: {args.only}{NC}")
        return 1
    if args.list:
        _list(drills)
        return 0

    t0 = time.monotonic()
    try:
        code = asyncio.run(_run_all(drills, args.parallel, args.stop_on_fail))
    except KeyboardInterrupt:
        print(f"\n{RED}Interrupted.{NC}")
        return 130
    elapsed = time.monotonic() - t0
    _report(drills, elapsed)
    if args.report:
        if args.report.startswith("junit="):
            out_path = Path(args.report[len("junit="):])
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(_junit_xml(drills, elapsed), encoding="utf-8")
            print(f"report written: {out_path}")
        else:
            print(
                f"{RED}unknown --report format: {args.report!r} "
                f"(expected junit=<path>){NC}"
            )
            return 2
    return code


if __name__ == "__main__":
    sys.exit(main())
