from dataclasses import dataclass

import pytest

from rgc_backend_kit.storage import (
    MINIO_CAPABILITIES,
    R2_CAPABILITIES,
    S3StorageConfig,
    StorageConfigurationError,
    StorageFactory,
    StorageProfileConfig,
)


@dataclass(slots=True)
class FakeStorageClient:
    bucket_name: str
    base_url: str

    def build_public_url(self, object_name: str) -> str:
        return f"{self.base_url}/{self.bucket_name}/{object_name}"


def test_factory_routes_profile_to_registered_client() -> None:
    factory = StorageFactory(
        clients={
            "minio_public": FakeStorageClient("public-assets", "https://img.example.com"),
            "minio_private": FakeStorageClient("private-files", "https://files.example.com"),
        },
        profiles={
            "avatars": StorageProfileConfig(client="minio_public", base_path="users/avatars", public=True),
            "secure_files": StorageProfileConfig(client="minio_private", base_path="secure"),
        },
    )

    assert factory.get_client_by_profile("avatars").bucket_name == "public-assets"
    assert factory.get_client_by_profile("secure_files").bucket_name == "private-files"


def test_profiled_storage_applies_base_path_before_building_url() -> None:
    factory = StorageFactory(
        clients={"r2_public": FakeStorageClient("cdn-assets", "https://cdn.example.com")},
        profiles={"recipe_images": StorageProfileConfig(client="r2_public", base_path="/recipes/images/")},
    )

    storage = factory.get_profiled_storage("recipe_images")

    assert storage.key("/demo.png") == "recipes/images/demo.png"
    assert storage.build_public_url("/demo.png") == "https://cdn.example.com/cdn-assets/recipes/images/demo.png"


def test_factory_rejects_profile_with_missing_client() -> None:
    with pytest.raises(StorageConfigurationError, match="missing clients"):
        StorageFactory(
            clients={},
            profiles={"avatars": StorageProfileConfig(client="missing")},
        )


def test_factory_from_configs_supports_multiple_s3_compatible_clients() -> None:
    built: dict[str, S3StorageConfig] = {}

    def builder(config: S3StorageConfig) -> FakeStorageClient:
        built[config.bucket_name] = config
        return FakeStorageClient(config.bucket_name, config.public_endpoint or "https://storage.example.com")

    factory = StorageFactory.from_configs(
        client_configs={
            "minio_public": S3StorageConfig(
                access_key="minio",
                secret_key="secret",
                endpoint="127.0.0.1:9000",
                public_endpoint="https://img.example.com",
                bucket_name="public-assets",
                secure=False,
                capabilities=MINIO_CAPABILITIES,
            ),
            "r2_public": S3StorageConfig(
                access_key="r2",
                secret_key="secret",
                endpoint="account.r2.cloudflarestorage.com",
                public_endpoint="https://cdn.example.com",
                bucket_name="cdn-assets",
                region="auto",
                capabilities=R2_CAPABILITIES,
            ),
        },
        profiles={
            "avatars": StorageProfileConfig(client="minio_public"),
            "recipe_images": StorageProfileConfig(client="r2_public"),
        },
        client_builder=builder,
    )

    assert set(factory.client_names()) == {"minio_public", "r2_public"}
    assert set(factory.profile_names()) == {"avatars", "recipe_images"}
    assert factory.get_client_by_profile("recipe_images").bucket_name == "cdn-assets"
    assert built["public-assets"].capabilities == MINIO_CAPABILITIES
    assert built["cdn-assets"].capabilities == R2_CAPABILITIES

