from dataclasses import dataclass
from datetime import timedelta


@dataclass(frozen=True, slots=True)
class JWTConfig:
    secret: str
    algorithm: str = "HS256"
    issuer: str | None = None
    audience: str | None = None
    access_token_ttl: timedelta = timedelta(minutes=60)
    refresh_token_ttl: timedelta = timedelta(days=7)
    remember_me_access_token_ttl: timedelta = timedelta(days=14)
    leeway_seconds: int = 0
    refresh_key_prefix: str = "refresh"
    revoked_key_prefix: str = "revoked"

    def __post_init__(self) -> None:
        if not self.secret:
            raise ValueError("JWT secret must not be empty.")
        if self.access_token_ttl.total_seconds() <= 0:
            raise ValueError("access_token_ttl must be positive.")
        if self.refresh_token_ttl.total_seconds() <= 0:
            raise ValueError("refresh_token_ttl must be positive.")

