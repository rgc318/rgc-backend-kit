# ai_recipes Migration Notes

This package is intended to replace reusable infrastructure code in `ai_recipes` without importing application internals.

The migration should keep business behavior in `ai_recipes` and move only reusable token/storage infrastructure into `rgc-backend-kit`.

## JWT Scope

Move token lifecycle responsibilities:

- access token issuing
- refresh token issuing
- token pair issuing
- token decode and claim validation
- access/refresh type separation
- refresh token storage
- refresh token rotation
- refresh token replay detection
- access token revocation
- direct JTI revocation
- Redis token store adapter

Keep business responsibilities in `ai_recipes`:

- username/password login
- password hash verification
- user status checks
- login attempt locking
- user context loading
- roles and permissions
- API response formatting

## JWT Coupling Points to Remove

- `app.utils.jwt_utils` reads global `settings`.
- `app.utils.jwt_utils` reads global `redis_factory`.
- JWT exceptions inherit from the application response exception hierarchy.
- `get_current_user` combines token validation with user loading, avatar handling, roles, and permissions.

## JWT Migration Order

1. Create a `JWTConfig` from `settings.security_settings`.
2. Create a `RedisTokenStore` from the existing Redis client.
3. Replace `create_access_token`, `create_refresh_token`, `decode_token`, `rotate_refresh_token`, and `revoke_token` internals with `JWTManager`.
4. Keep `get_current_user` in `ai_recipes`, but make it call `JWTManager.decode_access_token`.
5. Convert `rgc_backend_kit.security` exceptions to existing API error responses at the application boundary.
6. Run the existing `ai_recipes` auth tests and add compatibility tests for login, refresh, logout, and protected endpoints.

## JWT Compatibility Mapping

| `ai_recipes` function | `rgc-backend-kit` replacement |
| --- | --- |
| `create_token` | `issue_access_token` / `issue_refresh_token` |
| `create_access_token` | `issue_access_token` |
| `create_refresh_token` | `issue_stored_refresh_token` / `issue_pair` |
| `decode_token` | `decode_token` / `decode_access_token` / `decode_refresh_token` |
| `validate_token_type` | built into `decode_access_token` and `decode_refresh_token` |
| `rotate_refresh_token` | `rotate_refresh_token` |
| `revoke_token` | `revoke_access_token` / `revoke_jti` |
| `is_token_revoked` | `TokenStore.is_token_revoked` |

## Storage Scope

Move reusable storage responsibilities:

- S3-compatible client config
- MinIO/R2/AWS capability presets
- upload, delete, copy, stat, list
- presigned GET/PUT URL
- presigned POST policy
- public URL building
- multi-client registry
- business profile routing

Keep business responsibilities in `ai_recipes`:

- file database records
- user ownership checks
- file categories and business permissions
- upload validation policy
- API response formatting

## Storage Coupling Points to Remove

- `app.infra.storage.storage_factory` reads global `settings`.
- `S3CompatibleClient` imports application logger and `FileException`.
- URL building depends on application utility modules and config schemas.

## Storage Migration Order

1. Convert existing storage client config into `S3StorageConfig`.
2. Convert existing storage profiles into `StorageProfileConfig`.
3. Replace `app.infra.storage.storage_factory.StorageFactory` with `rgc_backend_kit.storage.StorageFactory`.
4. Convert `StorageOperationError` and `StorageConfigurationError` to existing file API exceptions at the application boundary.
5. Keep profile names in the business application because they are business concepts.
6. Run existing file API tests and add compatibility tests for public/private upload, URL building, delete, copy, and presigned operations.

