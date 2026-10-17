# Shopping reference datasets

Status: #785 Slice A (registry) + Slice B (staging/validation/preview) + Slice C (activation/rollback).

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

The registry key is `(dataset_id, version)`. Replaying the same version and content is idempotent. Reusing the same semantic version for different content is rejected as an immutable-version conflict.

The normalized record carries:

- `schema_version`, `dataset_id`, `dataset_type`, and `version`;
- a fixed `source_adapter` plus source URL/revision **metadata**;
- locale/country/region scope;
- licence, attribution, normalized redistribution policy, and content checksum;
- coverage, quality, dependencies, and the original manifest;
- bounded package size, deterministic record count, validation result/error;
- lifecycle timestamps, explicit state, and monotonic activation `state_revision`.

`redistribution` is normalized to `adopt`, `adapt`, `defer`, or `deny`. Verbose source-specific rights notes stay in `manifest`. `defer`/`deny` packages may be inspected in preview but are never returned by the runtime-active registry helper and are rejected again by the activation service.

## Canonical package schema v1

A package is a ZIP containing root `manifest.json` plus only declared `.csv`, `.json`, `.jsonl`, or `.txt` payloads. The manifest contains:

- `schema_version: 1`;
- stable lowercase `dataset_id`, canonical `dataset_type`, immutable `version`;
- optional HTTPS `source_url` metadata and `source_revision`;
- locale/country/region scope;
- `licence`, `attribution`, `redistribution`;
- `checksum` as `sha256:<hex>` over the sorted payload path + payload-digest set (excluding `manifest.json`, avoiding self-hashing);
- `coverage`, `quality`, `dependencies`, and a required public-data `privacy` declaration;
- `files[]` with exact path, SHA-256 and deterministic record count.

Each declared file must exist, every package payload must be declared, each file digest must match, the aggregate content checksum must match, and calculated record counts must match. CSV counts exclude the header; JSON lists and common `entries/items/products/records` arrays count their members; JSONL/TXT count non-empty records/lines.

## Bounded staging and security

Slice B exposes only an internal staging service. It performs no network access. The only accepted source identifiers are fixed adapters (`repository_fixture`, `operator_upload`); the later operator layer is responsible for authenticating/authorising uploads. A `source_url` in a manifest is metadata and is never fetched by this service.

ZIPs are inspected in memory and never extracted to disk. Validation rejects before content use when it sees:

- absolute paths, `..`, backslashes, duplicate paths, symlinks, or encrypted entries;
- unsupported file types;
- excessive package/file/uncompressed sizes, file counts, or suspicious compression ratios;
- malformed/non-UTF-8 manifest/data;
- unsupported schema versions.

Structural failures before a trustworthy package identity exists create no DB row. Once identity is trustworthy, payload checksum/count/dependency failures persist a `failed` registry row so operators can inspect the technical error without storing household content.

## Dependencies and rights

Dependencies are explicit `(dataset_id, version)` references. Staging requires an already validated preview/active dependency; activation rechecks that every dependency is **currently active and rights-safe**. A dependency changing after preview therefore blocks activation instead of silently changing package meaning.

`adopt` and `adapt` require reviewed licence metadata; `adapt` additionally requires attribution. `defer` and `deny` may reach preview with `runtime_eligible=false` and a blocker, but cannot appear through `active_reference_datasets()` and cannot be activated.

## Atomic activation, lease and revision

Slice C serialises mutations by semantic `dataset_id` using a short technical lease. Leases contain only dataset ID, technical worker owner, opaque UUID token and expiry; there is no user/family relation or free-text field. The same worker renews the same live token, a competing worker receives `lease_busy`, and an expired lease can be taken over with a rotated token.

Activation/disable/rollback additionally use `expected_revision` against `state_revision`. A stale caller receives a revision conflict and changes nothing. State transitions and history writes run inside one database transaction.

Activation rules:

- only validated, rights-safe `preview` or previously `disabled` packages may activate;
- dependencies are rechecked as active at commit time;
- the previous active version is disabled before the candidate becomes active;
- a conditional DB uniqueness constraint guarantees at most one `active` version for each `dataset_id`, even outside the service;
- retrying activation of the already active candidate is idempotent and does not append another history event.

Disable is non-destructive: it only changes reference-package state and writes a technical event. It does not delete package metadata, activation history, ShoppingItems, ShoppingLists, sessions, learned order, or household corrections.

Rollback uses append-only transition history to restore the package version that preceded the current transition. The current version becomes `disabled`, the previous validated version becomes `active`, and a rollback event records only technical dataset/version/revision information.

## Technical activation history

`ReferenceDatasetActivationEvent` records `dataset_id`, action, from/to version, resulting revision and optional machine-readable `reason_code`. It has no User/Family foreign key and deliberately has no arbitrary free-text reason. This keeps operational history useful without opening a place for household content.

## States

The lifecycle is explicit:

`staged -> validating -> preview -> activating -> active`

with `failed`, `stale`, `disabled`, and `rollback` as explicit non-happy-path states. Activation and rollback transitions are transactional; a failure rolls the entire state/history change back.

## Privacy and ownership

Public package metadata must not contain family IDs, user IDs, private item names, shopping lists, household routes, corrections, or household observations. The database model has no household/user relationships by construction. Slice B rejects manifests that declare private household/user/family/correction/observation content before registration.

Validation/activation telemetry consists only of technical dataset IDs, versions, checksums, file/record counts, state, revision, adapter, lease identifiers and error/reason codes. It contains no credentials or household content.

## Migrations

- `0246_shopping_reference_dataset` creates the independent registry.
- `0247_shopping_reference_validation_metadata` adds staging/validation metadata.
- `0248_shopping_reference_activation` adds revision, one-active-version constraint, technical lease, and activation history.

All are additive with respect to existing Shopping data. Runtime package disable/uninstall must not delete household data; historical shopping/session snapshots remain independent from this registry.

## Intentionally deferred

Slices A-C provide no free-URL fetch, archive extraction to disk, consumer lookup API, operator UI, or automatic update scheduler. Remaining #785 slices implement:

1. bounded read APIs for opt-in consumers;
2. operator GuidedFlow and operational documentation.
