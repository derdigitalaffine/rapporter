# Offline-first architecture

## Status

The accepted Shopping/Tasks/native Calendar offline program completed through
#705–#711 / #735 on 2026-10-15. Scoped acceptance and operational limits are
recorded in `offline-first-acceptance.md`; all 14 contracts below have evidence.
This does not declare unrelated modules or repository-wide baseline CI complete.

Offline capability is the current product priority. Until the acceptance criteria in this document are met for shopping, todos/tasks, and calendar, no unrelated product feature work should be started except for production-critical fixes, security fixes, dependency/security maintenance, or work strictly required by the offline program.

## Goal

Rapporter becomes a local-first PWA for the following domains:

- Shopping: full offline read/write
- Todos/tasks: full offline read/write, including semantically meaningful commands such as complete/reopen and workflow transitions
- Calendar: native FamilyOS events offline read/write; externally synchronized events offline-readable but read-only

The UI always reads from the local domain store. Online connectivity is a synchronization mechanism, not the primary data source.

## Core architecture

```text
React UI
   |
   v
Local domain store (IndexedDB)
   |\
   | +--> Outbox
   | +--> Conflicts
   | +--> Sync state / cursors
   v
Sync engine
   |
   v
POST /api/sync/
   |
   v
Django domain services
   |
   +--> PostgreSQL entities
   +--> version increment
   +--> SyncJournal entry
   |
   v
commit
   |
   v
Django Channels -> Redis -> WebSocket sync_available
```

The WebSocket only wakes clients up. Domain data is always transferred via `/api/sync/`.

## Local data model

IndexedDB should move from fallback snapshots toward normalized domain stores.

Required stores:

- `tasks`
- `taskLists`
- `shoppingLists`
- `shoppingItems`
- `events`
- `outbox`
- `conflicts`
- `syncState`
- `meta`

Every synchronized entity is namespaced by account and family and contains at least:

```text
account_id
family_id
id
version
data
sync_status
```

Recommended compound identity for local records:

```text
[account_id, family_id, id]
```

`syncState` is per account/family and contains at least:

```text
account_id
family_id
cursor
last_sync_at
schema_version
protocol_version
```

## IDs and idempotency

New offline entities receive their final UUID on the client before first synchronization.

The sync API must explicitly accept valid client-generated UUIDs for synchronizable entities. Do not rely on current DRF behavior for model IDs marked `editable=False`.

Every queued mutation has a unique `mutation_id` UUID used as the idempotency key.

## Outbox

A normal field mutation has this shape conceptually:

```json
{
  "mutation_id": "uuid",
  "family_id": "uuid",
  "entity_type": "task",
  "entity_id": "uuid",
  "operation": "update",
  "base_version": 17,
  "changes": {
    "title": "Hafermilch kaufen"
  }
}
```

Semantically meaningful actions use commands instead of pretending to be generic patches:

```json
{
  "mutation_id": "uuid",
  "family_id": "uuid",
  "entity_type": "task",
  "entity_id": "uuid",
  "operation": "command",
  "command": "complete_task",
  "base_version": 17
}
```

Examples of commands include task completion/reopen, workflow transitions, and other operations with important domain-side effects.

## Outbox compaction

Pending mutations for the same entity may be compacted when semantics are preserved.

Examples:

- create + update + update => one create with final values
- repeated field changes => one update containing the latest value per field
- create + delete before first server sync => remove both from the outbox

Commands with side effects must not be compacted unless their semantics are explicitly defined as safe.

## Bidirectional sync API

Use one endpoint for pushing local mutations and pulling server deltas:

```http
POST /api/sync/
```

Example request:

```json
{
  "protocol_version": 1,
  "family_id": "uuid",
  "cursor": 58420,
  "mutations": []
}
```

Example response:

```json
{
  "mode": "delta",
  "mutation_results": [
    {
      "mutation_id": "uuid",
      "status": "applied"
    }
  ],
  "changes": [
    {
      "cursor": 58421,
      "entity_type": "task",
      "entity_id": "uuid",
      "operation": "update",
      "version": 18,
      "changed_fields": ["title"],
      "data": {}
    }
  ],
  "cursor": 58429
}
```

