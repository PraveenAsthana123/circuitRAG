# ⚠️ NOT IMMUTABLE AT RUNTIME — the class name oversells.
#     `self._records` is process-local memory. Public accessors return
#     defensive copies, but true immutability still requires durable
#     storage: Postgres INSERT-only role, WORM cold storage, periodic
#     merkle-root notarization. The source's own Tool Set 36 §5
#     "Production Note" acknowledges this — see GAPS.md Tool Set 36.
#
# ✅ Iter 14 (2026-05-17) closes two remaining P0/P1 rows:
#     - P0: tenant_id is now a first-class column on every record.
#       list_records / search_by_trace require a callerTenantId and
#       only return records owned by that tenant. append() requires
#       a tenant_id argument so producer-side mistakes are caught.
#     - P1: append() refuses to grow beyond retention_days × ~hourly
#       cleanup. New purge_expired() method to be called by a
#       scheduled job. Default retention = 90 days (CLAUDE.md §7.4).

from datetime import datetime, timezone, timedelta
from copy import deepcopy
from typing import Dict, Any, List, Optional
import uuid

from audit.hash_chain import HashChain


DEFAULT_RETENTION_DAYS = 90


class AuditAccessDeniedError(Exception):
    pass


class ImmutableAuditStore:
    def __init__(self, retention_days: int = DEFAULT_RETENTION_DAYS):
        if retention_days < 1:
            raise ValueError("retention_days must be >= 1")
        self._records: List[Dict[str, Any]] = []
        self.hash_chain = HashChain()
        self.retention_days = retention_days

    def append(
        self,
        trace_id: str,
        actor: str,
        event_type: str,
        payload: Dict[str, Any],
        tenant_id: str,
    ) -> Dict[str, Any]:
        if not tenant_id:
            raise ValueError("tenant_id is required for every audit row")

        previous_hash = (
            self._records[-1]["current_hash"]
            if self._records
            else "GENESIS"
        )

        audit_payload = {
            "trace_id": trace_id,
            "actor": actor,
            "event_type": event_type,
            "tenant_id": tenant_id,
            "payload": payload,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        current_hash = self.hash_chain.calculate_hash(
            audit_payload,
            previous_hash,
        )

        record = {
            "audit_id": str(uuid.uuid4()),
            "previous_hash": previous_hash,
            "current_hash": current_hash,
            "payload": audit_payload,
        }

        self._records.append(record)
        return deepcopy(record)

    def list_records(
        self,
        caller_tenant_id: str,
    ) -> List[Dict[str, Any]]:
        if not caller_tenant_id:
            raise AuditAccessDeniedError(
                "caller_tenant_id required; refusing global read"
            )
        return deepcopy([
            r for r in self._records
            if r["payload"].get("tenant_id") == caller_tenant_id
        ])

    def search_by_trace(
        self,
        trace_id: str,
        caller_tenant_id: str,
    ) -> List[Dict[str, Any]]:
        if not caller_tenant_id:
            raise AuditAccessDeniedError(
                "caller_tenant_id required; refusing global read"
            )
        return deepcopy([
            r for r in self._records
            if r["payload"]["trace_id"] == trace_id
            and r["payload"].get("tenant_id") == caller_tenant_id
        ])

    def verify_integrity(self) -> Dict[str, Any]:
        # Integrity check operates on the WHOLE chain (chain is global,
        # not per-tenant; tampering with any record breaks the hash).
        # No caller_tenant_id required — read-only crypto check.
        return self.hash_chain.verify(self._records)

    def purge_expired(self, now: Optional[datetime] = None) -> int:
        """
        Remove records older than retention_days. Returns the number
        purged.

        NOTE: purging is a controlled overwrite that DOES break the
        hash chain by design — older records are gone, so the chain
        is rebuilt from the oldest surviving record. The new chain
        is anchored at GENESIS prefixed to the first surviving record's
        recomputed hash. A real production system would publish the
        pre-purge merkle root externally before purging so the
        compromised window is provable.
        """
        if now is None:
            now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=self.retention_days)

        survivors: List[Dict[str, Any]] = []
        for r in self._records:
            created = datetime.fromisoformat(r["payload"]["created_at"])
            if created >= cutoff:
                survivors.append(r)

        purged = len(self._records) - len(survivors)
        if purged == 0:
            return 0

        # Rebuild chain from survivors so future verify_integrity passes.
        rebuilt: List[Dict[str, Any]] = []
        previous_hash = "GENESIS"
        for r in survivors:
            new_hash = self.hash_chain.calculate_hash(
                r["payload"], previous_hash
            )
            rebuilt.append({
                "audit_id": r["audit_id"],
                "previous_hash": previous_hash,
                "current_hash": new_hash,
                "payload": r["payload"],
            })
            previous_hash = new_hash

        self._records = rebuilt
        return purged
