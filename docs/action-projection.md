# Task/Routine Action Projection

Issue #215 introduces one **read-only projection** across the existing `Task` and `Routine` domains. It does not create a third source of truth and does not migrate or merge either model.

## Endpoint

`GET /api/actions/?family=<uuid>&scope=today`

The caller must be an authenticated member of the active family. The family is explicit; inaccessible or suspended tenants are never projected.

The response is paginated and includes `ranking_version` (`actions-v1`). Every item has a typed opaque ID (`task:<uuid>` or `routine:<uuid>`), its canonical kind, display state, due/next-due information, context, repeat metadata, a deep link, and explicit actions that delegate to the existing Task or Routine endpoints.

## Filters

- `scope=today` — overdue/due work, active/waiting task workflow items, and items completed today.
- `scope=upcoming` — future dated open items.
- `scope=all` — current tasks plus all routines, including paused routines.
- `scope=mine` — incomplete tasks explicitly assigned to the current user.
- `scope=tasks` / `scope=routines` — type aliases over the `all` scope.
- `scope=completed` / `scope=recent` — activity from the last 30 days.
- `kind=tasks|routines|all` — optional type restriction.
- `list=<uuid>` — task-list context; routines are intentionally excluded.
- `workflow=<uuid>` — task-workflow context; routines are intentionally excluded.

## State and ranking

Projection never changes canonical due dates, workflow state, routine history, or completion state. Ranking is deterministic and display-only. `actions-v1` orders, in broad buckets:

1. overdue work;
2. tasks explicitly due today;
3. active/waiting task workflow work;
4. routines currently due;
5. high-priority or personally assigned tasks;
6. normal work;
7. completed-today/paused items.

Stable tie-breakers use due/next-due timestamp, priority, personal assignment, kind, title and typed ID. The response includes each item's ranking bucket and reasons so ordering is explainable.

Family timezone, not browser timezone, defines `today`. This includes DST transitions.

## Routine performance

Routine prediction reuses the existing canonical `routine_prediction()` service. The projection prefetches at most the latest 64 logs per routine before calling it, which bounds feed work while retaining enough history for the current cadence estimator. Reminder snooze state is prefetched only for the requesting membership.

The feed uses select/prefetch access for task list, assignee, workflow, bounded routine logs and reminder state; it must not perform per-item queries.

## Mutations

There is deliberately no polymorphic `POST /api/actions/<id>/done` endpoint. `primary_action` and `allowed_actions` point to the existing domain endpoints:

- Task complete/reopen → `/api/tasks/<uuid>/toggle/`
- Task workflow move → `/api/tasks/<uuid>/move/`
- Routine completion log → `/api/routines/<uuid>/done/`
- Routine reminder snooze → `/api/routines/<uuid>/snooze/`
- Task/Routine edit/reactivation → existing resource endpoint

This preserves Task workflow/status-history semantics and Routine log/target/reminder semantics.

## Compatibility and rollback

The feature is additive: existing Task and Routine endpoints, deep links, models and histories stay unchanged. There is no migration. Rollback is therefore removal of the `actions/` route and projection files; canonical data is unaffected.
