# Storage Guide

This guide shows common storage flows: public uploads, private files, presigned URLs, and multi-provider configuration.

## 1. Choose Provider Capabilities

Use presets for common providers:

```python
from rgc_backend_kit.storage import AWS_S3_CAPABILITIES, MINIO_CAPABILITIES, R2_CAPABILITIES
```

Typical choices:

| Provider | Capability preset |
| --- | --- |
| MinIO | `MINIO_CAPABILITIES` |
| Cloudflare R2 | `R2_CAPABILITIES` |
| AWS S3 | `AWS_S3_CAPABILITIES` |

Use `StorageCapabilities` directly if your provider differs.

## 2. Configure Public and Private Buckets

```python
from rgc_backend_kit.storage import MINIO_CAPABILITIES, S3StorageConfig, StorageFactory, StorageProfileConfig

factory = StorageFactory.from_configs(
    client_configs={
        "public": S3StorageConfig(
            access_key="minio",
            secret_key="minio123",
            endpoint="127.0.0.1:9000",
            public_endpoint="img.example.com",
            bucket_name="public-assets",
            secure=False,
            secure_public=True,
            default_acl="public-read",
            capabilities=MINIO_CAPABILITIES,
        ),
        "private": S3StorageConfig(
            access_key="minio",
            secret_key="minio123",
            endpoint="127.0.0.1:9000",
            bucket_name="secure-files",
            secure=False,
            capabilities=MINIO_CAPABILITIES,
        ),
    },
    profiles={
        "avatars": StorageProfileConfig(client="public", base_path="avatars", public=True),
        "attachments": StorageProfileConfig(client="private", base_path="attachments"),
    },
)
```

## 3. Upload a Public Object

```python
from io import BytesIO

avatars = factory.get_profiled_storage("avatars")
key = avatars.key("user-1.png")

metadata = avatars.client.put_object(
    key,
    BytesIO(b"image-bytes"),
    content_type="image/png",
)

public_url = avatars.build_public_url("user-1.png")
```

`ProfiledStorage.key()` applies the profile `base_path`, so `user-1.png` becomes `avatars/user-1.png`.

## 4. Upload a Private Object

```python
attachments = factory.get_profiled_storage("attachments")
key = attachments.key("contract.pdf")

attachments.client.put_object(
    key,
    file_obj,
    content_type="application/pdf",
)
```

For private objects, return a presigned URL instead of a public URL.

```python
download_url = attachments.client.generate_presigned_url(
    "get_object",
    key,
    expires_in=600,
)
```

## 5. Browser Direct Upload

Use presigned POST when the storage provider supports it.

```python
avatars = factory.get_profiled_storage("avatars")
key = avatars.key("user-1.png")

policy = avatars.client.generate_presigned_post_policy(
    key,
    expires_in=600,
    fields={"Content-Type": "image/png"},
    conditions=[
        ["content-length-range", 1, 5 * 1024 * 1024],
        {"Content-Type": "image/png"},
    ],
)
```

The client browser uploads to `policy["url"]` with `policy["fields"]`.

## 6. Copy and Delete

```python
avatars = factory.get_profiled_storage("avatars")
source_key = avatars.key("user-1.png")
destination_key = avatars.key("user-1-copy.png")

avatars.client.copy_object(destination_key, source_key)
avatars.client.remove_object(source_key)
```

## 7. List Objects

```python
avatars = factory.get_profiled_storage("avatars")
objects = avatars.client.list_objects(prefix=avatars.key(""))
```

## 8. R2 Configuration

```python
from rgc_backend_kit.storage import R2_CAPABILITIES, S3StorageConfig

r2_config = S3StorageConfig(
    access_key="...",
    secret_key="...",
    endpoint="<account-id>.r2.cloudflarestorage.com",
    public_endpoint="cdn.example.com",
    bucket_name="cdn-assets",
    region="auto",
    capabilities=R2_CAPABILITIES,
)
```

R2 commonly differs from MinIO in these ways:

- bucket creation is normally managed outside the application
- ACLs are usually not used
- public URL style is usually virtual-host/CDN style

