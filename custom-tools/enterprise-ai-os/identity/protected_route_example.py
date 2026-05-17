# Example from Tool Set 35 §8 — kept here for fidelity.
# Note: source uses `router` as if it's already-defined; in a real app
# this would import from a shared router module.

from fastapi import APIRouter, Depends
from identity.auth_dependency import require_role

router = APIRouter()


@router.post("/secure-deploy")
def secure_deploy(
    user=Depends(require_role("admin"))
):
    return {
        "allowed": True,
        "user": user,
        "action": "deploy"
    }
