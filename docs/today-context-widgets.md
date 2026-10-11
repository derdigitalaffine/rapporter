# Today Context Widgets

This is the dependency-safe Context Widgets slice from #398. It adds `tomorrow` and `family-load` without creating a new calendar, task, deadline, or recommendation model.

## Tomorrow

`tomorrow` is opt-in and default-hidden. It reads only canonical sources:

1. `/api/actions/?family=…&scope=upcoming`, filtered client-side to the exact next local civil day in the family timezone;
2. `/api/events/?family=…&start=<tomorrow>&end=<tomorrow>` for the same local civil day.

The shared store is keyed by family + timezone, coalesces all Tomorrow consumers, drops late generations, and clears content when the local day changes. A family or timezone switch therefore cannot render another context’s cached Tomorrow data.

The widget intentionally stays narrow: it shows authorized all-day/calendar entries and due actions for tomorrow. Weather warnings, weather-current facts, and waste events are not duplicated into this first dependency-safe projection. Those can be composed later only from canonical domain contracts.

## Family Load

`family-load` is also opt-in and default-hidden. It performs no additional fetch. It consumes the already shared Today Action/Calendar projection and exposes only concrete bottlenecks:

- actual timed calendar overlaps;
- the count of current high/critical open Today actions.

There is deliberately no family score, productivity score, per-person workload ranking, or inferred sensitive profile. If there is no concrete signal, the widget says so plainly.

## Layout and accessibility

Both widgets are registered in the canonical frontend/backend Today registry and support only `compact` and `medium`. Existing layouts gain hidden rows and remain otherwise unchanged; layout version stays v2.

Every rendered row is a real link to its source surface, status is textual rather than color-only, and the components preserve the existing Today DOM/focus order and one-column phone behavior.

## Deliberate boundaries

This slice does not implement `deadlines`, because #398 requires deadline/document facts to come from the canonical expiry/deadline contract rather than a second Today deadline model. It also does not touch Quick Actions (#195/PR #451) or the remaining Pinboard work (#220–#222).
