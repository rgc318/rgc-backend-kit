# Quickstart

This guide shows how to add `rgc-backend-kit` to a new backend project and use the JWT and storage modules.

## 1. Add Dependency

For most projects, install the package from PyPI:

```bash
pip install rgc-backend-kit
```

Or declare it in `pyproject.toml`:

```toml
[project]
dependencies = [
    "rgc-backend-kit>=0.1.0,<0.2.0",
]
```

Install only the optional integrations you need:

```bash
pip install "rgc-backend-kit[redis]"
pip install "rgc-backend-kit[fastapi]"
pip install "rgc-backend-kit[storage]"
```

For a project that needs all optional integrations:

```toml
[project]
dependencies = [
    "rgc-backend-kit[fastapi,redis,storage]>=0.1.0,<0.2.0",
]
```

If the host framework already constrains a shared dependency, keep that constraint in the host project. For example, Frappe 16 expects `PyJWT~=2.10.1`:

```toml
[project]
dependencies = [
    "PyJWT~=2.10.1",
    "rgc-backend-kit>=0.1.0,<0.2.0",
]
```

For library development:

```bash
uv sync --extra dev
```

## 2. Configure Environment

Example `.env`:

```env
JWT_SECRET=replace-with-a-long-random-secret
JWT_ISSUER=my-service
JWT_AUDIENCE=my-client

REDIS_URL=redis://:password@127.0.0.1:6379/0

MINIO_ACCESS_KEY=minio
MINIO_SECRET_KEY=minio123
MINIO_ENDPOINT=127.0.0.1:9000
MINIO_PUBLIC_ENDPOINT=img.example.com
MINIO_PUBLIC_BUCKET=public-assets
MINIO_PRIVATE_BUCKET=secure-files
```

The package does not read `.env` by itself. The host application should load environment variables and pass explicit config objects into this package.

The host application still owns business services such as login, user lookup, password verification, file records, permissions, and upload policies. See [Integration Boundary](integration-boundary.md) for recommended wrapper structure.

## 3. Create JWT Manager

```python
import os
from datetime import timedelta

import redis.asyncio as redis

from rgc_backend_kit.security import JWTConfig, JWTManager, RedisTokenStore

redis_client = redis.from_url(os.environ["REDIS_URL"], decode_responses=True)

jwt_manager = JWTManager(
    JWTConfig(
        secret=os.environ["JWT_SECRET"],
        issuer=os.getenv("JWT_ISSUER", "my-service"),
        audience=os.getenv("JWT_AUDIENCE", "my-client"),
        access_token_ttl=timedelta(minutes=60),
        refresh_token_ttl=timedelta(days=7),
        remember_me_access_token_ttl=timedelta(days=14),
    ),
    token_store=RedisTokenStore(redis_client),
)
```

## 4. Issue and Validate Tokens

```python
token_pair = await jwt_manager.issue_pair(
    subject="user-1",
    claims={"role": "admin"},
    remember_me=True,
)

payload = await jwt_manager.decode_access_token(token_pair.access_token)
assert payload.subject == "user-1"
```

Refresh token rotation:

```python
new_pair = await jwt_manager.rotate_refresh_token(token_pair.refresh_token)
```

Logout or revoke access token:

```python
await jwt_manager.revoke_access_token(token_pair.access_token)
```

## 5. Create Storage Factory

```python
import os

from rgc_backend_kit.storage import (
    MINIO_CAPABILITIES,
    S3StorageConfig,
    StorageFactory,
    StorageProfileConfig,
)

storage_factory = StorageFactory.from_configs(
    client_configs={
        "minio_public": S3StorageConfig(
            access_key=os.environ["MINIO_ACCESS_KEY"],
            secret_key=os.environ["MINIO_SECRET_KEY"],
            endpoint=os.environ["MINIO_ENDPOINT"],
            public_endpoint=os.environ["MINIO_PUBLIC_ENDPOINT"],
            bucket_name=os.environ["MINIO_PUBLIC_BUCKET"],
            secure=False,
            secure_public=True,
            capabilities=MINIO_CAPABILITIES,
        ),
        "minio_private": S3StorageConfig(
            access_key=os.environ["MINIO_ACCESS_KEY"],
            secret_key=os.environ["MINIO_SECRET_KEY"],
            endpoint=os.environ["MINIO_ENDPOINT"],
            bucket_name=os.environ["MINIO_PRIVATE_BUCKET"],
            secure=False,
            capabilities=MINIO_CAPABILITIES,
        ),
    },
    profiles={
        "avatars": StorageProfileConfig(client="minio_public", base_path="avatars", public=True),
        "private_files": StorageProfileConfig(client="minio_private", base_path="private"),
    },
)
```

## 6. Use Storage Profiles

```python
from io import BytesIO

avatars = storage_factory.get_profiled_storage("avatars")
key = avatars.key("user-1.png")

avatars.client.put_object(key, BytesIO(b"image-content"), content_type="image/png")
public_url = avatars.build_public_url("user-1.png")
```

Private presigned download:

```python
private_files = storage_factory.get_profiled_storage("private_files")
key = private_files.key("report.pdf")
download_url = private_files.client.generate_presigned_url("get_object", key, expires_in=600)
```

## 7. Run Tests

Default tests:

```bash
uv run --extra dev pytest -q
```

Redis integration tests:

```bash
REDIS_URL=redis://:password@127.0.0.1:6379/0 uv run --extra dev pytest -q -m integration
```
