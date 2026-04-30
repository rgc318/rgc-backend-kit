from __future__ import annotations

from dataclasses import dataclass, field
from time import monotonic
from typing import Any, Protocol


class TokenStore(Protocol):
    async def set_refresh_token(self, subject: str, jti: str, token: str, ttl_seconds: int) -> None:
        ...

    async def refresh_token_exists(self, subject: str, jti: str) -> bool:
        ...

    async def delete_refresh_token(self, subject: str, jti: str) -> None:
        ...

    async def revoke_token(self, jti: str, ttl_seconds: int) -> None:
        ...

    async def is_token_revoked(self, jti: str) -> bool:
        ...


class NullTokenStore:
    """No-op store for projects that only need stateless access tokens."""

    async def set_refresh_token(self, subject: str, jti: str, token: str, ttl_seconds: int) -> None:
        return None

    async def refresh_token_exists(self, subject: str, jti: str) -> bool:
        return True

    async def delete_refresh_token(self, subject: str, jti: str) -> None:
        return None

    async def revoke_token(self, jti: str, ttl_seconds: int) -> None:
        return None

    async def is_token_revoked(self, jti: str) -> bool:
        return False


@dataclass(slots=True)
class MemoryTokenStore:
    """In-memory store intended for tests and local prototypes."""

    refresh_prefix: str = "refresh"
    revoked_prefix: str = "revoked"
    _values: dict[str, tuple[str, float]] = field(default_factory=dict)

    async def set_refresh_token(self, subject: str, jti: str, token: str, ttl_seconds: int) -> None:
        self._values[self._refresh_key(subject, jti)] = (token, monotonic() + ttl_seconds)

    async def refresh_token_exists(self, subject: str, jti: str) -> bool:
        return self._exists(self._refresh_key(subject, jti))

    async def delete_refresh_token(self, subject: str, jti: str) -> None:
        self._values.pop(self._refresh_key(subject, jti), None)

    async def revoke_token(self, jti: str, ttl_seconds: int) -> None:
        self._values[self._revoked_key(jti)] = ("1", monotonic() + ttl_seconds)

    async def is_token_revoked(self, jti: str) -> bool:
        return self._exists(self._revoked_key(jti))

    def _exists(self, key: str) -> bool:
        value = self._values.get(key)
        if value is None:
            return False
        _, expires_at = value
        if monotonic() >= expires_at:
            self._values.pop(key, None)
            return False
        return True

    def _refresh_key(self, subject: str, jti: str) -> str:
        return f"{self.refresh_prefix}:{subject}:{jti}"

    def _revoked_key(self, jti: str) -> str:
        return f"{self.revoked_prefix}:{jti}"


@dataclass(slots=True)
class RedisTokenStore:
    """TokenStore adapter for redis.asyncio or compatible clients."""

    redis: Any
    refresh_prefix: str = "refresh"
    revoked_prefix: str = "revoked"

    async def set_refresh_token(self, subject: str, jti: str, token: str, ttl_seconds: int) -> None:
        await self.redis.set(self._refresh_key(subject, jti), token, ex=ttl_seconds)

    async def refresh_token_exists(self, subject: str, jti: str) -> bool:
        return bool(await self.redis.exists(self._refresh_key(subject, jti)))

    async def delete_refresh_token(self, subject: str, jti: str) -> None:
        await self.redis.delete(self._refresh_key(subject, jti))

    async def revoke_token(self, jti: str, ttl_seconds: int) -> None:
        await self.redis.set(self._revoked_key(jti), "1", ex=ttl_seconds)

    async def is_token_revoked(self, jti: str) -> bool:
        return bool(await self.redis.exists(self._revoked_key(jti)))

    def _refresh_key(self, subject: str, jti: str) -> str:
        return f"{self.refresh_prefix}:{subject}:{jti}"

    def _revoked_key(self, jti: str) -> str:
        return f"{self.revoked_prefix}:{jti}"
