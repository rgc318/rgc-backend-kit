from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from .exceptions import InvalidTokenError
from .jwt_manager import JWTManager

UserT = TypeVar("UserT")
LoadUser = Callable[[str], Awaitable[UserT | None]]


class FastAPIJWTAuth:
    def __init__(self, jwt_manager: JWTManager, token_url: str = "/auth/login") -> None:
        try:
            from fastapi.security import OAuth2PasswordBearer
        except ImportError as exc:
            raise RuntimeError("Install rgc-backend-kit[fastapi] to use FastAPIJWTAuth.") from exc

        self.jwt_manager = jwt_manager
        self.oauth2_scheme = OAuth2PasswordBearer(tokenUrl=token_url)

    def current_payload_dependency(self):
        from fastapi import Depends, HTTPException, status

        async def dependency(token: str = Depends(self.oauth2_scheme)):
            try:
                return await self.jwt_manager.decode_access_token(token)
            except InvalidTokenError as exc:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=str(exc) or "Invalid token.",
                    headers={"WWW-Authenticate": "Bearer"},
                ) from exc

        return dependency

    def current_user_dependency(self, load_user: LoadUser[UserT]):
        from fastapi import Depends, HTTPException, status

        payload_dependency = self.current_payload_dependency()

        async def dependency(payload: Any = Depends(payload_dependency)):
            user = await load_user(payload.subject)
            if user is None:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found.")
            return user

        return dependency

