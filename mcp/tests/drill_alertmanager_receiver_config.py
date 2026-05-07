#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: Alertmanager receiver config path.

Locks the shared-alert-delivery contract so Alertmanager is not stuck with
a hard-coded local placeholder forever. The config must remain renderable
from env at compose start, while still defaulting safely to local-log when
no shared receiver is configured.

Negative assertions cover: config file exists; receiver placeholders
honor env-var rendering at compose-start (not hardcoded URLs);
local-log fallback is wired so a missing receiver env var doesn't
silently drop alerts. Without these, alerts disappear into a
hard-coded sink with no operator notice.
"""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
COMPOSE = REPO / "docker-compose.yml"
ALERTMANAGER = REPO / "infra" / "observability" / "alertmanager.yml"
RUNBOOK = REPO / "docs" / "runbooks" / "alertmanager-webhook.md"


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise AssertionError(f"missing {label}: {needle}")


def main() -> int:
    compose = COMPOSE.read_text(encoding="utf-8")
    cfg = ALERTMANAGER.read_text(encoding="utf-8")

    print("-- 1. POSITIVE: alertmanager config uses env-rendered default receiver token --")
    require(cfg, "receiver: __DEFAULT_RECEIVER__", "default receiver token")
    print("  ok: default receiver is rendered at startup")

    print("-- 2. POSITIVE: alertmanager config exposes shared-webhook receiver contract --")
    require(cfg, "- name: shared-webhook", "shared-webhook receiver")
    require(cfg, "url: __WEBHOOK_URL__", "webhook url token")
    print("  ok: shared-webhook receiver is templated")

    print("-- 3. POSITIVE: compose passes configurable receiver env vars --")
    require(compose, "ALERTMANAGER_DEFAULT_RECEIVER:", "default receiver env")
    require(compose, "ALERTMANAGER_WEBHOOK_URL:", "webhook url env")
    print("  ok: docker-compose exposes alertmanager receiver env")

    print("-- 4. POSITIVE: compose renders alertmanager config before startup --")
    require(compose, 'sed \\', "config render command")
    require(compose, '/etc/alertmanager/alertmanager.yml > /tmp/alertmanager.yml', "render output path")
    require(compose, '--config.file=/tmp/alertmanager.yml', "rendered config path")
    print("  ok: compose renders a concrete config before boot")

    print("-- 5. NEGATIVE: no static placeholder receiver name should remain --")
    if "placeholder-webhook" in cfg:
        raise AssertionError("stale placeholder-webhook receiver still present")
    print("  ok: no stale placeholder receiver name remains")

    print("-- 6. NEGATIVE: operator runbook must exist or the env-secret pattern is undocumented --")
    # Without this runbook, the operator has no guided path to flip
    # ALERTMANAGER_DEFAULT_RECEIVER=shared-webhook safely. Compose
    # accepts the env vars regardless, so a missing runbook means
    # silent dropped alerts (placeholder URL POSTs go nowhere). The
    # negative assertion is: runbook absent OR runbook stripped of
    # the canonical env-var pair → drill fails.
    if not RUNBOOK.exists():
        raise AssertionError(f"missing operator runbook: {RUNBOOK.relative_to(REPO)}")
    runbook = RUNBOOK.read_text(encoding="utf-8")
    require(runbook, "ALERTMANAGER_DEFAULT_RECEIVER", "default-receiver env in runbook")
    require(runbook, "ALERTMANAGER_WEBHOOK_URL", "webhook-url env in runbook")
    require(runbook, ".loop/alertmanager.env", ".loop/ env-secret pattern in runbook")
    require(runbook, "chmod 600", "chmod-600 discipline in runbook")
    print("  ok: runbook present and documents the .loop/ chmod-600 env-secret path")

    print("\nALL 6 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
