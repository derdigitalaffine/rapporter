# Offline-first operational notes

## Components introduced by the program

- PostgreSQL sync journal and mutation-idempotency records
- `/api/sync/`
- versioned IndexedDB local domain store
- ASGI + Django Channels + Redis in the live phase

## Journal retention

Target retention is 90 days. Pruning must never remove entries newer than the documented retention boundary and must preserve the ability to detect stale cursors. Clients older than retained history recover through snapshot mode.

## Failure behavior

- Redis unavailable: WebSocket wakeups degrade; normal HTTP sync remains authoritative.
- WebSocket unavailable: startup/online/foreground/manual sync remains authoritative.
- authentication expired: local writes continue; network sync pauses until re-authentication.
- sync request interrupted: client retries with the same mutation IDs.
- server committed but response was lost: idempotency returns the prior semantic result without repeating side effects.
- client cursor too old: preserve local outbox and install a fresh snapshot.

## Deployment rule

Roll out core delta sync before enabling WebSocket live transport. Do not make correctness depend on Redis or Channels.

## Privacy rule

Explicit logout/account switch clears account-scoped private offline entities, outbox, conflicts, cursor state, and private cached shell metadata on the client.

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

## Recovery principles

Prefer replay/idempotency and snapshot recovery over destructive client resets. Never instruct users to clear browser storage as the primary recovery mechanism while pending offline work may exist.
