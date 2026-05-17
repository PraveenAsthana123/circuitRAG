# ⚠️ NOT IMMUTABLE AT RUNTIME — the class name oversells.
#     `self.records` is a plain Python list. Anyone with a reference
#     to the store can do `store.records[0]["current_hash"] = "X"`
#     and the chain breaks silently (until `verify_integrity()` is
#     called). True immutability requires:
#       1. A backing store that enforces insert-only at the DB layer
#          (Postgres role with INSERT but no UPDATE/DELETE/TRUNCATE)
#       2. WORM storage for cold archives (S3 Object Lock / Glacier
#          Vault Lock)
#       3. External notarization of merkle roots (e.g., periodic
#          publication to a transparency log)
#
#     The source's own Tool Set 36 §5 "Production Note" acknowledges
#     this — see GAPS.md Tool Set 36 for the P0 list.

from datetime import datetime
from typing import Dict, Any, List
import uuid

from audit.hash_chain import HashChain


class ImmutableAuditStore:
    def __init__(self):
        self.records: List[Dict[str, Any]] = []
        self.hash_chain = HashChain()

    def append(
        self,
        trace_id: str,
        actor: str,
        event_type: str,
        payload: Dict[str, Any]
    ) -> Dict[str, Any]:

        previous_hash = (
            self.records[-1]["current_hash"]
            if self.records
            else "GENESIS"
        )

        audit_payload = {
            "trace_id": trace_id,
            "actor": actor,
            "event_type": event_type,
            "payload": payload,
            "created_at": datetime.utcnow().isoformat()
        }

        current_hash = self.hash_chain.calculate_hash(
            audit_payload,
            previous_hash
        )

        record = {
            "audit_id": str(uuid.uuid4()),
            "previous_hash": previous_hash,
            "current_hash": current_hash,
            "payload": audit_payload
        }

        self.records.append(record)
        return record

    def list_records(self) -> List[Dict[str, Any]]:
        return self.records

    def search_by_trace(self, trace_id: str) -> List[Dict[str, Any]]:
        return [
            record for record in self.records
            if record["payload"]["trace_id"] == trace_id
        ]

    def verify_integrity(self) -> Dict[str, Any]:
        return self.hash_chain.verify(self.records)
