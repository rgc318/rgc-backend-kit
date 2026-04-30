from io import BytesIO

import pytest

from rgc_backend_kit.storage import (
    AWS_S3_CAPABILITIES,
    MINIO_CAPABILITIES,
    R2_CAPABILITIES,
    S3StorageConfig,
    S3StorageClient,
    StorageCapabilities,
    StorageOperationError,
)


class FakePaginator:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def paginate(self, **kwargs):
        self.calls.append(kwargs)
        return self.pages


class FakeBotoClient:
    def __init__(self, *, fail_methods: set[str] | None = None, head_bucket_fails: bool = False) -> None:
        self.fail_methods = fail_methods or set()
        self.head_bucket_fails = head_bucket_fails
        self.uploads = []
        self.copies = []
        self.deleted = []
        self.created_buckets = []
        self.head_buckets = []
        self.paginator = FakePaginator(
            [
                {"Contents": [{"Key": "prefix/a.txt", "Size": 1, "LastModified": "now", "ETag": '"etag-a"'}]},
                {},
            ]
        )

    def upload_fileobj(self, Fileobj, Bucket, Key, ExtraArgs):
        if "upload_fileobj" in self.fail_methods:
            raise RuntimeError("upload failed")
        self.uploads.append(
            {
                "content": Fileobj.read(),
                "bucket": Bucket,
                "key": Key,
                "extra_args": ExtraArgs,
            }
        )

    def head_object(self, Bucket, Key):
        if "head_object" in self.fail_methods:
            raise RuntimeError("head failed")
        return {"Bucket": Bucket, "Key": Key, "ETag": '"etag-value"', "ContentLength": 7}

    def delete_object(self, Bucket, Key):
        if "delete_object" in self.fail_methods:
            raise RuntimeError("delete failed")
        self.deleted.append({"bucket": Bucket, "key": Key})
        return {"Deleted": Key}

    def copy_object(self, **params):
        if "copy_object" in self.fail_methods:
            raise RuntimeError("copy failed")
        self.copies.append(params)
        return {"CopyObjectResult": {"ETag": '"copy-etag"'}}

    def generate_presigned_url(self, ClientMethod, Params, ExpiresIn):
        if "generate_presigned_url" in self.fail_methods:
            raise RuntimeError("url failed")
        return f"http://internal.local/{Params['Bucket']}/{Params['Key']}?method={ClientMethod}&expires={ExpiresIn}"

    def generate_presigned_post(self, Bucket, Key, Fields, Conditions, ExpiresIn):
        if "generate_presigned_post" in self.fail_methods:
            raise RuntimeError("post failed")
        return {
            "url": f"http://internal.local/{Bucket}",
            "fields": Fields or {},
            "conditions": Conditions or [],
            "expires": ExpiresIn,
        }

    def get_paginator(self, name):
        if "get_paginator" in self.fail_methods:
            raise RuntimeError("paginator failed")
        assert name == "list_objects_v2"
        return self.paginator

    def head_bucket(self, Bucket):
        self.head_buckets.append(Bucket)
        if self.head_bucket_fails:
            raise RuntimeError("bucket missing")
        return {}

    def create_bucket(self, **params):
        if "create_bucket" in self.fail_methods:
            raise RuntimeError("create bucket failed")
        self.created_buckets.append(params)


def make_config(
    *,
    capabilities=MINIO_CAPABILITIES,
    default_acl: str | None = "public-read",
    endpoint: str | None = "127.0.0.1:9000",
    public_endpoint: str | None = "img.example.com",
    cdn_base_url: str | None = None,
    region: str = "us-east-1",
) -> S3StorageConfig:
    return S3StorageConfig(
        access_key="key",
        secret_key="secret",
        endpoint=endpoint,
        public_endpoint=public_endpoint,
        cdn_base_url=cdn_base_url,
        bucket_name="bucket",
        region=region,
        secure=False,
        secure_public=True,
        default_acl=default_acl,
        capabilities=capabilities,
    )


