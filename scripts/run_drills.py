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


# ---------------------------------------------------------------------------
# Resource healers — ensures shared infrastructure that chaos drills kill
# (typically MCP_HR via fuser -k, but also drill-spawned child subprocesses
# that terminate at end) is alive again before the next drill that needs
# it runs. Without this, one chaos drill cascades 25+ subsequent drills
# into ConnectError, even though each would pass individually.
#
# A healer is (probe_url, launch_argv, env_overrides). After a drill
# releases its 'write' lock on a resource we know how to heal, the runner
# probes; if down, it relaunches the resource as a detached subprocess
# (start_new_session=True so a future killpg/fuser doesn't take it).
# ---------------------------------------------------------------------------
_HEALER_HEALTH_URL = {
    "mcp_hr": "http://127.0.0.1:8090/health",
    "mcp_itsm": "http://127.0.0.1:8091/health",
}
_HEALER_SCRIPT = {
    "mcp_hr": REPO / "mcp" / "server_hr.py",
    "mcp_itsm": REPO / "mcp" / "server_itsm.py",
}
_HEALER_PORT_VAR = {
    "mcp_hr": ("MCP_HR_PORT", "8090"),
    "mcp_itsm": ("MCP_ITSM_PORT", "8091"),
}
# Minimum env to start an MCP server in dev-stack mode. Real env may
# carry more (Postgres credentials, OTEL endpoint) — those flow from
# os.environ.copy() at heal time. This dict only sets what's
# nonstandard or what the heal must enforce.
_HEALER_ENV_DEFAULTS = {
    "DOCUMIND_AUTH_REQUIRED": "true",
    "MCP_AUTH_REQUIRED": "true",
    "DOCUMIND_JWT_PUBLIC_KEY_PATH": str(
        REPO / "scripts" / "dev-keys" / "jwt-public.pem",
    ),
    "MCP_JWT_PUBLIC_KEY_PATH": str(
        REPO / "scripts" / "dev-keys" / "jwt-public.pem",
    ),
    "DOCUMIND_PG_HOST": "localhost",
    "DOCUMIND_PG_PORT": "55432",
    "DOCUMIND_PG_USER": "documind_app",
    "DOCUMIND_PG_PASSWORD": "documind_app",
    "DOCUMIND_PG_DB": "documind",
}


def _is_alive(url: str, timeout_s: float = 1.0) -> bool:
    """Cheap liveness probe. Any 2xx counts as alive."""
    import urllib.request
    try:
        with urllib.request.urlopen(url, timeout=timeout_s) as r:
            return 200 <= r.status < 300
    except Exception:  # noqa: BLE001 — every connection failure means "dead"
        return False


def _heal_resource(resource: str) -> str:
    """Restart a healable resource if it's dead. Returns one of:
    'alive' (probe succeeded, no action), 'healed' (we restarted it
    and it came up), 'failed' (we tried to restart but it didn't
    come up within the bound), 'unknown' (resource has no healer)."""
    url = _HEALER_HEALTH_URL.get(resource)
    if not url:
        return "unknown"
    if _is_alive(url):
        return "alive"
    script = _HEALER_SCRIPT.get(resource)
    if script is None:
        return "unknown"
    port_var, port = _HEALER_PORT_VAR[resource]
    env = os.environ.copy()
    env.update(_HEALER_ENV_DEFAULTS)
    env[port_var] = port
    env["PYTHONPATH"] = str(REPO)
    # Use the SAME log path the dev-stack startup uses, not a runner-
    # specific path. Drills like drill_otel_actor_outcome_attrs grep
    # /tmp/mcp_hr.log for actor_identified lines; if the healer writes
    # somewhere else, those drills break for an unrelated reason.
    log_paths = {
        "mcp_hr": "/tmp/mcp_hr.log",
        "mcp_itsm": "/tmp/mcp_itsm.log",
    }
    log_path = log_paths.get(resource, f"/tmp/run_drills_heal_{resource}.log")
    log_fh = open(log_path, "ab")
    # start_new_session=True puts the child in its own session so a
    # future drill's `fuser -k <port>/tcp` only kills the listener,
    # not the whole shell. The new session detaches from the runner's
    # process group too, so the child outlives the runner if needed.
    subprocess.Popen(
        [PY_BIN, str(script)],
        env=env,
        stdout=log_fh, stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    # Bound the wait — a busted restart shouldn't hang the runner
    # forever. 8s covers a cold OTel-init + Postgres-pool warmup.
    deadline = time.monotonic() + 8.0
    while time.monotonic() < deadline:
        if _is_alive(url):
            return "healed"
        time.sleep(0.3)
    return "failed"

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
            # Heal any resource the drill held in 'write' mode that
            # the drill killed and didn't restore (chaos-test pattern).
            # Only heal write-mode holds — read-mode drills don't kill.
            # The probe is fast (<10ms) when the resource is alive,
            # so the no-op case has negligible cost.
            for res_name, res_mode in drill.resources:
                if res_mode != "write":
                    continue
                if res_name not in _HEALER_HEALTH_URL:
                    continue
                outcome = await asyncio.to_thread(_heal_resource, res_name)
                if outcome == "healed":
                    print(
                        f"  {YELLOW}↻ healed {res_name} after {drill.name}{NC}",
                        flush=True,
                    )
                elif outcome == "failed":
                    print(
                        f"  {RED}↻ failed to heal {res_name} after "
                        f"{drill.name} — subsequent drills may flake{NC}",
                        flush=True,
                    )


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
    # XML 1.0 prohibits raw control chars 0x00-0x1F EXCEPT tab/LF/CR.
    # ANSI escape sequences in drill output (e.g. ESC=0x1b for color
    # codes) survive into the tail and trip xml.etree's parser with
    # "not well-formed (invalid token)". Strip them before escaping.
    _CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

    def _esc(s: str) -> str:
        s = _CTRL_RE.sub("", s)
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
    p.add_argument(
        "--allow-resources",
        default=None,
        help=(
            "Comma-separated allow-list of resource names. Only drills whose "
            "resource set is a subset of this list (plus the always-allowed "
            "empty-set / 'none' / 'readonly' drills) will run. Useful for "
            "CI tiering: --allow-resources='' runs only zero-infra drills; "
            "--allow-resources=pg adds Postgres-only drills; "
            "--allow-resources=pg,inference,mcp_hr adds the full stack. "
            "Flag NOT passed = no resource filter (all drills run)."
        ),
    )
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

    # Resource-tag tier filter — used by CI to pick a subset that
    # matches the available infrastructure. Empty-resource drills
    # (tagged ``none``/``readonly``) ALWAYS pass because their
    # resource set is the empty subset of any allow-list. A non-
    # empty allow-list gates other drills: a drill is kept only
    # when every resource it declares is in the allow-list.
    # ``--allow-resources=''`` (empty string) means filter is ACTIVE
    # but the allow-list is empty — only zero-infra drills run.
    # NOT passing the flag at all means no filter — every drill runs.
    if args.allow_resources is not None:
        allowed = {
            r.strip()
            for r in args.allow_resources.split(",")
            if r.strip()
        }
        before = len(drills)
        drills = [
            d for d in drills
            if {name for name, _mode in d.resources} <= allowed
        ]
        skipped = before - len(drills)
        print(
            f"{BOLD}--allow-resources={sorted(allowed)} → kept {len(drills)} "
            f"of {before} drills (skipped {skipped} that need other "
            f"resources){NC}"
        )
        if not drills:
            print(f"{RED}No drills match resource filter{NC}")
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
