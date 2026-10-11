# Notifications: canonical in-app core

This slice of #203 adds a durable in-app notification center without replacing the existing push stack.

## Source of truth

`family.domain_notifications.notify_domain_event` remains the shared domain-event resolver. For every eligible recipient it now records a rendered `notifications.Notification` row before evaluating push-channel preferences. The notification row owns the in-app read/unread state. `NotificationBadgeState` is only a derived account-wide launcher badge mirror and can be rebuilt from unread notification rows.

Push preferences, detail level, quiet hours, and digest batching remain push-delivery policy. Turning push off must not remove the corresponding in-app activity. Originating domain mutations continue even if notification fan-out fails.

## Privacy and links

In-app rows persist only the recipient, family, event type, rendered title/body, priority, canonical internal resource URL, timestamps, and read state. Raw event context is not retained in the in-app store. Resource links must be same-origin application paths beginning with `/`; absolute, protocol-relative, credential-bearing, control-character, and backslash-based links are rejected. Fragments are dropped.

The existing event matrix in `family.domain_notifications.EVENT_SPECS` defines which normal family events enter this core. Actors remain excluded from their own event by default, and targeted events keep their existing recipient filtering.

## API

- `GET /api/notifications/?family=<uuid>&limit=<n>&cursor=<cursor>` returns deterministic cursor pages and the family-scoped unread count for the signed-in member.
- `PATCH /api/notifications/<uuid>/` with `{"read": true|false}` changes only the signed-in recipient's row and is idempotent.
- `POST /api/notifications/read-all/` with `{"family": "<uuid>"}` marks that membership's unread rows read.

Cross-family access fails closed with `404`. The UI surfaces the inbox on the existing Notifications page and uses only server-issued internal resource links.

## Deliberately out of scope for this slice

E-mail fan-out, a unified per-channel preference matrix, changes to existing push quiet-hours/digest behavior, retention cleanup, and further event coverage remain follow-up work under #203.
