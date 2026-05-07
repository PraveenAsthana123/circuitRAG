#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: services/frontend/app/api/v1/tts/route.ts structural contract.

The TTS proxy was added in commit 51bac70 (G-2, parallel-tool-
authored, 31 frontend files, +5169/-356) without an autonomous-loop
drill. Per ADR-020 it should have been audited within 2 iterations
of landing; we are at iteration 4+ since 51bac70. This drill closes
the ADR-020 gap on that one route.

Why this surface matters: the route is the only server-side
write-surface in the frontend (POST /api/v1/tts). It proxies to
four providers (kokoro_local → piper_http → piper_local → openai)
with audit logging, input caps, and failover. A regression here
is a real risk:

* Removed input cap → unbounded text → runaway OpenAI cost.
* Lost audit log → silent side-effects, no observability.
* Hardcoded OPENAI_API_KEY → secret leak.
* Missing failover stamp → operator cannot triage which provider
  served a request.

The drill locks all four invariants at the source-code level
(pure regex / Python parsing of TypeScript; no Next.js runtime).

Eight steps. Six negative assertions.

  1. POSITIVE: route file exists at the canonical path with
     non-trivial body. Without the file the endpoint is dead.
  2. NEGATIVE: file exports both POST AND GET async functions.
     POST = synthesise; GET = fetch audit row by id. Either
     missing breaks the contract.
  3. NEGATIVE: MAX_TEXT_CHARS constant is declared with value
     4000 (or higher; never lower). The cap protects against
     runaway OpenAI cost on an unbounded text payload.
  4. NEGATIVE: audit file path includes 'tts-audit.jsonl' — the
     project-conventional audit log location. Without the audit
     log the proxy ships silent side-effects.
  5. NEGATIVE: OPENAI_API_KEY is read from process.env (never
     hardcoded). Any string literal that looks like an OpenAI
     API key (sk-... pattern) in source = security regression.
  6. NEGATIVE: provider chain references all four named
     providers (kokoro_local, piper_http, piper_local, openai).
     A regression that drops a provider silently would leave
     the failover incomplete.
  7. NEGATIVE: failover_chain is included in the JSON response
     body AND in the audit row. Without it operators cannot
     triage which provider served a given request.
  8. POSITIVE: emit per-provider env-var inventory (operator
     visibility — which providers have keys configured).

Run: python3 mcp/tests/drill_tts_proxy_route.py
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ROUTE = REPO / "services" / "frontend" / "app" / "api" / "v1" / "tts" / "route.ts"

REQUIRED_PROVIDERS = ("kokoro_local", "piper_http", "piper_local", "openai")
MIN_TEXT_CAP = 4000
PROVIDER_ENV_VARS = {
    "kokoro_local": ("KOKORO_TTS_PYTHON", "KOKORO_MODEL_PATH", "KOKORO_VOICES_PATH"),
    "piper_http": ("PIPER_TTS_URL",),
    "piper_local": ("PIPER_TTS_BIN", "PIPER_MODEL_PATH"),
    "openai": ("OPENAI_API_KEY",),
}

GREEN = "\033[32m"
RED = "\033[31m"
BOLD = "\033[1m"
NC = "\033[0m"


def ok(msg: str) -> None:
    print(f"  {GREEN}{msg}{NC}")


def fail(msg: str) -> None:
    print(f"  {RED}x {msg}{NC}")
    raise SystemExit(1)


def step(title: str) -> None:
    print(f"\n{BOLD}-- {title} --{NC}")


