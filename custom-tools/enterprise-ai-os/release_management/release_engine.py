from typing import Dict, Any
from release_management.agent_release import AgentRelease
from release_management.prompt_release import PromptRelease
from release_management.canary_manager import CanaryManager
from release_management.rollback_manager import RollbackManager


class ReleaseEngine:
    def __init__(self):
        self.agent_release = AgentRelease()
        self.prompt_release = PromptRelease()
        self.canary = CanaryManager()
        self.rollback = RollbackManager()

    def release_agent_canary(
        self,
        agent_id: str,
        version: str,
        image_tag: str,
        approved_by: str
    ) -> Dict[str, Any]:

        release = self.agent_release.create_release(
            agent_id=agent_id,
            version=version,
            image_tag=image_tag,
            approved_by=approved_by
        )

        canary_plan = self.canary.create_plan(
            release_id=release["release_id"],
            stable_weight=90,
            canary_weight=10
        )

        release["status"] = "canary"
        release["canary_plan"] = canary_plan

        return release

    def rollback_release(
        self,
        failed_release_id: str,
        target_release_id: str,
        reason: str
    ) -> Dict[str, Any]:

        rollback = self.rollback.create_rollback(
            failed_release_id=failed_release_id,
            target_release_id=target_release_id,
            reason=reason
        )

        return self.rollback.complete_rollback(rollback)
