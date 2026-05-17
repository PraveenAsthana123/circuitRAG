from typing import Dict, Any


class CanaryManager:
    def create_plan(
        self,
        release_id: str,
        stable_weight: int = 90,
        canary_weight: int = 10
    ) -> Dict[str, Any]:

        if stable_weight + canary_weight != 100:
            raise ValueError("Traffic weights must total 100")

        return {
            "release_id": release_id,
            "stable_weight": stable_weight,
            "canary_weight": canary_weight,
            "status": "canary_started"
        }

    def increase_canary(
        self,
        plan: Dict[str, Any],
        new_canary_weight: int
    ) -> Dict[str, Any]:

        if new_canary_weight < 0 or new_canary_weight > 100:
            raise ValueError("Canary weight must be between 0 and 100")

        plan["canary_weight"] = new_canary_weight
        plan["stable_weight"] = 100 - new_canary_weight

        if new_canary_weight == 100:
            plan["status"] = "fully_promoted"
        else:
            plan["status"] = "canary_increased"

        return plan
