from datetime import datetime, timezone
from typing import Dict, Any
import uuid


class PromptRelease:
    def create_release(
        self,
        prompt_id: str,
        version: str,
        approved_by: str
    ) -> Dict[str, Any]:

        return {
            "release_id": str(uuid.uuid4()),
            "artifact_type": "prompt",
            "prompt_id": prompt_id,
            "version": version,
            "approved_by": approved_by,
            "status": "created",
            "created_at": datetime.now(timezone.utc).isoformat()
        }

    def mark_active(self, release: Dict[str, Any]) -> Dict[str, Any]:
        release["status"] = "active"
        release["activated_at"] = datetime.now(timezone.utc).isoformat()
        return release
