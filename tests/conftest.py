from datetime import timedelta

import pytest

from rgc_backend_kit.security import JWTConfig, JWTManager, MemoryTokenStore


@pytest.fixture
def jwt_config() -> JWTConfig:
    return JWTConfig(
        secret="test-secret-with-at-least-32-bytes",
        issuer="test-service",
        audience="test-audience",
        access_token_ttl=timedelta(minutes=5),
        refresh_token_ttl=timedelta(days=1),
        remember_me_access_token_ttl=timedelta(days=14),
    )


@pytest.fixture
def token_store() -> MemoryTokenStore:
    return MemoryTokenStore()


@pytest.fixture
def jwt_manager(jwt_config: JWTConfig, token_store: MemoryTokenStore) -> JWTManager:
    return JWTManager(jwt_config, token_store=token_store)

