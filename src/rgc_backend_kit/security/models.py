from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal


TokenType = Literal["access", "refresh"]


@dataclass(frozen=True, slots=True)
class TokenPair:
    access_token: str
    refresh_token: str
    access_expires_in: int
    refresh_expires_in: int
    access_jti: str
    refresh_jti: str
    token_type: str = "bearer"


@dataclass(frozen=True, slots=True)
class TokenPayload:
    subject: str
    token_type: TokenType
    jti: str
    issued_at: datetime
    not_before: datetime
    expires_at: datetime
    issuer: str | None = None
    audience: str | None = None
    claims: dict[str, Any] | None = None

    @classmethod
    def from_claims(cls, payload: dict[str, Any]) -> "TokenPayload":
        reserved = {"sub", "type", "jti", "iat", "nbf", "exp", "iss", "aud"}
        return cls(
            subject=str(payload["sub"]),
            token_type=payload["type"],
            jti=str(payload["jti"]),
            issued_at=_datetime_from_timestamp(payload["iat"]),
            not_before=_datetime_from_timestamp(payload["nbf"]),
            expires_at=_datetime_from_timestamp(payload["exp"]),
            issuer=payload.get("iss"),
            audience=payload.get("aud"),
            claims={key: value for key, value in payload.items() if key not in reserved},
        )


def ttl_seconds(delta: timedelta) -> int:
    return int(delta.total_seconds())


def _datetime_from_timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromtimestamp(int(value), tz=UTC)
