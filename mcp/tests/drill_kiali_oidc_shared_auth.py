#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: Kiali shared-environment auth contract.

The dev ConfigMap may keep auth.strategy=anonymous for single-operator
local work. Shared/SOC2 environments must have a concrete OpenID Connect
template and must not store the Kiali login-token signing key as a
literal in ConfigMap data.

6 steps, 4 negative.

  1. POSITIVE: OIDC template exists.
  2. POSITIVE: template contains Secret/kiali-signing-key.
  3. POSITIVE: template contains Secret/kiali with oidc-secret.
  4. NEGATIVE: shared template does not use auth.strategy=anonymous.
  5. NEGATIVE: login_token.signing_key uses secret:<name>:<key>.
  6. NEGATIVE: active dev ConfigMap documents why anonymous is dev-only.

Run: python3 mcp/tests/drill_kiali_oidc_shared_auth.py
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
TEMPLATE = REPO / "infra" / "kiali" / "kiali-cluster-config.oidc.yaml.template"
DEV_CFG = REPO / "infra" / "kiali" / "kiali-cluster-config.yaml"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _template_docs() -> list[dict]:
    raw = TEMPLATE.read_text(encoding="utf-8")
    rendered = re.sub(r"\$\{[A-Z0-9_]+\}", "placeholder", raw)
    return [doc for doc in yaml.safe_load_all(rendered) if doc]


def main() -> int:
    print("-- 1. POSITIVE: shared/SOC2 OIDC template exists --")
    require(TEMPLATE.exists(), f"missing {TEMPLATE.relative_to(REPO)}")
    print("  ok: OIDC template present")

    docs = _template_docs()

    print("-- 2. POSITIVE: template defines Secret/kiali-signing-key --")
    signing_secret = next(
        (
            doc
            for doc in docs
            if doc.get("kind") == "Secret"
            and doc.get("metadata", {}).get("name") == "kiali-signing-key"
        ),
        None,
    )
    require(signing_secret is not None, "missing Secret/kiali-signing-key")
    require("key" in signing_secret.get("stringData", {}), "signing key Secret missing stringData.key")
    print("  ok: signing-key Secret declared")

    print("-- 3. POSITIVE: template defines Secret/kiali oidc-secret --")
    oidc_secret = next(
        (
            doc
            for doc in docs
            if doc.get("kind") == "Secret"
            and doc.get("metadata", {}).get("name") == "kiali"
        ),
        None,
    )
    require(oidc_secret is not None, "missing Secret/kiali for OIDC client secret")
    require("oidc-secret" in oidc_secret.get("stringData", {}), "Secret/kiali missing oidc-secret")
    print("  ok: OIDC client secret uses Kiali's expected Secret/kiali key")

    print("-- 4. NEGATIVE: shared template must not use anonymous auth --")
    config_map = next(
        (
            doc
            for doc in docs
            if doc.get("kind") == "ConfigMap"
            and doc.get("metadata", {}).get("name") == "kiali"
        ),
        None,
    )
    require(config_map is not None, "missing ConfigMap/kiali in OIDC template")
    cfg = yaml.safe_load(config_map["data"]["config.yaml"])
    auth = cfg.get("auth", {})
    require(auth.get("strategy") == "openid", f"expected auth.strategy=openid, got {auth.get('strategy')!r}")
    require("issuer_uri" in auth.get("openid", {}), "openid.issuer_uri missing")
    require("client_id" in auth.get("openid", {}), "openid.client_id missing")
    print("  ok: shared template requires OpenID Connect")

    print("-- 5. NEGATIVE: signing_key must be a secret reference, not literal --")
    signing_key = cfg.get("login_token", {}).get("signing_key")
    require(
        signing_key == "secret:kiali-signing-key:key",
        f"login_token.signing_key must reference Secret/kiali-signing-key:key, got {signing_key!r}",
    )
    require("aed516789d7e2dd69b2edd366c1aa2c3" not in TEMPLATE.read_text(encoding="utf-8"), "template leaked dev literal signing key")
    print("  ok: signing key is Secret-mounted via secret:<name>:<key>")

    print("-- 6. NEGATIVE: dev ConfigMap marks anonymous as dev-only --")
    dev_text = DEV_CFG.read_text(encoding="utf-8")
    require("strategy: anonymous" in dev_text, "dev ConfigMap no longer carries explicit anonymous strategy")
    require("single-operator local development" in dev_text, "dev ConfigMap must document anonymous as dev-only")
    require("kiali-cluster-config.oidc.yaml.template" in dev_text, "dev ConfigMap must point shared operators to OIDC template")
    print("  ok: anonymous auth is documented as dev-only with shared OIDC pointer")

    print("\nALL 6 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
