from urllib.parse import quote, urlparse, urlunparse

from .config import StorageCapabilities


def build_public_storage_url(
    object_name: str,
    *,
    bucket_name: str,
    capabilities: StorageCapabilities,
    cdn_base_url: str | None = None,
    public_base_url: str | None = None,
    internal_base_url: str | None = None,
) -> str:
    base_url = cdn_base_url or public_base_url or internal_base_url
    if not base_url:
        raise ValueError("At least one public, CDN, or internal base URL is required.")

    base_url = base_url.rstrip("/")
    encoded_key = quote(object_name.lstrip("/"), safe="/")
    if capabilities.public_url_path_style:
        return f"{base_url}/{bucket_name}/{encoded_key}"
    return f"{base_url}/{encoded_key}"


def replace_url_origin(url: str, new_base_url: str) -> str:
    original = urlparse(url)
    replacement = urlparse(new_base_url)
    return urlunparse(
        (
            replacement.scheme,
            replacement.netloc,
            original.path,
            original.params,
            original.query,
            original.fragment,
        )
    )

