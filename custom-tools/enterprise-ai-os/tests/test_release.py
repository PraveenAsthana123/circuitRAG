# Tool Set 37 §6 baseline + Iter 35 validation drills.

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from release_management.release_engine import ReleaseEngine
from release_management.release_registry import (
    ReleaseRegistry,
    ReleaseNotFoundError,
    ReleaseInvalidStateError,
)


def _create_two_releases():
    """Helper: create v1 (will be the target) + v2 (will be the
    failed release we roll back from). Returns the engine + both."""
    engine = ReleaseEngine()
    v1 = engine.release_agent_canary(
        agent_id="planner", version="1.0.0",
        image_tag="planner:1.0.0", approved_by="lead",
    )
    v2 = engine.release_agent_canary(
        agent_id="planner", version="2.0.0",
        image_tag="planner:2.0.0", approved_by="lead",
    )
    return engine, v1, v2


def test_canary_release_creates_plan_and_registers():
    engine = ReleaseEngine()
    r = engine.release_agent_canary(
        agent_id="planner_agent", version="2.0.0",
        image_tag="planner-agent:2.0.0", approved_by="governance_lead",
    )
    assert r["status"] == "canary"
    assert r["canary_plan"]["canary_weight"] == 10
    # Registered.
    assert engine.registry.get(r["release_id"])["release_id"] == r["release_id"]


def test_canary_increase_changes_weights():
    engine = ReleaseEngine()
    r = engine.release_agent_canary(
        agent_id="x", version="1.0.0", image_tag="x:1", approved_by="lead",
    )
    r["canary_plan"] = engine.canary.increase_canary(
        plan=r["canary_plan"], new_canary_weight=50,
    )
    assert r["canary_plan"]["canary_weight"] == 50


def test_rollback_to_valid_target_completes():
    engine, v1, v2 = _create_two_releases()
    rollback = engine.rollback_release(
        failed_release_id=v2["release_id"],
        target_release_id=v1["release_id"],
        reason="latency regression",
    )
    assert rollback["status"] == "completed"
    # Registry now reflects: failed → rolled_back, target → active
    assert engine.registry.get(v2["release_id"])["status"] == "rolled_back"
    assert engine.registry.get(v1["release_id"])["status"] == "active"


def test_BACKDOOR_CHECK_rollback_to_unknown_target_rejected():
    """Pre-fix: any target_release_id string was accepted and the
    rollback marked 'completed'. Now: unknown id → NotFound."""
    engine, _v1, v2 = _create_two_releases()
    with pytest.raises(ReleaseNotFoundError):
        engine.rollback_release(
            failed_release_id=v2["release_id"],
            target_release_id="does-not-exist",
            reason="test",
        )


def test_rollback_to_self_rejected():
    """Cannot roll back to the same release that just failed."""
    engine, _v1, v2 = _create_two_releases()
    with pytest.raises(ReleaseInvalidStateError, match="same release"):
        engine.rollback_release(
            failed_release_id=v2["release_id"],
            target_release_id=v2["release_id"],
            reason="test",
        )


def test_rollback_to_already_failed_target_rejected():
    """Don't roll forward INTO a known-bad release."""
    engine, v1, v2 = _create_two_releases()
    # Mark v1 as failed (simulating: it was the previous canary that
    # itself failed, hence why v2 was being tried).
    engine.registry.update_status(v1["release_id"], "failed")
    with pytest.raises(ReleaseInvalidStateError, match="cannot roll forward"):
        engine.rollback_release(
            failed_release_id=v2["release_id"],
            target_release_id=v1["release_id"],
            reason="test",
        )


def test_engine_accepts_external_registry():
    """Caller can pass a pre-seeded registry — useful for restart
    recovery: load from durable storage, hand to engine."""
    reg = ReleaseRegistry()
    reg.register({"release_id": "pre-existing-1", "status": "active"})
    engine = ReleaseEngine(registry=reg)
    fresh = engine.release_agent_canary(
        agent_id="x", version="1", image_tag="x:1", approved_by="lead",
    )
    rollback = engine.rollback_release(
        failed_release_id=fresh["release_id"],
        target_release_id="pre-existing-1",
        reason="rollback to pre-existing",
    )
    assert rollback["status"] == "completed"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
