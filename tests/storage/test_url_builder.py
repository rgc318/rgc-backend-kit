from rgc_backend_kit.storage import S3StorageConfig, StorageCapabilities, build_public_storage_url
from rgc_backend_kit.storage.s3_client import S3StorageClient


def test_build_path_style_public_url() -> None:
    url = build_public_storage_url(
        "avatars/a b.png",
        bucket_name="public-assets",
        capabilities=StorageCapabilities(public_url_path_style=True),
        public_base_url="https://img.example.com",
    )

    assert url == "https://img.example.com/public-assets/avatars/a%20b.png"


def test_build_virtual_style_public_url() -> None:
    url = build_public_storage_url(
        "avatars/demo.png",
        bucket_name="public-assets",
        capabilities=StorageCapabilities(public_url_path_style=False),
        cdn_base_url="https://cdn.example.com",
    )

    assert url == "https://cdn.example.com/avatars/demo.png"


def test_s3_client_can_use_injected_boto_client_for_url_building() -> None:
    client = S3StorageClient(
        S3StorageConfig(
            access_key="key",
            secret_key="secret",
            endpoint="127.0.0.1:9000",
            public_endpoint="img.example.com",
            bucket_name="public-assets",
            secure=False,
            secure_public=True,
            capabilities=StorageCapabilities(public_url_path_style=True),
        ),
        boto3_client=object(),
    )

    assert client.build_public_url("demo.png") == "https://img.example.com/public-assets/demo.png"

