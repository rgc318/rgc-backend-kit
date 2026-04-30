from rgc_backend_kit.security import MemoryTokenStore, NullTokenStore, RedisTokenStore


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, tuple[str, int | None]] = {}
        self.deleted: list[str] = []

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.values[key] = (value, ex)

    async def exists(self, key: str) -> int:
        return int(key in self.values)

    async def delete(self, key: str) -> None:
        self.deleted.append(key)
        self.values.pop(key, None)


async def test_memory_token_store_expires_refresh_tokens() -> None:
    store = MemoryTokenStore()

    await store.set_refresh_token("user-1", "jti-1", "token", ttl_seconds=0)

    assert await store.refresh_token_exists("user-1", "jti-1") is False


async def test_memory_token_store_expires_revoked_tokens() -> None:
    store = MemoryTokenStore()

    await store.revoke_token("jti-1", ttl_seconds=0)

    assert await store.is_token_revoked("jti-1") is False


async def test_null_token_store_is_stateless_noop() -> None:
    store = NullTokenStore()

    await store.set_refresh_token("user-1", "jti-1", "token", ttl_seconds=1)
    await store.delete_refresh_token("user-1", "jti-1")
    await store.revoke_token("jti-1", ttl_seconds=1)

    assert await store.refresh_token_exists("user-1", "jti-1") is True
    assert await store.is_token_revoked("jti-1") is False


async def test_redis_token_store_uses_project_compatible_key_format() -> None:
    redis = FakeRedis()
    store = RedisTokenStore(redis)

    await store.set_refresh_token("user-1", "jti-1", "refresh-token", ttl_seconds=60)
    await store.revoke_token("access-jti", ttl_seconds=30)

    assert redis.values["refresh:user-1:jti-1"] == ("refresh-token", 60)
    assert redis.values["revoked:access-jti"] == ("1", 30)
    assert await store.refresh_token_exists("user-1", "jti-1") is True
    assert await store.is_token_revoked("access-jti") is True

    await store.delete_refresh_token("user-1", "jti-1")

    assert "refresh:user-1:jti-1" not in redis.values
    assert redis.deleted == ["refresh:user-1:jti-1"]

