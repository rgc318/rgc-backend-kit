# Storage Module

The storage module wraps S3-compatible object stores such as MinIO, AWS S3, Cloudflare R2, and compatible private services.

It provides a small reusable storage layer, not a business file-management service. File records, ownership checks, content moderation, and database persistence should stay in the host application.

## Design

- Multiple storage clients can be registered, each pointing at a different provider or bucket.
- Business scenarios can be routed through profiles such as `avatars`, `private_files`, or `recipe_images`.
- Storage configuration is explicit through `S3StorageConfig`.
- Provider differences are represented by `StorageCapabilities`.
- Public URL building is separated from upload, copy, delete, and presigned URL operations.
- Boto3 client creation is internal by default, but tests and host applications may inject a compatible client.

## Public API

- `S3StorageConfig`: endpoint, bucket, credentials, region, timeout, ACL, and public URL settings.
- `StorageCapabilities`: provider behavior flags.
- `S3StorageClient`: S3-compatible client implementation.
- `StorageFactory`: multi-client and profile registry.
- `StorageProfileConfig`: business profile mapping to a client and optional base path.
- `ProfiledStorage`: profile-aware wrapper that applies `base_path`.
- `MINIO_CAPABILITIES`, `R2_CAPABILITIES`, `AWS_S3_CAPABILITIES`: common provider presets.

## Capability Presets

```python
from rgc_backend_kit.storage import AWS_S3_CAPABILITIES, MINIO_CAPABILITIES, R2_CAPABILITIES

minio_capabilities = MINIO_CAPABILITIES
r2_capabilities = R2_CAPABILITIES
aws_capabilities = AWS_S3_CAPABILITIES
```

Use custom capabilities when the provider differs from these defaults:

```python
from rgc_backend_kit.storage import StorageCapabilities

custom_capabilities = StorageCapabilities(
    path_style="path",
    supports_acl=False,
    supports_bucket_creation=False,
    rewrite_presigned_host=True,
    public_url_path_style=True,
)
```

## MinIO Example

```python
from rgc_backend_kit.storage import MINIO_CAPABILITIES, S3StorageConfig, S3StorageClient

client = S3StorageClient(
    S3StorageConfig(
        access_key="minio",
        secret_key="minio123",
        endpoint="192.168.31.229:19000",
        public_endpoint="img.example.com",
        bucket_name="public-assets-bucket",
        secure=False,
        secure_public=True,
        default_acl="public-read",
        capabilities=MINIO_CAPABILITIES,
    )
)

url = client.build_public_url("avatars/user-1.png")
```

## Cloudflare R2 Example

```python
from rgc_backend_kit.storage import R2_CAPABILITIES, S3StorageConfig, S3StorageClient

client = S3StorageClient(
    S3StorageConfig(
        access_key="...",
        secret_key="...",
        endpoint="<account-id>.r2.cloudflarestorage.com",
        public_endpoint="cdn.example.com",
        bucket_name="cdn-assets",
        region="auto",
        capabilities=R2_CAPABILITIES,
    )
)
```

## Multiple Buckets and Profiles

One `S3StorageClient` points at one bucket. Multiple buckets or providers are represented by multiple registered clients.

```python
from rgc_backend_kit.storage import (
    MINIO_CAPABILITIES,
    R2_CAPABILITIES,
    S3StorageConfig,
    StorageFactory,
    StorageProfileConfig,
)

factory = StorageFactory.from_configs(
    client_configs={
        "minio_public": S3StorageConfig(
            access_key="minio",
            secret_key="minio123",
            endpoint="192.168.31.229:19000",
            public_endpoint="img.rgcdev.top",
            bucket_name="public-assets-bucket",
            secure=False,
            secure_public=True,
            capabilities=MINIO_CAPABILITIES,
        ),
        "minio_private": S3StorageConfig(
            access_key="minio",
            secret_key="minio123",
            endpoint="192.168.31.229:19000",
            bucket_name="secure-files-bucket",
            secure=False,
            capabilities=MINIO_CAPABILITIES,
        ),
        "r2_public": S3StorageConfig(
            access_key="...",
            secret_key="...",
            endpoint="<account-id>.r2.cloudflarestorage.com",
            public_endpoint="cdn.example.com",
            bucket_name="cdn-assets",
            region="auto",
            capabilities=R2_CAPABILITIES,
        ),
    },
    profiles={
        "avatars": StorageProfileConfig(client="minio_public", base_path="avatars", public=True),
        "private_files": StorageProfileConfig(client="minio_private", base_path="private"),
        "recipe_images": StorageProfileConfig(client="r2_public", base_path="recipes/images", public=True),
    },
)

avatars = factory.get_profiled_storage("avatars")
avatar_url = avatars.build_public_url("user-1.png")
```

## Object Operations

```python
from io import BytesIO

profiled = factory.get_profiled_storage("avatars")
client = profiled.client
key = profiled.key("user-1.png")

client.put_object(key, BytesIO(b"content"), content_type="image/png")
client.stat_object(key)
client.copy_object("avatars/user-1-copy.png", key)
client.generate_presigned_url("get_object", key, expires_in=3600)
client.generate_presigned_post_policy(key, expires_in=3600)
client.remove_object(key)
```

## Integration Testing

The storage integration suite can validate a real S3-compatible service such as MinIO.

```bash
STORAGE_ACCESS_KEY=minio \
STORAGE_SECRET_KEY=minio123 \
STORAGE_ENDPOINT=127.0.0.1:9000 \
STORAGE_PUBLIC_ENDPOINT=img.example.com \
STORAGE_PUBLIC_BUCKET=public-assets \
STORAGE_PRIVATE_BUCKET=secure-files \
uv run --extra dev pytest -q tests/integration/test_s3_storage_client.py
```

It verifies upload, stat, list, copy, public URL building, presigned URL generation, presigned POST policy generation, delete, and public/private bucket profile routing. The public and private bucket profiles are both tested with real upload, stat, list, and cleanup operations.

Cloudflare R2 integration can be tested separately when credentials are available:

```bash
R2_ACCESS_KEY=... \
R2_SECRET_KEY=... \
R2_ENDPOINT=<account-id>.r2.cloudflarestorage.com \
R2_BUCKET=cdn-assets \
R2_PUBLIC_ENDPOINT=cdn.example.com \
uv run --extra dev pytest -q -m integration tests/integration/test_r2_storage_client.py
```

The R2 test validates upload, stat, list, copy, presigned GET, presigned PUT, and cleanup. Presigned POST is not required by the R2 integration suite because compatibility differs by provider.

The current `ai_recipes` R2-style configuration uses:

```env
R2_ENDPOINT=3fe4d9c093fe77e5877f03447e4f349d.r2.cloudflarestorage.com
R2_BUCKET=test
R2_PUBLIC_ENDPOINT=r2.rgcdev.top
R2_REGION=auto
```

Keep R2 credentials in ignored environment files or CI secrets.

## Exceptions

- `StorageConfigurationError`: missing client/profile or invalid storage registry configuration.
- `StorageOperationError`: backend operation failed.
- `StorageError`: base storage exception.