def test_put_object_applies_acl_when_supported() -> None:
    fake = FakeBotoClient()
    client = S3StorageClient(make_config(), boto3_client=fake)

    result = client.put_object("a.txt", BytesIO(b"content"), content_type="text/plain")

    assert result["ETag"] == "etag-value"
    assert fake.uploads[0]["extra_args"] == {"ContentType": "text/plain", "ACL": "public-read"}


def test_put_object_omits_acl_when_provider_does_not_support_acl() -> None:
    fake = FakeBotoClient()
    client = S3StorageClient(make_config(capabilities=R2_CAPABILITIES), boto3_client=fake)

    client.put_object("a.txt", BytesIO(b"content"), content_type="text/plain")

    assert fake.uploads[0]["extra_args"] == {"ContentType": "text/plain"}


def test_put_object_can_override_default_acl() -> None:
    fake = FakeBotoClient()
    client = S3StorageClient(make_config(), boto3_client=fake)

    client.put_object("a.txt", BytesIO(b"content"), content_type="text/plain", acl="private")

    assert fake.uploads[0]["extra_args"]["ACL"] == "private"


def test_copy_object_preserves_metadata_and_applies_acl() -> None:
    fake = FakeBotoClient()
    client = S3StorageClient(make_config(), boto3_client=fake)

    client.copy_object("dest.txt", "source.txt")

    assert fake.copies[0]["CopySource"] == {"Bucket": "bucket", "Key": "source.txt"}
    assert fake.copies[0]["MetadataDirective"] == "COPY"
    assert fake.copies[0]["ACL"] == "public-read"


def test_copy_object_replaces_metadata_when_metadata_is_provided() -> None:
    fake = FakeBotoClient()
    client = S3StorageClient(make_config(), boto3_client=fake)

    client.copy_object(
        "dest.txt",
        "source.txt",
        metadata={"ContentType": "text/plain"},
        preserve_metadata=True,
    )

    assert fake.copies[0]["Metadata"] == {"ContentType": "text/plain"}
    assert fake.copies[0]["MetadataDirective"] == "REPLACE"


def test_copy_object_can_replace_metadata_without_custom_metadata() -> None:
    fake = FakeBotoClient()
    client = S3StorageClient(make_config(), boto3_client=fake)

    client.copy_object("dest.txt", "source.txt", preserve_metadata=False)

    assert fake.copies[0]["MetadataDirective"] == "REPLACE"


def test_copy_object_omits_acl_when_provider_does_not_support_acl() -> None:
    fake = FakeBotoClient()
    client = S3StorageClient(make_config(capabilities=R2_CAPABILITIES), boto3_client=fake)

    client.copy_object("dest.txt", "source.txt")

    assert "ACL" not in fake.copies[0]


def test_list_objects_normalizes_etag_and_handles_empty_pages() -> None:
    fake = FakeBotoClient()
    client = S3StorageClient(make_config(), boto3_client=fake)

    objects = client.list_objects("prefix")

    assert objects == [{"key": "prefix/a.txt", "size": 1, "last_modified": "now", "etag": "etag-a"}]
    assert fake.paginator.calls == [{"Bucket": "bucket", "Prefix": "prefix"}]


def test_presigned_get_and_put_url_rewrite_public_host() -> None:
    fake = FakeBotoClient()
    client = S3StorageClient(make_config(), boto3_client=fake)

    get_url = client.generate_presigned_url("get_object", "a.txt", expires_in=60)
    put_url = client.generate_presigned_url("put_object", "a.txt", expires_in=60)

    assert get_url.startswith("https://img.example.com/")
    assert "method=get_object" in get_url
    assert put_url.startswith("https://img.example.com/")
    assert "method=put_object" in put_url


def test_presigned_url_does_not_rewrite_when_capability_is_disabled() -> None:
    fake = FakeBotoClient()
    client = S3StorageClient(make_config(capabilities=R2_CAPABILITIES), boto3_client=fake)

    url = client.generate_presigned_url("get_object", "a.txt", expires_in=60)

    assert url.startswith("http://internal.local/")


