from fastapi import Depends, Header, HTTPException
from identity.jwt_auth import JWTAuth, TokenInvalidError


auth = JWTAuth()


def get_current_user(
    authorization: str | None = Header(default=None)
):
    if not authorization:
        raise HTTPException(
            status_code=401,
            detail="Missing Authorization header"
        )

    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Invalid Authorization header format"
        )

    token = authorization.replace("Bearer ", "")

    try:
        claims = auth.verify_token(token)
    except TokenInvalidError:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token"
        )

    return claims


def require_role(required_role: str):
    def dependency(user=Depends(get_current_user)):
        roles = user.get("roles", [])

        if required_role not in roles:
            raise HTTPException(
                status_code=403,
                detail=f"Missing required role: {required_role}"
            )

        return user

    return dependency
