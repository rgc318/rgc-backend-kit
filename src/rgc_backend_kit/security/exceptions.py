class JWTKitError(Exception):
    """Base class for JWT component errors."""


class InvalidTokenError(JWTKitError):
    """Token cannot be decoded or is semantically invalid."""


class TokenExpiredError(InvalidTokenError):
    """Token has expired."""


class TokenRevokedError(InvalidTokenError):
    """Token has been revoked."""


class TokenTypeMismatchError(InvalidTokenError):
    """Token type does not match the operation."""


class RefreshTokenReuseError(InvalidTokenError):
    """Refresh token was already rotated or is no longer stored."""

