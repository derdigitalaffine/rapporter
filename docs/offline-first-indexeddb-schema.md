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

## Generic response engine (#706 integration)

`offline-sync-engine.js` consumes the scoped store without introducing a second
IndexedDB database. Entity writes and outbox entries commit together. Unattempted
field edits may compact; an attempted mutation is immutable until acknowledged,
so a lost response can be retried under the same UUID. Side-effect commands never
compact. At most one mutation per entity is sent in a batch to preserve create
and command dependencies.

Snapshot installation, mutation acknowledgement, conflicts and cursor advance
commit together. A reset preserves pending mutations. Authorized visibility
manifests purge revoked/deleted canonical data; affected unsent edits are retained
in the conflict store. Unsupported protocol responses cannot advance the cursor.
Authentication failures pause retries without clearing local work. Explicit
account cleanup stops/aborts engines and awaits in-flight responses first.

The module is not yet a domain cutover. Existing Shopping/Task/Calendar consumers
remain unchanged until their dedicated migration slices. Web Locks serialize
local read/modify/write on supporting browsers; live/multi-tab fallback remains
part of #710 and is not claimed complete here.

## Version 2: ordered outbox migration

The local database now opens at version 2. Existing version-1 stores and records
are preserved. The upgrade adds `outbox.scopeOrder` on account/family/order and
backfills absent local order to zero. This field is not part of the HTTP mutation
fingerprint. Attempted mutations remain immutable on the wire. Upgrade failure
aborts the whole transaction; unsupported future versions are never auto-reset.
`offline-recovery.test.mjs` seeds a v1 sending mutation plus conflict, upgrades it,
and checks payload/state/scope preservation. It also proves future-schema refusal
leaves pending records intact. Rollback restrictions are in the operations runbook.
