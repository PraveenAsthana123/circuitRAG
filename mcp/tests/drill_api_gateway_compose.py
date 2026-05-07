#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: api-gateway compose wiring + nginx upstream.

Locks the api-gateway entry in docker-compose.yml + nginx upstream
that routes through it. Without this drill, the api-gateway service
block can silently regress to "code only" status and traffic would
skip the gateway's middleware chain (JWT, rate limit, audit).

Negative assertions cover: api-gateway service block missing; build
context wrong; healthcheck missing; nginx upstream not pointing at
api-gateway:8080; no fallback to host.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
COMPOSE = REPO / "docker-compose.yml"
NGINX = REPO / "infra" / "nginx" / "nginx.conf"
GATEWAY_DIR = REPO / "services" / "api-gateway"


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise AssertionError(f"missing {label}: {needle!r}")


def main() -> int:
    print("-- 1. POSITIVE: api-gateway service code exists --")
    if not GATEWAY_DIR.exists():
        raise AssertionError(f"missing {GATEWAY_DIR.relative_to(REPO)}")
    if not (GATEWAY_DIR / "Dockerfile").exists():
        raise AssertionError("api-gateway Dockerfile missing")
    if not (GATEWAY_DIR / "cmd" / "main.go").exists():
        raise AssertionError("api-gateway cmd/main.go missing")
    print("  ok: services/api-gateway/ exists with Dockerfile + cmd/main.go")

    print("-- 2. POSITIVE: docker-compose.yml has api-gateway service block --")
    compose = COMPOSE.read_text(encoding="utf-8")
    require(compose, "  api-gateway:", "api-gateway service block")
    require(compose, "documind-api-gateway", "container_name")
    print("  ok: api-gateway service block present")

    print("-- 3. POSITIVE: build context points at services/api-gateway/Dockerfile --")
    # Block from "  api-gateway:" until next 2-space-indented service or EOF
    block_match = re.search(
        r"^  api-gateway:\n(.*?)(?=\n  [a-z]|\nvolumes:|\Z)",
        compose,
        re.DOTALL | re.MULTILINE,
    )
    if not block_match:
        raise AssertionError("could not extract api-gateway service block")
    block = block_match.group(1)
    require(block, "services/api-gateway/Dockerfile", "Dockerfile path")
    print("  ok: build context references services/api-gateway/Dockerfile")

    print("-- 4. POSITIVE: api-gateway exposes port 8080 --")
    require(block, "8080:8080", "port 8080:8080 mapping")
    print("  ok: 8080:8080 port mapping")

    print("-- 5. POSITIVE: api-gateway healthcheck on /healthz --")
    require(block, "healthcheck:", "healthcheck section")
    require(block, "/healthz", "/healthz path in healthcheck")
    print("  ok: healthcheck on /healthz")

    print("-- 6. POSITIVE: api-gateway depends on redis (rate-limit backend) --")
    require(block, "redis:", "depends_on redis")
    require(block, "service_healthy", "service_healthy condition")
    print("  ok: depends_on redis service_healthy")

    print("-- 7. NEGATIVE: api-gateway env MUST NOT hardcode JWKS URI --")
    # Hardcoded JWKS would couple gateway to identity-svc routing.
    # Must be env-overrideable.
    if 'API_GATEWAY_JWKS_URI: "http' in block and "${" not in block:
        raise AssertionError(
            "API_GATEWAY_JWKS_URI must be env-overrideable, not hardcoded"
        )
    require(block, "${API_GATEWAY_JWKS_URI", "JWKS env-overrideable")
    print("  ok: JWKS URI is env-overrideable with default fallback")

    print("-- 8. POSITIVE: nginx upstream gateway includes api-gateway:8080 --")
    nginx = NGINX.read_text(encoding="utf-8")
    upstream_match = re.search(
        r"upstream gateway \{(.*?)\}", nginx, re.DOTALL
    )
    if not upstream_match:
        raise AssertionError("nginx upstream gateway block missing")
    upstream = upstream_match.group(1)
    require(upstream, "api-gateway:8080", "container-DNS upstream entry")
    print("  ok: nginx upstream gateway points at api-gateway:8080")

    print("-- 9. NEGATIVE: nginx upstream MUST keep host fallback as backup --")
    # If the operator runs api-gateway natively (outside compose), the
    # host.docker.internal entry must still be reachable. The 'backup'
    # keyword ensures nginx prefers the container DNS but falls back.
    if "host.docker.internal:8080" not in upstream:
        raise AssertionError(
            "nginx upstream lost host.docker.internal:8080 fallback — "
            "natively-running gateway will be unreachable"
        )
    if "backup" not in upstream:
        raise AssertionError(
            "host.docker.internal entry must carry 'backup' keyword so it "
            "fires only when api-gateway:8080 is dead"
        )
    print("  ok: host.docker.internal:8080 backup fallback preserved")

    print("-- 10. NEGATIVE: api-gateway entry MUST NOT bypass NGINX --")
    # The api-gateway must sit BEHIND nginx per main.go's docstring.
    # If a future change exposes :8080 as the public ingress (replacing
    # nginx), the trust-boundary contract breaks. Drill flags any
    # 'profiles: [public]' or similar exposure pattern.
    if "profiles:" in block:
        # Inspect profile values; reject any 'public' / 'edge' label
        prof_match = re.search(r"profiles:\s*\[([^\]]*)\]", block)
        if prof_match:
            profiles = [p.strip().strip('"').strip("'") for p in prof_match.group(1).split(",")]
            for forbidden in ("public", "edge", "ingress"):
                if forbidden in profiles:
                    raise AssertionError(
                        f"api-gateway carries {forbidden!r} profile — it must "
                        f"sit BEHIND nginx, not be the public ingress"
                    )
    print("  ok: api-gateway does not bypass NGINX as public ingress")

    print("-- 11. POSITIVE: api-gateway is opt-in via profiles --")
    # File-header philosophy: "Application services are run natively".
    # api-gateway in compose must be opt-in (profiles: [app]) so default
    # `docker compose up` excludes it; explicit `--profile app` to enable.
    require(block, "profiles:", "profiles directive (opt-in)")
    require(block, '"app"', "app profile token")
    print("  ok: api-gateway is opt-in via profiles: [\"app\"]")

    print("\nALL 11 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
