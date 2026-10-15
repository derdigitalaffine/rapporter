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
