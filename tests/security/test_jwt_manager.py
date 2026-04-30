from datetime import UTC, datetime, timedelta

import jwt
import pytest

from rgc_backend_kit.security import (
    InvalidTokenError,
    JWTConfig,
    JWTManager,
    MemoryTokenStore,
    RefreshTokenReuseError,
    TokenExpiredError,
    TokenRevokedError,
    TokenTypeMismatchError,
)


async def test_issue_pair_and_decode_access_token(jwt_manager: JWTManager) -> None:
    pair = await jwt_manager.issue_pair("user-1", {"role": "admin"})
    payload = await jwt_manager.decode_access_token(pair.access_token)

    assert payload.subject == "user-1"
    assert payload.token_type == "access"
    assert payload.claims == {"role": "admin"}
    assert payload.issuer == "test-service"
    assert payload.audience == "test-audience"


async def test_issue_pair_returns_expected_expiration_seconds(jwt_manager: JWTManager) -> None:
    pair = await jwt_manager.issue_pair("user-1")

    assert pair.access_expires_in == 5 * 60
    assert pair.refresh_expires_in == 24 * 60 * 60
    assert pair.token_type == "bearer"
    assert pair.access_jti
    assert pair.refresh_jti


async def test_remember_me_uses_longer_access_token_ttl(jwt_manager: JWTManager) -> None:
    pair = await jwt_manager.issue_pair("user-1", remember_me=True)

    assert pair.access_expires_in == 14 * 24 * 60 * 60


async def test_decode_rejects_wrong_token_type(jwt_manager: JWTManager) -> None:
    pair = await jwt_manager.issue_pair("user-1")

    with pytest.raises(TokenTypeMismatchError):
        await jwt_manager.decode_access_token(pair.refresh_token)


async def test_rotate_refresh_token_invalidates_old_refresh_token(jwt_manager: JWTManager) -> None:
    pair = await jwt_manager.issue_pair("user-1", {"scope": "read"})

    rotated = await jwt_manager.rotate_refresh_token(pair.refresh_token, {"scope": "write"})
    rotated_payload = await jwt_manager.decode_access_token(rotated.access_token)

    assert rotated.refresh_token != pair.refresh_token
    assert rotated_payload.claims == {"scope": "write"}
    with pytest.raises(RefreshTokenReuseError):
        await jwt_manager.rotate_refresh_token(pair.refresh_token)


async def test_decode_refresh_token_rejects_token_missing_from_store(jwt_config: JWTConfig) -> None:
    issuer = JWTManager(jwt_config, token_store=MemoryTokenStore())
    verifier = JWTManager(jwt_config, token_store=MemoryTokenStore())
    pair = await issuer.issue_pair("user-1")

    with pytest.raises(RefreshTokenReuseError):
        await verifier.decode_refresh_token(pair.refresh_token)


async def test_decode_refresh_token_can_skip_store_verification(jwt_config: JWTConfig) -> None:
    issuer = JWTManager(jwt_config, token_store=MemoryTokenStore())
    verifier = JWTManager(jwt_config, token_store=MemoryTokenStore())
    pair = await issuer.issue_pair("user-1")

    payload = await verifier.decode_refresh_token(pair.refresh_token, verify_store=False)

    assert payload.subject == "user-1"


async def test_issue_stored_refresh_token_can_be_verified(jwt_manager: JWTManager) -> None:
    token, expires_in, jti = await jwt_manager.issue_stored_refresh_token("user-1", {"scope": "refresh"})

    payload = await jwt_manager.decode_refresh_token(token)

    assert expires_in == 24 * 60 * 60
    assert payload.subject == "user-1"
    assert payload.jti == jti
    assert payload.claims == {"scope": "refresh"}


async def test_revoke_access_token_blocks_future_access_decode(jwt_manager: JWTManager) -> None:
    pair = await jwt_manager.issue_pair("user-1")

    await jwt_manager.revoke_access_token(pair.access_token)

    with pytest.raises(TokenRevokedError):
        await jwt_manager.decode_access_token(pair.access_token)


async def test_revoke_jti_marks_token_as_revoked(jwt_manager: JWTManager) -> None:
    pair = await jwt_manager.issue_pair("user-1")
    payload = await jwt_manager.decode_access_token(pair.access_token)

    await jwt_manager.revoke_jti(payload.jti, expires_in=60)

    with pytest.raises(TokenRevokedError):
        await jwt_manager.decode_access_token(pair.access_token)


async def test_invalid_token_raises_library_exception(jwt_manager: JWTManager) -> None:
    with pytest.raises(InvalidTokenError):
        await jwt_manager.decode_access_token("not-a-jwt")


async def test_expired_token_raises_token_expired(jwt_config: JWTConfig) -> None:
    manager = JWTManager(jwt_config, token_store=MemoryTokenStore())
    token, _ = manager.issue_access_token("user-1", expires_delta=timedelta(seconds=-1))

    with pytest.raises(TokenExpiredError):
        await manager.decode_access_token(token)


async def test_decode_rejects_wrong_issuer(jwt_config: JWTConfig) -> None:
    token = jwt.encode(
        {
            "sub": "user-1",
            "type": "access",
            "jti": "jti-1",
            "iat": datetime.now(UTC),
            "nbf": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(minutes=5),
            "iss": "other-service",
            "aud": jwt_config.audience,
        },
        jwt_config.secret,
        algorithm=jwt_config.algorithm,
    )
    manager = JWTManager(jwt_config, token_store=MemoryTokenStore())

    with pytest.raises(InvalidTokenError, match="Invalid issuer"):
        await manager.decode_access_token(token)


async def test_decode_rejects_wrong_audience(jwt_config: JWTConfig) -> None:
    token = jwt.encode(
        {
            "sub": "user-1",
            "type": "access",
            "jti": "jti-1",
            "iat": datetime.now(UTC),
            "nbf": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(minutes=5),
            "iss": jwt_config.issuer,
            "aud": "other-audience",
        },
        jwt_config.secret,
        algorithm=jwt_config.algorithm,
    )
    manager = JWTManager(jwt_config, token_store=MemoryTokenStore())

    with pytest.raises(InvalidTokenError, match="Audience"):
        await manager.decode_access_token(token)


async def test_decode_rejects_missing_required_claim(jwt_config: JWTConfig) -> None:
    token = jwt.encode(
        {
            "sub": "user-1",
            "type": "access",
            "iat": datetime.now(UTC),
            "nbf": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(minutes=5),
            "iss": jwt_config.issuer,
            "aud": jwt_config.audience,
        },
        jwt_config.secret,
        algorithm=jwt_config.algorithm,
    )
    manager = JWTManager(jwt_config, token_store=MemoryTokenStore())

    with pytest.raises(InvalidTokenError, match="jti"):
        await manager.decode_access_token(token)


def test_config_rejects_empty_secret() -> None:
    with pytest.raises(ValueError, match="secret"):
        JWTConfig(secret="")


def test_config_rejects_non_positive_ttl() -> None:
    with pytest.raises(ValueError, match="access_token_ttl"):
        JWTConfig(secret="test-secret-with-at-least-32-bytes", access_token_ttl=timedelta(seconds=0))
