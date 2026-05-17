from typing import Dict, Any


class TenantStore:
    def __init__(self):
        self.tenants = {}

    def create_tenant(
        self,
        tenant_id: str,
        name: str,
        plan: str = "enterprise"
    ) -> Dict[str, Any]:

        tenant = {
            "tenant_id": tenant_id,
            "name": name,
            "plan": plan,
            "status": "active"
        }

        self.tenants[tenant_id] = tenant
        return tenant

    def get_tenant(self, tenant_id: str):
        return self.tenants.get(tenant_id)

    def is_active(self, tenant_id: str) -> bool:
        tenant = self.get_tenant(tenant_id)
        return bool(tenant and tenant["status"] == "active")
