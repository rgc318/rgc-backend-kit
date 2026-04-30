import os
from io import BytesIO
from uuid import uuid4

import pytest

from rgc_backend_kit.storage import (
    MINIO_CAPABILITIES,
    S3StorageConfig,
    S3StorageClient,
    StorageFactory,
    StorageOperationError,
    StorageProfileConfig,
)


pytestmark = pytest.mark.integration


def bool_from_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def public_config_from_env() -> S3StorageConfig | None:
    access_key = os.getenv("STORAGE_ACCESS_KEY") or os.getenv("MINIO_ACCESS_KEY")
    secret_key = os.getenv("STORAGE_SECRET_KEY") or os.getenv("MINIO_SECRET_KEY")
    endpoint = os.getenv("STORAGE_ENDPOINT") or os.getenv("MINIO_ENDPOINT")
    bucket = os.getenv("STORAGE_PUBLIC_BUCKET") or os.getenv("MINIO_PUBLIC_BUCKET")
    if not access_key or not secret_key or not endpoint or not bucket:
        return None

    return S3StorageConfig(
        access_key=access_key,
        secret_key=secret_key,
        endpoint=endpoint,
        public_endpoint=os.getenv("STORAGE_PUBLIC_ENDPOINT") or os.getenv("MINIO_PUBLIC_ENDPOINT") or endpoint,
        bucket_name=bucket,
        secure=bool_from_env("STORAGE_SECURE", False),
        secure_public=bool_from_env("STORAGE_SECURE_PUBLIC", bool_from_env("STORAGE_SECURE", False)),
        capabilities=MINIO_CAPABILITIES,
    )


def private_config_from_env() -> S3StorageConfig | None:
    public_config = public_config_from_env()
    bucket = os.getenv("STORAGE_PRIVATE_BUCKET") or os.getenv("MINIO_PRIVATE_BUCKET")
    if not public_config or not bucket:
        return None

    return S3StorageConfig(
        access_key=public_config.access_key,
        secret_key=public_config.secret_key,
        endpoint=public_config.endpoint,
        bucket_name=bucket,
        secure=public_config.secure,
        capabilities=MINIO_CAPABILITIES,
    )


@pytest.fixture
def public_storage_client() -> S3StorageClient:
    config = public_config_from_env()
    if config is None:
        pytest.skip(
            "Set STORAGE_ACCESS_KEY, STORAGE_SECRET_KEY, STORAGE_ENDPOINT, and STORAGE_PUBLIC_BUCKET "
            "to run S3-compatible storage integration tests."
        )
    return S3StorageClient(config)


def cleanup(client: S3StorageClient, *keys: str) -> None:
    for key in keys:
        try:
            client.remove_object(key)
        except StorageOperationError:
            pass


def test_s3_storage_client_object_lifecycle(public_storage_client: S3StorageClient) -> None:
    prefix = f"rgc-backend-kit-it/{uuid4().hex}"
    source_key = f"{prefix}/source.txt"
    copied_key = f"{prefix}/copied.txt"
    cleanup(public_storage_client, source_key, copied_key)

    try:
        metadata = public_storage_client.put_object(
            source_key,
            BytesIO(b"storage integration content"),
            content_type="text/plain",
        )
        assert metadata["ETag"]

        stat = public_storage_client.stat_object(source_key)
        assert stat["ContentLength"] == len(b"storage integration content")

        objects = public_storage_client.list_objects(prefix)
        assert any(item["key"] == source_key for item in objects)

        copy_result = public_storage_client.copy_object(copied_key, source_key)
        assert copy_result
        assert public_storage_client.stat_object(copied_key)["ContentLength"] == len(b"storage integration content")

        public_url = public_storage_client.build_public_url(source_key)
        assert source_key in public_url

        presigned_url = public_storage_client.generate_presigned_url("get_object", source_key, expires_in=60)
        assert source_key in presigned_url

        post_policy = public_storage_client.generate_presigned_post_policy(
            f"{prefix}/browser-upload.txt",
            expires_in=60,
            fields={"Content-Type": "text/plain"},
            conditions=[{"Content-Type": "text/plain"}],
        )
        assert "url" in post_policy
        assert "fields" in post_policy
    finally:
        cleanup(public_storage_client, source_key, copied_key, f"{prefix}/browser-upload.txt")


def assert_profile_can_write_and_read(factory: StorageFactory, profile_name: str, content: bytes) -> None:
    storage = factory.get_profiled_storage(profile_name)
    key = storage.key(f"{uuid4().hex}.txt")
    cleanup(storage.client, key)

    try:
        metadata = storage.client.put_object(key, BytesIO(content), content_type="text/plain")
        assert metadata["ETag"]
        assert storage.client.stat_object(key)["ContentLength"] == len(content)
        assert any(item["key"] == key for item in storage.client.list_objects(storage.profile.base_path))
    finally:
        cleanup(storage.client, key)


def test_storage_factory_reads_and_writes_real_public_and_private_buckets() -> None:
    public_config = public_config_from_env()
    private_config = private_config_from_env()
    if public_config is None or private_config is None:
        pytest.skip("Set public and private storage bucket environment variables to run multi-bucket integration test.")

    factory = StorageFactory.from_configs(
        client_configs={
            "public": public_config,
            "private": private_config,
        },
        profiles={
            "public_assets": StorageProfileConfig(client="public", base_path="public-it", public=True),
            "private_files": StorageProfileConfig(client="private", base_path="private-it"),
        },
    )

    assert factory.get_client_by_profile("public_assets").bucket_name == public_config.bucket_name
    assert factory.get_client_by_profile("private_files").bucket_name == private_config.bucket_name
    assert factory.get_profiled_storage("public_assets").key("demo.txt").startswith("public-it/")
    assert factory.get_profiled_storage("private_files").key("demo.txt").startswith("private-it/")
    assert_profile_can_write_and_read(factory, "public_assets", b"public bucket content")
    assert_profile_can_write_and_read(factory, "private_files", b"private bucket content")
