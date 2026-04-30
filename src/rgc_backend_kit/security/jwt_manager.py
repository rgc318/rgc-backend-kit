from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import jwt
from jwt import ExpiredSignatureError, InvalidTokenError as PyJWTInvalidTokenError, PyJWTError

from .config import JWTConfig
from .exceptions import (
    InvalidTokenError,
    RefreshTokenReuseError,
    TokenExpiredError,
    TokenRevokedError,
    TokenTypeMismatchError,
)
from .models import TokenPair, TokenPayload, TokenType, ttl_seconds
from .token_store import NullTokenStore, TokenStore


class JWTManager:
    def __init__(self, config: JWTConfig, token_store: TokenStore | None = None) -> None:
        self.config = config
        self.token_store = token_store or NullTokenStore()

    async def issue_pair(
        self,
        subject: str,
        claims: dict[str, Any] | None = None,
        *,
        remember_me: bool = False,
    ) -> TokenPair:
        access_ttl = self.config.remember_me_access_token_ttl if remember_me else self.config.access_token_ttl
        access_token, access_jti = self.issue_access_token(subject, claims, expires_delta=access_ttl)
        refresh_token, refresh_jti = self.issue_refresh_token(subject, claims)
        await self.token_store.set_refresh_token(
            subject=subject,
            jti=refresh_jti,
            token=refresh_token,
            ttl_seconds=ttl_seconds(self.config.refresh_token_ttl),
        )
        return TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            access_expires_in=ttl_seconds(access_ttl),
            refresh_expires_in=ttl_seconds(self.config.refresh_token_ttl),
            access_jti=access_jti,
            refresh_jti=refresh_jti,
        )

    def issue_access_token(
        self,
        subject: str,
        claims: dict[str, Any] | None = None,
        *,
        expires_delta: timedelta | None = None,
    ) -> tuple[str, str]:
        return self._issue_token(subject, "access", claims, expires_delta or self.config.access_token_ttl)

    def issue_refresh_token(
        self,
        subject: str,
        claims: dict[str, Any] | None = None,
        *,
        expires_delta: timedelta | None = None,
    ) -> tuple[str, str]:
        return self._issue_token(subject, "refresh", claims, expires_delta or self.config.refresh_token_ttl)

    async def issue_stored_refresh_token(
        self,
        subject: str,
        claims: dict[str, Any] | None = None,
        *,
        expires_delta: timedelta | None = None,
    ) -> tuple[str, int, str]:
        ttl = expires_delta or self.config.refresh_token_ttl
        token, jti = self.issue_refresh_token(subject, claims, expires_delta=ttl)
        ttl_value = ttl_seconds(ttl)
        await self.token_store.set_refresh_token(subject, jti, token, ttl_value)
        return token, ttl_value, jti

    async def decode_access_token(self, token: str) -> TokenPayload:
        payload = await self.decode_token(token, expected_type="access")
        if await self.token_store.is_token_revoked(payload.jti):
            raise TokenRevokedError("Access token has been revoked.")
        return payload

    async def decode_refresh_token(self, token: str, *, verify_store: bool = True) -> TokenPayload:
        payload = await self.decode_token(token, expected_type="refresh")
        if verify_store and not await self.token_store.refresh_token_exists(payload.subject, payload.jti):
            raise RefreshTokenReuseError("Refresh token is no longer valid.")
        return payload

    async def decode_token(self, token: str, *, expected_type: TokenType | None = None) -> TokenPayload:
        try:
            raw_payload = jwt.decode(
                token,
                self.config.secret,
                algorithms=[self.config.algorithm],
                issuer=self.config.issuer,
                audience=self.config.audience,
                leeway=self.config.leeway_seconds,
                options={"require": ["sub", "exp", "iat", "nbf", "jti", "type"]},
            )
        except ExpiredSignatureError as exc:
            raise TokenExpiredError("Token has expired.") from exc
        except (PyJWTInvalidTokenError, PyJWTError) as exc:
            raise InvalidTokenError(str(exc)) from exc

        if expected_type and raw_payload.get("type") != expected_type:
            raise TokenTypeMismatchError(f"Expected {expected_type} token.")

        try:
            return TokenPayload.from_claims(raw_payload)
        except (KeyError, TypeError, ValueError) as exc:
            raise InvalidTokenError("Token payload is incomplete or invalid.") from exc

    async def rotate_refresh_token(
        self,
        refresh_token: str,
        claims: dict[str, Any] | None = None,
    ) -> TokenPair:
        payload = await self.decode_refresh_token(refresh_token, verify_store=True)
        await self.token_store.delete_refresh_token(payload.subject, payload.jti)
        merged_claims = {**(payload.claims or {}), **(claims or {})}
        return await self.issue_pair(subject=payload.subject, claims=merged_claims)

    async def revoke_access_token(self, token: str) -> None:
        payload = await self.decode_token(token, expected_type="access")
        ttl = max(0, int((payload.expires_at - datetime.now(UTC)).total_seconds()))
        if ttl > 0:
            await self.token_store.revoke_token(payload.jti, ttl)

    async def revoke_jti(self, jti: str, expires_in: int | None = None) -> None:
        await self.token_store.revoke_token(jti, expires_in or ttl_seconds(self.config.refresh_token_ttl))

    def _issue_token(
        self,
        subject: str,
        token_type: TokenType,
        claims: dict[str, Any] | None,
        expires_delta: timedelta,
    ) -> tuple[str, str]:
        now = datetime.now(UTC)
        expires_at = now + expires_delta
        jti = str(uuid4())
        payload: dict[str, Any] = {
            **(claims or {}),
            "sub": subject,
            "exp": expires_at,
            "iat": now,
            "nbf": now,
            "jti": jti,
            "type": token_type,
        }
        if self.config.issuer:
            payload["iss"] = self.config.issuer
        if self.config.audience:
            payload["aud"] = self.config.audience

        return jwt.encode(payload, self.config.secret, algorithm=self.config.algorithm), jti
