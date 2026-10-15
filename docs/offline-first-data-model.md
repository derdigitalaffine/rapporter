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

## Implemented backend foundation (#706)

The five canonical models now expose a non-editable `version`. Their ORM save,
QuerySet update/bulk-create/bulk-update, delete/cascade and event participant
changes append metadata-only `SyncJournal` records in the same transaction.
The initial implementation deliberately serializes synchronized writes on one
`SyncSequence` row. This bounds throughput but makes cursor watermarks follow
commit order; PostgreSQL sequence allocation by itself would miss late commits.
Explicit synchronized row locks acquire the sequence lock first. Raw SQL and
`save_base` are not supported write paths; new writers must use the model service.

`POST /api/sync/` reuses domain viewsets, serializers, shopping visibility and
native calendar validation. Task commands call the existing Unified Action
service. Successful receipts are scoped by actor/family and fingerprint the
whole mutation; changed-payload reuse is rejected. Each batch item owns its
transaction. Retained-history gaps cause a conflict rather than an unsafe merge.

Responses carry a fresh authorized `visibility` manifest. Clients remove local
entities absent from this manifest, including revoked private lists and physical
deletions, while preserving unsent work in conflicts. Hidden tombstone IDs and
historical private payloads are never disclosed. Delta object reads and snapshot
reads share the locked response watermark. Parent lists contain no nested items.

Migration `0240` is additive. Roll back application code before reversing it;
reversing the migration removes offline versions/journal/receipts and requires
clients to take a fresh snapshot before any later re-enable. Do not contract
these tables while pending clients still exist. The offline feature freeze stays
active: this slice alone does not complete #706 or enable domain cutover.
