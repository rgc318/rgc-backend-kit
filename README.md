# rgc-backend-kit

`rgc-backend-kit` is a reusable Python backend component library extracted from `ai_recipes`.

It currently provides:

- `rgc_backend_kit.security`: framework-neutral JWT token lifecycle management.
- `rgc_backend_kit.storage`: S3-compatible object storage clients, capability presets, and profile routing.

The package is designed for business services that need shared infrastructure without importing another application's settings, ORM models, response classes, or global factories.

Host applications still own business logic such as login, password verification, permissions, file records, upload policies, and response schemas. See [Integration Boundary](docs/integration-boundary.md).

## Requirements

- Python `>=3.10`
- `pyjwt>=2.8.0,<2.13.0` for JWT support
- Optional `redis` for Redis-backed token storage
- Optional `fastapi` for FastAPI dependency adapters
- Optional `boto3` / `botocore` for S3-compatible storage

## Install

From PyPI:

```bash
pip install rgc-backend-kit
```

With optional features:

```bash
pip install "rgc-backend-kit[fastapi,redis,storage]"
```

As a dependency in another project:

```toml
[project]
dependencies = [
    "rgc-backend-kit>=0.1.1,<0.2.0",
]
```

Use extras only for the optional integrations that project needs:

```toml
[project]
dependencies = [
    "rgc-backend-kit[redis]>=0.1.1,<0.2.0",
    "rgc-backend-kit[storage]>=0.1.1,<0.2.0",
]
```

Host applications may add their own constraints for shared dependencies. For example, a Frappe 16 app should let Frappe keep `PyJWT` in its supported range and only add this package directly:

```toml
[project]
dependencies = [
    "rgc-backend-kit>=0.1.1,<0.2.0",
]
```

Local development:

```bash
uv sync --extra dev
```

## JWT Quick Start

```python
from datetime import timedelta

from rgc_backend_kit.security import JWTConfig, JWTManager, RedisTokenStore

manager = JWTManager(
    config=JWTConfig(
        secret="replace-with-a-long-random-secret",
        issuer="my-service",
        audience="my-client",
        access_token_ttl=timedelta(minutes=60),
        refresh_token_ttl=timedelta(days=7),
    ),
    token_store=RedisTokenStore(redis),
)

token_pair = await manager.issue_pair(subject="user-id", claims={"role": "admin"})
payload = await manager.decode_access_token(token_pair.access_token)
rotated = await manager.rotate_refresh_token(token_pair.refresh_token)
await manager.revoke_access_token(rotated.access_token)
```

## Storage Quick Start

```python
from rgc_backend_kit.storage import (
    MINIO_CAPABILITIES,
    S3StorageConfig,
    StorageFactory,
    StorageProfileConfig,
)

factory = StorageFactory.from_configs(
    client_configs={
        "minio_public": S3StorageConfig(
            access_key="minio",
            secret_key="minio123",
            endpoint="127.0.0.1:9000",
            public_endpoint="img.example.com",
            bucket_name="public-assets",
            secure=False,
            secure_public=True,
            capabilities=MINIO_CAPABILITIES,
        )
    },
    profiles={
        "avatars": StorageProfileConfig(
            client="minio_public",
            base_path="avatars",
            public=True,
        )
    },
)

avatars = factory.get_profiled_storage("avatars")
url = avatars.build_public_url("demo.png")
```

## Tests

Default tests do not require external services:

```bash
uv run --extra dev pytest -q
```

Redis integration tests require a real Redis instance:

```bash
REDIS_URL=redis://:password@127.0.0.1:6379/0 uv run --extra dev pytest -q -m integration
```

Build package artifacts:

```bash
uv build
```

Validate the built wheel in an isolated environment before publishing:

```bash
rm -rf /tmp/rgc-backend-kit-package-full-test
mkdir -p /tmp/rgc-backend-kit-package-full-test
cd /tmp/rgc-backend-kit-package-full-test
uv venv
uv pip install '/home/rgc318/Projects/rgc-backend-kit/dist/rgc_backend_kit-0.1.1-py3-none-any.whl[fastapi,redis,storage]' httpx
```

## Documentation

- [Quickstart](docs/quickstart.md)
- [Security Module](docs/security.md)
- [FastAPI JWT Guide](docs/fastapi-auth-guide.md)
- [Storage Module](docs/storage.md)
- [Storage Guide](docs/storage-guide.md)
- [Integration Boundary](docs/integration-boundary.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Package Validation](docs/package-validation.md)
- [Testing Guide](tests/README.md)
- [ai_recipes Migration Notes](docs/ai-recipes-migration.md)
