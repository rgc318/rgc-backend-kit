# Package Validation

This document describes the release-style validation flow for `rgc-backend-kit`.

The goal is to verify not only the source tree, but also the built wheel installed in a clean environment.

## Validation Levels

1. Source tests
2. Redis integration tests
3. Build artifacts
4. Wheel installation in an isolated environment
5. Package-level functionality smoke test

## 1. Source Tests

Run the default test suite from the repository root:

```bash
uv run --extra dev pytest -q
```

Expected current result:

```text
32 passed, 2 deselected
```

The two deselected tests are Redis integration tests.

## 2. Redis Integration Tests

Run integration tests with a real Redis service:

```bash
REDIS_URL=redis://:password@127.0.0.1:6379/0 \
uv run --extra dev pytest -q -m integration
```

Expected current result:

```text
2 passed, 32 deselected
```

These tests verify:

- refresh token persistence in Redis
- Redis TTL behavior
- refresh token rotation
- old refresh token key deletion
- access token revoke blacklist writes
- revoked access token rejection

## 3. Build Artifacts

Build wheel and source distribution:

```bash
uv build
```

Expected artifacts:

```text
dist/rgc_backend_kit-0.1.0.tar.gz
dist/rgc_backend_kit-0.1.0-py3-none-any.whl
```

## 4. Install Wheel in an Isolated Environment

Create a clean temporary environment:

```bash
rm -rf /tmp/rgc-backend-kit-package-full-test
mkdir -p /tmp/rgc-backend-kit-package-full-test
cd /tmp/rgc-backend-kit-package-full-test

uv venv
uv pip install \
  '/home/rgc318/Projects/rgc-backend-kit/dist/rgc_backend_kit-0.1.0-py3-none-any.whl[fastapi,redis,storage]' \
  httpx
```

Confirm imports come from the isolated `site-packages`, not the source tree:

```bash
.venv/bin/python - <<'PY'
import rgc_backend_kit
import rgc_backend_kit.security
import rgc_backend_kit.storage

print(rgc_backend_kit.__file__)
print(rgc_backend_kit.security.__file__)
print(rgc_backend_kit.storage.__file__)
PY
```

The output should point to:

```text
/tmp/rgc-backend-kit-package-full-test/.venv/lib/.../site-packages/rgc_backend_kit/...
```

## 5. Package Functionality Smoke Test

Run a package-level script from the isolated environment. This verifies the installed wheel package instead of the source tree.

