from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Protocol

from .config import S3StorageConfig, StorageProfileConfig
from .exceptions import StorageConfigurationError
from .s3_client import S3StorageClient


class StorageClient(Protocol):
    bucket_name: str

    def build_public_url(self, object_name: str) -> str:
        ...


ClientBuilder = Callable[[S3StorageConfig], StorageClient]


@dataclass(frozen=True, slots=True)
class ProfiledStorage:
    client: StorageClient
    profile: StorageProfileConfig

    def key(self, object_name: str) -> str:
        normalized = object_name.lstrip("/")
        base_path = self.profile.base_path.strip("/")
        if not base_path:
            return normalized
        return f"{base_path}/{normalized}" if normalized else base_path

    def build_public_url(self, object_name: str) -> str:
        return self.client.build_public_url(self.key(object_name))


class StorageFactory:
    def __init__(
        self,
        *,
        clients: Mapping[str, StorageClient] | None = None,
        profiles: Mapping[str, StorageProfileConfig] | None = None,
    ) -> None:
        self._clients = dict(clients or {})
        self._profiles = dict(profiles or {})
        self._validate_profiles()

    @classmethod
    def from_configs(
        cls,
        *,
        client_configs: Mapping[str, S3StorageConfig],
        profiles: Mapping[str, StorageProfileConfig] | None = None,
        client_builder: ClientBuilder | None = None,
    ) -> "StorageFactory":
        builder = client_builder or S3StorageClient
        clients = {name: builder(config) for name, config in client_configs.items()}
        return cls(clients=clients, profiles=profiles)

    def register_client(self, name: str, client: StorageClient) -> None:
        if not name:
            raise StorageConfigurationError("Storage client name must not be empty.")
        self._clients[name] = client
        self._validate_profiles()

    def register_profile(self, name: str, profile: StorageProfileConfig) -> None:
        if not name:
            raise StorageConfigurationError("Storage profile name must not be empty.")
        self._profiles[name] = profile
        self._validate_profiles()

    def get_client(self, name: str) -> StorageClient:
        try:
            return self._clients[name]
        except KeyError as exc:
            raise StorageConfigurationError(f"Storage client '{name}' is not registered.") from exc

    def get_profile(self, name: str) -> StorageProfileConfig:
        try:
            return self._profiles[name]
        except KeyError as exc:
            raise StorageConfigurationError(f"Storage profile '{name}' is not registered.") from exc

    def get_client_by_profile(self, profile_name: str) -> StorageClient:
        profile = self.get_profile(profile_name)
        return self.get_client(profile.client)

    def get_profiled_storage(self, profile_name: str) -> ProfiledStorage:
        profile = self.get_profile(profile_name)
        return ProfiledStorage(client=self.get_client(profile.client), profile=profile)

    def client_names(self) -> tuple[str, ...]:
        return tuple(self._clients)

    def profile_names(self) -> tuple[str, ...]:
        return tuple(self._profiles)

    def _validate_profiles(self) -> None:
        missing = sorted(
            {profile.client for profile in self._profiles.values() if profile.client not in self._clients}
        )
        if missing:
            names = ", ".join(missing)
            raise StorageConfigurationError(f"Storage profiles reference missing clients: {names}.")

