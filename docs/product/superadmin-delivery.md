# Superadmin delivery summary

Issue: #205 (roadmap #223)

## Endpoint

`GET /api/superadmin/delivery/summary/?period=30d`

Supported periods are `24h`, `7d`, `30d`, `90d`, and `365d`. The response compares delivery event counts with the immediately preceding period of equal length. Queue and subscription values are request-time operational snapshots rather than persisted dashboard state, and no server-side dashboard snapshot is retained.

Access is restricted by the existing `IsSuperAdmin` permission.

## Mail health

The mail section exposes only operational state:

- whether the effective SMTP transport is configured
- current transactional outbox counts by status (`queued`, `sending`, `sent`, `retry`, `failed`, `canceled`)
- `mail.sent` / `mail.failed` event counts and comparison
- delivery success rate with `null` for an empty denominator
- allow-listed `error_class` aggregates from `mail.failed`
- timestamp of the last successful mail delivery event

The endpoint does not return SMTP credentials, recipients, recipient hashes, template context, message bodies, or reference payloads.

## Push health

The push section combines the canonical `family.PushSubscription` operational state with #204 telemetry:

- total, active and inactive push-subscription counts
- `push.sent` / `push.failed` event counts and comparison
- success rate
- allow-listed failure classes
- timestamp of the last successful push delivery event

Subscription endpoints, `p256dh` keys, auth secrets and user-agent values are never serialized.

## Privacy boundary

Only aggregate operational metadata is returned. Notification titles/bodies, mail bodies, addresses, push endpoints/keys, tokens, private family content, and raw audit metadata are excluded by design.
