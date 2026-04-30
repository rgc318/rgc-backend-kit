# FastAPI JWT Guide

This guide shows how to use the security module in a FastAPI application.

The package handles token lifecycle. Your application still owns user lookup, password verification, roles, permissions, and response format.

## 1. Create Auth Components

```python
from datetime import timedelta

import redis.asyncio as redis

from rgc_backend_kit.security import JWTConfig, JWTManager, RedisTokenStore
from rgc_backend_kit.security.fastapi_adapter import FastAPIJWTAuth

redis_client = redis.from_url("redis://:password@127.0.0.1:6379/0", decode_responses=True)

jwt_manager = JWTManager(
    JWTConfig(
        secret="replace-with-a-long-random-secret",
        issuer="my-service",
        audience="my-client",
        access_token_ttl=timedelta(minutes=60),
        refresh_token_ttl=timedelta(days=7),
    ),
    token_store=RedisTokenStore(redis_client),
)

auth = FastAPIJWTAuth(jwt_manager, token_url="/auth/login")
```

## 2. Implement User Loader

The loader receives the token `sub` claim.

```python
async def load_user(user_id: str):
    user = await user_service.get_by_id(user_id)
    if user is None or not user.is_active:
        return None
    return user
```

## 3. Protect Routes

```python
from fastapi import Depends, FastAPI

app = FastAPI()
get_current_user = auth.current_user_dependency(load_user)

@app.get("/me")
async def me(user=Depends(get_current_user)):
    return {
        "id": user.id,
        "username": user.username,
    }
```

## 4. Login Endpoint

Password verification is application code. Token issuing uses `JWTManager`.

```python
from fastapi import HTTPException
from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str
    remember_me: bool = False


@app.post("/auth/login")
async def login(data: LoginRequest):
    user = await user_service.get_by_username(data.username)
    if user is None or not password_service.verify(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password.")

    pair = await jwt_manager.issue_pair(
        subject=str(user.id),
        claims={"username": user.username},
        remember_me=data.remember_me,
    )
    return {
        "access_token": pair.access_token,
        "refresh_token": pair.refresh_token,
        "token_type": pair.token_type,
        "expires_in": pair.access_expires_in,
    }
```

## 5. Refresh Endpoint

Refresh rotation invalidates the old refresh token and issues a new pair.

```python
class RefreshRequest(BaseModel):
    refresh_token: str


@app.post("/auth/refresh")
async def refresh(data: RefreshRequest):
    try:
        pair = await jwt_manager.rotate_refresh_token(data.refresh_token)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid refresh token.") from exc

    return {
        "access_token": pair.access_token,
        "refresh_token": pair.refresh_token,
        "token_type": pair.token_type,
        "expires_in": pair.access_expires_in,
    }
```

If the old refresh token is reused after rotation, `RefreshTokenReuseError` is raised.

## 6. Logout Endpoint

Logout normally revokes the current access token. If your application also wants to invalidate a refresh token, decode it and delete it through the token store or rotate your session model accordingly.

```python
from fastapi.security import OAuth2PasswordBearer

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


@app.post("/auth/logout")
async def logout(token: str = Depends(oauth2_scheme)):
    await jwt_manager.revoke_access_token(token)
    return {"ok": True}
```

## 7. Exception Mapping

Recommended mapping:

| Exception | HTTP status |
| --- | --- |
| `TokenExpiredError` | `401` |
| `TokenRevokedError` | `401` |
| `TokenTypeMismatchError` | `401` |
| `RefreshTokenReuseError` | `401` |
| `InvalidTokenError` | `401` |

For business permission failures, use your application's authorization layer and return `403`.

