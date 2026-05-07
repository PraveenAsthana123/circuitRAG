#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill for C4 — §48 decision audit row endpoint (Phase C4).

Verifies:
  - app/explainability.py exposes assemble_explanation + REQUIRED_AUDIT_FIELDS
  - assemble_explanation populates ALL §48.4 fields (placeholders OK)
  - cost aggregation across multiple task_runs (B3 retry-loop produces
    multiple runs per task; explain row sums them)
  - last routing_decision in task_runs is the authoritative one for
    model_name / model_version / backend / tier
  - input_hash is canonical across goal+args (deterministic)

Negative assertions:
  1. Missing required field MUST surface as a structured failure
     (REQUIRED_AUDIT_FIELDS contract).
  2. NO routing_decision in any run → model_name/backend/tier MUST be
     None (not '' or 'unknown' or absent — explicit).
  3. Same task_id + same goal MUST produce the same input_hash.
  4. Cost aggregation MUST sum across runs, not take last (B3 retries
     could otherwise hide cumulative spend).

Resource tag = readonly.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SVC = REPO / "services" / "agent-orchestrator-svc"
MODULE = SVC / "app" / "explainability.py"


def _import():
    spec = importlib.util.spec_from_file_location("c4_explain", MODULE)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["c4_explain"] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    print("-- 1. POSITIVE: explainability module loads --")
    mod = _import()
    assert hasattr(mod, "assemble_explanation")
    assert hasattr(mod, "REQUIRED_AUDIT_FIELDS")
    assert hasattr(mod, "_hash_input")
    print(f"  ok: REQUIRED_AUDIT_FIELDS has {len(mod.REQUIRED_AUDIT_FIELDS)} fields")

    print("-- 2. POSITIVE: §48.4 required fields are comprehensive --")
    must_have = {
        "request_id", "timestamp", "tenant_id", "model_name",
        "prompt_version", "input_features", "input_hash",
        "prediction", "confidence", "explanation",
        "rules_applied", "guardrails_triggered", "human_override",
        "cost_tokens", "cost_usd_cents",
    }
    actual = set(mod.REQUIRED_AUDIT_FIELDS)
    missing = must_have - actual
    assert not missing, f"REQUIRED_AUDIT_FIELDS missing §48.4 keys: {missing}"
    print("  ok: all §48.4 keys present in REQUIRED_AUDIT_FIELDS")

    print("-- 3. POSITIVE: assemble basic task with one run --")
    task = {
        "task_id": "task-abc",
        "tenant_id": "acme",
        "goal": "implement OAuth2 PKCE",
        "status": "completed",
        "risk_level": "high",
        "confidence": 0.85,
        "worker_output": "patch produced",
        "approval_reasons": ["high-risk task"],
        "tool_namespace": None,
        "tool_name": None,
        "tool_arguments": {},
        "audit_events": [{"role": "manager", "event": "planned", "at": "2026-04-30T12:00:00Z"}],
        "created_at": "2026-04-30T12:00:00Z",
    }
    runs = [{
        "tokens_in": 100, "tokens_out": 50, "cost_usd_cents": 12,
        "duration_ms": 5000,
        "routing_decision": {
            "chosen": {"role_id": "coder_executor", "model": "claude-sonnet-4-6",
                       "tier": "tier_b", "backend": "claude_cli"},
            "fallback_chain": [], "reason": "R2_novel_complex_to_tier_b", "inputs": {},
        },
    }]
    row = mod.assemble_explanation(task=task, task_runs=runs)
    assert row["request_id"] == "task-abc"
    assert row["tenant_id"] == "acme"
    assert row["model_name"] == "claude-sonnet-4-6"
    assert row["tier"] == "tier_b"
    assert row["backend"] == "claude_cli"
    assert row["confidence"] == 0.85
    print(f"  ok: assembled with model={row['model_name']}, tier={row['tier']}")

    print("-- 4. NEGATIVE: every REQUIRED_AUDIT_FIELDS key present (no silent omission) --")
    missing = [f for f in mod.REQUIRED_AUDIT_FIELDS if f not in row]
    assert not missing, f"row missing required keys: {missing}"
    print(f"  ok: all {len(mod.REQUIRED_AUDIT_FIELDS)} required keys present")

    print("-- 5. POSITIVE: cost aggregation sums across runs (B3 retry case) --")
    runs_multi = [
        {"tokens_in": 100, "tokens_out": 50, "cost_usd_cents": 12, "duration_ms": 5000,
         "routing_decision": {"chosen": {"role_id": "coder_executor", "model": "qwen", "tier": "tier_a", "backend": "ollama"}}},
        {"tokens_in": 80, "tokens_out": 40, "cost_usd_cents": 0, "duration_ms": 3000,
         "routing_decision": {"chosen": {"role_id": "reviewer", "model": "starcoder2:7b", "tier": "tier_a", "backend": "ollama"}}},
        {"tokens_in": 200, "tokens_out": 90, "cost_usd_cents": 25, "duration_ms": 8000,
         "routing_decision": {"chosen": {"role_id": "coder_executor", "model": "gpt-5.2-codex", "tier": "tier_b", "backend": "codex_cli"}}},
    ]
    row = mod.assemble_explanation(task=task, task_runs=runs_multi)
    assert row["cost_tokens"]["in"] == 380, f"expected 380, got {row['cost_tokens']['in']}"
    assert row["cost_tokens"]["out"] == 180
    assert row["cost_usd_cents"] == 37, f"expected 37, got {row['cost_usd_cents']}"
    assert row["latency_ms"] == 16000
    # LAST run's routing is authoritative.
    assert row["model_name"] == "gpt-5.2-codex", (
        f"expected last run's model, got {row['model_name']}"
    )
    print(f"  ok: cost summed across 3 runs ({row['cost_usd_cents']} cents); last run's model used")

    print("-- 6. NEGATIVE: no routing_decision anywhere → None (not 'unknown') --")
    runs_no_routing = [{"tokens_in": 0, "tokens_out": 0, "cost_usd_cents": 0, "duration_ms": 100}]
    row = mod.assemble_explanation(task=task, task_runs=runs_no_routing)
    assert row["model_name"] is None, f"expected None, got {row['model_name']!r}"
    assert row["backend"] is None
    assert row["tier"] is None
    print("  ok: no routing → explicit None (not silent default)")

    print("-- 7. NEGATIVE: same goal+args → same input_hash (deterministic) --")
    h1 = mod._hash_input("implement X", "hr", "leave_request", {"days": 3})
    h2 = mod._hash_input("implement X", "hr", "leave_request", {"days": 3})
    h3 = mod._hash_input("implement Y", "hr", "leave_request", {"days": 3})
    assert h1 == h2, "input_hash NOT deterministic"
    assert h1 != h3, "different goal must produce different hash"
    print(f"  ok: input_hash deterministic ({h1[:16]}...)")

    print("-- 8. POSITIVE: human_override flag from approvals --")
    row_no_approval = mod.assemble_explanation(task=task, task_runs=runs)
    assert row_no_approval["human_override"] is False
    row_with_approval = mod.assemble_explanation(
        task=task, task_runs=runs,
        approvals=[{"approval_id": "x", "decision": "approve"}],
    )
    assert row_with_approval["human_override"] is True
    print("  ok: human_override flips True when approval present")

    print("-- 9. POSITIVE: rules_applied + guardrails_triggered surface from task --")
    task_with_guardrails = dict(task)
    task_with_guardrails["audit_events"] = [
        {"role": "security_advisor", "event": "flagged_secret_handling", "at": "2026-04-30T12:01:00Z"},
        {"role": "policy", "event": "evaluated", "approval_reasons": ["high-risk task"]},
    ]
    row = mod.assemble_explanation(task=task_with_guardrails, task_runs=runs)
    assert "high-risk task" in row["rules_applied"]
    assert any("security_advisor" in g for g in row["guardrails_triggered"]), (
        f"security_advisor event must surface as guardrail: {row['guardrails_triggered']}"
    )
    print(f"  ok: rules + guardrails extracted; {len(row['guardrails_triggered'])} guardrail signals")

    print("-- 10. POSITIVE: row is JSON-serializable for /explain endpoint --")
    import json
    json.dumps(row)
    print("  ok: row serializes")

    print()
    print("ALL 10 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
