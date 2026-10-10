# Revocable auth sessions and fresh re-authentication

FamilyOS binds JWT cookies to an explicit server-side `AuthSession`. The session is the security identity for one logical login; access and refresh tokens are only short-lived credentials for that session.

## Session invariants

Every successful login creates exactly one `AuthSession` with an opaque UUID `sid`. Access and refresh JWTs carry that same `sid`, the authentication method and the timestamp of the most recent real authentication. Refresh rotation keeps the logical `sid`; it never creates a new visible session.

Authenticated requests validate both the JWT and the referenced database session. A revoked or absolutely expired session therefore stops working immediately instead of waiting for the access token to expire. This intentionally adds one indexed session lookup per authenticated request in exchange for predictable revocation semantics.

A session stores only security-purpose metadata: user, timestamps, authentication method, refresh-token state and a coarse browser/OS label derived from the User-Agent. FamilyOS does not store an IP address, location, persistent device fingerprint or external Geo-IP result for this feature.

## Refresh rotation and reuse

`AuthSession.current_refresh_jti` records the refresh token that is currently allowed to rotate. Rotation runs under a PostgreSQL row lock and moves that JTI to `previous_refresh_jti` before issuing the next token pair.

A short grace window exists only for a legitimate race where two tabs sent the same cookie before the winning response could update the browser cookie. During that grace the losing request succeeds without minting a second refresh token. Reuse of an older rotated token outside the grace is treated as suspicious and revokes the entire logical session.

Defaults:

```env
AUTH_SESSION_REFRESH_REUSE_GRACE_SECONDS=5
AUTH_SESSION_ABSOLUTE_DAYS=90
```

The absolute lifetime caps both access and refresh JWT expiry. JWT refresh never extends it.

## Fresh authentication

`last_reauthenticated_at` is updated only by a real authentication ceremony, never by JWT refresh. The centralized freshness window defaults to ten minutes:

```env
AUTH_SESSION_FRESH_SECONDS=600
```

Use `auth_sessions.service.require_fresh_session(request)` for sensitive endpoints. Password re-authentication is exposed as `POST /api/auth/reauth/password/` and is protected by the central `reauth.password` abuse scope from #206. A successful confirmation updates only the current session and refreshes its access-token `auth_time` claim.

Current sensitive uses include “revoke all other sessions” and Superadmin mutations such as tenant creation, tenant suspension/reactivation and Owner invitation. Future primary-email, password and passkey changes must reuse the same freshness helper rather than implementing per-view age checks.

## User API and Security Center

The current endpoints are:

- `GET /api/auth/sessions/` — list the caller's live sessions and mark the current one;
- `DELETE /api/auth/sessions/{sid}/` — revoke one other session; missing and cross-user IDs deliberately have the same response shape;
- `POST /api/auth/sessions/revoke-others/` — keep only the current session; requires fresh authentication;
- `POST /api/auth/reauth/password/` — confirm the current password and refresh freshness;
- `POST /api/auth/logout/` — revoke the current server-side session through its refresh cookie and clear both cookies.

The profile Security Center shows only coarse client information, creation/last-seen timestamps and authentication method. It makes no location claim and exposes no session belonging to another account.

## Integration contracts for #199 and #201

Password reset (#199) must call:

```python
revoke_all_user_sessions(user, reason="password_reset")
```

before establishing any new post-recovery session. The backend test suite already locks this contract down, so a reset implementation cannot safely leave prior refresh rights active.

Passkey login and passkey re-authentication (#201) use the same `AuthSession` model. A passkey login should call `create_session(..., auth_method=AuthSession.AuthMethod.PASSKEY)`; a successful passkey step-up should call `mark_reauthenticated(..., auth_method=AuthSession.AuthMethod.PASSKEY)`. Do not create a parallel passkey-session table or independent freshness timestamp.

## Retention and operations

`last_seen_at` writes are rate-limited by `AUTH_SESSION_SEEN_WRITE_SECONDS` (default five minutes) to avoid a database write on every request. Revoked/long-expired rows can be removed with:

```bash
python manage.py cleanup_auth_sessions
```

Retention defaults to 30 days after revocation/long expiry and is configurable through `AUTH_SESSION_RETENTION_DAYS`.

## Deployment note

JWTs issued before this feature do not contain `sid` and are intentionally rejected after deployment. Existing users may therefore need to sign in once after the migration. This is a one-time compatibility break that avoids silently keeping legacy, non-revocable refresh rights alive.
