import os
from datetime import timedelta
from uuid import uuid4

import pytest

from rgc_backend_kit.security import JWTConfig, JWTManager, RedisTokenStore, TokenRevokedError


pytestmark = pytest.mark.integration


def redis_url_from_env() -> str | None:
    if redis_url := os.getenv("REDIS_URL"):
        return redis_url

    host = os.getenv("REDIS_HOST")
    port = os.getenv("REDIS_PORT")
    if not host or not port:
        return None

    db = os.getenv("REDIS_DB", "0")
    password = os.getenv("REDIS_PASSWORD")
    auth = f":{password}@" if password else ""
    return f"redis://{auth}{host}:{port}/{db}"


@pytest.fixture
async def redis_client():
    redis_url = redis_url_from_env()
    if not redis_url:
        pytest.skip("Set REDIS_URL or REDIS_HOST/REDIS_PORT to run Redis integration tests.")

    redis = pytest.importorskip("redis.asyncio")
    client = redis.from_url(redis_url, decode_responses=True)
    try:
        await client.ping()
    except Exception as exc:
        pytest.skip(f"Redis is unavailable: {exc}")

    yield client
    await client.aclose()


@pytest.fixture
def redis_prefixes() -> tuple[str, str]:
    suffix = uuid4().hex
    return f"it-refresh:{suffix}", f"it-revoked:{suffix}"


async def cleanup_prefix(redis_client, prefix: str) -> None:
    async for key in redis_client.scan_iter(f"{prefix}:*"):
        await redis_client.delete(key)


async def test_redis_store_persists_refresh_token_and_supports_rotation(redis_client, redis_prefixes) -> None:
    refresh_prefix, revoked_prefix = redis_prefixes
    store = RedisTokenStore(redis_client, refresh_prefix=refresh_prefix, revoked_prefix=revoked_prefix)
    manager = JWTManager(
        JWTConfig(
            secret="integration-test-secret-with-at-least-32-bytes",
            issuer="integration-test",
            audience="integration-test-client",
            access_token_ttl=timedelta(minutes=5),
            refresh_token_ttl=timedelta(minutes=10),
        ),
        token_store=store,
    )

    try:
        pair = await manager.issue_pair("user-1", {"scope": "read"})
        refresh_key = f"{refresh_prefix}:user-1:{pair.refresh_jti}"

        assert await redis_client.exists(refresh_key) == 1
        assert await redis_client.ttl(refresh_key) > 0

        rotated = await manager.rotate_refresh_token(pair.refresh_token)

        assert await redis_client.exists(refresh_key) == 0
        assert await redis_client.exists(f"{refresh_prefix}:user-1:{rotated.refresh_jti}") == 1
    finally:
        await cleanup_prefix(redis_client, refresh_prefix)
        await cleanup_prefix(redis_client, revoked_prefix)


async def test_redis_store_persists_access_token_revocation(redis_client, redis_prefixes) -> None:
    refresh_prefix, revoked_prefix = redis_prefixes
    store = RedisTokenStore(redis_client, refresh_prefix=refresh_prefix, revoked_prefix=revoked_prefix)
    manager = JWTManager(
        JWTConfig(
            secret="integration-test-secret-with-at-least-32-bytes",
            issuer="integration-test",
            audience="integration-test-client",
            access_token_ttl=timedelta(minutes=5),
            refresh_token_ttl=timedelta(minutes=10),
        ),
        token_store=store,
    )

    try:
        pair = await manager.issue_pair("user-1")
        await manager.revoke_access_token(pair.access_token)

        revoked_key = f"{revoked_prefix}:{pair.access_jti}"
        assert await redis_client.exists(revoked_key) == 1
        assert await redis_client.ttl(revoked_key) > 0

        with pytest.raises(TokenRevokedError):
            await manager.decode_access_token(pair.access_token)
    finally:
        await cleanup_prefix(redis_client, refresh_prefix)
        await cleanup_prefix(redis_client, revoked_prefix)

