# Smart Quickstart contract

This is the canonical implementation contract for #195. It layers ranking and user control on top of the existing Create registry from #191; it does not introduce a second registry or a second mutation path.

## Availability before ranking

`availableCreateActions(...)` remains the sole authority for role, capability and module availability. Smart Quickstart receives only those already-authorized actions. A disabled or unauthorized Baby/Pet module can therefore never be restored by history, pins, direct mode or cached ranking data.

The precedence for quick suggestions is:

1. availability / permission / module gates,
2. hidden-from-quickstart preference,
3. pinned and explicit manual order,
4. current page/context match,
5. learned deterministic recency/frequency and optional time pattern,
6. stable `CREATE_ACTIONS` product order.

`Alle Aktionen / All actions` always shows every currently available action in stable product groups. Hiding affects only the compact quickstart.

## Cold start and deterministic ranking

Personalized scoring is inactive until at least five successful create signals exist in the active learning scope. Before that threshold, quickstart uses pins/manual order, current context and stable registry order only.

After the threshold, ranking uses bounded aggregate metadata: count, most recent successful use, per-context counts and optional coarse local time buckets. No ML/LLM dependency is involved and the score is never an authorization decision.

The palette copies the ranked quick list when it opens. It does not live-rerank while a person is navigating it, so keyboard/touch focus cannot jump under the user.

## Privacy and successful-use semantics

The server stores only:

- membership / family relation,
- stable `action_id`,
- successful-use count and last-used timestamp,
- bounded page/context counters,
- bounded coarse time-bucket counters,
- short-lived UUID receipts used for idempotency.

Create payload contents are explicitly outside this contract: no task title, shopping item, note, amount, document name, pregnancy/baby detail, pet-health detail or other domain value is accepted by the usage endpoint.

Usage is emitted by `CreateFlowHost` only after the canonical domain editor reports a successful create. Opening/cancelling an editor is not a positive signal. Creating an intermediate shopping list before the intended shopping item is not counted as the item action. Baby/Pet module root navigation is not recorded as a care/health subaction.

## Preferences and direct mode

Preferences are membership-scoped and exposed under Profile → Quickstart & Add. Users can:

- enable/disable learned ordering and context ranking,
- pin and hide quick suggestions,
- move actions with keyboard-operable buttons,
- choose 2–6 compact quick actions,
- opt into coarse time-pattern ranking,
- choose family-only or cross-family aggregate learning,
- reset learned aggregates,
- explicitly enable direct mode and optionally fix its action.

Direct mode is off by default. With direct mode off, a FAB tap always opens the compact quickstart. With it on, the primary FAB can execute the chosen/top quick action and a separate 44px+ menu control remains available to open the palette.

## Family vs. global learning

Default scope is `family`. `global` aggregates only memberships belonging to the same user in active families. Preferences themselves remain attached to the current membership; only aggregate usage is combined. Reset in global mode clears the same user's aggregate usage/receipts across active family memberships without touching domain objects.

## Offline and idempotency

The client caches the latest ranking payload per family. Successful offline/transient-failure usage signals are queued locally in a bounded queue and replayed sequentially on reconnect. Each signal has a UUID; the server receipt makes replay idempotent. The queue carries metadata only and never reimplements a domain mutation.

## Accessibility and responsive behavior

Quickstart keeps 44px+ controls, a focusable dialog, Escape/Back close behavior, and the existing overlay focus return. At 390px the quick grid uses two columns and collapses to one below 390px; no horizontal scrolling is required. Manual ordering never relies on drag-and-drop. Reduced-motion preferences remain respected by the shared design system.