```bash
REDIS_URL=redis://:password@127.0.0.1:6379/0 \
.venv/bin/python - <<'PY'
import asyncio
import os
from datetime import timedelta
from io import BytesIO
from uuid import uuid4

import redis.asyncio as redis
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from rgc_backend_kit.security import (
    InvalidTokenError,
    JWTConfig,
    JWTManager,
    MemoryTokenStore,
    RedisTokenStore,
    RefreshTokenReuseError,
    TokenExpiredError,
    TokenRevokedError,
    TokenTypeMismatchError,
)
from rgc_backend_kit.security.fastapi_adapter import FastAPIJWTAuth
from rgc_backend_kit.storage import (
    AWS_S3_CAPABILITIES,
    MINIO_CAPABILITIES,
    R2_CAPABILITIES,
    S3StorageConfig,
    S3StorageClient,
    StorageConfigurationError,
    StorageFactory,
    StorageProfileConfig,
)


class FakeBotoClient:
    def upload_fileobj(self, Fileobj, Bucket, Key, ExtraArgs):
        self.upload = (Fileobj.read(), Bucket, Key, ExtraArgs)

    def head_object(self, Bucket, Key):
        return {"Bucket": Bucket, "Key": Key, "ETag": '"etag"', "ContentLength": 12}

    def delete_object(self, Bucket, Key):
        return {"Deleted": Key}

    def copy_object(self, **params):
        return {"CopyObjectResult": {"ETag": '"copy-etag"'}, "Params": params}

    def generate_presigned_url(self, ClientMethod, Params, ExpiresIn):
        return f"http://internal.local/{Params['Bucket']}/{Params['Key']}?expires={ExpiresIn}"

    def generate_presigned_post(self, Bucket, Key, Fields, Conditions, ExpiresIn):
        return {"url": f"http://internal.local/{Bucket}", "fields": Fields or {}}

    def get_paginator(self, name):
        class Paginator:
            def paginate(self, Bucket, Prefix):
                return [{"Contents": [{"Key": "avatars/a.png", "Size": 10, "LastModified": "now", "ETag": '"etag"'}]}]

        return Paginator()


class FactoryFakeClient:
    def __init__(self, config):
        self.bucket_name = config.bucket_name

    def build_public_url(self, key):
        return f"https://cdn.example.com/{self.bucket_name}/{key}"


async def main():
    manager = JWTManager(
        JWTConfig(
            secret="package-test-secret-with-at-least-32-bytes",
            issuer="package-test",
            audience="package-client",
            access_token_ttl=timedelta(minutes=5),
            refresh_token_ttl=timedelta(minutes=10),
        ),
        token_store=MemoryTokenStore(),
    )

    pair = await manager.issue_pair("user-1", {"role": "admin"})
    payload = await manager.decode_access_token(pair.access_token)
    assert payload.subject == "user-1"

    rotated = await manager.rotate_refresh_token(pair.refresh_token)
    try:
        await manager.rotate_refresh_token(pair.refresh_token)
    except RefreshTokenReuseError:
        pass
    else:
        raise AssertionError("old refresh token was reusable")

    await manager.revoke_access_token(rotated.access_token)
    try:
        await manager.decode_access_token(rotated.access_token)
    except TokenRevokedError:
        pass
    else:
        raise AssertionError("revoked access token was accepted")

    expired, _ = manager.issue_access_token("user-1", expires_delta=timedelta(seconds=-1))
    try:
        await manager.decode_access_token(expired)
    except TokenExpiredError:
        pass
    else:
        raise AssertionError("expired token was accepted")

    try:
        await manager.decode_access_token(pair.refresh_token)
    except TokenTypeMismatchError:
        pass
    else:
        raise AssertionError("refresh token accepted as access token")

    try:
        await manager.decode_access_token("not-a-token")
    except InvalidTokenError:
        pass
    else:
        raise AssertionError("invalid token was accepted")

    redis_client = redis.from_url(os.environ["REDIS_URL"], decode_responses=True)
    suffix = uuid4().hex
    refresh_prefix = f"pkg-refresh:{suffix}"
    revoked_prefix = f"pkg-revoked:{suffix}"
    redis_manager = JWTManager(
        JWTConfig(secret="redis-package-test-secret-with-at-least-32-bytes"),
        token_store=RedisTokenStore(redis_client, refresh_prefix=refresh_prefix, revoked_prefix=revoked_prefix),
    )

    try:
        redis_pair = await redis_manager.issue_pair("redis-user")
        assert await redis_client.exists(f"{refresh_prefix}:redis-user:{redis_pair.refresh_jti}") == 1
        await redis_manager.revoke_access_token(redis_pair.access_token)
        assert await redis_client.exists(f"{revoked_prefix}:{redis_pair.access_jti}") == 1
    finally:
        async for key in redis_client.scan_iter(f"{refresh_prefix}:*"):
            await redis_client.delete(key)
        async for key in redis_client.scan_iter(f"{revoked_prefix}:*"):
            await redis_client.delete(key)
        await redis_client.aclose()

    auth = FastAPIJWTAuth(manager)
    app = FastAPI()

    async def load_user(user_id):
        return {"id": user_id}

    @app.get("/me")
    async def me(user=Depends(auth.current_user_dependency(load_user))):
        return user

    response = TestClient(app).get("/me", headers={"Authorization": f"Bearer {pair.access_token}"})
    assert response.status_code == 200

    fake = FakeBotoClient()
    storage_client = S3StorageClient(
        S3StorageConfig(
            access_key="key",
            secret_key="secret",
            endpoint="127.0.0.1:9000",
            public_endpoint="img.example.com",
            bucket_name="public-assets",
            secure=False,
            secure_public=True,
            default_acl="public-read",
            capabilities=MINIO_CAPABILITIES,
        ),
        boto3_client=fake,
    )
    assert storage_client.put_object("avatars/a.png", BytesIO(b"content"), content_type="image/png")["ETag"] == "etag"
    assert storage_client.build_public_url("avatars/a b.png") == "https://img.example.com/public-assets/avatars/a%20b.png"
    assert storage_client.generate_presigned_url("get_object", "avatars/a.png").startswith("https://img.example.com/")

    factory = StorageFactory.from_configs(
        client_configs={
            "minio": storage_client.config,
            "r2": S3StorageConfig(
                access_key="r2",
                secret_key="secret",
                endpoint="account.r2.cloudflarestorage.com",
                bucket_name="cdn-assets",
                region="auto",
                capabilities=R2_CAPABILITIES,
            ),
            "aws": S3StorageConfig(
                access_key="aws",
                secret_key="secret",
                bucket_name="aws-assets",
                capabilities=AWS_S3_CAPABILITIES,
            ),
        },
        profiles={"avatars": StorageProfileConfig(client="minio", base_path="avatars")},
        client_builder=FactoryFakeClient,
    )
    assert factory.get_profiled_storage("avatars").key("a.png") == "avatars/a.png"

    try:
        StorageFactory(clients={}, profiles={"bad": StorageProfileConfig(client="missing")})
    except StorageConfigurationError:
        pass
    else:
        raise AssertionError("missing client profile was accepted")


asyncio.run(main())
print("full package functionality test passed")
PY
```

