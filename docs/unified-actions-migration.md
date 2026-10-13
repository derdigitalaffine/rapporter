# Unified Actions migration and compatibility gates

Related: #594, ADR-0002, `docs/action-projection.md`, `docs/unified-actions-schedule-v1.md`.

This document turns the Unified Actions direction into a migration contract. It is intentionally stricter than a feature checklist: every later schema or API PR must state which row(s) of this matrix it changes and how rollback remains possible.

## Current sources of truth

| Concern | Current canonical source | Compatibility requirement during migration |
| --- | --- | --- |
| Task identity/content | `Task` | Existing UUIDs, URLs and API mutations continue to resolve. |
| Task completion | `Task.completed_at` + workflow/status history | Completion state remains consistent with any new occurrence record. |
| Task workflow | existing Task workflow models/events | Action migration must not bypass workflow invariants. |
| Task recurrence | `Task.recurrence` legacy field/semantics | Translate only lossless patterns; ambiguous values stay legacy-backed. |
| Routine identity/config | `Routine` | Existing UUIDs, URLs, reminder settings and edit flows continue to resolve. |
| Routine execution history | `RoutineLog` | History is immutable/lossless and maps idempotently to Action occurrences. |
| Routine prediction | current routine prediction service | Remains fallback until prediction-v2 parity is demonstrated. |
| To-do read model | `actions-v1` projection | Existing typed IDs and ranking semantics stay stable unless explicitly versioned. |
| Smart focus | `todo-focus-v1` + TodoPreference/TodoActionPreference | Preferences must remain attached to the same logical work item after identity migration. |
| Context | `ContextLink` and source domain | No Action migration may copy source-domain content or widen ACL. |
| Automation | existing AutomationRule/execution engine | Existing trigger behavior remains compatible; redesign is out of scope for initial Action migration. |

## Migration phases

### Phase 0 — Contract only

No runtime behavior changes.

Required artifacts:
- ADR-0002 accepted;
- `action-schedule-v1` documented;
- this compatibility matrix;
- work slices reference #594.

Rollback: delete/revert documentation only.

### Phase 1 — Expand

Add Action/occurrence/schedule persistence additively.

Rules:
- no legacy column/table removal;
- all new rows carry family/tenant ownership;
- stable legacy mapping is explicit and unique;
- constraints prevent one Action from accidentally mapping to conflicting legacy objects;
- migrations are backwards-compatible with the previous application version where deployment strategy requires it.

Rollback: previous app can ignore new tables/columns.

### Phase 2 — Mirror/backfill

Create Action mirrors for eligible legacy objects.

Backfill requirements:
- idempotent;
- resumable;
- bounded batches;
- deterministic mapping;
- no new user-visible completion/history events merely because a row was migrated;
- ambiguous legacy recurrence is preserved, not guessed.

A reconciliation report must identify:
- missing mirrors;
- duplicate mappings;
- title/assignee/due mismatches for fields expected to be mirrored;
- completion parity mismatches;
- occurrence/RoutineLog count mismatches.

Rollback: mirrored rows may remain unused; legacy stays canonical.

### Phase 3 — Dual write / shadow read

New command service writes Action plus required compatibility state.

Mandatory properties:
- one idempotency key per mutation where retries are possible;
- atomic transaction for same-database paired writes when practical;
- deterministic repair path if a partial side effect can occur;
- shadow read compares Action projection with legacy projection without changing user-visible result;
- parity mismatches are observable without logging sensitive contents.

Rollback: route reads/writes back to legacy service and reconcile any Action-only rows created during the window.

### Phase 4 — Action primary

Action becomes canonical for explicitly migrated common fields/commands.

Legacy APIs become adapters, not independent business logic.

Cutover gate requires:
- shadow parity green for agreed stability window;
- no unresolved high-severity reconciliation mismatches;
- existing API/E2E compatibility tests green;
- automation compatibility tests green;
- deep-link aliases tested;
- rollback rehearsal documented.

Rollback: compatibility adapter can reconstruct/read the legacy shape without losing Action occurrence history.

### Phase 5 — Legacy read-only

Legacy Task/Routine records required for IDs/history remain readable but do not accept independent writes for migrated semantics.

No table/column deletion yet.

### Phase 6 — Contract/removal

Only a separate later PR may remove obsolete persistence/API paths.

Before removal:
- retention/history policy approved;
- all supported clients migrated;
- backups/restores tested;
- no active automation/integration depends on removed endpoint/field;
- at least one stable release window has elapsed after Action-primary cutover;
- a dedicated rollback/restoration plan exists.

## Identity compatibility

### Existing typed action IDs

`task:<uuid>` and `routine:<uuid>` are public compatibility identifiers in `actions-v1`.

They must not disappear when an Action row is introduced.

During migration, the server may internally resolve:

