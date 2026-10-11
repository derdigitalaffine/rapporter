# Superadmin security summary

Issue: #205 (roadmap #223)

## Endpoint

`GET /api/superadmin/security/summary/?period=30d`

Supported periods are `24h`, `7d`, `30d`, `90d`, and `365d`. The response also compares counts with the immediately preceding period of equal length. Values are a request-time snapshot; the endpoint does not auto-refresh or retain dashboard query state.

Access is restricted by the existing `IsSuperAdmin` permission. The aggregate security summary is intentionally separate from the bounded `/api/superadmin/audit/` explorer: this endpoint exposes trends only, not event rows. Both contracts may coexist in the Superadmin UI without sharing raw metadata.

## Metrics

The endpoint consumes the canonical privacy-minimized audit events defined by #204:

- `auth.login.succeeded`
- `auth.login.failed`
- `auth.rate_limited`
- `auth.password_reset.completed`
- `auth.email.verified`
- `auth.passkey.registered`
- `auth.passkey.removed`
- `auth.session.revoked`

Successful login methods are grouped only by the allow-listed `auth_method` values (`password`, `passkey`, `legacy`). Unknown identifiers from failed login attempts are never enumerated or exposed by this summary.

`login_success_rate_pct` is successful logins divided by successful plus failed login events. `passkey_share_pct` is successful passkey logins divided by successful logins carrying a canonical authentication method. Both are `null` when their denominator is zero.

These metrics are operational telemetry, not a user/family risk score and not a basis for opaque automated enforcement.

## Privacy boundary

The response exposes only aggregate counts and rates. It never serializes attempted identifiers, identifier hashes, request IDs, IP history, raw event metadata, tokens, passkey credential material, family content, mail bodies, or notification payloads.

This slice intentionally does not add risk scoring or infer security state from private content. It is a backend contract for the later #205 cockpit UI and can be rendered with non-color text/table alternatives.
