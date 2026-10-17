# Shopping reference datasets

Status: #785 Slice A (registry) + Slice B (staging/validation/preview).

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
- lifecycle timestamps and explicit state.

`redistribution` is normalized to `adopt`, `adapt`, `defer`, or `deny`. Verbose source-specific rights notes stay in `manifest`. `defer`/`deny` packages may be inspected in preview but are never returned by the runtime-active registry helper, even if a state is corrupted to `active`. Slice C additionally enforces this at activation time.

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

Dependencies are explicit `(dataset_id, version)` references and must resolve to already validated `preview` or rights-safe `active` packages. Missing dependencies fail validation without changing any previously active package.

`adopt` and `adapt` require reviewed licence metadata; `adapt` additionally requires attribution. `defer` and `deny` may reach preview with `runtime_eligible=false` and a blocker, but cannot appear through `active_reference_datasets()`.

## States

The lifecycle is explicit:

`staged -> validating -> preview -> activating -> active`

with `failed`, `stale`, `disabled`, and `rollback` as explicit non-happy-path states. Slice B stops at `preview`/`failed`. Transactional activation, one-active-version semantics, worker lease and rollback belong to Slice C.

## Privacy and ownership

Public package metadata must not contain family IDs, user IDs, private item names, shopping lists, household routes, corrections, or household observations. The database model has no household/user relationships by construction. Slice B rejects manifests that declare private household/user/family/correction/observation content before registration.

Validation telemetry consists only of technical dataset IDs, versions, checksums, file/record counts, state, adapter and error codes/messages. It contains no credentials or household content.

## Migration and rollback

Migration `0246_shopping_reference_dataset` creates the independent registry. Migration `0247_shopping_reference_validation_metadata` only adds staging/validation metadata. Neither rewrites existing Shopping data. Runtime package disable/uninstall must not delete household data; historical shopping/session snapshots remain independent from this registry.

## Intentionally deferred

Slices A+B provide no free-URL fetch, archive extraction to disk, activation/rollback, consumer lookup API, operator UI, worker, or automatic update. Remaining #785 slices implement:

1. atomic activation/disable/rollback plus worker lease/resume;
2. bounded read APIs for opt-in consumers;
3. operator GuidedFlow and operational documentation.
