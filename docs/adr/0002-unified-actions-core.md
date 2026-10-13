# ADR-0002: Unified Actions is the canonical execution domain

- **Status:** Accepted
- **Date:** 2026-10-13
- **Related:** #594, #590, #214, #215, #217, #123, #241

## Context

FamilyOS currently has two canonical execution models:

- `Task` for one-off/due/assigned/workflow work;
- `Routine` + `RoutineLog` for repeatable execution history and learned cadence.

`actions-v1` already projects both into one read-only To-do feed. That was deliberately additive and preserved both sources of truth. The product direction now goes further: users should experience one coherent Action system, including one-click completion, repeat schedules, adaptive timing, assignment, actual actor/duration capture, Context Links, widgets and quick capture.

Keeping Task and Routine as permanent peer canonical models would force every future feature to duplicate scheduling, completion, assignment, statistics, quick-capture and context semantics. Replacing them in one migration would instead create unacceptable risk for existing IDs, deep links, workflow invariants, RoutineLog history and automations.

## Decision

FamilyOS will introduce a **Unified Action Core** as the eventual canonical execution domain and migrate Task/Routine semantics to it incrementally.

The migration is additive and reversible. There is no big-bang table replacement.

### Canonical Action identity

A future `Action` row owns common execution identity and common fields such as:

- family/tenant;
- title and optional description;
- assignee and creator;
- priority and optional estimate;
- icon and semantic accent token;
- source;
- common state required by the execution layer.

Domain-specific capabilities remain normalized extensions. Workflow, schedules, Context Links and rich domain data must not turn `Action` into an unbounded JSON bucket.

During migration, an Action may retain stable nullable legacy references to one existing Task or Routine. Legacy identity is mapping metadata, not a second user-visible copy.

### Completion is an occurrence event

The common write primitive is an idempotent execution occurrence rather than a polymorphic boolean toggle.

An occurrence records at minimum:

- action identity;
- `occurred_at`;
- actual actor when known;
- optional actual duration;
- source (`ui`, `quick_capture`, `widget`, `automation`, `import`, ...);
- idempotency/request key.

For a one-off Task, current `completed_at` remains compatible during migration and is derived/projected consistently from the Action execution state. For repeatable work, multiple occurrences are valid. Existing RoutineLog history must be preserved losslessly and mapped to the common occurrence contract before it can be retired as a separate canonical write path.

**Assignee is never inferred as the actual completion actor.**

### Scheduling is a versioned server contract

Repeat semantics use `action-schedule-v1`, documented separately in `docs/unified-actions-schedule-v1.md`.

The contract supports static, learning and adaptive modes, exact times, flexible windows, weekday-specific overrides/exclusions and long recurrence intervals. Prediction is server-side, deterministic/testable and explainable.

Observed behavior may improve predictions. It may not silently rewrite an explicit static schedule. Adaptive schedules may produce a proposed change only after confidence/stability thresholds are satisfied.

### Context stays linked, not copied

Notes, documents, shopping lists, polls/decisions, calendar events and other domains remain canonical in their own models. Actions reference them through typed Context Links/adapters under the original domain authorization rules.

A recurring shopping workflow therefore does not copy shopping items into Action. A recurring vote does not copy votes into Action.

### `actions-v1` becomes the compatibility boundary

During migration, `actions-v1` remains the stable authorized projection consumed by Today/To-do surfaces.

Changes must be versioned when response semantics materially change. A migration must not silently reinterpret an existing ranking or mutation contract.

The existing typed IDs (`task:<uuid>` / `routine:<uuid>`) stay valid until explicit alias/deep-link migration is complete. New clients must not require consumers to understand which persistence table currently backs a projected action.

### Writes move behind a service layer

New Unified Actions features write through one server-side command/service boundary. Direct creation of new cross-domain behavior through model-specific ad-hoc writes is not allowed.

During migration the service may dual-write to Action and legacy models. Dual writes must be atomic where practical, idempotent, observable and repairable by a deterministic reconciliation job.

## Migration states

Each migrated object is conceptually in one of these states:

1. `legacy_only` — current Task/Routine is canonical; no Action mirror required.
2. `mirrored` — Action mirror exists; legacy remains canonical; parity is measured.
3. `action_primary` — Action is canonical for migrated common fields; compatibility writes/read projections keep legacy behavior working.
4. `legacy_readonly` — legacy row remains for stable IDs/history/API compatibility but is no longer an independent writer.
5. `retired` — legacy compatibility can be removed only after explicit release gates and retention/history verification.

A migration may move forward only when the previous state's parity checks are green. Rollback from `mirrored` or `action_primary` must not delete user history.

## Compatibility invariants

Until an explicit later ADR supersedes them:

- existing Task IDs, URLs and API clients continue to work;
- existing Routine IDs, URLs and RoutineLog history continue to work;
- Task workflow terminal state and `completed_at` remain consistent;
- retries cannot create duplicate completion occurrences;
- family/tenant isolation applies to Action, occurrence, schedule and mapping rows;
- family timezone defines schedule interpretation and learned local-time features;
- DST transitions must be covered by tests;
- automation trigger `task_completed` remains compatible during migration;
- Smart To-do preferences cannot become orphaned when backing identity migrates;
- no destructive schema removal occurs before shadow-read parity and repair checks have been green for the agreed stability window.

## UX implications

The canonical merge is not permission to overload the interface.

- Simple Mode remains the default creation/editing path.
- Extended Mode progressively reveals schedule, learning, workflow, context and automation details.
- Today/List/Widget use common Action interaction primitives.
- Repeatable Actions are one-click executable with undo.
- Assignment is shown only when present, using a compact avatar badge.
- Icon/accent are optional presentation metadata and never the only state signal.
- mobile/touch and desktop are both first-class surfaces.

## Explicit non-goals of this ADR

This ADR does not redesign the full If/Then automation engine. #594 requires clean Action domain events and compatibility adapters only; automation authoring/execution architecture is a separate follow-up.

This ADR also does not make Action the canonical store for notes, documents, shopping contents, poll votes, calendar event contents or other domain-owned data.

## Consequences

### Positive

- one long-term execution model for tasks and routines;
- one completion/event basis for learning and #590 statistics;
- schedules and predictions can be shared by Today, widgets and quick capture;
- migration can ship in small reversible slices;
- domain data and ACLs remain authoritative in their existing domains.

### Trade-offs

- a transition period necessarily contains compatibility mappings and dual-write complexity;
- parity/reconciliation tooling becomes a release requirement rather than optional cleanup;
- legacy APIs cannot be removed quickly;
- Action Core must resist becoming a catch-all model.

These trade-offs are accepted because they reduce permanent product duplication without putting existing family data at risk.

## Guardrail for future changes

Any change that bypasses the Action command boundary for new shared execution semantics, destructively migrates Task/Routine data without parity/rollback, or duplicates domain-owned context data into Action must explicitly supersede this ADR.