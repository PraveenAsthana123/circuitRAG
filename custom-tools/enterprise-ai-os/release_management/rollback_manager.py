from datetime import datetime, timezone
from typing import Dict, Any
import uuid


class RollbackManager:
    def create_rollback(
        self,
        failed_release_id: str,
        target_release_id: str,
        reason: str
    ) -> Dict[str, Any]:

        return {
            "rollback_id": str(uuid.uuid4()),
            "failed_release_id": failed_release_id,
            "target_release_id": target_release_id,
            "reason": reason,
            "status": "created",
            "created_at": datetime.now(timezone.utc).isoformat()
        }

    def complete_rollback(
        self,
        rollback: Dict[str, Any]
    ) -> Dict[str, Any]:

        rollback["status"] = "completed"
        rollback["completed_at"] = datetime.now(timezone.utc).isoformat()
        return rollback
