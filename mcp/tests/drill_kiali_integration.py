#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: Kiali integration via minikube/dm-istio + port-forward to host:20001.

Locks the canonical Kiali install pattern after the docker-compose
mesh-profile container approach failed (Kiali v1.86 hard-blocks on
"unable to load in-cluster configuration"). The fix shipped in this
commit:

  1. Kiali deploys INSIDE minikube via the official Istio addon.
  2. scripts/kiali-port-forward.sh forwards in-cluster svc/kiali
     20001:20001 to the host so docker-compose-based services
     (frontend BFF) can reach it.
  3. Frontend BFF probes http://localhost:20001/kiali/healthz
     (NOT /healthz — Kiali's web_root is /kiali per its config).
  4. forceStatus: "NOT_CONFIGURED" override REMOVED — Kiali now
     contributes a real HEALTHY/UNREACHABLE signal to all-green.

8 steps, 4 negative.

  1. POSITIVE: scripts/kiali-port-forward.sh exists + executable
  2. POSITIVE: BFF route Kiali entry uses /kiali web_root in health_url
  3. POSITIVE: BFF route Kiali entry uses ui_url ending in /kiali
  4. NEGATIVE: BFF route does NOT pin Kiali to forceStatus
              (proves Kiali contributes a real probe signal)
  5. NEGATIVE: BFF route Kiali health_url does NOT use bare /healthz
              (would 404 — Kiali web_root is /kiali)
  6. NEGATIVE: scripts/kiali-port-forward.sh does NOT skip the
              idempotent pkill (reusing :20001 would silently fail)
  7. NEGATIVE: scripts/kiali-port-forward.sh does NOT hardcode
              context (must respect MINIKUBE_PROFILE env)
  8. POSITIVE: docker-compose.yml kiali service kept under
              `profiles: ["mesh"]` so default `up` skips it
              (the broken compose container approach must NOT
              come back on by default)

Per CLAUDE.md §43 (drill discipline; ≥3 negatives), §47 (observability
is first-class), §49 (compose footer — Kiali joins integrations-health
+ tools-launcher + monitoring), §51 (forensic substrate), §57.7
(honesty — Kiali claims HEALTHY only when actually reachable).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PF_SCRIPT = REPO / "scripts" / "kiali-port-forward.sh"
BFF_ROUTE = REPO / "services" / "frontend" / "app" / "api" / "v1" / "integrations-health" / "route.ts"
COMPOSE = REPO / "docker-compose.yml"

GREEN = "\033[32m"
RED = "\033[31m"
BOLD = "\033[1m"
NC = "\033[0m"


def step(t: str) -> None:
    print(f"\n{BOLD}── {t} ──{NC}")


def ok(m: str) -> None:
    print(f"  {GREEN}✓ {m}{NC}")


def fail(m: str) -> None:
    print(f"  {RED}✗ {m}{NC}")
    raise SystemExit(1)


def main() -> int:
    # ── 1. port-forward script exists + executable ─────────────────────
    step("1. POSITIVE: scripts/kiali-port-forward.sh exists + executable")
    if not PF_SCRIPT.exists():
        fail(f"missing: {PF_SCRIPT.relative_to(REPO)}")
    mode = PF_SCRIPT.stat().st_mode
    if not (mode & 0o100):
        fail("script not executable (chmod +x scripts/kiali-port-forward.sh)")
    pf_text = PF_SCRIPT.read_text(encoding="utf-8")
    ok(f"port-forward script {len(pf_text)}b · executable")

    # ── 2. BFF Kiali entry uses /kiali web_root in health_url ─────────
    step("2. POSITIVE: BFF Kiali health_url uses /kiali/healthz path")
    bff = BFF_ROUTE.read_text(encoding="utf-8")
    kiali_idx = bff.find('name: "Kiali"')
    if kiali_idx < 0:
        fail("BFF missing Kiali entry")
    kiali_block = bff[kiali_idx : kiali_idx + 1200]
    if "/kiali/healthz" not in kiali_block:
        fail("Kiali health_url does NOT include /kiali/healthz — would 404")
    ok("Kiali health_url targets /kiali/healthz (correct web_root path)")

    # ── 3. BFF Kiali ui_url uses /kiali web_root ──────────────────────
    step("3. POSITIVE: BFF Kiali ui_url ends in /kiali (matches web_root)")
    if not re.search(r'ui_url:[^,]*"http://localhost:20001/kiali"', kiali_block):
        fail("Kiali ui_url does NOT target /kiali web_root")
    ok("Kiali ui_url targets http://localhost:20001/kiali")

    # ── 4. NEGATIVE: forceStatus override removed ─────────────────────
    step("4. NEGATIVE: BFF Kiali entry has NO forceStatus override")
    if "forceStatus" in kiali_block:
        fail(
            "Kiali entry still pins forceStatus — would mask the real "
            "probe signal. Remove it now that Istio + Kiali are installed."
        )
    ok("Kiali entry contributes a REAL probe signal (no forceStatus mask)")

    # ── 5. NEGATIVE: bare /healthz path would 404 ─────────────────────
    step("5. NEGATIVE: BFF Kiali health_url does NOT use bare /healthz")
    if re.search(r'health_url:\s*"http://localhost:20001/healthz"', kiali_block):
        fail(
            "Kiali health_url uses bare /healthz — would 404 because Kiali "
            "is configured with web_root: /kiali (see infra/kiali/kiali.yaml)"
        )
    ok("Kiali health_url avoids the bare /healthz 404 trap")

    # ── 6. NEGATIVE: port-forward script is idempotent (pkill present) ─
    step("6. NEGATIVE: port-forward script does NOT skip idempotent pkill")
    if "pkill" not in pf_text:
        fail(
            "kiali-port-forward.sh missing pkill — second invocation would "
            "fail with 'address already in use' silently in nohup output"
        )
    if "port-forward.*svc/kiali" not in pf_text and "port-forward" not in pf_text:
        fail("kiali-port-forward.sh does not invoke port-forward")
    ok("port-forward script is idempotent (pkill before nohup)")

    # ── 7. NEGATIVE: script does NOT hardcode context ─────────────────
    step("7. NEGATIVE: port-forward script does NOT hardcode minikube context")
    if "MINIKUBE_PROFILE" not in pf_text:
        fail(
            "kiali-port-forward.sh hardcodes context — must respect "
            "MINIKUBE_PROFILE env var (operators may use a different profile)"
        )
    ok("port-forward script honors MINIKUBE_PROFILE env")

    # ── 8. POSITIVE: compose kiali still gated by mesh profile ────────
    step("8. POSITIVE: docker-compose kiali still under profiles: ['mesh']")
    compose_text = COMPOSE.read_text(encoding="utf-8")
    kiali_compose_idx = compose_text.find("kiali:")
    if kiali_compose_idx < 0:
        fail("docker-compose.yml missing kiali service (template removed?)")
    kiali_compose_block = compose_text[kiali_compose_idx : kiali_compose_idx + 1500]
    if 'profiles: ["mesh"]' not in kiali_compose_block:
        fail(
            "compose kiali service is NOT gated by profiles: ['mesh'] — "
            "default `docker compose up` would crash-loop kiali again "
            "(unable to load in-cluster configuration)"
        )
    ok("compose kiali stays gated by mesh profile (broken path stays opt-in)")

    print(f"\n{BOLD}{GREEN}ALL 8 STEPS PASSED{NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
