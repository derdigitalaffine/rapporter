# Offline IndexedDB schema contract

This document defines the local persistence contract for Rapporter's local-first migration.

## Stores

Use normalized, account- and family-scoped stores for `taskLists`, `tasks`, `shoppingLists`, `shoppingItems`, `events`, `outbox`, `conflicts`, `syncState`, and `meta`.

Every synchronized entity is keyed by account + family + entity UUID and stores `version`, `data`, and `sync_status`.

## Outbox

Each durable mutation stores `mutation_id`, account/family scope, entity type/id, operation, base version, payload/changes/command, timestamps, retry count, and last error. Index by family and entity so safe compaction is possible.

## Local transaction rule

For local-first user actions, mutate the local entity and upsert/compact the matching outbox entry in the same IndexedDB transaction whenever practical.

## Applying sync responses

Apply canonical entity changes/tombstones, mutation acknowledgements, conflicts, and cursor advancement atomically per family where practical. Never advance the cursor if local application fails.

## Snapshot reset

Preserve pending outbox/conflicts, replace the synchronized base entities only for the target account/family, install `snapshot_cursor`, re-apply pending optimistic state, then request deltas after the snapshot cursor.

## Logout

Explicit logout/account switch clears private local entities, outbox, conflicts, sync state, and account-scoped private caches for that account.

## Migrations

Use explicit IndexedDB version migrations. Pending outbox work has priority over cache convenience. Never silently wipe pending mutations during a PWA update.

## P0 persistence implementation (partial #706)

`frontend/src/local-sync-store.js` introduces the additive `familyos-local-sync`
version-1 database with all nine stores above. Each uses the compound key
`[accountId, familyId, id]`, with scope and account indexes. Outbox also has an
entity index. Identifiers are nonempty strings; callers normalize server IDs.
Payloads cannot override the store instance's account/family namespace.

`createLocalSyncStore(scope)` exposes `get`, `list`, atomic `write` batches and
`enqueue(entityStore, entity, mutation)` for committing an optimistic entity and
its durable mutation together. Outbox `id` equals `mutation_id`. `write` supports
puts and deletes across stores so future sync response application can commit
acknowledgements, conflicts, entity changes and cursor together. Promises resolve
only after transaction commit; clone/request errors abort the entire batch.

`clearLocalSyncAccount(accountId)` atomically deletes that account's records in
all families and all nine stores. The session integration must stop writers/sync
before calling it. This helper does not yet replace the existing logout flow.

This is persistence infrastructure only: the legacy `famuhle-offline-v1` shopping
path remains the active consumer until #707 cutover. No legacy queue is imported,
cleared or silently discarded here. Outbox compaction, response reconciliation,
protocol negotiation, future version migrations and logout wiring remain in #706.
Rollback before cutover simply removes the unused module; after cutover, pending
mutations must be drained or exported before any destructive rollback. Browser
regressions cover isolation, reload durability, atomic failure and account cleanup.
