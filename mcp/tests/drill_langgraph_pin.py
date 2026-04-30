#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: LangGraph + langchain-core exact-pin contract.

Per global §16 reproducible-builds requirement, langgraph and
langchain-core MUST be pinned to exact versions in
services/agent-orchestrator-svc/requirements.txt. Range pinning
(>=1.1,<2) permits silent minor-version drift in transitive
LLM-orchestration behaviour — the kind of drift that changes agent
output without a single line of code changing in this repo.

Negative assertions cover: requirements file absent; range pin
remaining (>=, ~=, comma-separated bounds); installed version
diverges from pinned version; rationale comment stripped.
"""
from __future__ import annotations

import re
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
REQS = REPO / "services" / "agent-orchestrator-svc" / "requirements.txt"

# Exact-pin regex: package==version (no slop)
EXACT_PIN_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._\-]*)==([0-9][0-9A-Za-z.\-+]*)\s*$")
# Range markers we explicitly reject for these two packages
RANGE_MARKERS = (">=", "<=", "~=", "<", ">")
PINNED_PACKAGES = {"langgraph", "langchain-core"}


def main() -> int:
    print("-- 1. POSITIVE: orchestrator requirements file exists --")
    if not REQS.exists():
        raise AssertionError(f"missing requirements: {REQS.relative_to(REPO)}")
    text = REQS.read_text(encoding="utf-8")
    print("  ok: requirements file exists")

    print("-- 2. POSITIVE: rationale comment for exact-pin discipline present --")
    if "exact versions" not in text or "global §16" not in text:
        raise AssertionError(
            "requirements.txt must carry rationale comment citing global §16 "
            "(reproducible builds); without it future bumps lose context"
        )
    print("  ok: rationale comment cites global §16")

    print("-- 3. POSITIVE: langgraph + langchain-core both have exact == pins --")
    pinned = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-e"):
            continue
        # Strip inline comment if any
        line = line.split("#", 1)[0].strip()
        m = EXACT_PIN_RE.match(line)
        if m:
            pinned[m.group(1).lower()] = m.group(2)
    for pkg in PINNED_PACKAGES:
        if pkg not in pinned:
            raise AssertionError(
                f"{pkg} must have an exact == pin (got: {find_loose_line(text, pkg)!r})"
            )
        print(f"  ok: {pkg} pinned to {pinned[pkg]}")

    print("-- 4. NEGATIVE: no range pin (>=, <, ~=) for langgraph or langchain-core --")
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("-e"):
            continue
        # Strip inline comment
        body = stripped.split("#", 1)[0].strip()
        if not body:
            continue
        for pkg in PINNED_PACKAGES:
            # match "<pkg>" at the start, with optional extras like [foo]
            if body.lower().startswith(pkg + "==") or body.lower().startswith(pkg + "["):
                # exact-pin case (or extras with == handled later)
                if any(m in body for m in RANGE_MARKERS) and "==" not in body:
                    raise AssertionError(
                        f"{pkg} carries range marker (got: {body!r}); "
                        f"per global §16 must be exact =="
                    )
            elif body.lower().startswith(pkg + ">=") or body.lower().startswith(pkg + "~="):
                raise AssertionError(
                    f"{pkg} carries range marker (got: {body!r}); "
                    f"per global §16 must be exact =="
                )
    print("  ok: no range markers on either package")

    print("-- 5. NEGATIVE: pinned versions must match what's installed in .venv --")
    # If the .venv is unavailable, skip — but if it's present, pin must agree.
    # Otherwise we ship a pin that isn't reproducible against the dev env.
    try:
        from importlib.metadata import version as _version, PackageNotFoundError
    except Exception:
        print("  skip: importlib.metadata unavailable")
        print("\nALL 5 STEPS PASSED")
        return 0
    for pkg, want in pinned.items():
        if pkg not in PINNED_PACKAGES:
            continue
        try:
            have = _version(pkg)
        except Exception:
            print(f"  skip: {pkg} not installed in this env")
            continue
        if have != want:
            raise AssertionError(
                f"{pkg} pinned to {want} but installed version is {have}; "
                f"either bump the pin (deliberate) or reinstall (dev-env drift)"
            )
        print(f"  ok: {pkg} pin {want} matches installed {have}")

    print("\nALL 5 STEPS PASSED")
    return 0


def find_loose_line(text: str, pkg: str) -> str:
    for line in text.splitlines():
        if pkg.lower() in line.lower():
            return line.strip()
    return "<not found>"


if __name__ == "__main__":
    raise SystemExit(main())
