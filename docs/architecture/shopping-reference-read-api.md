# Shopping reference consumer read API

Status: #785 Slice D. Depends on the registry, validator and activation contracts from Slices A-C.

## Purpose

Active public shopping-reference packages are optional advisory inputs for existing Shopping cores. This slice makes their validated records queryable without shipping bulk datasets in the frontend bundle and without making Shopping depend on a package being installed.

The empty-registry behavior remains valid: consumers receive empty results and continue with their existing local/server logic.

## Materialized runtime records

Validation materializes each declared package record into `ReferenceDatasetRecord` plus normalized `ReferenceDatasetSearchTerm` rows. The original package remains immutable by `(dataset_id, version, checksum/manifest fingerprint)`; materialization is a derived server-side index for that exact version.

Runtime payloads are **typed and allow-listed per canonical dataset type**:

- `store_reference`: stable store/chain identity, public branch/location/source metadata;
- `lexicon`: stable term IDs, labels, aliases/synonyms, category/department mapping and ambiguity/provenance metadata;
- `gtin_product`: validated GTIN/EAN, product label/brand/quantity/category and source provenance;
- `store_layout_evidence`: branch/store/section/category ordering evidence and provenance.

Unknown fields are dropped before persistence. A record with no supported public fields is rejected. This prevents an accidentally included `user_id`, household note, item name or other undeclared field from becoming a public runtime API merely because a package claimed to be public.

Lexicon packages retain the `ABSTAIN` ambiguity requirement. Non-tombstoned GTIN records must pass GTIN-8/12/13/14 check-digit validation before materialization.

## Resource budgets

Materialization is bounded:

- max 100,000 materialized records per package version;
- max 32 KiB JSON payload per materialized record;
- max 64 normalized search terms per record;
- max 500,000 normalized search terms per package version;
- search terms max 200 characters;
- CSV headers must be unique and non-empty;
- all package/archive limits from Slice B still apply before materialization.

The complete record/term budget is checked before the existing derived index is replaced. Search terms are then written in bounded batches rather than accumulated as an unbounded database-write list. Materialization is transactional: a failed new materialization does not leave a half-built record/search index and does not destroy an already valid derived index.

## Search terms and stable identity

Search terms are NFKC-normalized, whitespace-collapsed and case-folded. Primary labels, aliases, stable IDs and supported codes are indexed separately by kind. CSV aliases may use `|` or `;`; JSON aliases may be arrays.

Stable record keys prefer the most specific available identity. In particular, branch/sample/store/layout evidence IDs win over a shared chain ID so multiple branches of the same retailer do not collapse into one runtime record.

Tombstones remain versioned records but do not receive searchable terms and are never returned by consumer queries.

## Consumer API

Authenticated endpoints:

- `GET /api/shopping-reference/active/`
  - bounded summary of runtime-eligible active datasets;
  - includes dataset/version/type/scope, licence/attribution, revision and record count.
- `GET /api/shopping-reference/search/`
  - required: `type`, `q`;
  - optional: `dataset_id`, `locale`, `country`, `exact=0|1`, `limit`, `offset`;
  - prefix search by default, deterministic exact-match-first ordering;
  - `limit` 1..50, `offset` 0..1000, query length 2..120;
  - returns `next_offset` only while another bounded page is available.

The service layer also exposes exact normalized lookup for consumers that already have a stable lookup key; this remains bounded to at most 10 records.

No endpoint exposes staged, preview, failed, stale, disabled, `defer`, `deny`, runtime-ineligible or tombstoned data.

## Response provenance

Every returned record carries its public payload plus source metadata:

- dataset ID and version;
- canonical dataset type;
- locale/country/region;
- licence and attribution;
- active state revision.

Consumers must treat this as advisory reference provenance, not ShoppingItem or household truth.

## Consumer rules

- #783 may use lexicon/GTIN results only to improve suggestions. Unknown/ambiguous items remain creatable and `ABSTAIN` remains valid.
- #782 may use store/layout results only with a concrete compatible store reference and evidence scope. Learned household order and manual corrections win.
- #781 Store/Checkout must work identically when the read API returns no packages or errors.
- No external API call occurs per keypress. Search is against local PostgreSQL materialized rows.
- No full dataset is copied into JavaScript bundles or returned in one response.

## Privacy

`ReferenceDatasetRecord` and `ReferenceDatasetSearchTerm` have no Family/User/ShoppingList/ShoppingItem relationship. Search/activation telemetry uses only technical dataset/version/count/error information. Household observations, private item names, routes and corrections remain in their existing private domains.

## Remaining #785 work

Slice E owns the operator `GuidedFlow`: authenticated package/source selection, rights/attribution review, validate, preview/diff, explicit activate/rollback, operational states and documentation. It must reuse the existing staging/lease/activation services rather than introduce another importer or daemon.
