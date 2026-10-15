# Offline-first implementation workplan

Accepted 2026-10-15 through #706–#711 and PR #735. The scoped PostgreSQL/Redis,
real-domain offline, browser store/engine and Node suites passed. The evidence
map and operational limits are in `offline-first-acceptance.md`.

This workplan turns `docs/offline-first-architecture.md` into an ordered delivery queue. It is intentionally sequential: unrelated feature work is paused until the offline definition of done is met.

## Priority rule

Allowed before completion of the offline program:

1. production-critical bug fixes
2. security/privacy fixes
3. required dependency/security maintenance
4. changes strictly necessary to deliver or validate the offline program

Everything else waits.

## P0 - Foundation contract

### Backend

- [x] Add explicit monotonic `version` to synchronized domain entities.
- [x] Add `SyncJournal` with monotonic cursor, family scope, operation, version, changed fields, and timestamp.
- [x] Add processed-mutation/idempotency persistence keyed by `mutation_id` and family/account context.
- [x] Define synchronized entity registry for shopping, tasks, and native family events.
- [x] Add central domain/mutation service boundary for synchronized writes.
- [x] Ensure entity mutation + version increment + journal entry are atomic.
- [x] Add client-generated UUID acceptance for synchronized creates.
- [x] Implement `POST /api/sync/` protocol v1.
- [x] Implement independent per-mutation results (`applied`, `already_applied`, `conflict`, `rejected`).
- [x] Implement field-aware conflict detection using changes since `base_version`.
- [x] Implement delete tombstones through `SyncJournal`.
- [x] Implement snapshot/reset mode with `snapshot_cursor`.
- [x] Implement 90-day journal-retention boundary and stale-cursor response.
- [x] Add authorization tests proving a family cannot read/write another family's journal/snapshot/mutations.

### Frontend

- [x] Introduce a versioned IndexedDB schema for normalized entities.
- [x] Namespace all domain data by account + family.
- [x] Implement generic outbox records with `mutation_id`, `base_version`, operation, and payload.
- [x] Implement outbox compaction rules.
- [x] Implement conflict store.
- [x] Implement per-family sync state/cursor store.
- [x] Implement local schema migrations that preserve pending outbox records.
- [x] Implement sync protocol version negotiation/guard.
- [x] Implement sync engine with a single-flight lock.
- [x] Trigger sync on app start, `online`, foreground resume, and manual action.
- [x] Pause sync on authentication failure while preserving local work.
- [x] Clear all private local account data on explicit logout/account switch.
- [x] Add subtle global offline/sync/action-required state.
- [x] Request persistent storage as best effort after successful login.

### CI / test harness

- [x] Add deterministic test helpers for toggling browser network availability.
- [x] Add fixtures for two independent clients/users in the same family.
- [x] Add fixtures for stale cursors and snapshot recovery.
- [x] Add idempotency test where the response is lost after server commit.

## P1 - Shopping pilot

- [x] Replace shopping snapshot-as-source behavior with normalized local entities.
- [x] Route shopping UI reads through the local store.
- [x] Route shopping creates/updates/checks/deletes through local-first mutations even while online.
- [x] Support offline create list/item.
- [x] Support offline rename/edit quantity/category/note/position as applicable.
- [x] Support offline check/uncheck.
- [x] Support offline delete.
- [x] Reconcile accepted mutations to canonical server state.
- [x] Add field-conflict UI.
- [x] Add shopping E2E matrix for reload, reconnect, concurrent edits, compaction, retry, and deletion.

Exit criterion: shopping is fully usable without network after prefetch and converges automatically on reconnect.

## P2 - Todos/tasks

- [x] Normalize task lists/tasks in IndexedDB.
- [x] Route task UI reads through the local store.
- [x] Route task writes through local-first mutations.
- [x] Implement task create/edit/delete offline.
- [x] Implement `complete_task` / reopen command semantics.
- [x] Implement workflow-transition command semantics.
- [x] Cover recurrence-sensitive behavior without bypassing existing domain logic.
- [x] Reconcile assignee/due date/priority/tags safely.
- [x] Add task field-conflict UI and tests.

Exit criterion: todo/task workflows in the agreed scope are fully usable offline and converge without silent loss.

## P3 - Calendar

- [x] Normalize native and external event data locally.
- [x] Prefetch 90 days past and 12 months future.
- [x] Route calendar reads through the local store.
- [x] Implement native FamilyOS event create/edit/delete offline.
- [x] Enforce external synchronized events as read-only while offline and online unless their source-specific integration explicitly supports writes.
- [x] Implement event field conflicts and delete-vs-edit conflicts.
- [x] Add calendar E2E coverage for offline reload/reconnect and external-source read-only behavior.

Exit criterion: the agreed calendar window is available offline; native events are editable and external events remain safely read-only.

## P4 - Live transport

- [x] Add ASGI entry point.
- [x] Add Django Channels.
- [x] Add Redis service/configuration/channel layer.
- [x] Add authenticated family-scoped WebSocket consumer.
- [x] Emit `sync_available` only after successful DB commit.
- [x] Add browser WebSocket client that triggers normal delta sync.
- [x] Add multi-tab sync leader election and takeover.
- [x] Add fallback tests proving sync still converges without WebSocket.

Exit criterion: online changes appear live, but WebSocket failure never breaks correctness.

## P5 - Robustness and release gate

- [x] Add Background Sync where supported; keep it optional.
- [x] Add storage quota diagnostics/low-space messaging.
- [x] Add conflict center/polish.
- [x] Add journal pruning job/management command and operational documentation.
- [x] Add protocol compatibility tests.
- [x] Add stale-client snapshot recovery tests.
- [x] Add explicit logout/privacy regression tests.
- [x] Add upgrade tests with pending outbox mutations.
- [x] Document Redis/ASGI deployment and rollback.
- [x] Document operational recovery for journal/sync failures.
- [x] Run the full offline E2E matrix in CI.

## Release gate

No unrelated roadmap item moves into implementation until every item in the definition of done in `docs/offline-first-architecture.md` is satisfied or explicitly waived in a documented architecture/product decision.
