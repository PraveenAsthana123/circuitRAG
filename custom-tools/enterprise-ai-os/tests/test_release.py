# Test script from Tool Set 37 §6 — reformatted as a runnable pytest

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from release_management.release_engine import ReleaseEngine


def test_release_engine_canary_and_rollback():
    engine = ReleaseEngine()

    agent_release = engine.release_agent_canary(
        agent_id="planner_agent",
        version="2.0.0",
        image_tag="planner-agent:2.0.0",
        approved_by="governance_lead"
    )

    assert agent_release["status"] == "canary"
    assert agent_release["canary_plan"]["canary_weight"] == 10
    assert agent_release["canary_plan"]["stable_weight"] == 90

    agent_release["canary_plan"] = engine.canary.increase_canary(
        plan=agent_release["canary_plan"],
        new_canary_weight=50
    )
    assert agent_release["canary_plan"]["canary_weight"] == 50

    rollback = engine.rollback_release(
        failed_release_id=agent_release["release_id"],
        target_release_id="previous-release-id",
        reason="latency regression detected"
    )

    assert rollback["status"] == "completed"


if __name__ == "__main__":
    test_release_engine_canary_and_rollback()
    print("OK")