Expected output:

```text
full package functionality test passed
```

This script covers:

- JWT access and refresh issuing
- token decoding
- token type validation
- refresh rotation
- refresh replay rejection
- access token revocation
- expired and invalid token rejection
- Redis-backed refresh and revoke keys
- FastAPI adapter
- S3-compatible client operations with an injected fake boto client
- public URL and presigned URL rewriting
- `StorageFactory` multi-client/profile behavior
- MinIO, R2, and AWS capability presets

## Real Storage Integration

When a MinIO or other S3-compatible service is available, run:

```bash
STORAGE_ACCESS_KEY=minio \
STORAGE_SECRET_KEY=minio123 \
STORAGE_ENDPOINT=127.0.0.1:9000 \
STORAGE_PUBLIC_ENDPOINT=img.example.com \
STORAGE_PUBLIC_BUCKET=public-assets \
STORAGE_PRIVATE_BUCKET=secure-files \
uv run --extra dev pytest -q tests/integration/test_s3_storage_client.py
```

This validates the real storage lifecycle with unique temporary object keys and cleanup.

To verify the built wheel against a real storage service, install the storage extra in a clean environment:

```bash
rm -rf /tmp/rgc-backend-kit-storage-package-test
mkdir -p /tmp/rgc-backend-kit-storage-package-test
cd /tmp/rgc-backend-kit-storage-package-test

uv venv
uv pip install '/home/rgc318/Projects/rgc-backend-kit/dist/rgc_backend_kit-0.1.0-py3-none-any.whl[storage]'
```

Then run a storage lifecycle script from that environment:

```bash
STORAGE_ACCESS_KEY=minio \
STORAGE_SECRET_KEY=minio123 \
STORAGE_ENDPOINT=127.0.0.1:9000 \
STORAGE_PUBLIC_ENDPOINT=img.example.com \
STORAGE_PUBLIC_BUCKET=public-assets \
STORAGE_PRIVATE_BUCKET=secure-files \
.venv/bin/python - <<'PY'
import os
from io import BytesIO
from uuid import uuid4

from rgc_backend_kit.storage import (
    MINIO_CAPABILITIES,
    S3StorageClient,
    S3StorageConfig,
    StorageFactory,
    StorageOperationError,
    StorageProfileConfig,
)

config = S3StorageConfig(
    access_key=os.environ["STORAGE_ACCESS_KEY"],
    secret_key=os.environ["STORAGE_SECRET_KEY"],
    endpoint=os.environ["STORAGE_ENDPOINT"],
    public_endpoint=os.environ["STORAGE_PUBLIC_ENDPOINT"],
    bucket_name=os.environ["STORAGE_PUBLIC_BUCKET"],
    secure=False,
    secure_public=True,
    capabilities=MINIO_CAPABILITIES,
)
client = S3StorageClient(config)
prefix = f"rgc-backend-kit-pkg-it/{uuid4().hex}"
source_key = f"{prefix}/source.txt"
copy_key = f"{prefix}/copy.txt"

def cleanup(*keys):
    for key in keys:
        try:
            client.remove_object(key)
        except StorageOperationError:
            pass

try:
    client.put_object(source_key, BytesIO(b"package storage content"), content_type="text/plain")
    assert client.stat_object(source_key)["ContentLength"] == len(b"package storage content")
    assert any(item["key"] == source_key for item in client.list_objects(prefix))
    assert client.copy_object(copy_key, source_key)
    assert source_key in client.generate_presigned_url("get_object", source_key, expires_in=60)

    private_config = S3StorageConfig(
        access_key=os.environ["STORAGE_ACCESS_KEY"],
        secret_key=os.environ["STORAGE_SECRET_KEY"],
        endpoint=os.environ["STORAGE_ENDPOINT"],
        bucket_name=os.environ["STORAGE_PRIVATE_BUCKET"],
        secure=False,
        capabilities=MINIO_CAPABILITIES,
    )
    factory = StorageFactory.from_configs(
        client_configs={"public": config, "private": private_config},
        profiles={
            "public_assets": StorageProfileConfig(client="public", base_path="public-it", public=True),
            "private_files": StorageProfileConfig(client="private", base_path="private-it"),
        },
    )
    assert factory.get_client_by_profile("public_assets").bucket_name == os.environ["STORAGE_PUBLIC_BUCKET"]
    assert factory.get_client_by_profile("private_files").bucket_name == os.environ["STORAGE_PRIVATE_BUCKET"]
finally:
    cleanup(source_key, copy_key)

print("storage wheel integration test passed")
PY
```

Expected output:

```text
storage wheel integration test passed
```
