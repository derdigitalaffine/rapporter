# FamilyOS UX Philosophy

This document is the product-wide interaction contract for FamilyOS. New and existing features must follow it unless an issue explicitly documents a reviewed exception.

## 1. One app, not mini-apps

FamilyOS domains may have distinct data models, but users should experience one coherent product. Tasks, calendar, shopping, expenses, documents, cards/tickets and optional modules reuse shared navigation, create, sheet, permission, notification and context-link patterns.

A module orchestrates context; it must not duplicate a canonical domain simply to get its own UI.

## 2. Fixed primary information architecture

Primary navigation remains:

- Heute
- Aufgaben
- Einkauf
- Kalender
- Mehr

Optional modules do not add permanent primary tabs by default. They appear under `Mehr`, via context on `Heute`, through a single `Hinzufügen` entry, or through deep links when relevant.

## 3. Today is relevance, not inventory

`Heute` shows what is currently useful, actionable or time-relevant. Configuration areas and static feature catalogs do not get widgets merely for completeness.

A widget should prefer one immediately useful action over decorative metrics. If nothing is relevant, it may stay hidden or render a calm empty state according to the widget contract.

## 4. One tap to the working state

For frequent, unambiguous actions, one tap should enter the actual working state rather than a module landing page.

Examples:

- a loyalty card on Today opens its scannable code directly;
- a relevant ticket opens its entry view directly;
- a task quick action opens task capture;
- a shopping quick action opens item capture;
- a contextual FAB opens the matching create flow directly.

One-tap does not mean unsafe invisible mutation. Destructive, financial, privacy-sensitive or ambiguous changes still require suitable confirmation or undo.

## 5. Progressive disclosure

The default surface contains only the information needed for the common case. Advanced properties remain available behind `Mehr`, details or an advanced mode.

Do not put ten equally weighted actions on a screen because ten capabilities exist.

## 6. Maximum one root create entry per optional module

An optional module may contribute at most one root item to global `Hinzufügen`. Detailed actions appear only after the user chooses the module and only when relevant to the current lifecycle/context.

Canonical FamilyOS objects remain canonical: a module-created task is still a Task; a module-created event is still a Calendar Event; a module expense is still an Expense.

## 7. Consistent interaction primitives

Reuse the same primitives for:

- create flows
- bottom sheets/dialogs
- back/escape/history
- deep links
- cards/list rows
- primary/secondary/tertiary/destructive actions
- file upload
- sharing
- permissions and read-only states
- notifications

Do not invent a feature-specific navigation or modal system without a reviewed reason.

## 8. Preserve functionality while simplifying

UX consolidation must not silently delete features. Rare actions may move to `Mehr`, detail or context menus, but remain discoverable and tested.

Historical completed issues remain historical; follow-up work should link to them rather than rewriting their original delivery scope.

## 9. Mobile-first, adaptive everywhere

Primary mobile target: 390×844.

Requirements:

- no horizontal page overflow;
- primary touch targets 44px+;
- no drag-only, swipe-only or long-press-only core action;
- status is never communicated by color alone;
- keyboard and screen-reader operation on desktop;
- 200% zoom without loss of core function;
- phone landscape must remain a deliberate compact layout;
- tablet/desktop use additional space intentionally rather than stretching phone UI.

## 10. Recognition over recall

Show useful known choices and context instead of making users remember hidden structure. Keep labels, iconography and action placement stable enough to support muscle memory.

Do not reorder primary actions unpredictably based on usage history.

## 11. Context beats duplication

Use Context Links for relationships between domains where possible. A Trip, Child, Pet or School context should link to the same task, note, document, event, shopping item or expense shown elsewhere.

## 12. Permission-aware before interaction

The UI should not advertise an action that will predictably fail with 403. Available actions derive from capabilities/permissions, while the server remains authoritative.

## 13. Offline and temporary access are explicit states

When a feature supports offline use, the offline copy must obey the same effective access rules and be removed after access is revoked on next sync.

Temporary shares must have explicit expiry/revocation semantics and must not silently grant broader family access.

## 14. Smart means assistive

Smart features may sort, prefill, suggest, extract and explain. They do not autonomously share, purchase, diagnose, settle money or create sensitive records without user review where correctness or consent matters.

## 15. Product copy

Use short, concrete labels that describe the user's goal. Prefer labels such as `Karten & Tickets`, `Ausgaben & Budgets`, `Reisekosten`, `Abrechnen`, `Eingelöst` and `Hinzufügen` over internal architecture terms.

## Pull-request checklist

For any user-facing change, verify:

- Does it reuse a canonical domain rather than duplicate one?
- Is the frequent path as short as possible?
- Are advanced actions progressively disclosed?
- Does it preserve existing functionality?
- Does it follow the fixed primary navigation?
- Does it reuse shared create/sheet/back/deep-link patterns?
- Are permissions anticipated in UI and enforced on the server?
- Is 390×844 usable with 44px+ primary targets and no overflow?
- Are keyboard, screen-reader and 200% zoom supported where applicable?
- Is user documentation updated or explicitly tracked?
