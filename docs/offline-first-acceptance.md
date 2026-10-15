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

## Final acceptance evidence map (#711)

Scope remains the accepted Shopping, Tasks and native Calendar domains; external
Calendar sources are offline-readable/read-only. No other product module is
implicitly declared fully offline-capable.

| Contract | Executable evidence |
|---|---|
| Offline shell/prefetch/reload/reconnect and explicit logout | `offline-real.spec.js` with PostgreSQL/Django, plus runtime/store suites |
| Shopping/Tasks/Calendar use one durable local path | per-domain Node runtime suites and real domain UI flows |
| Lost reply, stable retry IDs, compaction, conflicts, snapshot retention | `offline-sync-engine.test.mjs`, `test_offline_sync.py` |
| Two clients: disjoint merge, field conflict, exactly-once retry, deletion | final two-context case in `offline-real.spec.js` |
| Journal pruning, reset boundary, receipts and recent-row protection | `test_sync_recovery.py` in PostgreSQL offline-sync CI |
| Pending-work-safe schema upgrade and future-version refusal | `offline-recovery.test.mjs` |
| Storage capability denial and optional worker wake-up | `offline-recovery.test.mjs` |
| Cross-tab sign-out privacy | `offline-shopping-runtime.test.mjs` |
| Live membership, payload restriction and revocation | `test_sync_live.py` |
| Leader/takeover/reconnect/follower refresh and no-WebSocket fallback | `offline-live.test.mjs` |
| Redis/ASGI deployment, retention, recovery and rollback | `offline-first-operations.md` |

The new final matrix must pass scoped CI before #711/#705 are closed. Browser
infrastructure-only failures may be recorded under the owner's explicit Chromium
exception; authorization, convergence, preservation or idempotency failures cannot.
Repository-wide unrelated baseline failures remain with their existing owners.
