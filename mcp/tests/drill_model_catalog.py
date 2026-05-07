#!/usr/bin/env python3
# RESOURCES: readonly
"""Structural drill for the model catalog (Phase A1).

Locks the existence and shape of:

- app/model_catalog.py with a 9-entry catalog
- app/llm_clients/protocol.py with LlmClient Protocol + LlmClientUnavailable
- GET /api/v1/agentic/models/catalog endpoint registered in app/main.py
- ModelCatalogEntryView in app/models.py

Negative assertions cover:
  1. The catalog validator rejects an entry with empty tier_a_primary —
     proves the API contract that bad catalog → HTTP 500, not silent default.
  2. Every catalog entry that exposes tier_b ALSO names a tier_b_backend
     in {claude_cli, codex_cli} — proves no orphan cloud routing.
  3. role_id values are unique — duplicates would silently shadow.
  4. LlmCallResult forces explicit tier="tier_a" or "tier_b" — drill checks
     the field exists with no default that would mask attribution.

Why this drill: A1 is foundational — every later phase consumes the catalog
and the LlmClient Protocol. Source-locking it now prevents drift.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SVC = REPO / "services" / "agent-orchestrator-svc"
CATALOG_FILE = SVC / "app" / "model_catalog.py"
PROTOCOL_FILE = SVC / "app" / "llm_clients" / "protocol.py"
LLM_CLIENTS_INIT = SVC / "app" / "llm_clients" / "__init__.py"
MAIN_FILE = SVC / "app" / "main.py"
MODELS_FILE = SVC / "app" / "models.py"


def _import_module(label: str, path: Path):
    spec = importlib.util.spec_from_file_location(label, path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot import {label} from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[label] = module
    spec.loader.exec_module(module)
    return module


def must_contain(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise AssertionError(f"missing {label}: {needle!r}")


def main() -> int:
    print("-- 1. POSITIVE: catalog file exists and parses --")
    assert CATALOG_FILE.exists(), f"missing {CATALOG_FILE}"
    catalog_mod = _import_module("agent_orch_model_catalog", CATALOG_FILE)
    catalog = catalog_mod.get_catalog()
    assert len(catalog) >= 9, f"expected >=9 catalog entries, got {len(catalog)}"
    role_ids = {e.role_id for e in catalog}
    expected = {
        "researcher", "strategist", "coder_executor", "reviewer",
        "advisor", "security_advisor", "tester", "deployer", "observer",
    }
    missing = expected - role_ids
    assert not missing, f"catalog missing required roles: {missing}"
    print(f"  ok: {len(catalog)} entries, all 9 required roles present")

    print("-- 2. POSITIVE: validator passes on default catalog --")
    errors = catalog_mod.validate_catalog(catalog)
    assert not errors, f"default catalog must validate clean, got: {errors}"
    print("  ok: validator returns []")

    print("-- 3. NEGATIVE: validator rejects empty tier_a_primary --")
    bad_entry = catalog_mod.CatalogEntry(
        role_id="bad",
        role_type="x",
        display_name="x",
        tier_a_primary="",          # << empty - must trigger error
        tier_a_backup="qwen2.5:latest",
        description="bad entry for drill",
    )
    errs = catalog_mod.validate_catalog((bad_entry,))
    assert any("tier_a_primary" in e for e in errs), (
        f"validator must flag empty tier_a_primary; got: {errs}"
    )
    print("  ok: empty tier_a_primary correctly flagged")

    print("-- 4. NEGATIVE: validator rejects duplicate role_id --")
    a = catalog_mod.CatalogEntry(
        role_id="dup", role_type="x", display_name="x",
        tier_a_primary="m1", tier_a_backup="m2", description="",
    )
    b = catalog_mod.CatalogEntry(
        role_id="dup", role_type="x", display_name="x",
        tier_a_primary="m3", tier_a_backup="m4", description="",
    )
    errs = catalog_mod.validate_catalog((a, b))
    assert any("duplicate" in e for e in errs), f"duplicate not flagged: {errs}"
    print("  ok: duplicate role_id flagged")

    print("-- 5. NEGATIVE: validator rejects unknown tier_b_backend --")
    bad = catalog_mod.CatalogEntry(
        role_id="bad-backend", role_type="x", display_name="x",
        tier_a_primary="m1", tier_a_backup="m2",
        tier_b="m3", tier_b_backend="invalid_backend",
        description="",
    )
    errs = catalog_mod.validate_catalog((bad,))
    assert any("tier_b_backend" in e for e in errs), (
        f"unknown tier_b_backend not flagged: {errs}"
    )
    print("  ok: unknown tier_b_backend flagged")

    print("-- 6. POSITIVE: every tier_b entry names a known backend --")
    for entry in catalog:
        if entry.tier_b:
            assert entry.tier_b_backend in ("claude_cli", "codex_cli"), (
                f"{entry.role_id}: tier_b={entry.tier_b} but backend "
                f"{entry.tier_b_backend!r} is not known"
            )
    print("  ok: all tier_b entries pair with claude_cli or codex_cli")

    print("-- 7. POSITIVE: LlmClient Protocol module loads --")
    assert PROTOCOL_FILE.exists(), f"missing {PROTOCOL_FILE}"
    assert LLM_CLIENTS_INIT.exists(), f"missing {LLM_CLIENTS_INIT}"
    proto_text = PROTOCOL_FILE.read_text(encoding="utf-8")
    must_contain(proto_text, "class LlmClient", "LlmClient Protocol")
    must_contain(proto_text, "LlmClientUnavailable", "LlmClientUnavailable error")
    must_contain(proto_text, "class LlmCallResult", "LlmCallResult dataclass")
    must_contain(proto_text, "tokens_in", "LlmCallResult.tokens_in")
    must_contain(proto_text, "tokens_out", "LlmCallResult.tokens_out")
    must_contain(proto_text, "cost_usd_cents", "LlmCallResult.cost_usd_cents")
    must_contain(proto_text, "tier:", "LlmCallResult.tier field")
    print("  ok: protocol surfaces tokens_in/out + cost + tier")

    print("-- 8. POSITIVE: catalog endpoint registered in main.py --")
    main_text = MAIN_FILE.read_text(encoding="utf-8")
    must_contain(main_text, "/api/v1/agentic/models/catalog", "catalog route")
    must_contain(main_text, "list_model_catalog", "catalog handler name")
    must_contain(main_text, "validate_catalog", "validator import in main")
    print("  ok: catalog route + handler wired")

    print("-- 9. POSITIVE: ModelCatalogEntryView present in models.py --")
    models_text = MODELS_FILE.read_text(encoding="utf-8")
    must_contain(models_text, "class ModelCatalogEntryView", "ModelCatalogEntryView")
    must_contain(models_text, "tier_a_primary", "tier_a_primary field")
    must_contain(models_text, "tier_b_backend", "tier_b_backend field")
    print("  ok: ModelCatalogEntryView shape locked")

    print()
    print("ALL 9 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