```text
task:<legacy uuid> -> Action <uuid>
routine:<legacy uuid> -> Action <uuid>
```

but clients must not be forced to discover that mapping in the first migration slices.

If a future `action:<uuid>` public ID is introduced:
- old IDs remain aliases for a documented compatibility period;
- saved Smart To-do preferences are migrated/rebound idempotently;
- deep links redirect/resolve server-side rather than relying on client guesses;
- analytics/statistics do not double-count legacy and new IDs as separate work.

## Completion parity

A completion command has exactly one logical execution result.

During coexistence:

### One-off Task

- successful completion creates/identifies one Action occurrence;
- Task `completed_at` represents the current compatibility state;
- retry with same request/idempotency key does not create a second occurrence;
- reopen semantics remain explicit and do not delete historical audit events silently.

### Routine

- each accepted RoutineLog maps to one Action occurrence;
- existing `request_id` uniqueness is preserved;
- backfill uses a deterministic derived idempotency key for historical logs;
- deleting/recreating history to fit the new model is forbidden.

### Actor and assignee

- actual actor comes from authenticated mutation context/event provenance;
- assignee remains planning metadata;
- actor is never synthesized from assignee during migration/backfill unless the historic record truly contains that fact.

## Schedule compatibility

Legacy schedule sources remain valid until individually migrated.

Adapter priority during transition:

1. explicit `action-schedule-v1` if present and activated for that object;
2. lossless adapter from legacy source;
3. existing legacy scheduling/prediction behavior as fallback.

A migration must expose whether a schedule is:
- native-v1;
- losslessly adapted;
- legacy-only/ambiguous.

No UI may show a normalized rule as user-confirmed if it was only guessed from an ambiguous legacy recurrence string.

## Prediction compatibility

`action-prediction-v2` may be introduced in shadow mode first.

Parity is not strict timestamp equality because v2 intentionally learns weekday/time windows. Required comparison instead covers:
- due/upcoming/overdue class regressions;
- next expected occurrence plausibility;
- timezone/day-boundary correctness;
- static-rule authority;
- no silent new exclusions;
- no duplicate reminders/notifications.

Today ranking must not consume v2 until its contract is explicitly versioned and tested.

## Smart preference migration

Todo preferences currently use typed action IDs.

When canonical Action IDs appear:
- pins/hides must follow the same logical Action;
- no preference may cross family boundaries;
- migration must deduplicate aliases referring to the same Action;
- reset semantics remain unchanged;
- user preference history is not used as schedule-learning behavior data.

## Context and ACL gate

Action adoption cannot widen authorization.

For every linked source domain:
- Action visibility does not imply source-object visibility;
- source domain remains permission authority;
- unauthorized context is omitted/redacted server-side;
- search, Today, widgets, notifications and quick capture must use the same effective authorization;
- cross-family guessed IDs receive negative tests.

## Automation compatibility gate

Initial Action work does not redesign AutomationRule.

Until later redesign:
- existing `task_completed` automation behavior must continue for legacy Task-backed Actions;
- an Action completion must not accidentally fire both a legacy and a new equivalent automation twice;
- external-event Actions (for example waste collection) need stable idempotent occurrence identity;
- AutomationExecution/fingerprint behavior remains authoritative for existing rules.

A later automation ADR may introduce generic Action events, but it must define deduplication against legacy triggers before cutover.

## Release checklist for every Unified Actions PR

- [ ] Canonical work issue/claim current.
- [ ] Collision scan against #223, open in-progress issues and PRs repeated.
- [ ] Migration phase named.
- [ ] Legacy source(s) touched named.
- [ ] New source of truth, if any, explicit.
- [ ] Tenant/ACL impact tested or `none` justified.
- [ ] Idempotency impact documented.
- [ ] Timezone/DST impact documented where scheduling is involved.
- [ ] Existing Task API compatibility assessed.
- [ ] Existing Routine API/RoutineLog compatibility assessed.
- [ ] `actions-v1`/`todo-focus-v1` compatibility assessed.
- [ ] Automation compatibility assessed.
- [ ] Backfill/reconcile behavior documented if persistence changes.
- [ ] Rollback path documented.
- [ ] User docs included when visible flow changes.
- [ ] CI fully green before merge.

## First implementation slices after this contract

Recommended order:

1. **Occurrence foundation** — additive execution event + Task/Routine adapters, no UI cutover.
2. **Schedule persistence/parser** — `action-schedule-v1`, adapters and test vectors.
3. **Prediction v2 shadow mode** — weekday/time-window learning with explanations and proposal feedback.
4. **Common command service** — one-click completion/idempotency across projected actions.
5. **Action UI primitives / Quick Capture** — only after server contracts are stable.
6. **Mirror/backfill Action core** — parity tooling before canonical cutover.

This order keeps user-visible innovation moving while postponing irreversible persistence cutover until the new contracts have production evidence.