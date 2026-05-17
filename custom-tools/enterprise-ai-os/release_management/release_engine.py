# ✅ P1 IMPROVED (Iter 35, 2026-05-17): rollback_release now validates
#     against a ReleaseRegistry. Pre-fix it created + completed a
#     rollback object for ANY target_release_id (including
#     non-existent ones, including the SAME release that just
#     failed). Pure theater.
#
#     Now:
#       - registers each release on creation
#       - rollback_release rejects unknown target_release_id
#         (ReleaseNotFoundError)
#       - rejects targeting a release whose status is 'failed' or
#         'rolled_back' (can't roll forward into a known-bad state)
#       - rejects targeting the same release that just failed
#       - updates registry statuses through the rollback so a
#         subsequent list_releases() reflects reality
#
#     Real production still needs an Argo Rollouts / Flagger call
#     to apply the rollback to the cluster — this stub closes the
#     "validates target before declaring completed" gap.

from typing import Dict, Any, Optional

from release_management.agent_release import AgentRelease
from release_management.prompt_release import PromptRelease
from release_management.canary_manager import CanaryManager
from release_management.rollback_manager import RollbackManager
from release_management.release_registry import (
    ReleaseRegistry,
    ReleaseInvalidStateError,
)


class ReleaseEngine:
    def __init__(self, registry: Optional[ReleaseRegistry] = None):
        self.agent_release = AgentRelease()
        self.prompt_release = PromptRelease()
        self.canary = CanaryManager()
        self.rollback = RollbackManager()
        self.registry = registry or ReleaseRegistry()

    def release_agent_canary(
        self,
        agent_id: str,
        version: str,
        image_tag: str,
        approved_by: str,
    ) -> Dict[str, Any]:
        release = self.agent_release.create_release(
            agent_id=agent_id,
            version=version,
            image_tag=image_tag,
            approved_by=approved_by,
        )
        canary_plan = self.canary.create_plan(
            release_id=release["release_id"],
            stable_weight=90,
            canary_weight=10,
        )
        release["status"] = "canary"
        release["canary_plan"] = canary_plan
        # Iter 35: register so subsequent rollback can validate.
        self.registry.register(release)
        return release

    def rollback_release(
        self,
        failed_release_id: str,
        target_release_id: str,
        reason: str,
    ) -> Dict[str, Any]:
        # Iter 35: validation BEFORE declaring "completed".
        if failed_release_id == target_release_id:
            raise ReleaseInvalidStateError(
                "Cannot roll back to the same release that just failed"
            )

        # Target must exist.
        target = self.registry.get(target_release_id)  # raises NotFound

        # Target must be in a known-good state.
        bad_target_states = {"failed", "rolled_back"}
        if target.get("status") in bad_target_states:
            raise ReleaseInvalidStateError(
                f"Target release {target_release_id} is in state "
                f"'{target['status']}'; cannot roll forward into it"
            )

        rollback = self.rollback.create_rollback(
            failed_release_id=failed_release_id,
            target_release_id=target_release_id,
            reason=reason,
        )
        completed = self.rollback.complete_rollback(rollback)

        # Reflect rollback in the registry.
        known_ids = [r["release_id"] for r in self.registry.list_releases()]
        if failed_release_id in known_ids:
            self.registry.update_status(failed_release_id, "rolled_back")
        self.registry.update_status(target_release_id, "active")

        return completed
