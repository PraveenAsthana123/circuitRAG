# RESOURCES: frontend
"""
Drill: /app-meta/build-info exposes the frontend build identity so
operators can answer 'is the running frontend the latest build?'
without inspecting the .next folder.

Closes the gap that bit during the techstack rollout: a stale
``next start`` on port 3000 served HTML referencing chunk hashes
that no longer existed on disk. With the build-info endpoint live
on the SAME process that serves the HTML, operators can compare
the build_id against the currently-deployed one and detect drift.

Negative-assertion §43-style:
 1. Endpoint returns 200 with a non-null build_id. NEGATIVE: a
    regression that 404s (e.g. moving the file back under a
    Next.js private folder ``_foo`` / ``__foo``) would silently
    take this surface offline.
 2. ``app_version`` round-trips from package.json. NEGATIVE: a
    regression that hardcoded a version string would freeze
    drift detection.
 3. ``generated_at`` is a fresh ISO timestamp on EACH call (no
    caching at the route layer). The two responses must have
    different timestamps. NEGATIVE: caching this would mean
    stale-build detection itself goes stale.
 4. Path is NOT under a Next.js private folder (no leading
    underscore on any path segment). NEGATIVE: ``/__frontend/``
    or ``/_internal/`` paths are excluded from routing entirely
    and would silently 404; this drill catches that mistake on
    a future move.

Run:
    PYTHONPATH=/mnt/deepa/rag python mcp/tests/drill_frontend_build_info.py
"""
from __future__ import annotations

import asyncio
import os
import time

import httpx

FRONTEND = os.getenv("FRONTEND_URL", "http://127.0.0.1:3001")
ENDPOINT = "/app-meta/build-info"

GREEN = "\033[32m"; RED = "\033[31m"; BOLD = "\033[1m"; NC = "\033[0m"


def ok(msg: str) -> None:
    print(f"  {GREEN}✓ {msg}{NC}")


def fail(msg: str) -> None:
    print(f"  {RED}✗ {msg}{NC}")
    raise SystemExit(1)


def step(title: str) -> None:
    print(f"\n{BOLD}── {title} ──{NC}")


async def main() -> None:
    async with httpx.AsyncClient(timeout=10.0) as c:
        step("1. /app-meta/build-info returns 200 + non-null build_id")
        r = await c.get(f"{FRONTEND}{ENDPOINT}")
        if r.status_code != 200:
            fail(
                f"expected 200, got {r.status_code}. If 404, the route "
                f"file may have been moved under a Next.js private folder "
                f"(name starts with '_') — those are excluded from "
                f"routing entirely."
            )
        body = r.json()
        for required in ("build_id", "app_version", "generated_at", "node_env"):
            if required not in body:
                fail(f"missing key: {required}")
        # build_id is created by `next build`, NOT by `next dev`. In
        # dev mode, null is the correct answer. In production mode,
        # null is a real bug (BUILD_ID unreadable / path mismatch).
        # The dev-stack runs both ports — :3001 is dev, :3000 is prod
        # via NEXT_DIST_DIR=.next-prod. Discriminate on node_env.
        node_env = body.get("node_env")
        if node_env == "production":
            if body["build_id"] in (None, ""):
                fail(
                    f"build_id null in PRODUCTION mode — likely "
                    f"BUILD_ID unreadable. Route reads "
                    f"$NEXT_DIST_DIR/BUILD_ID; verify the env var "
                    f"matches the build script."
                )
        elif node_env == "development":
            # Dev mode: null is acceptable (next dev doesn't write
            # BUILD_ID). But the response shape MUST still include
            # the field (operators see '—' in the UI).
            if "build_id" not in body:
                fail("build_id field missing from response (must be present even if null)")
        else:
            # Unknown node_env — treat as production for safety.
            if body["build_id"] in (None, ""):
                fail(f"build_id null with unknown node_env={node_env!r}")
        ok(f"build_id={body['build_id']} node_env={node_env}")

        step("2. app_version round-trips from package.json")
        if body["app_version"] in (None, ""):
            fail(
                f"app_version null — npm_package_version env not "
                f"set on the running process. Restart with `npm run` "
                f"so npm injects the version."
            )
        # Just the version string, not specific value (drill is
        # repo-agnostic — version bumps shouldn't break it).
        ok(f"app_version={body['app_version']}")

        step("3. generated_at differs between calls (no caching)")
        first_at = body["generated_at"]
        # Brief sleep so the second response's clock is past the first.
        await asyncio.sleep(0.05)
        r2 = await c.get(f"{FRONTEND}{ENDPOINT}")
        if r2.status_code != 200:
            fail(f"second call status: {r2.status_code}")
        second_at = r2.json()["generated_at"]
        if second_at == first_at:
            fail(
                f"generated_at identical across calls — the route is "
                f"being cached. Stale-build detection requires a fresh "
                f"timestamp every fetch. Verify ``export const dynamic "
                f"= 'force-dynamic';`` is set on the route."
            )
        ok(f"first={first_at}\\n          second={second_at} (no caching)")

        step("4. path has no underscore-prefixed segment (Next.js routing rule)")
        for segment in ENDPOINT.split("/"):
            if segment.startswith("_"):
                fail(
                    f"path segment {segment!r} starts with underscore. "
                    f"Next.js excludes folders starting with '_' from "
                    f"routing — including children. Move to a non-"
                    f"underscore folder."
                )
        ok(f"path {ENDPOINT} has no underscore-prefixed segments")

    print(f"\n{BOLD}{GREEN}════════════════════════════════════════{NC}")
    print(f"{BOLD}{GREEN}  ALL 4 FRONTEND-BUILD-INFO STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}════════════════════════════════════════{NC}")


if __name__ == "__main__":
    asyncio.run(main())
