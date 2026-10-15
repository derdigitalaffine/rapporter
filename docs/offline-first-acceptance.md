# Offline-first acceptance gate

The roadmap freeze is lifted only when all required offline-first scenarios for Shopping, Tasks/Todos, and Calendar are implemented, documented, and green in CI.

Required outcomes:

- app shell and prefetched core data load without network
- supported native entities are fully usable offline
- local changes survive reload/restart where browser storage persists
- reconnect sync is automatic and idempotent
- true conflicts preserve both values
- non-overlapping changes merge automatically
- deletes propagate via tombstones
- stale cursors recover through snapshots without losing the local outbox
- explicit logout clears private account-scoped local data
- migrated UI reads from the local store online and offline
- WebSocket failure does not prevent convergence
- the required offline E2E matrix is green

Until this gate is met, unrelated product feature implementation remains paused except for production-critical fixes, security/privacy fixes, required dependency/security maintenance, and work strictly required by this offline program.
