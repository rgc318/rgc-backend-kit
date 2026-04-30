# Troubleshooting

## JWT

### Token Has Expired

Symptom:

```text
TokenExpiredError
```

Cause:

- `exp` is in the past
- access token TTL is too short
- client keeps using an old token after refresh

Fix:

- Use refresh token rotation to obtain a new token pair.
- Check server clock drift.
- Adjust `access_token_ttl` only if the product requirements allow it.

### Invalid Audience

Symptom:

```text
InvalidTokenError: Audience doesn't match
```

Cause:

- Token was issued with a different `aud`.
- Verifier has `JWTConfig.audience` set incorrectly.

Fix:

- Use the same audience value when issuing and verifying tokens.
- If your system does not need audience validation, set `audience=None`.

### Invalid Issuer

Symptom:

```text
InvalidTokenError: Invalid issuer
```

Cause:

- Token was issued by another service.
- Verifier has `JWTConfig.issuer` set incorrectly.

Fix:

- Align `issuer` values between services.

### Refresh Token Reuse

Symptom:

```text
RefreshTokenReuseError
```

Cause:

- Refresh token was already rotated.
- Refresh token was deleted from Redis.
- A different Redis database or prefix is being used.

Fix:

- Ensure the client stores the latest refresh token after every refresh.
- Verify Redis URL and `refresh_prefix`.

### Revoked Access Token Still Works

Cause:

- `decode_token` was used directly instead of `decode_access_token`.
- A `NullTokenStore` is being used.
- Redis connection points to a different database.

Fix:

- Use `decode_access_token` for protected routes.
- Use `RedisTokenStore` in production.
- Verify `REDIS_URL`.

## Storage

### Public URL Uses Internal Host

Cause:

- `public_endpoint` is not configured.
- `cdn_base_url` is not configured.
- `secure_public` has the wrong value.

Fix:

- Set `public_endpoint="img.example.com"`.
- Set `secure_public=True` when the public endpoint uses HTTPS.

### Presigned URL Uses Internal Host

Cause:

- Some S3-compatible providers generate signatures using the internal endpoint.
- `rewrite_presigned_host` is disabled.

Fix:

- For MinIO with public gateway access, use `MINIO_CAPABILITIES` or set `rewrite_presigned_host=True`.

### Bucket Creation Fails

Cause:

- Provider does not allow application-side bucket creation.
- Credentials do not have bucket creation permission.

Fix:

- For R2/AWS production buckets, create buckets outside the application.
- Set `supports_bucket_creation=False`.

### ACL Error

Cause:

- Provider does not support ACL.
- Bucket policy rejects ACL usage.

Fix:

- Use `R2_CAPABILITIES` for R2.
- Set `supports_acl=False`.
- Prefer bucket policy/CDN access control over per-object ACLs when appropriate.

