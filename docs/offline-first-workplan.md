# Offline-first implementation workplan

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

- [ ] Add explicit monotonic `version` to synchronized domain entities.
- [ ] Add `SyncJournal` with monotonic cursor, family scope, operation, version, changed fields, and timestamp.
- [ ] Add processed-mutation/idempotency persistence keyed by `mutation_id` and family/account context.
- [ ] Define synchronized entity registry for shopping, tasks, and native family events.
- [ ] Add central domain/mutation service boundary for synchronized writes.
- [ ] Ensure entity mutation + version increment + journal entry are atomic.
- [ ] Add client-generated UUID acceptance for synchronized creates.
- [ ] Implement `POST /api/sync/` protocol v1.
- [ ] Implement independent per-mutation results (`applied`, `already_applied`, `conflict`, `rejected`).
- [ ] Implement field-aware conflict detection using changes since `base_version`.
- [ ] Implement delete tombstones through `SyncJournal`.
- [ ] Implement snapshot/reset mode with `snapshot_cursor`.
- [ ] Implement 90-day journal-retention boundary and stale-cursor response.
- [ ] Add authorization tests proving a family cannot read/write another family's journal/snapshot/mutations.

### Frontend

- [ ] Introduce a versioned IndexedDB schema for normalized entities.
- [ ] Namespace all domain data by account + family.
- [ ] Implement generic outbox records with `mutation_id`, `base_version`, operation, and payload.
- [ ] Implement outbox compaction rules.
- [ ] Implement conflict store.
- [ ] Implement per-family sync state/cursor store.
- [ ] Implement local schema migrations that preserve pending outbox records.
- [ ] Implement sync protocol version negotiation/guard.
- [ ] Implement sync engine with a single-flight lock.
- [ ] Trigger sync on app start, `online`, foreground resume, and manual action.
- [ ] Pause sync on authentication failure while preserving local work.
- [ ] Clear all private local account data on explicit logout/account switch.
- [ ] Add subtle global offline/sync/action-required state.
- [ ] Request persistent storage as best effort after successful login.

### CI / test harness

- [ ] Add deterministic test helpers for toggling browser network availability.
- [ ] Add fixtures for two independent clients/users in the same family.
- [ ] Add fixtures for stale cursors and snapshot recovery.
- [ ] Add idempotency test where the response is lost after server commit.

## P1 - Shopping pilot

- [ ] Replace shopping snapshot-as-source behavior with normalized local entities.
- [ ] Route shopping UI reads through the local store.
- [ ] Route shopping creates/updates/checks/deletes through local-first mutations even while online.
- [ ] Support offline create list/item.
- [ ] Support offline rename/edit quantity/category/note/position as applicable.
- [ ] Support offline check/uncheck.
- [ ] Support offline delete.
- [ ] Reconcile accepted mutations to canonical server state.
- [ ] Add field-conflict UI.
- [ ] Add shopping E2E matrix for reload, reconnect, concurrent edits, compaction, retry, and deletion.

Exit criterion: shopping is fully usable without network after prefetch and converges automatically on reconnect.

## P2 - Todos/tasks

- [ ] Normalize task lists/tasks in IndexedDB.
- [ ] Route task UI reads through the local store.
- [ ] Route task writes through local-first mutations.
- [ ] Implement task create/edit/delete offline.
- [ ] Implement `complete_task` / reopen command semantics.
- [ ] Implement workflow-transition command semantics.
- [ ] Cover recurrence-sensitive behavior without bypassing existing domain logic.
- [ ] Reconcile assignee/due date/priority/tags safely.
- [ ] Add task field-conflict UI and tests.

Exit criterion: todo/task workflows in the agreed scope are fully usable offline and converge without silent loss.

## P3 - Calendar

- [ ] Normalize native and external event data locally.
- [ ] Prefetch 90 days past and 12 months future.
- [ ] Route calendar reads through the local store.
- [ ] Implement native FamilyOS event create/edit/delete offline.
- [ ] Enforce external synchronized events as read-only while offline and online unless their source-specific integration explicitly supports writes.
- [ ] Implement event field conflicts and delete-vs-edit conflicts.
- [ ] Add calendar E2E coverage for offline reload/reconnect and external-source read-only behavior.

Exit criterion: the agreed calendar window is available offline; native events are editable and external events remain safely read-only.

## P4 - Live transport

- [ ] Add ASGI entry point.
- [ ] Add Django Channels.
- [ ] Add Redis service/configuration/channel layer.
- [ ] Add authenticated family-scoped WebSocket consumer.
- [ ] Emit `sync_available` only after successful DB commit.
- [ ] Add browser WebSocket client that triggers normal delta sync.
- [ ] Add multi-tab sync leader election and takeover.
- [ ] Add fallback tests proving sync still converges without WebSocket.

Exit criterion: online changes appear live, but WebSocket failure never breaks correctness.

## P5 - Robustness and release gate

- [ ] Add Background Sync where supported; keep it optional.
- [ ] Add storage quota diagnostics/low-space messaging.
- [ ] Add conflict center/polish.
- [ ] Add journal pruning job/management command and operational documentation.
- [ ] Add protocol compatibility tests.
- [ ] Add stale-client snapshot recovery tests.
- [ ] Add explicit logout/privacy regression tests.
- [ ] Add upgrade tests with pending outbox mutations.
- [ ] Document Redis/ASGI deployment and rollback.
- [ ] Document operational recovery for journal/sync failures.
- [ ] Run the full offline E2E matrix in CI.

## Release gate

No unrelated roadmap item moves into implementation until every item in the definition of done in `docs/offline-first-architecture.md` is satisfied or explicitly waived in a documented architecture/product decision.