def test_presigned_post_policy_rewrites_public_host() -> None:
    fake = FakeBotoClient()
    client = S3StorageClient(make_config(), boto3_client=fake)

    policy = client.generate_presigned_post_policy(
        "a.txt",
        expires_in=60,
        fields={"Content-Type": "text/plain"},
        conditions=[{"Content-Type": "text/plain"}],
    )

    assert policy["url"] == "https://img.example.com/bucket"
    assert policy["fields"] == {"Content-Type": "text/plain"}
    assert policy["conditions"] == [{"Content-Type": "text/plain"}]


def test_build_public_url_prefers_cdn_base_url() -> None:
    client = S3StorageClient(
        make_config(
            capabilities=StorageCapabilities(public_url_path_style=True),
            cdn_base_url="https://cdn.example.com",
            public_endpoint="img.example.com",
        ),
        boto3_client=object(),
    )

    assert client.build_public_url("a b.txt") == "https://cdn.example.com/bucket/a%20b.txt"


def test_build_public_url_uses_virtual_style_when_configured() -> None:
    client = S3StorageClient(
        make_config(capabilities=StorageCapabilities(public_url_path_style=False)),
        boto3_client=object(),
    )

    assert client.build_public_url("a.txt") == "https://img.example.com/a.txt"


def test_create_bucket_skips_when_bucket_exists() -> None:
    fake = FakeBotoClient()
    S3StorageClient(make_config(capabilities=MINIO_CAPABILITIES), boto3_client=fake)

    assert fake.head_buckets == ["bucket"]
    assert fake.created_buckets == []


def test_create_bucket_when_missing() -> None:
    fake = FakeBotoClient(head_bucket_fails=True)
    S3StorageClient(make_config(capabilities=MINIO_CAPABILITIES), boto3_client=fake)

    assert fake.created_buckets == [{"Bucket": "bucket"}]


def test_create_aws_bucket_with_region_constraint() -> None:
    fake = FakeBotoClient(head_bucket_fails=True)
    S3StorageClient(
        make_config(
            capabilities=StorageCapabilities(supports_bucket_creation=True),
            endpoint=None,
            public_endpoint=None,
            region="ap-east-1",
        ),
        boto3_client=fake,
    )

    assert fake.created_buckets == [
        {"Bucket": "bucket", "CreateBucketConfiguration": {"LocationConstraint": "ap-east-1"}}
    ]


@pytest.mark.parametrize(
    ("method", "call"),
    [
        ("upload_fileobj", lambda client: client.put_object("a.txt", BytesIO(b"content"), content_type="text/plain")),
        ("delete_object", lambda client: client.remove_object("a.txt")),
        ("copy_object", lambda client: client.copy_object("b.txt", "a.txt")),
        ("head_object", lambda client: client.stat_object("a.txt")),
        ("get_paginator", lambda client: client.list_objects("prefix")),
        ("generate_presigned_url", lambda client: client.generate_presigned_url("get_object", "a.txt")),
        ("generate_presigned_post", lambda client: client.generate_presigned_post_policy("a.txt")),
    ],
)
def test_s3_operation_failures_raise_storage_operation_error(method, call) -> None:
    fake = FakeBotoClient(fail_methods={method})
    client = S3StorageClient(make_config(), boto3_client=fake)

    with pytest.raises(StorageOperationError):
        call(client)


def test_bucket_creation_failure_raises_storage_operation_error() -> None:
    fake = FakeBotoClient(fail_methods={"create_bucket"}, head_bucket_fails=True)

    with pytest.raises(StorageOperationError):
        S3StorageClient(make_config(capabilities=MINIO_CAPABILITIES), boto3_client=fake)


def test_capability_presets_match_expected_provider_behaviors() -> None:
    assert MINIO_CAPABILITIES.supports_acl is True
    assert MINIO_CAPABILITIES.rewrite_presigned_host is True
    assert R2_CAPABILITIES.supports_acl is False
    assert R2_CAPABILITIES.public_url_path_style is False
    assert AWS_S3_CAPABILITIES.path_style == "virtual"
