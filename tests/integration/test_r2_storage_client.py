import os
from io import BytesIO
from uuid import uuid4

import pytest

from rgc_backend_kit.storage import R2_CAPABILITIES, S3StorageConfig, S3StorageClient, StorageOperationError


pytestmark = pytest.mark.integration


def r2_config_from_env() -> S3StorageConfig | None:
    access_key = os.getenv("R2_ACCESS_KEY")
    secret_key = os.getenv("R2_SECRET_KEY")
    endpoint = os.getenv("R2_ENDPOINT")
    bucket = os.getenv("R2_BUCKET")
    if not access_key or not secret_key or not endpoint or not bucket:
        return None

    return S3StorageConfig(
        access_key=access_key,
        secret_key=secret_key,
        endpoint=endpoint,
        public_endpoint=os.getenv("R2_PUBLIC_ENDPOINT"),
        bucket_name=bucket,
        region=os.getenv("R2_REGION", "auto"),
        secure=True,
        secure_public=True,
        capabilities=R2_CAPABILITIES,
    )


@pytest.fixture
def r2_client() -> S3StorageClient:
    config = r2_config_from_env()
    if config is None:
        pytest.skip("Set R2_ACCESS_KEY, R2_SECRET_KEY, R2_ENDPOINT, and R2_BUCKET to run R2 integration tests.")
    return S3StorageClient(config)


def cleanup(client: S3StorageClient, *keys: str) -> None:
    for key in keys:
        try:
            client.remove_object(key)
        except StorageOperationError:
            pass


def test_r2_object_lifecycle_and_presigned_get_put(r2_client: S3StorageClient) -> None:
    prefix = f"rgc-backend-kit-r2-it/{uuid4().hex}"
    source_key = f"{prefix}/source.txt"
    copied_key = f"{prefix}/copied.txt"
    cleanup(r2_client, source_key, copied_key)

    try:
        result = r2_client.put_object(source_key, BytesIO(b"r2 integration content"), content_type="text/plain")
        assert result["ETag"]
        assert r2_client.stat_object(source_key)["ContentLength"] == len(b"r2 integration content")
        assert any(item["key"] == source_key for item in r2_client.list_objects(prefix))
        assert r2_client.copy_object(copied_key, source_key)
        assert r2_client.stat_object(copied_key)["ContentLength"] == len(b"r2 integration content")
        assert source_key in r2_client.generate_presigned_url("get_object", source_key, expires_in=60)
        assert source_key in r2_client.generate_presigned_url("put_object", source_key, expires_in=60)
    finally:
        cleanup(r2_client, source_key, copied_key)
