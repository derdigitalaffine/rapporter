# Today Core Daily Experience

This document describes the dependency-safe first delivery slice of #412. It composes Today from existing canonical Task/Action and Calendar projections; it does not introduce a second task, calendar, create, or pin data model.

## Core surfaces

Today now has a non-widget situation line directly below the hero plus two canonical widgets:

- `focus`: at most three explainable urgent/relevant items. Candidates come from the canonical `/api/actions/?family=…&scope=today` projection and authorized warning events. The UI shows the reason an item is present instead of an opaque score.
- `timeline`: a chronological day projection over authorized Calendar events plus Tasks that have a real due timestamp. Date-only/midnight task deadlines are deliberately not invented into a clock time. Warning, weather, and waste facts are not repeated in the timeline when they already have dedicated Today treatment.
- `TodaySituation`: a compact, non-widget summary of open Today actions, the next timed item, and calendar overlaps. Every fact deep-links to its source surface.

The existing Week Compass and unified To-do widget remain canonical Today widgets. To-do mutations refresh the shared Today core data so Focus, Timeline, Situation, and To-do do not drift apart.

## Shared reads and family switching

`frontend/src/todayCoreData.js` owns the Today core read cache. For one family/day it coalesces consumers onto:

1. one Today Action Projection read;
2. one current-day Calendar read.

Stores are keyed by family ID and local civil day. A family switch subscribes to a different store. Forced refreshes use a generation token so a late response from an earlier request cannot overwrite the newer generation.

The Week Compass intentionally keeps its broader week-range Calendar read because it has a different time window. The situation/focus/timeline bundle does not fan out one request per fact.

## Layout migration

The Today layout contract remains version 2. The old IDs are compatibility aliases:

- `priority` -> `focus`
- `next` -> `timeline`

Both frontend and backend normalize those aliases in place. Existing order and visibility are retained, stale v2 clients may still submit the old IDs, and canonical responses/persistence use `focus` and `timeline`. Unknown/disabled widget rows continue to survive without arbitrary domain payloads.

Fresh layouts lead with the dependency-safe core: Focus, Timeline, Week Compass, To-do, and the existing Pinboard entry. Optional module/context widgets stay available through the Widget Library but are not all enabled by default.

## Deliberate boundaries

This slice does **not** close #412.

- Final Today Quick Actions remain blocked on the Smart Quickstart contract in #195 / PR #451. Today will consume that contract instead of creating a parallel ranking or create registry.
- Final compact Pinboard projection remains blocked on the remaining Pinboard sharing/UX/migration work (#220, #221, #222). The existing Pinboard widget is left intact here.
- No new mutation endpoint or micro-endpoint was added for Today.

## Accessibility and responsive behavior

- Situation facts and all widget rows are real links/buttons with source destinations.
- Focus never relies on color alone; every candidate has a textual reason.
- Timeline keeps DOM order equal to chronological visual order.
- Core surfaces collapse to one column on phones and avoid horizontal scrolling at 320/390px.
- Existing Edit Mode keyboard, pointer, touch, live-region, and 44px controls remain the single layout-editing path.

## Registry parity after the approved status/Pinboard updates (#557)

The current product decisions in #510/#539/#541 make Day Status (`situation`) configurable and show about three compact posts in a medium Pinboard widget. Both frontend and backend registries now describe Day Status as compact/medium (compact by default) and Pinboard as compact/medium/wide (medium by default). New layouts start with Day Status, Focus, Timeline, Week, To-do and Pinboard.

This aligns fresh server defaults and size validation with the existing UI. Saved personal layouts keep their existing order, visibility, supported size and revision; registry metadata does not overwrite them. Missing widgets remain additive under the existing compatibility policy. No schema/data migration or domain/permission change is needed. Rollback restores the previous registry metadata; stored choices remain unchanged.

The dedicated `quick-actions` registry widget remains a separate #412 delivery. The existing domain Add buttons already delegate to canonical Create flows, but they do not satisfy that remaining widget acceptance criterion. The initial-delivery boundaries above are historical; current Pinboard interactions use the canonical #386 consumer.
