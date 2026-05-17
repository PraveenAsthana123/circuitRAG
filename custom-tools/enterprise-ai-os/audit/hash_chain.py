import hashlib
import json
from typing import Dict, Any


class HashChain:
    def canonical_json(self, payload: Dict[str, Any]) -> str:
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))

    def calculate_hash(
        self,
        payload: Dict[str, Any],
        previous_hash: str
    ) -> str:
        raw = self.canonical_json(payload) + previous_hash
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def verify(
        self,
        records: list[Dict[str, Any]]
    ) -> Dict[str, Any]:
        previous_hash = "GENESIS"

        for index, record in enumerate(records):
            payload = record["payload"]
            expected = self.calculate_hash(payload, previous_hash)

            if record["current_hash"] != expected:
                return {
                    "valid": False,
                    "failed_index": index,
                    "audit_id": record.get("audit_id")
                }

            previous_hash = record["current_hash"]

        return {
            "valid": True,
            "records_checked": len(records)
        }
