# Offline-first test plan

The offline program is not complete until these scenarios are automated in CI.

## Core scenarios

- App shell loads offline after an authenticated/install cycle.
- Prefetched Shopping, Tasks, and Calendar data is available offline without first opening every screen.
- Offline create/edit/check-or-complete/delete survives page reload.
- Reconnect syncs automatically.
- Replaying the same `mutation_id` never duplicates side effects.
- A lost HTTP response after server commit converges on retry.
- Non-overlapping concurrent field edits auto-merge.
- Overlapping incompatible field edits create a resolvable conflict with both values preserved.
- Delete-vs-edit creates a conflict where required.
- Physical server delete reaches clients through a tombstone.
- A cursor older than journal retention triggers snapshot recovery without losing local outbox entries.
- Explicit logout clears private account-scoped IndexedDB data.
- Expired server auth pauses sync while retaining local offline work.
- IndexedDB schema upgrades preserve pending mutations.
- External calendar events remain offline-readable and read-only.
- A second tab can take over sync leadership if the first closes.
- WebSocket failure does not prevent convergence via startup/online/foreground/manual sync.

## Shopping pilot

- create list offline
- create item offline
- edit item name/quantity/category/note offline as supported
- check/uncheck offline
- delete offline
- repeated edits compact safely
- create then delete before first sync produces no server object
- two users check/edit concurrently

## Tasks

- create/edit/delete offline
- complete/reopen command behavior
- workflow transition command behavior
- recurrence-sensitive behavior remains correct
- assignee/due date/priority/tag changes reconcile correctly

## Calendar

- native event create/edit/delete offline
- calendar window is prefetched
- concurrent native event edits follow field-conflict rules
- external event is visible offline but cannot be mutated

## CI requirements

Tests must run deterministically with browser network toggling and at least two independent client contexts for concurrency cases. The release gate in `docs/offline-first-architecture.md` remains closed while required offline scenarios are failing or unimplemented.
