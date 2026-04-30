# Test Suite

The test suite is split by module and contract surface.

## Layout

- `tests/security/test_jwt_manager.py`: JWT issuing, decoding, refresh rotation, revocation, claim validation, and config validation.
- `tests/security/test_token_store.py`: memory, null, and Redis-compatible token store behavior.
- `tests/security/test_fastapi_adapter.py`: FastAPI dependency adapter behavior.
- `tests/integration/test_redis_token_store.py`: real Redis refresh-token and revoke behavior.
- `tests/integration/test_s3_storage_client.py`: real S3-compatible object lifecycle and real public/private multi-bucket read/write behavior.
- `tests/integration/test_r2_storage_client.py`: real Cloudflare R2 object lifecycle when R2 credentials are available.
- `tests/storage/test_s3_client.py`: S3-compatible client branch coverage with fake boto clients.
- `tests/storage/test_storage_factory.py`: multi-client and profile routing.
- `tests/storage/test_url_builder.py`: public URL and S3-compatible client URL behavior.

## Default Tests

Default tests do not require Redis, S3, MinIO, R2, or any other external service.

```bash
uv run --extra dev pytest -q
```

Expected current result:

```text
57 passed, 5 deselected
```

## Redis Integration Tests

Redis integration tests are marked with `integration` and excluded from the default run.

Run with `REDIS_URL`:

```bash
REDIS_URL=redis://:password@127.0.0.1:6379/0 uv run --extra dev pytest -q -m integration
```

Or with separate variables:

```bash
REDIS_HOST=127.0.0.1 \
REDIS_PORT=6379 \
REDIS_DB=0 \
REDIS_PASSWORD=password \
uv run --extra dev pytest -q -m integration
```

Expected current result when Redis is available:

```text
2 passed, 60 deselected
```

## S3-Compatible Storage Integration Tests

Storage integration tests are also marked with `integration` and skipped unless storage environment variables are present.

```bash
STORAGE_ACCESS_KEY=minio \
STORAGE_SECRET_KEY=minio123 \
STORAGE_ENDPOINT=127.0.0.1:9000 \
STORAGE_PUBLIC_ENDPOINT=img.example.com \
STORAGE_PUBLIC_BUCKET=public-assets \
STORAGE_PRIVATE_BUCKET=secure-files \
uv run --extra dev pytest -q tests/integration/test_s3_storage_client.py
```

The storage integration tests create unique object keys under `rgc-backend-kit-it/`, `public-it/`, and `private-it/`, then clean them up after the run. Both the public and private bucket profiles are verified with real upload, stat, list, and delete operations.

## R2 Integration Tests

R2 integration tests are skipped unless Cloudflare R2 credentials are present.

```bash
R2_ACCESS_KEY=... \
R2_SECRET_KEY=... \
R2_ENDPOINT=<account-id>.r2.cloudflarestorage.com \
R2_BUCKET=cdn-assets \
R2_PUBLIC_ENDPOINT=cdn.example.com \
uv run --extra dev pytest -q -m integration tests/integration/test_r2_storage_client.py
```

The R2 test validates upload, stat, list, copy, presigned GET, presigned PUT, and cleanup. Presigned POST is intentionally not required for R2 because provider compatibility differs from MinIO/S3.

## Full Local Verification

```bash
REDIS_URL=redis://:password@127.0.0.1:6379/0 \
uv run --extra dev pytest -q -m 'unit or contract or integration or not integration'
```

Expected current result:

```text
61 passed, 1 skipped
```

Build package:

```bash
uv build
```

Package installation validation is documented in [Package Validation](../docs/package-validation.md).
