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
        failures = []

        for index, record in enumerate(records):
            payload = record["payload"]
            expected_hash = self.calculate_hash(payload, previous_hash)
            actual_hash = record.get("current_hash")
            expected_previous_hash = previous_hash
            actual_previous_hash = record.get("previous_hash")
            reasons = []

            if actual_previous_hash != expected_previous_hash:
                reasons.append("previous_hash_mismatch")
            if actual_hash != expected_hash:
                reasons.append("current_hash_mismatch")

            if reasons:
                failures.append({
                    "index": index,
                    "audit_id": record.get("audit_id"),
                    "reasons": reasons,
                    "expected_previous_hash": expected_previous_hash,
                    "actual_previous_hash": actual_previous_hash,
                    "expected_hash": expected_hash,
                    "actual_hash": actual_hash,
                })

            # Advance with the recorded hash so one corrupt payload does
            # not hide later independent corruptions behind cascade noise.
            previous_hash = actual_hash

        if failures:
            first = failures[0]
            return {
                "valid": False,
                "records_checked": len(records),
                "failed_index": first["index"],
                "audit_id": first["audit_id"],
                "failures": failures,
            }

        return {
            "valid": True,
            "records_checked": len(records),
            "failures": [],
        }
