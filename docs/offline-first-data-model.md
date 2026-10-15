# Offline-first backend data model

## Synchronized entities

Initial scope:

- ShoppingList
- ShoppingItem
- TaskList
- Task
- native FamilyEvent

Each synchronized entity receives an explicit monotonic integer `version` used for optimistic concurrency. `updated_at` remains metadata and is not the concurrency token.

## SyncJournal

Conceptual model:

```text
id / cursor (monotonic)
family_id
entity_type
entity_id
operation: create | update | delete
version
changed_fields
created_at
```

The cursor ordering must be stable and monotonic. The journal carries deletion tombstones after domain rows are physically deleted.

## ProcessedMutation

Conceptual model:

```text
mutation_id (UUID)
family_id
actor/user scope as required
entity_type
entity_id
result_status
result_version
result_payload (minimal canonical result as needed)
created_at
```

The idempotency record must be persisted atomically with the domain mutation and journal append so a lost HTTP response can be retried without repeating side effects.

## Domain mutation service

All writes to synchronized entities must flow through one mutation/domain service boundary, including REST endpoints, sync endpoint processing, schedulers/workers, admin/internal actions, and integration code that mutates native synchronized entities.

Within one database transaction:

1. validate authorization/domain rules
2. mutate entity
3. increment version
4. append SyncJournal
5. persist ProcessedMutation for sync-originated mutations

After commit, publish `sync_available` in the live phase.

## Client-generated UUIDs

Protocol v1 uses client-generated final UUIDs for offline creates. Serializers/sync services must explicitly accept and validate these UUIDs for synchronized creates; current model defaults alone are not sufficient to guarantee this behavior.

## Field-aware conflict support

`SyncJournal.changed_fields` records which logical fields changed for each entity version. For an update with a stale `base_version`, aggregate changed fields between `base_version` and current version. If there is no overlap with client changes, merge; otherwise return field conflicts unless a domain-specific rule resolves them safely.

## Snapshot scope

Snapshots are per authorized family and include the agreed local-first domain data. External calendar events may be included for read-only local display but are not accepted as mutable sync entities in protocol v1.
