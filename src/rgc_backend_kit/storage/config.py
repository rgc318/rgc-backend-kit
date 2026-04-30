from dataclasses import dataclass, field
from typing import Literal


AddressingStyle = Literal["auto", "path", "virtual"]
SignatureVersion = Literal["v4", "v2"]


@dataclass(frozen=True, slots=True)
class StorageCapabilities:
    path_style: AddressingStyle = "auto"
    signature_version: SignatureVersion = "v4"
    supports_acl: bool = True
    supports_bucket_creation: bool = False
    rewrite_presigned_host: bool = False
    public_url_path_style: bool = True


MINIO_CAPABILITIES = StorageCapabilities(
    path_style="path",
    supports_acl=True,
    supports_bucket_creation=True,
    rewrite_presigned_host=True,
    public_url_path_style=True,
)

R2_CAPABILITIES = StorageCapabilities(
    path_style="virtual",
    supports_acl=False,
    supports_bucket_creation=False,
    rewrite_presigned_host=False,
    public_url_path_style=False,
)

AWS_S3_CAPABILITIES = StorageCapabilities(
    path_style="virtual",
    supports_acl=True,
    supports_bucket_creation=False,
    rewrite_presigned_host=False,
    public_url_path_style=False,
)


@dataclass(frozen=True, slots=True)
class S3StorageConfig:
    access_key: str
    secret_key: str
    bucket_name: str
    endpoint: str | None = None
    public_endpoint: str | None = None
    cdn_base_url: str | None = None
    region: str = "us-east-1"
    secure: bool = True
    secure_public: bool | None = None
    default_acl: str | None = None
    connect_timeout: int = 5
    read_timeout: int = 30
    capabilities: StorageCapabilities = field(default_factory=StorageCapabilities)

    def __post_init__(self) -> None:
        if not self.access_key:
            raise ValueError("access_key must not be empty.")
        if not self.secret_key:
            raise ValueError("secret_key must not be empty.")
        if not self.bucket_name:
            raise ValueError("bucket_name must not be empty.")


@dataclass(frozen=True, slots=True)
class StorageProfileConfig:
    client: str
    base_path: str = ""
    public: bool = False
    default_expires_in: int = 3600

    def __post_init__(self) -> None:
        if not self.client:
            raise ValueError("profile client must not be empty.")
        if self.default_expires_in <= 0:
            raise ValueError("default_expires_in must be positive.")
