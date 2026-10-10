# Auth abuse protection

FamilyOS uses one central abuse-protection service for authentication, recovery, invitation and sensitive administrator flows. The implementation lives in `backend/auth_abuse/` and deliberately avoids per-view magic numbers.

## Stable scopes

The following scope names are API contracts for current and upcoming auth work:

- `login.password`
- `login.passkey.options`
- `login.passkey.verify`
- `reauth.password`
- `password_reset.request`
- `email_verification.resend`
- `invite.create`
- `invite.resend`
- `webauthn.registration.options`
- `webauthn.authentication.options`
- `superadmin.sensitive_action`

Each scope has a burst window, a sustained window, an identity-key strategy, a base/max cooldown and a privacy-safe audit category in `auth_abuse.service.POLICIES`. Future passkey/fresh-session work should call `enforce()` with one of these scopes instead of creating local throttles.

## Current enforcement

The current application enforces:

- password login via `login.password`;
- invitation creation via `invite.create`;
- invitation renewal/resend via `invite.resend`;
- current superadmin mutations via `superadmin.sensitive_action`.

Password-login failures use the same generic response for known and unknown identifiers. A rate-limited login keeps that same generic detail and adds HTTP `429`, `Retry-After`, `code=rate_limited` and a numeric `retry_after`. Successful logins forgive identifier-specific counters, while network/global pressure remains.

## Persistent multi-worker store

Counters are stored in PostgreSQL through `AuthAbuseBucket`. A bucket is unique by scope, HMAC key and window kind. Enforcement uses transactions plus `SELECT ... FOR UPDATE`; concurrent first writers are reconciled through the database uniqueness constraint. This makes the budget shared across Gunicorn workers and across application replicas using the same database.

Cooldowns are progressive and capped. When a cooldown ends, one probe is allowed without discarding the sustained-window history. This prevents permanent account lockout while still slowing repeated failures.

## Privacy and identity keys

Raw login identifiers and raw client IP values are never persisted in abuse buckets. Values are normalized and keyed with HMAC-SHA256 using `AUTH_ABUSE_HMAC_KEY` (falling back to `DJANGO_SECRET_KEY` when unset). Stored `key_kind` values contain only non-sensitive categories such as `network`, `identifier`, `user`, `family` and `global`.

IPv4 defaults to `/32`; IPv6 defaults to `/64` so temporary IPv6 interface addresses cannot trivially bypass network limits. Prefix sizes are configurable.

### Reverse proxies

`X-Forwarded-For` is ignored unless the direct peer (`REMOTE_ADDR`) belongs to an explicitly configured `AUTH_TRUSTED_PROXY_CIDRS` network. When trusted, the chain is walked from right to left and only configured trusted proxy hops are discarded. This prevents blindly trusting a client-supplied forwarding header.

Example for an installation whose application is reachable only from a known reverse-proxy network:

```env
AUTH_TRUSTED_PROXY_CIDRS=172.20.0.0/16
```

Use the actual proxy/network CIDR for the deployment. Leaving this setting empty is safe: forwarded addresses are ignored and the direct peer is used.

## Configuration

Optional environment variables:

```env
# Recommended as a separate random secret; unset/blank falls back to DJANGO_SECRET_KEY.
AUTH_ABUSE_HMAC_KEY=
AUTH_TRUSTED_PROXY_CIDRS=
AUTH_ABUSE_IPV4_PREFIX=32
AUTH_ABUSE_IPV6_PREFIX=64
AUTH_ABUSE_RETENTION_SECONDS=86400
```

Changing the HMAC key intentionally invalidates the link to existing buckets; old hashed rows age out and can be cleaned up.

## Audit and operations

Rate-limit hits emit a warning through the `security.auth_abuse` logger with only audit category, scope, key kind and retry duration. Raw identifiers, IPs and HMAC digests are not logged.

Expired rows can be removed with:

```bash
python manage.py cleanup_auth_abuse
```

The break-glass path is CLI-only; there is no public HTTP bypass:

```bash
python manage.py reset_auth_abuse --scope login.password
python manage.py reset_auth_abuse --all
```

Use reset only during an operational recovery. Normal users must never need it because cooldowns expire automatically.

## Follow-up integration

Issues #201/#202 can reuse the already-declared `reauth.password`, passkey/WebAuthn and `superadmin.sensitive_action` scopes when fresh-session and step-up authentication land. This change intentionally does not invent those future authentication flows early.
