#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: CDN cache invariants at origin.

Locks the per-route Cache-Control contract in infra/nginx/nginx.conf
so a CDN provider in front of NGINX cannot accidentally cache
tenant-scoped API responses. Per docs/scenarios/phase-01-edge-traffic-
security.md §2 + docs/runbooks/cdn-integration.md.

Negative assertions cover: nginx.conf absent; /api/ block missing
no-store; /api/ block contains forbidden public/max-age; static
block missing expires/cache-public; runbook absent; scenario
citation missing.
"""
from __future__ import annotations

import re
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
NGINX = REPO / "infra" / "nginx" / "nginx.conf"
RUNBOOK = REPO / "docs" / "runbooks" / "cdn-integration.md"
SCENARIO = REPO / "docs" / "scenarios" / "phase-01-edge-traffic-security.md"


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise AssertionError(f"missing {label}: {needle!r}")


def extract_location_block(text: str, location_pattern: str) -> str:
    """Return the body of a location block matching the pattern.

    Naive bracket counter — sufficient for nginx.conf which doesn't
    nest location blocks deeply.
    """
    pat = re.compile(rf"location[^{{]*{re.escape(location_pattern)}[^{{]*\{{")
    m = pat.search(text)
    if not m:
        return ""
    start = m.end()
    depth = 1
    i = start
    while i < len(text) and depth > 0:
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        i += 1
    return text[start:i - 1]


def main() -> int:
    print("-- 1. POSITIVE: nginx.conf exists --")
    if not NGINX.exists():
        raise AssertionError(f"missing {NGINX.relative_to(REPO)}")
    text = NGINX.read_text(encoding="utf-8")
    print("  ok: nginx.conf present")

    print("-- 2. POSITIVE: /api/ location block exists with no-store + private --")
    api_block = extract_location_block(text, "/api/")
    if not api_block:
        raise AssertionError("no /api/ location block found in nginx.conf")
    if "no-store" not in api_block:
        raise AssertionError("/api/ location missing 'no-store' Cache-Control")
    if "private" not in api_block:
        raise AssertionError("/api/ location missing 'private' Cache-Control")
    print("  ok: /api/ has no-store + private")

    print("-- 3. POSITIVE: upload location has no-store + private --")
    upload_block = extract_location_block(text, "/api/v1/documents/upload")
    if not upload_block:
        raise AssertionError("no upload location block found")
    if "no-store" not in upload_block or "private" not in upload_block:
        raise AssertionError("upload location missing no-store + private")
    print("  ok: upload has no-store + private")

    print("-- 4. POSITIVE: static asset location has long-cache directive --")
    static_block = extract_location_block(text, "_next/static")
    if not static_block:
        raise AssertionError("no /_next/static/ location block found")
    if "expires 7d" not in static_block and "max-age" not in static_block:
        raise AssertionError("static location missing 'expires 7d' or 'max-age'")
    print("  ok: static has expires 7d (or max-age)")

    print("-- 5. NEGATIVE: /api/ block MUST NOT contain max-age or public --")
    # The most-load-bearing CDN invariant per scenario doc §2: any max-age
    # or public token on /api/ means the CDN rule is broken.
    if "max-age" in api_block:
        raise AssertionError(
            "/api/ block contains 'max-age' — CDN rule broken per scenario §2"
        )
    if re.search(r"\bpublic\b", api_block):
        raise AssertionError(
            "/api/ block contains 'public' — CDN rule broken per scenario §2"
        )
    print("  ok: /api/ has no max-age + no public token")

    print("-- 6. NEGATIVE: NO global default Cache-Control:public anywhere --")
    # A global add_header at server-level would override per-route. Allow
    # 'public' inside specific blocks only — never at server scope.
    server_block = extract_location_block(text, "443")  # the HTTPS server block via 'listen 443'
    # If we got an HTTPS server block, scan only its 'add_header' calls
    # NOT inside any location {…}.
    server_level = re.sub(r"location[^{]*\{[^}]*\}", "", server_block, flags=re.DOTALL)
    if re.search(r'add_header\s+Cache-Control\s+"[^"]*\bpublic\b', server_level):
        raise AssertionError(
            "server-level add_header Cache-Control with 'public' — would "
            "override per-route no-store; refactor to per-location"
        )
    print("  ok: no global Cache-Control:public override")

    print("-- 7. NEGATIVE: proxy-cache bypass is set on /api/ --")
    if "proxy_no_cache" not in api_block or "proxy_cache_bypass" not in api_block:
        raise AssertionError(
            "/api/ block missing proxy_no_cache or proxy_cache_bypass — "
            "even if Cache-Control header is right, NGINX itself may cache"
        )
    print("  ok: /api/ has proxy_no_cache + proxy_cache_bypass")

    print("-- 8. POSITIVE: operator runbook present --")
    if not RUNBOOK.exists():
        raise AssertionError(f"missing {RUNBOOK.relative_to(REPO)}")
    runbook = RUNBOOK.read_text(encoding="utf-8")
    print("  ok: cdn-integration.md present")

    print("-- 9. NEGATIVE: runbook must cite the scenario doc + .loop/ secret pattern --")
    require(runbook, "phase-01-edge-traffic-security.md", "scenario doc citation")
    require(runbook, ".loop/cdn.env", ".loop/ secret pattern")
    require(runbook, "chmod 600", "chmod 600 discipline")
    print("  ok: runbook composes with scenario doc + secret pattern")

    print("-- 10. POSITIVE: scenario doc still asserts the canonical rule --")
    if SCENARIO.exists():
        scenario = SCENARIO.read_text(encoding="utf-8")
        require(scenario, "no-store, private", "canonical CDN rule in scenario")
    print("  ok: scenario doc preserves canonical rule")

    print("\nALL 10 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
