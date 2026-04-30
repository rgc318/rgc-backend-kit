# Security Module

The security module provides framework-neutral JWT token lifecycle management.

It covers the reusable token layer only. Login forms, password verification, user status checks, roles, permissions, and API response formatting should stay in the business application.

## Design

- No dependency on application settings, ORM models, user services, or business exceptions.
- All configuration is provided through `JWTConfig`.
- Redis is optional and injected through `TokenStore`.
- FastAPI support lives in `FastAPIJWTAuth`; `JWTManager` itself is framework-neutral.
- Exceptions are package-level Python exceptions that host applications can translate to their own API error format.

## Public API

- `JWTConfig`: signing algorithm, secret, issuer, audience, token TTLs, key prefixes, and leeway.
- `JWTManager`: token issuing, decoding, refresh rotation, and revocation.
- `TokenPair`: return model for access/refresh token pairs.
- `TokenPayload`: decoded token payload model.
- `TokenStore`: async protocol for refresh storage and access-token blacklist checks.
- `MemoryTokenStore`: in-memory store for tests and local prototypes.
- `NullTokenStore`: no-op store for stateless-only use cases.
- `RedisTokenStore`: adapter for `redis.asyncio` compatible clients.
- `FastAPIJWTAuth`: optional FastAPI dependency adapter.

## Token Claims

Issued tokens include:

- `sub`: subject, usually user id
- `type`: `access` or `refresh`
- `jti`: unique token id
- `iat`: issued at
- `nbf`: not before
- `exp`: expiration
- `iss`: issuer, when configured
- `aud`: audience, when configured
- custom claims passed by the application

Decoding validates signature, expiration, not-before, issuer, audience, required claims, and token type.

## Basic Usage

```python
from datetime import timedelta

from rgc_backend_kit.security import JWTConfig, JWTManager, MemoryTokenStore

manager = JWTManager(
    JWTConfig(
        secret="replace-with-a-long-random-secret",
        issuer="my-service",
        audience="my-client",
        access_token_ttl=timedelta(minutes=60),
        refresh_token_ttl=timedelta(days=7),
    ),
    token_store=MemoryTokenStore(),
)

pair = await manager.issue_pair("user-1", {"role": "admin"})
payload = await manager.decode_access_token(pair.access_token)
```

## Refresh Token Rotation

```python
pair = await manager.issue_pair("user-1")
rotated = await manager.rotate_refresh_token(pair.refresh_token)
```

Rotation verifies that the refresh token:

- is signed correctly
- is not expired
- has token type `refresh`
- still exists in the configured `TokenStore`

After rotation, the old refresh token is deleted from the store. Reusing it raises `RefreshTokenReuseError`.

## Revocation

Access token revocation stores the token `jti` in the configured store until the token would naturally expire.

```python
await manager.revoke_access_token(access_token)
```

Direct JTI revocation is also available:

```python
await manager.revoke_jti("token-jti", expires_in=3600)
```

`decode_access_token` checks the revocation store and raises `TokenRevokedError` for revoked access tokens.

## Redis Integration

```python
import redis.asyncio as redis

from rgc_backend_kit.security import JWTConfig, JWTManager, RedisTokenStore

redis_client = redis.from_url("redis://:password@127.0.0.1:6379/0", decode_responses=True)

manager = JWTManager(
    JWTConfig(secret="replace-with-a-long-random-secret", issuer="my-service"),
    token_store=RedisTokenStore(redis_client),
)
```

Default Redis key formats are compatible with the original `ai_recipes` token utility:

- `refresh:{subject}:{jti}`
- `revoked:{jti}`

Custom prefixes can be supplied:

```python
RedisTokenStore(redis_client, refresh_prefix="my-refresh", revoked_prefix="my-revoked")
```

## FastAPI Integration

```python
from fastapi import Depends, FastAPI

from rgc_backend_kit.security.fastapi_adapter import FastAPIJWTAuth

auth = FastAPIJWTAuth(manager, token_url="/auth/login")
app = FastAPI()

async def load_user(user_id: str):
    return await user_service.get_user_context(user_id)

get_current_user = auth.current_user_dependency(load_user)

@app.get("/me")
async def me(user=Depends(get_current_user)):
    return user
```

The adapter validates the access token, extracts `sub`, calls the supplied user loader, and returns `401` for invalid tokens or missing users.

## Exceptions

- `InvalidTokenError`: invalid signature, invalid issuer/audience, malformed token, or missing claim.
- `TokenExpiredError`: token has expired.
- `TokenRevokedError`: access token has been revoked.
- `TokenTypeMismatchError`: token type is not valid for the operation.
- `RefreshTokenReuseError`: refresh token is not present in the store, usually because it was rotated or deleted.

## Test Coverage

The JWT test suite covers:

- access and refresh token issuing
- stored refresh tokens
- `remember_me` access token TTL
- issuer and audience checks
- expiration and required claims
- access/refresh token type separation
- refresh rotation and replay protection
- access token revocation
- direct JTI revocation
- memory, null, and Redis-compatible token stores
- FastAPI dependency adapter behavior
- real Redis integration tests

