# Shopping reference datasets

Status: Slice A of #785 — registry contract only.

## Boundary

`ReferenceDataset` stores metadata for optional **public reference packages**. It is global and deliberately has no `Family`, `User`, `ShoppingList`, `ShoppingItem`, household-memory, or observation relationship. Shopping remains fully functional when the registry is empty.

A package is advisory input for existing shopping cores. It never becomes the source of truth for a shopping item, a family's corrections, learned store order, or historical checkout/session data.

## Canonical dataset types

| Runtime type | Research/evidence input |
| --- | --- |
| `store_reference` | chain/store reference packages such as #786 / PR #793 |
| `lexicon` | conservative term/synonym/category mappings such as #787 / PR #794 |
| `gtin_product` | validated GTIN/product mappings such as #788 / PR #795 |
| `store_layout_evidence` | branch-specific layout evidence such as #789 / PR #790 |

Research `data_kind` values remain in the stored original `manifest`; runtime consumers use the stable canonical type above.

## Versioned manifest registry

The registry key is `(dataset_id, version)`. Registering the same package version twice is rejected, while multiple versions of one semantic dataset may coexist for later validation, activation, and rollback.

The normalized record carries:

- `schema_version`, `dataset_id`, `dataset_type`, and `version`;
- source URL/revision metadata only — Slice A does not fetch arbitrary URLs;
- locale/country/region scope;
- licence, attribution, normalized redistribution policy, and checksum;
- coverage, quality, dependencies, and the original manifest;
- lifecycle timestamps and explicit state.

`redistribution` is normalized to `adopt`, `adapt`, `defer`, or `deny`. Verbose source-specific rights notes stay in `manifest`. In later slices, `defer`/`deny` must block activation unless an explicitly reviewed policy says otherwise; merely storing a record is never activation.

## States

The schema reserves the explicit lifecycle required by #785:

`staged -> validating -> preview -> activating -> active`

with `failed`, `stale`, `disabled`, and `rollback` as explicit non-happy-path states. Slice A does not implement transitions or an active-version uniqueness rule; those belong to the transactional activation/rollback slice.

## Privacy and ownership

Public package metadata must not contain family IDs, user IDs, private item names, shopping lists, household routes, or household corrections. The database model has no household/user relationships by construction. Validation of uploaded/source manifest content is added in Slice B before any package can reach preview/activation.

Telemetry for future import jobs may contain technical dataset IDs, versions, checksums, counts, state, timing, and error classes only — never private household content or credentials.

## Migration and rollback

Migration `0246_shopping_reference_dataset` is expand-only: it creates an independent registry table and does not rewrite existing shopping data. Runtime package disable/uninstall is not represented by deleting household data. Historical shopping/session snapshots remain independent from this registry.

## Intentionally deferred

Slice A provides no source adapter, free-URL fetch, archive extraction, package activation, consumer lookup API, operator UI, worker, or automatic update. Subsequent #785 slices implement, in order:

1. staging/validation/preview with fixed adapters or authorised uploads and resource/security limits;
2. atomic activation/disable/rollback;
3. bounded read APIs for opt-in consumers;
4. operator GuidedFlow and operational documentation.
