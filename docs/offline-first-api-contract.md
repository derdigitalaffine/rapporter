# Offline sync API contract v1

This document specifies the first public contract for Rapporter's local-first synchronization layer. It is intentionally narrow and covers Shopping, Todos/Tasks, and Calendar only.

## Endpoint

```http
POST /api/sync/
Content-Type: application/json
```

Authentication uses the normal Rapporter authenticated session. The server must authorize membership for the requested `family_id` before processing mutations or returning changes.

## Request

```json
{
  "protocol_version": 1,
  "family_id": "UUID",
  "cursor": 58420,
  "mutations": []
}
```

Fields:

- `protocol_version`: integer, required
- `family_id`: UUID, required
- `cursor`: integer or null; null requests an initial snapshot
- `mutations`: array, may be empty

## Mutation envelope

```json
{
  "mutation_id": "UUID",
  "entity_type": "task",
  "entity_id": "UUID",
  "operation": "update",
  "base_version": 17,
  "changes": {
    "title": "Hafermilch kaufen"
  }
}
```

Required common fields:

- `mutation_id`: stable idempotency UUID generated client-side
- `entity_type`: registry key
- `entity_id`: final client/server entity UUID
- `operation`: one of `create`, `update`, `delete`, `command`
- `base_version`: null for create; required for update/delete/commands that act on an existing entity

### Create

```json
{
  "mutation_id": "UUID",
  "entity_type": "shopping_item",
  "entity_id": "UUID",
  "operation": "create",
  "base_version": null,
  "data": {
    "shopping_list": "UUID",
    "name": "Milch",
    "quantity": "2"
  }
}
```

### Update

```json
{
  "mutation_id": "UUID",
  "entity_type": "shopping_item",
  "entity_id": "UUID",
  "operation": "update",
  "base_version": 4,
  "changes": {
    "quantity": "3"
  }
}
```

### Delete

```json
{
  "mutation_id": "UUID",
  "entity_type": "shopping_item",
  "entity_id": "UUID",
  "operation": "delete",
  "base_version": 4
}
```

### Command

```json
{
  "mutation_id": "UUID",
  "entity_type": "task",
  "entity_id": "UUID",
  "operation": "command",
  "command": "complete_task",
  "base_version": 11,
  "args": {}
}
```

## Mutation results

Each mutation is processed independently and returns one result.

### Applied

```json
{
  "mutation_id": "UUID",
  "status": "applied",
  "entity_type": "task",
  "entity_id": "UUID",
  "version": 12
}
```

### Already applied

Returned when the same `mutation_id` was committed previously.

```json
{
  "mutation_id": "UUID",
  "status": "already_applied",
  "entity_type": "task",
  "entity_id": "UUID",
  "version": 12
}
```

The outcome must be semantically equivalent to the original successful processing. Retrying a mutation must not duplicate domain side effects.

### Conflict

```json
{
  "mutation_id": "UUID",
  "status": "conflict",
  "entity_type": "event",
  "entity_id": "UUID",
  "server_version": 9,
  "conflicts": {
    "title": {
      "client": "Elternabend Schule",
      "server": "Elternabend Klasse 3b"
    }
  },
  "server_data": {}
}
```

Only truly overlapping incompatible fields should conflict. Non-overlapping server/client field changes should be merged automatically.

### Rejected

Used for validation, authorization, unsupported operations, or domain-rule rejection.

```json
{
  "mutation_id": "UUID",
  "status": "rejected",
  "code": "validation_error",
  "errors": {}
}
```

A rejected mutation must not block unrelated mutations in the same request.

## Delta response

```json
{
  "protocol_version": 1,
  "mode": "delta",
  "mutation_results": [],
  "changes": [
    {
      "cursor": 58421,
      "family_id": "UUID",
      "entity_type": "task",
      "entity_id": "UUID",
      "operation": "update",
      "version": 12,
      "changed_fields": ["title"],
      "data": {
        "id": "UUID",
        "version": 12,
        "title": "Hafermilch kaufen"
      }
    }
  ],
  "cursor": 58429
}
```

For deletes:

```json
{
  "cursor": 58422,
  "family_id": "UUID",
  "entity_type": "task",
  "entity_id": "UUID",
  "operation": "delete",
  "version": 13,
  "changed_fields": []
}
```

## Snapshot response

If `cursor` is null or older than retained journal history, the server returns a snapshot.

```json
{
  "protocol_version": 1,
  "mode": "snapshot",
  "reset_required": true,
  "mutation_results": [],
  "snapshot_cursor": 60000,
  "snapshot": {
    "task_lists": [],
    "tasks": [],
    "shopping_lists": [],
    "shopping_items": [],
    "events": []
  },
  "cursor": 60000
}
```

The client must never discard pending local mutations merely because `reset_required` is true. Pending mutations are uploaded/validated first or preserved across snapshot installation.

## Initial entity registry

Protocol v1 initially supports:

- `shopping_list`
- `shopping_item`
- `task_list`
- `task`
- `event` for native FamilyOS events

External synchronized calendar events may appear in snapshots/deltas for read-only local presentation but do not accept create/update/delete mutations unless a future source-specific contract explicitly enables that.

## Field-level merge rules

The server determines which fields changed after `base_version` using `SyncJournal.changed_fields`.

For an update mutation:

1. load current entity and version
2. if `current.version == base_version`, apply normally
3. otherwise collect server-changed fields after `base_version`
4. if intersection with client `changes.keys()` is empty, merge automatically
5. otherwise return `conflict` for overlapping fields that cannot be resolved by a domain rule

Domain commands may define their own conflict semantics.

## Transaction and journal rules

For every successful synchronized write, the following are atomic:

1. domain mutation
2. entity version increment
3. SyncJournal append
4. processed-mutation result persistence

The WebSocket wake-up is emitted only after commit.

## Cursor rules

- Cursor is scoped by family in client state.
- Server cursor is monotonic for journal ordering.
- Clients must treat the cursor as opaque ordering state; do not infer wall-clock time from it.
- A response cursor represents all changes included in the response.

## Protocol compatibility

Unsupported newer protocol versions return a machine-readable error and do not apply mutations.

The server may support multiple protocol versions during rolling upgrades. IndexedDB schema versioning is separate from sync protocol versioning.

## Security requirements

- Never return changes for families the authenticated account cannot access.
- Never accept mutations targeting entities outside the requested/authorized family.
- Client-provided UUIDs do not imply authorization.
- Idempotency keys must be scoped sufficiently to prevent cross-account/cross-family collisions or information disclosure.
- External calendar source ownership/family checks remain enforced.

## Optional projection freshness (calendar consumer)

Clients may send `calendar_projection_key`, the last `projections.calendar_key`.
On snapshot, calendar journal changes, family-timezone changes or a changed local
calendar day, the response includes canonical `calendar_occurrences`,
`calendar_window` and a new key. Existing recurrence and birthday cores calculate
these views; no second recurrence engine is introduced. Birthday projections are
refreshed independently. The client merges projection metadata atomically with
entities/outbox/cursor and keeps normalized master IDs for every write. A missing
hint is safe and simply requests the projection again.
