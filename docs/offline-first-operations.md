# Offline-first operational notes

## Components introduced by the program

- PostgreSQL sync journal and mutation-idempotency records
- `/api/sync/`
- versioned IndexedDB local domain store
- ASGI + Django Channels + Redis live wake-up transport

## Journal retention

Target retention is 90 days. Pruning must never remove entries newer than the documented retention boundary and must preserve the ability to detect stale cursors. Clients older than retained history recover through snapshot mode.

## Failure behavior

- Redis unavailable: WebSocket wakeups degrade; normal HTTP sync remains authoritative.
- WebSocket unavailable: startup/online/foreground/manual sync remains authoritative.
- authentication expired: local writes continue; network sync pauses until re-authentication.
- sync request interrupted: client retries with the same mutation IDs.
- server committed but response was lost: idempotency returns the prior semantic result without repeating side effects.
- client cursor too old: preserve local outbox and install a fresh snapshot.

## ASGI / Redis deployment

The standard Compose topology runs Django through Daphne/ASGI and adds a transient Redis 7 service. Redis contains wake-up messages only; it is not a database and does not need persistence. The channel layer uses `OFFLINE_REDIS_URL` (default `redis://redis:6379/0`) when `OFFLINE_LIVE_ENABLED=true`.

Caddy's existing reverse proxy supports WebSocket upgrades on `/ws/sync/<family>/`; no separate public port is required. WebSocket authentication reuses the application JWT cookie and checks active family membership before joining the family channel group. Messages contain only `sync_available`, the family id, and a cursor hint. Domain payloads and writes never travel over WebSocket.

### Safe rollback

Set `OFFLINE_LIVE_ENABLED=false` or remove Redis availability and redeploy. Clients continue to converge through the same startup, online, foreground and manual HTTP sync triggers. Because the live layer has no schema and stores no authoritative data, rollback requires no data migration and must not clear IndexedDB/outbox state.

### Redis outage

Do not reset clients or PostgreSQL. Restore Redis when convenient; missed wake-ups are harmless because HTTP sync compares cursors. Post-commit publication is best-effort and cannot roll back a committed domain mutation.

## Deployment rule

Roll out core delta sync before enabling WebSocket live transport. Do not make correctness depend on Redis or Channels.

## Privacy rule

Explicit logout/account switch clears account-scoped private offline entities, outbox, conflicts, cursor state, live leader leases/channels, and private cached shell metadata on the client.

## Diagnostics to expose/log

Without logging sensitive field payloads unnecessarily, diagnostics should make it possible to determine:

- account/family scope identifier where safe for server logs
- client protocol version
- starting/ending cursor
- mutation count and result statuses
- snapshot/reset occurrence
- conflict count
- server processing duration
- journal prune boundary
- live transport enabled/disabled and connection/takeover state without domain payloads

## Recovery principles

Prefer replay/idempotency and snapshot recovery over destructive client resets. Never instruct users to clear browser storage as the primary recovery mechanism while pending offline work may exist.
