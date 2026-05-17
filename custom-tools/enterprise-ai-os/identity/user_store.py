from typing import Dict, Any


class UserStore:
    def __init__(self):
        self.users = {}

    def create_user(
        self,
        user_id: str,
        email: str,
        tenant_id: str,
        status: str = "active"
    ) -> Dict[str, Any]:

        user = {
            "user_id": user_id,
            "email": email,
            "tenant_id": tenant_id,
            "status": status
        }

        self.users[user_id] = user
        return user

    def get_user(self, user_id: str):
        return self.users.get(user_id)

    def is_active(self, user_id: str) -> bool:
        user = self.get_user(user_id)
        return bool(user and user["status"] == "active")
