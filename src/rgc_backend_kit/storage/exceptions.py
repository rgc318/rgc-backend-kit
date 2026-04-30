class StorageError(Exception):
    """Base class for storage component errors."""


class StorageConfigurationError(StorageError):
    """Storage client configuration is invalid."""


class StorageOperationError(StorageError):
    """Storage backend operation failed."""

