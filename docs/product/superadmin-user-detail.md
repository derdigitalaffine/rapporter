# Superadmin user detail

Issue: #205 (roadmap #223)

## Endpoint

`GET /api/superadmin/users/{user_id}/`

The endpoint is exposed through the already included family API URL set so the existing top-level Superadmin URL configuration and its write-action routes remain unchanged. Access requires the existing `IsSuperAdmin` permission. This is a read-only administrative view and does not grant any additional write capability.

## Payload

The detail response contains:

- the canonical Superadmin user-directory row, including account status, primary-email verification, memberships, last activity/login and aggregate active session/passkey counts
- active session metadata, capped at 50 rows: auth method, client label, creation/last-seen/last-reauthentication timestamps and absolute expiry
- passkey aggregate state: active count, revoked count and last-use timestamp
- the latest 50 account-related `auth.*` audit events with timestamp, event key, outcome, reason, optional family ID, target type and only the allow-listed `auth_method` value
- account-related invitation history, capped at 50 rows, matched by accepted account or known account email and reduced to family/role/lifecycle metadata

## Privacy boundary

The endpoint never serializes:

- session UUIDs, refresh JTIs or refresh-token state
- WebAuthn credential IDs, public keys, transport data or passkey labels
- invite tokens or token digests
- raw audit metadata, request/correlation IDs or target IDs
- full IP/location histories or attempted unknown login identifiers
- mail/push bodies, notification content or private family-domain content

`auth_method` is copied from audit metadata only when it is one of the explicit categories `password`, `passkey`, `recovery` or `legacy`; all other metadata values are discarded.

Administrative email/recovery writes keep their existing fresh-reauthentication and audit contracts. Visibility in this detail endpoint does not authorize those actions.