def main() -> int:
    step("1. POSITIVE: route file exists with substantive body")
    if not ROUTE.is_file():
        fail(f"route missing at {ROUTE}")
    body = ROUTE.read_text()
    if len(body) < 4000:
        fail(
            f"route body suspiciously short ({len(body)} bytes); "
            "expected real implementation, not a stub"
        )
    ok(f"route exists ({len(body):,} bytes)")

    step("2. NEGATIVE: POST AND GET both exported")
    if not re.search(r"export\s+async\s+function\s+POST\s*\(", body):
        fail("export async function POST(...) missing")
    if not re.search(r"export\s+async\s+function\s+GET\s*\(", body):
        fail("export async function GET(...) missing")
    ok("both POST + GET exports present")

    step("3. NEGATIVE: MAX_TEXT_CHARS declared with value >= 4000")
    m = re.search(
        r"\bMAX_TEXT_CHARS\b\s*=\s*([\d_]+)",
        body,
    )
    if not m:
        fail("MAX_TEXT_CHARS constant not declared")
    cap_value = int(m.group(1).replace("_", ""))
    if cap_value < MIN_TEXT_CAP:
        fail(
            f"MAX_TEXT_CHARS = {cap_value} < {MIN_TEXT_CAP}; "
            "input cap weakened (cost-regression risk)"
        )
    if not re.search(
        r"text\.length\s*>\s*MAX_TEXT_CHARS|length\s*>\s*MAX_TEXT_CHARS",
        body,
    ):
        fail(
            "MAX_TEXT_CHARS declared but not enforced "
            "(no `text.length > MAX_TEXT_CHARS` guard)"
        )
    ok(f"MAX_TEXT_CHARS = {cap_value} declared AND enforced")

    step("4. NEGATIVE: audit file path includes 'tts-audit.jsonl'")
    if "tts-audit.jsonl" not in body:
        fail(
            "tts-audit.jsonl path not present; audit log destination "
            "missing means silent side-effects"
        )
    if not re.search(r"\bappendFile\s*\(", body):
        fail(
            "appendFile() not called; audit row never written even "
            "though path is declared"
        )
    ok("tts-audit.jsonl path declared AND appendFile() invoked")

    step("5. NEGATIVE: OPENAI_API_KEY read from env; no hardcoded sk-... literals")
    if not re.search(r"process\.env\.OPENAI_API_KEY", body):
        fail("process.env.OPENAI_API_KEY not referenced; missing env source")
    # Hardcoded OpenAI key pattern: sk-<>=20+ chars in a single quoted literal.
    leak_pat = re.compile(r"['\"](sk-[A-Za-z0-9_-]{20,})['\"]")
    leaks = leak_pat.findall(body)
    if leaks:
        fail(
            f"hardcoded OpenAI-key-shaped literal(s) in source: "
            f"{[l[:8] + '...' for l in leaks]}. SECURITY REGRESSION."
        )
    ok("OPENAI_API_KEY sourced from env; no hardcoded sk-... literals")

    step("6. NEGATIVE: provider chain references all four named providers")
    missing_providers = [p for p in REQUIRED_PROVIDERS if p not in body]
    if missing_providers:
        fail(
            f"provider chain incomplete; missing: {missing_providers}. "
            "Failover dropped a tier."
        )
    # Also lock the ProviderName union type so removal is loud.
    if not re.search(r"ProviderName\s*=", body):
        fail(
            "ProviderName type alias missing; without it future "
            "removals slip past TypeScript"
        )
    ok(f"all 4 providers present: {list(REQUIRED_PROVIDERS)}; ProviderName declared")

    step("7. NEGATIVE: failover_chain stamped on response AND audit row")
    if body.count("failover_chain") < 2:
        fail(
            f"failover_chain mentioned only {body.count('failover_chain')} "
            "time(s); needs to land on BOTH the JSON response AND the "
            "audit row"
        )
    if "failover_chain" not in body or "AuditRow" not in body:
        fail("AuditRow type or failover_chain field missing")
    # The AuditRow type itself must declare failover_chain as a field.
    audit_row_decl = re.search(
        r"type\s+AuditRow\s*=\s*\{([^}]+)\}",
        body, re.DOTALL,
    )
    if not audit_row_decl:
        fail("AuditRow type literal not parseable")
    if "failover_chain" not in audit_row_decl.group(1):
        fail("AuditRow type does not include failover_chain field")
    ok(
        f"failover_chain appears {body.count('failover_chain')} times AND "
        "is a field of AuditRow"
    )

    step("8. POSITIVE: per-provider env-var inventory")
    rows = []
    for provider, env_vars in PROVIDER_ENV_VARS.items():
        configured = [v for v in env_vars if os.environ.get(v)]
        rows.append(
            f"{provider}: {len(configured)}/{len(env_vars)} "
            f"env vars set"
        )
    for r in rows:
        ok(r)

    print(f"\n{BOLD}{GREEN}{'=' * 50}{NC}")
    print(f"{BOLD}{GREEN}  ALL 8 TTS-PROXY-ROUTE STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}  (6 negative assertions: 2, 3, 4, 5, 6, 7){NC}")
    print(f"{BOLD}{GREEN}{'=' * 50}{NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
