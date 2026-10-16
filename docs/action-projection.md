# Task/Routine Action Projection

Issue #215 introduces one **read-only projection** across the existing `Task` and `Routine` domains. It does not create a third source of truth and does not migrate or merge either model. Issue #217 adds an optional, per-membership Smart To-do presentation layer on top; canonical Task/Routine data remains untouched.

## Endpoint

`GET /api/actions/?family=<uuid>&scope=today`

The caller must be an authenticated member of the active family. The family is explicit; inaccessible or suspended tenants are never projected.

The response is paginated and includes `ranking_version` (`actions-v1`). `results` remains the DRF-compatible page and `actions` is an equivalent explicit alias for To-do clients. Every item has a typed opaque ID (`task:<uuid>` or `routine:<uuid>`), its canonical kind, display state, due/next-due information, context, repeat metadata, a deep link, and explicit actions that delegate to the existing Task or Routine endpoints.

For `scope=today`, the response may additionally contain `focus` (at most five entries), `preferences`, and `focus_ranking_version` (`todo-focus-v1`). These are presentation metadata only.

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

## To-do Hub presentation

The main `To-dos` surface is a consumer of this projection, not a second task system. Its default route (`?page=todo`) opens **Upcoming / Anstehend** and requests `scope=upcoming` with the active `family` explicitly. `Today / Heute` remains available as an explicit subview and requests `scope=today`; the remaining list/workflow/routine management links continue to deep-link into their canonical domains.

Projected actions are grouped into content-dependent, collapsible sections such as overdue, due, routines, in-progress/waiting, and up next. Empty sections are omitted. Section summaries expose their item count and use native keyboard/screen-reader-operable disclosure semantics; primary task/routine mutations still come exclusively from each projected row's `primary_action` / `allowed_actions`.

Creating a planned task is intentionally **not** implemented as another form inside the To-do Hub. On the To-do page, the app-wide `+` control opens the canonical Task create flow directly; its adjacent quickstart control keeps the wider Create Registry reachable. The retrospective `Ich habe gerade …` capture remains a separate canonical completion flow and is progressively disclosed below the planned actions. This keeps #191/#195/#400 Create/Form ownership intact while preserving #594 capture semantics.

## Canonical state and ranking (`actions-v1`)

Projection never changes canonical due dates, workflow state, routine history, or completion state. Ranking is deterministic and display-only. `actions-v1` orders, in broad buckets:

1. overdue work;
2. tasks explicitly due today;
3. active/waiting task workflow work;
4. routines currently due;
5. high-priority or personally assigned tasks;
6. normal work;
7. completed-today/paused items.

Stable tie-breakers use due/next-due timestamp, priority, personal assignment, kind, title and typed ID. The response includes each item's ranking bucket and reasons so ordering is explainable. Family timezone, not browser timezone, defines `today`, including DST transitions.

## Smart To-do focus (`todo-focus-v1`)

Smart To-do is deliberately not an AI/ML profile and exposes no numeric productivity or risk score. It consumes only the already authorized `actions-v1` rows plus explicit per-membership controls:

- Smart ranking enabled/disabled;
- Today sort mode (`smart` or `chronological`);
- opaque typed Action IDs explicitly pinned by the user;
- opaque typed Action IDs explicitly hidden from the focus section.

No titles, notes, document/health content, inferred interests or usage telemetry are persisted for Smart To-do. Preferences are family/user scoped through `Membership`.

When enabled, `focus` contains at most five currently actionable items. Explicit pins outrank the canonical action order; otherwise `actions-v1` order is preserved. Hidden entries remain in the normal action feed. Paused/completed entries, routines completed today and currently snoozed routines are not suggested. Explanations use stable semantic reasons such as `overdue`, `due_today`, `routine_due`, `assigned_to_me`, `high_priority`, `workflow_active`, `workflow_waiting`, and `pinned`.

When Smart ranking is disabled, `focus` is empty and the Today feed uses stable chronological/domain ordering. Choosing `chronological` explicitly has the same ordering effect while leaving Smart preferences otherwise enabled.

The client preserves the relative order of surviving focus IDs during ordinary refreshes so keyboard/screen-reader interaction is not disrupted by live reordering. An explicit preference change (pin/hide/reset/sort) is allowed to recompute focus immediately because that is a user-directed decision.

## Preference mutation

`PATCH /api/actions/?family=<uuid>` updates only Smart To-do preference records. Accepted fields are:

- `smart_ranking_enabled: bool`
- `today_sort: "smart" | "chronological"`
- `action_id` together with `pinned: bool` and/or `hidden_from_focus: bool`
- `reset: true`

Action preferences are accepted only for typed IDs currently visible through that member's canonical family projection. Cross-family or invisible objects cannot be used to create preference rows. `reset` restores Smart ranking/default sort and removes explicit per-action overrides.

This PATCH endpoint never completes Tasks, writes RoutineLogs, changes due dates, assignees or priorities, or creates domain objects.

## Routine performance

Routine prediction reuses the existing canonical `routine_prediction()` service. The projection prefetches at most the latest 64 logs per routine before calling it, which bounds feed work while retaining enough history for the current cadence estimator. Reminder snooze state is prefetched only for the requesting membership.

The feed uses select/prefetch access for task list, assignee, workflow, bounded routine logs and reminder state; it must not perform per-item queries.

## Canonical mutations

There is deliberately no polymorphic `POST /api/actions/<id>/done` endpoint. `primary_action` and `allowed_actions` point to the existing domain endpoints:

- Task complete/reopen → `/api/tasks/<uuid>/toggle/`
- Task workflow move → `/api/tasks/<uuid>/move/`
- Routine completion log → `/api/routines/<uuid>/done/`
- Routine reminder snooze → `/api/routines/<uuid>/snooze/`
- Task/Routine edit/reactivation → existing resource endpoint

This preserves Task workflow/status-history semantics and Routine log/target/reminder semantics.

## Compatibility and rollback

The feature remains additive: existing Task and Routine endpoints, deep links, models and histories stay unchanged. Removing Smart To-do requires dropping only its preference tables and the focus decoration/UI; canonical task/routine data is unaffected. The underlying `actions-v1` projection can continue to operate independently.