Allowed mutation result statuses initially:

- `applied`
- `already_applied`
- `conflict`
- `rejected`

One failed mutation must not fail the whole batch. Each mutation is processed independently in its own server transaction.

## Server-side journal

Add a durable `SyncJournal` with a monotonically increasing cursor.

Conceptual fields:

```text
cursor
family_id
entity_type
entity_id
operation
version
changed_fields
created_at
```

The journal records create/update/delete changes. It is also the source of tombstones for entities that were physically deleted from normal domain tables.

Retention target: 90 days.

If a client cursor is older than the earliest retained journal entry, `/api/sync/` returns `mode: snapshot` / `reset_required` and provides or initiates a fresh snapshot without discarding the local outbox.

## Versioning and conflicts

Add an explicit monotonically increasing integer `version` to all synchronized records. `updated_at` remains useful metadata but must not be the only optimistic concurrency mechanism.

Every update mutation includes `base_version`.

Conflict detection is field-aware. If fields changed by the client do not overlap with fields changed on the server since `base_version`, merge automatically. If the same field was changed incompatibly, return a conflict containing both local and server values.

Delete-vs-edit is a conflict unless a domain-specific rule says otherwise.

## Snapshot consistency

Snapshots are tied to a fixed `snapshot_cursor`.

Workflow:

1. Server chooses `snapshot_cursor`.
2. Client receives a snapshot corresponding to that consistency boundary.
3. Client installs the snapshot locally.
4. Client immediately asks for deltas after `snapshot_cursor`.

Writes do not need to be globally blocked while a snapshot downloads.

## Domain service requirement

All writes for synchronized entities must go through a central domain/mutation service.

The following must happen in the same database transaction:

1. mutate entity
2. increment `version`
3. write `SyncJournal`

Only after commit may the backend emit a WebSocket `sync_available` event.

This requirement applies to writes originating from REST, `/api/sync/`, workers, schedulers, admin/internal actions, and integrations that modify native synchronized entities.

## Live operation

Add:

- ASGI entry point
- Django Channels
- Redis channel layer
- WebSocket consumer authenticated to the current account
- one family group per accessible family, e.g. `family:<uuid>`

WebSocket payload:

```json
{
  "type": "sync_available",
  "family_id": "uuid",
  "cursor": 59420
}
```

No domain object payloads are required over WebSocket. The client responds by running a normal `/api/sync/` cycle.

## Sync triggers

Run the sync engine on:

- app start
- offline -> online
- app returning to foreground
- `sync_available` WebSocket event
- manual "sync now"
- Background Sync where supported, as progressive enhancement only

## Multi-tab coordination

Use a browser leader-election mechanism so that one tab owns:

- WebSocket connection
- outbox processing
- `/api/sync/` execution

Other tabs continue to read/write the shared IndexedDB state and signal the leader, e.g. using `BroadcastChannel`.

Server-side mutation idempotency remains mandatory; leader election is an optimization, not the correctness boundary.

## Service worker boundary

Keep the current hand-written service worker.

Cache Storage is limited to app shell/static resources, push handling, update behavior, and Background Sync trigger plumbing.

Private domain data must not be stored as generic `/api/*` HTTP cache entries.

IndexedDB is the source of truth for offline domain data.

## Authentication and local privacy

- Offline use remains available after app restart while the user has not explicitly logged out.
- An expired server session does not delete local data or outbox mutations.
- Synchronization pauses until server re-authentication succeeds.
- Explicit logout/account switch clears local private data, conflicts, cursors, and outbox for that account.
- Data must be namespaced by account and family to prevent cross-account leakage on shared devices.

## Storage durability

After successful login, attempt `navigator.storage.persist()` as best effort. Failure to grant persistent storage must not block offline operation.

Use `navigator.storage.estimate()` for diagnostics/low-space warnings when useful.

## Schema and protocol versioning

Maintain separate versions for:

- IndexedDB schema
- sync protocol

