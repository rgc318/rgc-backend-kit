from __future__ import annotations

from typing import Any, BinaryIO

from .config import S3StorageConfig
from .exceptions import StorageOperationError
from .url_builder import build_public_storage_url, replace_url_origin


class S3StorageClient:
    def __init__(self, config: S3StorageConfig, boto3_client: Any | None = None) -> None:
        self.config = config
        self.bucket_name = config.bucket_name
        self.endpoint_url = self._base_url(config.endpoint, secure=config.secure)
        self.public_base_url = self._base_url(
            config.public_endpoint,
            secure=config.secure_public if config.secure_public is not None else config.secure,
        )
        self.s3 = boto3_client or self._create_boto3_client()
        if config.capabilities.supports_bucket_creation:
            self.create_bucket_if_not_exists()

    def put_object(
        self,
        object_name: str,
        data: BinaryIO,
        *,
        content_type: str,
        acl: str | None = "USE_CONFIG",
    ) -> dict[str, Any]:
        extra_args: dict[str, Any] = {"ContentType": content_type}
        final_acl = self.config.default_acl if acl == "USE_CONFIG" else acl
        if self.config.capabilities.supports_acl and final_acl:
            extra_args["ACL"] = final_acl

        try:
            self.s3.upload_fileobj(
                Fileobj=data,
                Bucket=self.bucket_name,
                Key=object_name,
                ExtraArgs=extra_args,
            )
            response = self.s3.head_object(Bucket=self.bucket_name, Key=object_name)
        except Exception as exc:
            raise StorageOperationError(f"Failed to upload object '{object_name}'.") from exc

        etag = response.get("ETag")
        if isinstance(etag, str):
            response["ETag"] = etag.strip('"')
        return response

    def remove_object(self, object_name: str) -> dict[str, Any]:
        try:
            return self.s3.delete_object(Bucket=self.bucket_name, Key=object_name)
        except Exception as exc:
            raise StorageOperationError(f"Failed to remove object '{object_name}'.") from exc

    def copy_object(
        self,
        destination_key: str,
        source_key: str,
        *,
        acl: str | None = "USE_CONFIG",
        metadata: dict[str, str] | None = None,
        preserve_metadata: bool = True,
    ) -> dict[str, Any]:
        metadata_directive = "COPY" if preserve_metadata else "REPLACE"
        params: dict[str, Any] = {
            "CopySource": {"Bucket": self.bucket_name, "Key": source_key},
            "Bucket": self.bucket_name,
            "Key": destination_key,
            "MetadataDirective": metadata_directive,
        }
        if metadata:
            params["Metadata"] = metadata
            params["MetadataDirective"] = "REPLACE"

        final_acl = self.config.default_acl if acl == "USE_CONFIG" else acl
        if self.config.capabilities.supports_acl and final_acl:
            params["ACL"] = final_acl

        try:
            return self.s3.copy_object(**params)
        except Exception as exc:
            raise StorageOperationError(
                f"Failed to copy object from '{source_key}' to '{destination_key}'."
            ) from exc

    def stat_object(self, object_name: str) -> dict[str, Any]:
        try:
            return self.s3.head_object(Bucket=self.bucket_name, Key=object_name)
        except Exception as exc:
            raise StorageOperationError(f"Failed to stat object '{object_name}'.") from exc

    def list_objects(self, prefix: str = "") -> list[dict[str, Any]]:
        try:
            paginator = self.s3.get_paginator("list_objects_v2")
            pages = paginator.paginate(Bucket=self.bucket_name, Prefix=prefix)
        except Exception as exc:
            raise StorageOperationError(f"Failed to list objects with prefix '{prefix}'.") from exc

        objects: list[dict[str, Any]] = []
        for page in pages:
            for item in page.get("Contents", []):
                etag = item.get("ETag")
                objects.append(
                    {
                        "key": item.get("Key"),
                        "size": item.get("Size"),
                        "last_modified": item.get("LastModified"),
                        "etag": etag.strip('"') if isinstance(etag, str) else etag,
                    }
                )
        return objects

    def generate_presigned_url(self, client_method: str, object_name: str, expires_in: int = 3600) -> str:
        try:
            url = self.s3.generate_presigned_url(
                ClientMethod=client_method,
                Params={"Bucket": self.bucket_name, "Key": object_name},
                ExpiresIn=expires_in,
            )
        except Exception as exc:
            raise StorageOperationError(f"Failed to generate presigned URL for '{object_name}'.") from exc

        if self.config.capabilities.rewrite_presigned_host and self.public_base_url:
            return replace_url_origin(url, self.public_base_url)
        return url

    def generate_presigned_post_policy(
        self,
        object_name: str,
        *,
        expires_in: int = 3600,
        conditions: list[Any] | None = None,
        fields: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            policy = self.s3.generate_presigned_post(
                Bucket=self.bucket_name,
                Key=object_name,
                Fields=fields,
                Conditions=conditions,
                ExpiresIn=expires_in,
            )
        except Exception as exc:
            raise StorageOperationError(f"Failed to generate presigned POST for '{object_name}'.") from exc

        if self.config.capabilities.rewrite_presigned_host and self.public_base_url and "url" in policy:
            policy["url"] = replace_url_origin(policy["url"], self.public_base_url)
        return policy

    def build_public_url(self, object_name: str) -> str:
        return build_public_storage_url(
            object_name,
            bucket_name=self.bucket_name,
            capabilities=self.config.capabilities,
            cdn_base_url=self.config.cdn_base_url,
            public_base_url=self.public_base_url,
            internal_base_url=self.endpoint_url,
        )

    def create_bucket_if_not_exists(self) -> None:
        try:
            self.s3.head_bucket(Bucket=self.bucket_name)
        except Exception:
            try:
                params: dict[str, Any] = {"Bucket": self.bucket_name}
                if self.config.region != "us-east-1" and self.config.endpoint is None:
                    params["CreateBucketConfiguration"] = {"LocationConstraint": self.config.region}
                self.s3.create_bucket(**params)
            except Exception as exc:
                raise StorageOperationError(f"Failed to create bucket '{self.bucket_name}'.") from exc

    def _create_boto3_client(self) -> Any:
        try:
            import boto3
            from botocore.client import Config as BotoConfig
        except ImportError as exc:
            raise RuntimeError("Install rgc-backend-kit[storage] to use S3StorageClient.") from exc

        addressing_style = self.config.capabilities.path_style
        boto_addressing_style = None if addressing_style == "auto" else addressing_style
        signature_version = {"v4": "s3v4", "v2": "s3"}[self.config.capabilities.signature_version]
        return boto3.client(
            "s3",
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.config.access_key,
            aws_secret_access_key=self.config.secret_key,
            region_name=self.config.region,
            config=BotoConfig(
                signature_version=signature_version,
                s3={"addressing_style": boto_addressing_style},
                connect_timeout=self.config.connect_timeout,
                read_timeout=self.config.read_timeout,
            ),
        )

    @staticmethod
    def _base_url(endpoint: str | None, *, secure: bool) -> str | None:
        if not endpoint:
            return None
        if endpoint.startswith(("http://", "https://")):
            return endpoint.rstrip("/")
        scheme = "https" if secure else "http"
        return f"{scheme}://{endpoint.rstrip('/')}"

