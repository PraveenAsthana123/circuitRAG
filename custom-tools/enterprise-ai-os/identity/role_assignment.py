from typing import Dict, List


class RoleAssignment:
    def __init__(self):
        self.user_roles: Dict[str, List[str]] = {}

    def assign_role(self, user_id: str, role: str):
        if user_id not in self.user_roles:
            self.user_roles[user_id] = []

        if role not in self.user_roles[user_id]:
            self.user_roles[user_id].append(role)

        return {
            "user_id": user_id,
            "roles": self.user_roles[user_id]
        }

    def has_role(self, user_id: str, role: str) -> bool:
        return role in self.user_roles.get(user_id, [])

    def get_roles(self, user_id: str):
        return self.user_roles.get(user_id, [])
