#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: Langfuse compose wiring + runbook contract.

Locks the langfuse service block in docker-compose.yml + the
operator runbook so future drift can't:
  - silently expose Langfuse on the default profile (philosophy
    violation — opt-in only)
  - lose the .loop/<svc>.env secret pattern from the runbook
  - hardcode dev-only NEXTAUTH_SECRET as the prod default (the
    'CHANGE_ME' marker must remain so prod operators know to set it)

Negative assertions: service block missing; profiles directive
missing or empty; runbook absent or stripped of secret pattern;
NEXTAUTH_SECRET hardcoded without CHANGE_ME marker; port collides
with grafana 3001.
"""
from __future__ import annotations

import re
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
COMPOSE = REPO / "docker-compose.yml"
RUNBOOK = REPO / "docs" / "runbooks" / "langfuse.md"


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise AssertionError(f"missing {label}: {needle!r}")


def main() -> int:
    print("-- 1. POSITIVE: docker-compose.yml has langfuse service block --")
    compose = COMPOSE.read_text(encoding="utf-8")
    require(compose, "  langfuse:", "langfuse service block")
    require(compose, "documind-langfuse", "langfuse container_name")
    require(compose, "langfuse/langfuse:2", "langfuse image tag pin")
    print("  ok: langfuse block present + image pinned")

    print("-- 2. POSITIVE: langfuse depends on postgres --")
    block_match = re.search(
        r"^  langfuse:\n(.*?)(?=\n  [a-z]|\nvolumes:|\Z)",
        compose,
        re.DOTALL | re.MULTILINE,
    )
    if not block_match:
        raise AssertionError("could not extract langfuse service block")
    block = block_match.group(1)
    require(block, "depends_on:", "depends_on section")
    require(block, "postgres:", "postgres dep")
    require(block, "service_healthy", "service_healthy condition")
    print("  ok: depends_on postgres service_healthy")

    print("-- 3. POSITIVE: healthcheck on /api/public/health --")
    require(block, "healthcheck:", "healthcheck section")
    require(block, "/api/public/health", "langfuse health endpoint")
    print("  ok: healthcheck on /api/public/health")

    print("-- 4. NEGATIVE: langfuse MUST be opt-in via profiles --")
    # Per file-header philosophy + the api-gateway precedent (commit
    # 4f8e1b0). Default `docker compose up` excludes langfuse.
    require(block, "profiles:", "profiles directive")
    require(block, '"observability"', "observability profile token")
    print("  ok: langfuse opt-in via profiles: [\"observability\"]")

    print("-- 5. NEGATIVE: NEXTAUTH_SECRET MUST carry CHANGE_ME marker --")
    # If a future commit replaces 'CHANGE_ME...' with a real-looking
    # default, prod deploys may inherit the dev secret. Drill catches.
    require(block, "CHANGE_ME", "CHANGE_ME marker in dev secrets")
    require(block, "NEXTAUTH_SECRET", "NEXTAUTH_SECRET env")
    require(block, "SALT", "SALT env")
    print("  ok: dev secrets carry CHANGE_ME marker")

    print("-- 6. NEGATIVE: port MUST NOT collide with grafana (3001) --")
    # langfuse uses 3000 internally. Must publish to 3002 (or any
    # non-3001) to coexist with grafana on 3001.
    port_match = re.search(r'-\s*"(\d+):3000"', block)
    if not port_match:
        raise AssertionError("langfuse port mapping not found")
    host_port = port_match.group(1)
    if host_port == "3001":
        raise AssertionError(
            f"langfuse host port {host_port} collides with grafana"
        )
    print(f"  ok: langfuse publishes to host port {host_port} (not 3001)")

    print("-- 7. POSITIVE: runbook present + cites secret pattern --")
    if not RUNBOOK.exists():
        raise AssertionError(f"missing {RUNBOOK.relative_to(REPO)}")
    runbook = RUNBOOK.read_text(encoding="utf-8")
    for needle, label in [
        ("Langfuse", "langfuse heading"),
        (".loop/langfuse.env", ".loop/ secret pattern"),
        ("chmod 600", "chmod 600 discipline"),
        ("LANGFUSE_PUBLIC_KEY", "public key env reference"),
        ("LANGFUSE_SECRET_KEY", "secret key env reference"),
    ]:
        require(runbook, needle, label)
    print("  ok: runbook documents secret pattern + key envs")

    print("-- 8. NEGATIVE: runbook MUST cite the brutal rule + cost-benefit --")
    # Without a clear cost-benefit anchor, operators may run langfuse
    # continuously and pay token-cost overhead without LLM-call needs.
    require(runbook, "Brutal rule", "Brutal rule heading")
    require(runbook, "FinOps", "FinOps tie-back")
    print("  ok: Brutal rule + FinOps tie-back present")

    print("-- 9. POSITIVE: runbook documents wiring example for Python service --")
    require(runbook, "@observe()", "@observe decorator example")
    require(runbook, "langfuse_context", "langfuse_context import")
    print("  ok: wiring example present")

    print("\nALL 9 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
