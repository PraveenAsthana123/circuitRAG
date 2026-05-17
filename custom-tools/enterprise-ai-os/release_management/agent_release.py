from datetime import datetime, timezone
from typing import Dict, Any
import uuid


class AgentRelease:
    def create_release(
        self,
        agent_id: str,
        version: str,
        image_tag: str,
        approved_by: str
    ) -> Dict[str, Any]:

        return {
            "release_id": str(uuid.uuid4()),
            "artifact_type": "agent",
            "agent_id": agent_id,
            "version": version,
            "image_tag": image_tag,
            "approved_by": approved_by,
            "status": "created",
            "created_at": datetime.now(timezone.utc).isoformat()
        }

    def mark_deployed(self, release: Dict[str, Any]) -> Dict[str, Any]:
        release["status"] = "deployed"
        release["deployed_at"] = datetime.now(timezone.utc).isoformat()
        return release
