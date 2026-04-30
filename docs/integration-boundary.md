# Integration Boundary

`rgc-backend-kit` is intended to remove the need to rebuild JWT and storage infrastructure in every backend project.

It is not intended to replace each project's business services.

## What This Package Provides

Security:

- access token issuing
- refresh token issuing
- token pair issuing
- access/refresh token type validation
- refresh token rotation
- refresh token replay protection
- access token revocation
- direct JTI revocation
- Redis-backed refresh token storage and blacklist storage
- FastAPI dependency adapter

Storage:

- S3-compatible client
- MinIO, R2, and AWS S3 capability presets
- upload, delete, copy, stat, and list
- presigned GET/PUT URLs
- presigned POST policy
- public URL construction
- multi-client and multi-profile routing
- public/private multi-bucket support

## What The Host Application Still Owns

Authentication business logic:

- login request schema
- username/password lookup
- password hash verification
- user status checks
- login failure lockout
- role and permission loading
- response format
- audit logging

File business logic:

- upload endpoint schema
- allowed file types
- max file size policy
- business object ownership checks
- database file records
- uploader/user context
- file visibility rules
- image processing or virus scanning
- object naming rules tied to business concepts

## Recommended Host Project Structure

```text
my_service/
  app/
    core/
      config.py
      redis.py
    auth/
      jwt.py          # creates JWTManager
      service.py      # login, refresh, logout
      dependencies.py # get_current_user, permission checks
    storage/
      factory.py      # creates StorageFactory
      service.py      # file business logic and DB records
    users/
      service.py
      models.py
```

## JWT Thin Wrapper Example

```python
# app/auth/jwt.py
from datetime import timedelta

import redis.asyncio as redis

from rgc_backend_kit.security import JWTConfig, JWTManager, RedisTokenStore


def create_jwt_manager(settings) -> JWTManager:
    redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
    return JWTManager(
        JWTConfig(
            secret=settings.JWT_SECRET,
            issuer=settings.JWT_ISSUER,
            audience=settings.JWT_AUDIENCE,
            access_token_ttl=timedelta(minutes=settings.ACCESS_TOKEN_MINUTES),
            refresh_token_ttl=timedelta(days=settings.REFRESH_TOKEN_DAYS),
        ),
        token_store=RedisTokenStore(redis_client),
    )
```

```python
# app/auth/service.py
from fastapi import HTTPException


class AuthService:
    def __init__(self, jwt_manager, user_service, password_service):
        self.jwt_manager = jwt_manager
        self.user_service = user_service
        self.password_service = password_service

    async def login(self, username: str, password: str):
        user = await self.user_service.get_by_username(username)
        if user is None or not self.password_service.verify(password, user.password_hash):
            raise HTTPException(status_code=401, detail="Invalid credentials.")

        return await self.jwt_manager.issue_pair(
            subject=str(user.id),
            claims={"username": user.username},
        )

    async def refresh(self, refresh_token: str):
        return await self.jwt_manager.rotate_refresh_token(refresh_token)

    async def logout(self, access_token: str):
        await self.jwt_manager.revoke_access_token(access_token)
```

## Storage Thin Wrapper Example

```python
# app/storage/factory.py
from rgc_backend_kit.storage import MINIO_CAPABILITIES, S3StorageConfig, StorageFactory, StorageProfileConfig


def create_storage_factory(settings) -> StorageFactory:
    return StorageFactory.from_configs(
        client_configs={
            "public": S3StorageConfig(
                access_key=settings.STORAGE_ACCESS_KEY,
                secret_key=settings.STORAGE_SECRET_KEY,
                endpoint=settings.STORAGE_ENDPOINT,
                public_endpoint=settings.STORAGE_PUBLIC_ENDPOINT,
                bucket_name=settings.STORAGE_PUBLIC_BUCKET,
                secure=settings.STORAGE_SECURE,
                secure_public=settings.STORAGE_SECURE_PUBLIC,
                capabilities=MINIO_CAPABILITIES,
            ),
            "private": S3StorageConfig(
                access_key=settings.STORAGE_ACCESS_KEY,
                secret_key=settings.STORAGE_SECRET_KEY,
                endpoint=settings.STORAGE_ENDPOINT,
                bucket_name=settings.STORAGE_PRIVATE_BUCKET,
                secure=settings.STORAGE_SECURE,
                capabilities=MINIO_CAPABILITIES,
            ),
        },
        profiles={
            "avatars": StorageProfileConfig(client="public", base_path="avatars", public=True),
            "attachments": StorageProfileConfig(client="private", base_path="attachments"),
        },
    )
```

```python
# app/storage/service.py
from io import BytesIO
from uuid import uuid4


class FileService:
    def __init__(self, storage_factory, file_repo):
        self.storage_factory = storage_factory
        self.file_repo = file_repo

    async def upload_avatar(self, user_id: str, content: bytes, content_type: str):
        storage = self.storage_factory.get_profiled_storage("avatars")
        object_name = storage.key(f"{user_id}/{uuid4().hex}.png")

        metadata = storage.client.put_object(
            object_name,
            BytesIO(content),
            content_type=content_type,
        )

        record = await self.file_repo.create(
            user_id=user_id,
            object_name=object_name,
            profile_name="avatars",
            content_type=content_type,
            etag=metadata.get("ETag"),
        )

        return {
            "record_id": record.id,
            "object_name": object_name,
            "url": storage.build_public_url(object_name.removeprefix("avatars/")),
        }
```

## Practical Rule

Use this package for infrastructure behavior that should be consistent across services.

Keep business decisions in the host application, especially anything involving users, permissions, database records, product rules, or response schemas.

