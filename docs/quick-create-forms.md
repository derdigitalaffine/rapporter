# Quick Create form contract

This document is the field-classification contract for #405 and builds on the shared form foundation from #404. Quick Create changes presentation only: existing domain objects, APIs, permissions, idempotency and offline behavior remain authoritative.

## Classification rules

- **core**: required or near-universal information that belongs in the first view.
- **contextual**: shown in the first view only when the current context cannot provide a safe, unambiguous value.
- **advanced**: remains in the same canonical editor but is revealed through **Weitere Details / More details**. Opening or closing advanced fields must not discard entered values.
- Edit flows may show advanced fields by default. The compact classification primarily governs new-object Quick Create.

## Task

| Class | Fields | Rationale |
| --- | --- | --- |
| core | title | A task needs a concise action name. |
| contextual | due date/time; task list; assignee | Due is common but optional. List and assignee stay compact when an existing page/list context already resolves them. |
| advanced | priority; workflow status; estimate; tags; notes | Useful for planning, but not required to capture the task. |

The existing `/tasks/` API, workflow fields and permission behavior remain unchanged.

## Event

| Class | Fields | Rationale |
| --- | --- | --- |
| core | title; start; end | These define the event on the calendar. |
| contextual | person/member | Relevant when the event belongs to a particular family member; optional otherwise. |
| advanced | location; notes; recurrence | Valuable metadata, but not required for fast capture. |

The existing `/events/` payload and canonical `calendar.event` domain remain unchanged.

## Shopping item

| Class | Fields | Rationale |
| --- | --- | --- |
| core | item name | The only universally necessary value. |
| contextual | quantity; shopping list | Quantity is often useful but optional. The list selector appears only when the active context cannot resolve one safely. |
| advanced | category; aisle; note; favorite | Organization metadata is secondary to capture. |

The existing `/shopping-items/` API and list-context behavior remain unchanged.

## Shopping / task list

| Class | Fields | Rationale |
| --- | --- | --- |
| core | name | Required identity of the list. |
| contextual | store/shop for shopping lists | Helpful at creation time when known, but not universally required. |
| advanced | symbol/icon; task workflow settings | Configuration belongs behind progressive disclosure. |

The existing task-list and shopping-list APIs remain unchanged.

## Expense

| Class | Fields | Rationale |
| --- | --- | --- |
| core | amount | Quick expense capture starts with the amount. |
| contextual | title/merchant; payer/funding source; participants | Keep existing safe defaults and only ask when the current family/context does not resolve them. |
| advanced | date; currency; split details; ledger; budget; receipt workflow and other allocation metadata | These remain in the same canonical `ExpenseEditor`; budget behavior continues to follow #245 and receipt processing keeps its existing contract. |

The existing `/expenses/` API, `client_request_id`, receipt workflow, permission checks and online/offline rules remain unchanged.

## Global Create / CreateFlowHost

`GlobalCreate` and `CreateFlowHost` own no duplicate form fields. They continue to route the canonical action IDs to the same domain editors. Action availability remains owned by #191 and ranking remains owned by #195. Today quick actions from #398 must invoke these same actions instead of introducing widget-specific forms.

## Shared UX and accessibility

All migrated Quick Create surfaces use #404 primitives for field labeling, rows, progressive disclosure, actions and error presentation. New-object flows keep one dominant save action, preserve values after validation errors and after toggling **Weitere Details**, maintain 44px+ primary targets, and remain usable at 320px, 390×844 and 200% zoom without horizontal scrolling. Existing server-side validation and permissions remain the final authority.
