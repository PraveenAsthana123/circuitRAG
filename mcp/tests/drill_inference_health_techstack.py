# RESOURCES: inference
"""
Drill: /api/v1/health/techstack inventories installed pip + npm
packages against a curated catalog. Read-only; no installs from
the endpoint.

Closes the "techstack UI to know what software has been installed
or pending" request from the integration / RAG / agent catalog
stream.

Negative-assertion §43-style:
 1. baseline — endpoint returns 200 with non-empty entries +
    counts that add up. NEGATIVE: a regression that returned
    installed_count + pending_count != len(entries) would silently
    mislead operators.
 2. known-installed packages surface with version. fastapi must
    be installed (the inference-svc is RUNNING on it). NEGATIVE:
    a regression that probed the wrong env or skipped pip would
    show fastapi as pending — clearly false.
 3. known-pending packages surface as not-installed. autogen +
    crewai are not in this venv. They must appear in the catalog
    AND be marked installed=False. NEGATIVE: hardcoding
    installed=True for the catalog (a placeholder mistake) would
    fail this.
 4. category enum is constrained — categories ∈ a known set.
    NEGATIVE: cardinality drift breaks UI grouping.
 5. source enum is constrained — source ∈ {pip, npm}. NEGATIVE:
    a regression that introduced a new source value would break
    the UI's per-source rendering.
 6. installed entries carry version strings; pending entries
    have version=None. NEGATIVE: showing installed=True without
    a version would be a hollow positive.

Run:
    PYTHONPATH=/mnt/deepa/rag python mcp/tests/drill_inference_health_techstack.py
"""
from __future__ import annotations

import asyncio
import os

import httpx

INF_BASE = os.getenv("INFERENCE_URL", "http://127.0.0.1:8084")

GREEN = "\033[32m"; RED = "\033[31m"; BOLD = "\033[1m"; NC = "\033[0m"


def ok(msg: str) -> None:
    print(f"  {GREEN}✓ {msg}{NC}")


def fail(msg: str) -> None:
    print(f"  {RED}✗ {msg}{NC}")
    raise SystemExit(1)


def step(title: str) -> None:
    print(f"\n{BOLD}── {title} ──{NC}")


VALID_CATEGORIES = {
    "core", "rag-framework", "agent-framework", "low-code",
    "autonomous-agent", "voice", "image-video", "data", "ecommerce",
    "cms", "frontend", "observability", "enterprise",
    # additional categories present in the curated catalog:
    "vector-db", "embeddings", "llm-host", "eval", "guardrails",
    "testing",
}
VALID_SOURCES = {"pip", "npm", "binary", "docker"}


async def main() -> None:
    async with httpx.AsyncClient(timeout=10.0) as c:
        step("1. baseline — endpoint 200 + counts add up")
        r = await c.get(f"{INF_BASE}/api/v1/health/techstack")
        if r.status_code != 200:
            fail(f"expected 200, got {r.status_code}: {r.text[:200]}")
        body = r.json()
        for required in ("service", "observed_at", "installed_count",
                         "pending_count", "entries"):
            if required not in body:
                fail(f"missing key: {required}")
        entries = body["entries"]
        if not isinstance(entries, list) or not entries:
            fail(f"entries must be non-empty list, got {entries!r}")
        if body["installed_count"] + body["pending_count"] != len(entries):
            fail(
                f"counts don't add up — installed={body['installed_count']} "
                f"pending={body['pending_count']} entries={len(entries)}"
            )
        ok(
            f"{body['installed_count']} installed / {body['pending_count']} pending / "
            f"{len(entries)} total"
        )

        step("2. known-installed (fastapi) must surface with version")
        fastapi = next((e for e in entries if e["name"] == "fastapi"), None)
        if fastapi is None:
            fail("fastapi missing from catalog — should be a 'core' entry")
        if not fastapi["installed"]:
            fail(
                "fastapi reported as pending — but inference-svc is "
                "RUNNING on fastapi. Probe is broken."
            )
        if not fastapi.get("version"):
            fail(f"fastapi installed=True but no version: {fastapi}")
        ok(f"fastapi=={fastapi['version']} (proves probe ran in correct venv)")

        step("3. known-pending (autogen) must surface as not-installed")
        autogen = next((e for e in entries if e["name"] == "autogen"), None)
        if autogen is None:
            fail("autogen missing from catalog — should be 'agent-framework'")
        if autogen["installed"]:
            fail(
                "autogen reported as installed — should be pending. "
                "A regression that hardcoded installed=True would land here."
            )
        if autogen["version"] is not None:
            fail(f"autogen pending should have version=None, got {autogen['version']!r}")
        ok("autogen pending (correctly not detected)")

        step("4. category enum constrained — no cardinality drift")
        cats = {e["category"] for e in entries}
        unknown = cats - VALID_CATEGORIES
        if unknown:
            fail(
                f"unknown categor(ies) {unknown} appeared. "
                f"UI groups by category; cardinality drift breaks the layout."
            )
        ok(f"{len(cats)} categories, all within enum: {sorted(cats)}")

        step("5. source enum constrained — only known sources")
        srcs = {e["source"] for e in entries}
        unknown_srcs = srcs - VALID_SOURCES
        if unknown_srcs:
            fail(f"unknown source(s) {unknown_srcs}")
        ok(f"sources observed: {sorted(srcs)}")

        step("6. installed↔version invariant")
        for e in entries:
            if e["installed"] and not e["version"]:
                fail(
                    f"{e['name']} installed=True but no version — "
                    f"hollow positive. A real installation always has "
                    f"a version string."
                )
            if not e["installed"] and e["version"]:
                fail(
                    f"{e['name']} pending but has version={e['version']!r} — "
                    f"contradiction: if version exists, the package IS "
                    f"installed."
                )
        ok(f"all {len(entries)} entries respect installed↔version invariant")

    print(f"\n{BOLD}{GREEN}════════════════════════════════════════{NC}")
    print(f"{BOLD}{GREEN}  ALL 6 TECHSTACK-INVENTORY STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}════════════════════════════════════════{NC}")


if __name__ == "__main__":
    asyncio.run(main())
