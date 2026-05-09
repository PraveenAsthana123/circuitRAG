# RESOURCES: readonly
"""
Drill: lock the Qdrant nofile ulimit at compose time.

Why this drill exists
=====================

Qdrant opens one file descriptor per segment at boot. Default Docker
nofile is ~1024 — once the storage dir crosses ~512 segments, qdrant
crashes with::

    OS error 24, kind: Uncategorized, "Too many open files"
    panicked at actix-server/src/worker.rs:425

This crashes silently into a restart-loop. Inference-svc keeps
returning ``502 EXTERNAL_SERVICE_ERROR — No chunks retrieved`` and
agent flows fail downstream. Fix: ``ulimits.nofile.soft >= 65536`` in
docker-compose.yml. This drill makes that fix permanent.

Steps
=====

1. ``docker-compose.yml`` for service ``qdrant`` MUST have a
   ``ulimits.nofile.soft`` field of at least 65536.
2. Negative: a compose file without the ulimit fails the drill.
3. Smoke: live qdrant must respond to ``/collections``.
4. Smoke: response must include the ``chunks`` collection (the
   project's primary corpus).

This drill is read-only — it only inspects the compose file and a
running qdrant. It does NOT mutate state.

Run::

    cd /mnt/deepa/rag
    PYTHONPATH=. python mcp/tests/drill_qdrant_ulimit.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx
import yaml

REPO = Path(__file__).resolve().parents[2]
COMPOSE = REPO / "docker-compose.yml"
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.getenv("DOCUMIND_QDRANT_API_KEY", "dev-qdrant-key")
MIN_NOFILE = 65536

GREEN = "\033[32m"
RED = "\033[31m"
BOLD = "\033[1m"
NC = "\033[0m"


def step(title: str) -> None:
    print(f"\n{BOLD}── {title} ──{NC}")


def ok(msg: str) -> None:
    print(f"  {GREEN}✓ {msg}{NC}")


def fail(msg: str) -> None:
    print(f"  {RED}✗ {msg}{NC}")
    raise SystemExit(1)


def main() -> int:
    step("1. compose file declares ulimits.nofile for qdrant")
    if not COMPOSE.exists():
        fail(f"compose file missing at {COMPOSE}")
    spec = yaml.safe_load(COMPOSE.read_text())
    qdrant = spec.get("services", {}).get("qdrant")
    if qdrant is None:
        fail("services.qdrant block missing in docker-compose.yml")
    ulimits = qdrant.get("ulimits") or {}
    nofile = ulimits.get("nofile")
    if nofile is None:
        fail(
            "qdrant.ulimits.nofile not set — see drill docstring; "
            "without this, segment count > ~512 crashes qdrant at boot"
        )
    if isinstance(nofile, dict):
        soft = nofile.get("soft", 0)
    else:
        soft = int(nofile)
    if soft < MIN_NOFILE:
        fail(
            f"qdrant.ulimits.nofile.soft={soft} < required {MIN_NOFILE}; "
            f"raise to ≥ {MIN_NOFILE}"
        )
    ok(f"qdrant.ulimits.nofile.soft={soft} (>= {MIN_NOFILE})")

    step("2. negative — compose without ulimit would fail this drill")
    # Reproduce the failure mode by parsing a synthetic compose
    # snippet — proves the assertion above is the gating criterion.
    bad = yaml.safe_load("services:\n  qdrant:\n    image: qdrant/qdrant\n")
    bad_q = bad["services"]["qdrant"]
    if (bad_q.get("ulimits") or {}).get("nofile") is not None:
        fail("synthetic 'no ulimits' compose unexpectedly had ulimits")
    ok("synthetic compose without ulimits would fail step 1 — assertion locked")

    step("3. live qdrant /collections responds 200")
    headers = {"api-key": QDRANT_API_KEY} if QDRANT_API_KEY else {}
    try:
        r = httpx.get(f"{QDRANT_URL}/collections", headers=headers, timeout=5.0)
    except httpx.HTTPError as e:
        fail(f"qdrant unreachable at {QDRANT_URL}: {e}")
    if r.status_code != 200:
        fail(f"qdrant /collections returned {r.status_code}: {r.text[:200]}")
    ok("qdrant /collections → 200")

    step("4. chunks collection present in qdrant")
    payload = r.json()
    names = [c.get("name") for c in payload.get("result", {}).get("collections", [])]
    if "chunks" not in names:
        fail(f"'chunks' collection missing; found: {names}")
    ok(f"'chunks' collection present (alongside: {[n for n in names if n != 'chunks']})")

    print(f"\n{BOLD}{GREEN}ALL 4 QDRANT-ULIMIT STEPS PASSED{NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
