# Form Foundation

This document is the canonical frontend contract for the shared form primitives introduced by #404 as Slice A of #400.

## Scope

The foundation standardizes layout, semantics, error navigation, progressive disclosure, actions, and entity selection. It does **not** encode domain fields, backend validation, permissions, create-flow ranking, or schema-driven form generation.

The primitives live in `frontend/src/form-primitives.jsx` and consume only the semantic tokens from `frontend/src/design-system.css`.

## Primitives

- `FormShell`: form boundary with an optional visible title and description. Forms stay at a readable maximum width.
- `FormSection`: semantic `fieldset`/`legend` section. Use it when fields belong to one meaningful section.
- `FormField`: visible label, optional help text, required marker, and inline error wiring. It owns the control id and `aria-describedby`/`aria-invalid` linkage.
- `FormRow`: responsive grouping for fields that are semantically coupled. It is always one column on narrow screens and may become two or more columns from 640 px upward.
- `FieldGroup`: bordered semantic `fieldset` for a tightly related set of controls such as radio buttons or switches.
- `ProgressiveFieldGroup`: explicit disclosure for contextual or advanced fields. Closed fields are removed from the tab order; state changes are announced politely.
- `FormActions`: action area that stacks on narrow screens, wraps on larger screens, and preserves 44 px minimum target height.
- `ErrorSummary`: focusable top-level error list. Each entry links to and focuses its invalid field.
- `EntityPicker`: generic search/select/remove interaction for people, lists, tags, locations, and similar entities. Selection is controlled through `selectedIds` and `onChange`; domain loading, ranking, permissions, and persistence remain with the caller.

## Field classes and progressive disclosure

Every domain form should classify fields before migration:

1. **Core** — needed for the common successful submit path. Show directly.
2. **Contextual** — useful only after another choice or in a specific context. Reveal near the controlling field.
3. **Advanced** — valid but uncommon configuration. Put behind `ProgressiveFieldGroup` with a meaningful label and optional summary.

Do not hide required fields or validation errors behind a closed advanced section. When validation makes a hidden field invalid, open the owning section before focusing or linking to that field.

## Accessibility contract

- A placeholder is never the only label.
- Related controls use `fieldset`/`legend` where the relationship matters.
- Native input semantics are preferred over custom widgets.
- Touch targets are at least 44 px high for primary interactive controls.
- DOM order is the reading and tab order; responsive CSS may change columns but must not reorder fields.
- `ErrorSummary` is placed before the first section when submit validation fails. It receives focus and its links move focus to the corresponding field.
- Inline errors stay associated with their field via `aria-describedby` and `aria-invalid`.
- Progressive disclosure is controlled by a real button with `aria-expanded` and `aria-controls`; the visibility change is announced through a polite live region.
- `EntityPicker` uses a native search input plus real buttons for selection/removal instead of inventing a partial combobox implementation. If a future use case needs full autocomplete/listbox behavior, implement the complete WAI-ARIA interaction contract rather than adding isolated roles.

## Responsive contract

Mobile is canonical. At 320 px and 390 px, field rows collapse to one column and action/selection controls must not cause horizontal overflow. Desktop rows are only for semantically paired fields; do not use columns merely to reduce vertical space. Forms should remain usable at 200% browser zoom.

## EntityPicker contract

`EntityPicker` accepts `items`, `selectedIds`, and `onChange`, with optional `getItemId` and `getItemLabel` adapters. `onChange` always receives an array of ids, including single-select mode. The picker filters the supplied items locally; remote search/debouncing belongs to a domain wrapper which supplies a new `items` collection.

Selected entities are shown before search results and can always be removed by a named button. Search results exclude already-selected entities. Empty results have visible text and are announced through the results live region.

## Adoption rules

Migrate domain forms in the follow-up issues from #400 instead of doing opportunistic broad rewrites. A migration may compose these primitives but must keep domain-specific business rules in the domain component. Do not modify `GlobalCreate`/`CreateFlowHost` as part of this foundation slice; that coordination surface belongs to #191 and later #400 work.

For each migrated form, validate at least the common submit path, server/client errors, keyboard traversal, 320/390 px layouts, and 200% zoom. Add focused Playwright coverage in the domain slice where the primitive is exercised through a real user flow.
