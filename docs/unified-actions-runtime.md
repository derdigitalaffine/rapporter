# Unified Actions runtime rollout

Related: #594, ADR-0002, action-schedule-v1.

## Runtime contracts

Legacy Task and Routine rows remain authoritative in this additive rollout.
`Action` mirrors stable legacy references; configured actions gain versioned schedules,
icons and accent tokens. Existing IDs, URLs, Task workflow invariants, RoutineLog,
Task completion timestamps and Task-based automation remain compatible.

`POST /api/actions/execute/` accepts a typed `action_id`, UUID `request_id`,
`operation` (`complete`, `reopen`, `undo`), optional `duration_minutes` (0–10080),
and a source from ui/quick_capture/widget/automation/import. Undo requires a
completion ID. Receipt rows survive undo, so replaying the original completion
cannot execute it again. The authenticated user is the actor; assignment is separate.
For task workflows the lock order is list → legacy object → Action.

`PATCH /api/actions/completions/<id>/duration/` lets the actor supply/correct duration.
`ActionCompletion` exposes occurred_at, actor, duration, source, legacy RoutineLog
reference and undone_at. #590 should exclude undone events, retain unknown actors
for historical Task imports and never infer actor from assignee. Notes/content are
not required by scheduling or statistics. No person performance score is produced.

`GET/PATCH /api/actions/<task|routine>/<legacy UUID>/` manages schedule, icon,
accent and explicit adaptive proposal feedback. `schedule_text` uses a bounded,
server-owned DE/EN grammar. Unsupported phrases return validation errors and stay
editable in the visual scheduler. Static rules never change from observations.
Learning uses robust circular local-time estimates and cadence; adaptive proposals
require six weekday samples, median deviation at least 60 minutes and median
spread no more than 30 minutes. Rejecting an identical proposal suppresses it.
DST gaps shift forward; ambiguous clock times use the first occurrence explicitly.
Day-only predictions include a day window and `day_only`, not a midnight deadline.

`GET/POST /api/actions/capture/?family=<UUID>` suggests visible existing actions,
requires explicit create-new or existing-action selection, and records completion.
Create+complete is transactional and retry-safe. The original title is retained.

`GET/PATCH /api/actions/settings/?family=<UUID>` separates personal capture/calendar
preferences from owner/adult family adaptive/calendar/history settings. Calendar
planning defaults off, needs family and personal opt-in, and only consumes busy
start/end values. Exact static times remain authoritative. Learning retention is
an observation horizon; it does not delete legacy history or completion events.

Context creation/linking (`actions/from-context`) reuses the canonical Context
Registry and source ACLs. Task/Routine `action.context` links reference Notes,
Documents, Shopping Lists, Decisions, Calendar Events, Trips and Birthday contexts.
Document visibility/management stay owned by Documents. Failed creation/linking
rolls back without leaving an orphan Task/Routine. An explicit decision-round command
clones a linked canonical Decision definition into a new canonical Decision with
new options and no votes, preserving existing context-bound ACLs.

Waste commands address the existing waste FamilyEvent, recording at most one active
completion per event occurrence. Ordinary calendar cards are not made executable.
The Today waste widget uses one batched status query and an explicit compact button
with undo and accessible labels.

## Migration / operations

1. Apply the additive migration normally (`python manage.py migrate`).
2. Run `python manage.py reconcile_actions` to backfill legacy Tasks and RoutineLogs.
3. Run it again: no duplicate Action or RoutineLog-backed completion rows appear.
4. Run `python manage.py reconcile_actions --check` for a read-only shadow parity
   report (`actions-shadow-v1 checked=… drift=…`). Zero drift is the rollout target.
5. Keep the legacy-authoritative mirror phase while collecting parity evidence.
6. Action-primary, endpoint retirement and table removal require the stability gates
   from unified-actions-migration.md. This change performs no destructive cutover.

Rollback deploys the previous application version **while retaining the additive
tables**. Legacy rows/logs remain readable; stored actor/duration/settings/receipts
are retained for re-upgrade. Do not reverse the additive schema as an app rollback.
No timer, private-content analysis, automatic vote/decision adoption or autonomous
schedule rewrite is introduced.

## Validation

Tests cover Task/routine/event retry and undo, attribution/duration, hidden/foreign/
suspended denial, workflow terminal/reopen parity, repeated repair, explicit capture,
private-note denial without orphans, schedule modes, weekday windows/exclusions,
long monthly nth-weekday recurrence, DST gap/fold, sparse confidence, robust outliers,
proposal suppression, canonical vote-free rounds and manager/personal settings.
PostgreSQL migration and full application/browser compatibility are CI gates.

## Domain-event adapters

`ActionDomainEvent` is an additive, deduplicated adapter stream of
`action.created`, `action.completed`, `action.reopened`, `action.assigned`,
`action.schedule_changed` and `action.occurrence_due`. It carries references and
actor only; completion facts remain in ActionCompletion. The existing integration
scheduler emits due events; it does not introduce a second worker. Task-completed
legacy automation stays authoritative during the mirror phase. Configured routine
reminders consume the same prediction contract as Today.