Local migrations must preserve unsynchronized outbox entries whenever technically possible. A PWA update must never silently wipe the database while pending mutations exist.

## Product UX

Use a quiet global sync state:

- offline
- synchronizing
- synced
- action required

Individual rows may show a subtle pending-sync marker where useful.

Real conflicts must keep both values and offer explicit resolution, e.g. local value, server value, or manual merge for text.

## Prefetch policy

After authenticated startup, proactively synchronize the family core dataset instead of only caching screens that were visited.

Initial calendar window:

- 90 days into the past
- 12 months into the future

Shopping and current/open task data should be available without requiring a previous visit to each screen.

Large media/attachments remain on-demand unless separately specified.

## Delivery phases

### Phase 0 - foundation

Backend:

- explicit entity `version`
- `SyncJournal`
- idempotency store for processed mutations
- domain/mutation service layer
- `/api/sync/`
- delta response
- snapshot/reset response
- client-generated UUID support

Frontend:

- normalized IndexedDB schema
- account/family namespacing
- outbox
- conflicts
- sync state
- protocol/schema migrations
- sync engine
- logout cleanup
- minimal sync status UI

### Phase 1 - shopping pilot

Migrate shopping from fallback snapshots/unused mutation scaffolding to the common local-first engine.

Acceptance coverage includes offline create/edit/check/delete, reconnect, retry/idempotency, compaction, and concurrent edits.

### Phase 2 - todos/tasks

Migrate tasks and task lists, including commands for workflow/status behavior and recurrence-sensitive actions.

### Phase 3 - calendar

Native FamilyOS events become local-first read/write. Externally synchronized events are local-first read-only.

### Phase 4 - live transport

Introduce ASGI, Channels, Redis, family-scoped WebSocket wakeups, and browser sync-leader coordination.

The product must remain functionally correct without WebSockets.

### Phase 5 - robustness and polish

- Background Sync progressive enhancement
- persistent storage request
- quota diagnostics
- conflict center/polish
- journal pruning
- protocol compatibility tests
- long-offline snapshot recovery

## Required test matrix

At minimum automate these scenarios:

- online -> offline -> edit -> reload -> edit -> online
- two clients edit different fields of the same entity -> automatic merge
- two clients edit the same field differently -> conflict
- server commits mutation but client loses HTTP response -> retry is `already_applied`, no duplicate effect
- create offline -> edit repeatedly -> one compacted create
- create offline -> delete before first sync -> no server mutation
- physical server delete -> offline client receives tombstone
- client offline > 90 days -> snapshot reset preserves local outbox
- app update migrates IndexedDB while pending mutations exist
- explicit logout clears private local account data
- expired auth pauses sync but preserves offline work
- external calendar events remain readable but not editable offline
- multi-tab leader fails -> another tab takes over
- WebSocket unavailable -> foreground/online/manual sync still converges

## Definition of done for the offline program

The feature freeze may be lifted only when all of the following are true for shopping, todos/tasks, and calendar scope:

1. App shell loads without network after one successful installation/login cycle.
2. Core prefetched data is available offline without visiting every screen first.
3. Supported native entities can be created, edited, completed/checked, and deleted offline as applicable.
4. Offline work survives app reload and device/browser restart where browser storage persists.
5. Reconnect synchronizes automatically and idempotently.
6. Concurrent non-overlapping edits merge automatically.
7. True field conflicts are preserved and resolvable without silent data loss.
8. Deletes propagate reliably via the sync journal.
9. Snapshot recovery works for stale cursors without dropping the local outbox.
10. Explicit logout removes private cached account data.
11. Online and offline UI use the same local-first data path.
12. Required E2E test matrix is green in CI.
13. WebSocket live mode is additive; loss of WebSocket transport does not break convergence.
14. Documentation and operational notes for Redis/ASGI, migrations, journal retention, and recovery are complete.

## Non-goals for the initial offline program

Until the above definition of done is reached, do not expand the offline scope to unrelated FamilyOS modules. Do not introduce CRDTs unless concrete conflict cases prove the field-aware version model insufficient. Do not replace the existing service worker solely to obtain a different caching library.
