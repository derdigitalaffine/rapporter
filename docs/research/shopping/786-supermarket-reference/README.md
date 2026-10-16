# #786 – DE supermarket chain/store reference research package

This directory is an **optional research/data artefact** for #785. It does not change the Shopping runtime, does not seed mandatory data, and does not claim a complete German store inventory.

## Decision

| Source | Decision | What it is good for | Licence / redistribution | Main gap |
| --- | --- | --- | --- | --- |
| Name Suggestion Index (NSI) `brands/shop/supermarket` | **adopt** for chain identity | Canonical names, variants, Wikidata links and location-set semantics | BSD-3-Clause; keep licence notice | Not a branch/store register |
| OpenStreetMap | **adapt** only through a reviewed bounded extract | Public supermarket POIs, addresses and coordinates where mapped | ODbL 1.0; attribution and share-alike obligations must be reviewed for distributed derived databases | Coverage and tagging quality vary; closures/renames lag |
| Wikidata | **adopt** for identity joins | Stable public entity identifiers | CC0 | Not a branch register |
| Official store locators | **defer per provider** | Potential verification of opening/closure/address | Rights differ; redistribution is blocked until explicitly established | Scraping/redistribution may be prohibited |

Pinned NSI revision for this research snapshot: `98458cdd8147784c4e3eaf9ace2a95d3ee9cf3f6`.
The NSI source distinguishes the German Aldi Nord/Aldi Süd location semantics and must not be filtered by a naive `country == DE` check. `chains.csv` therefore keeps project-owned stable `chain_id` values separate from upstream IDs.

## Important identity rules

- `de.netto-salling` and `de.netto-marken-discount` are unrelated chains and **must never be merged by the alias “Netto”**.
- Brand identity and a concrete branch are separate records. A branch candidate needs its own source namespace/id, verification timestamp, confidence and lifecycle status.
- A public POI is evidence for a place only. It is **not** evidence for products, prices, stock, aisle positions or a household's shopping history.
- User/family IDs, shopping lists, routes and manual household corrections are forbidden in this package.

## Coverage report

This snapshot deliberately reports **coverage evidence, not completeness**.

- The bundled chain sample contains 7 identities selected to exercise difficult German variants.
- The bundled real-world sample contains 2 evidence rows and **0 importable branch records**. Both rows are retained only to test the evidence schema because no stable OSM element ID was captured during this bounded research pass.
- The OSM Germany shops inventory page exposes large spelling/tagging variation (for example separate `Rewe`/`REWE`, many `Netto` variants, and `Penny` variants). Those counts are useful as a warning against name-count “coverage” claims, not as a trustworthy nationwide denominator.
- No region or chain gets a percentage coverage number until a pinned regional extract and an independently defined denominator are available.

### Source × region/chain matrix for this snapshot

| Source | Region / chain scope actually evidenced here | Identity evidence | Branch evidence | Importable branches | Coverage % |
| --- | --- | --- | --- | ---: | --- |
| NSI pinned snapshot | Germany split for Aldi Nord/Aldi Süd | pinned upstream IDs for the two Aldi variants; additional project chain IDs remain separate from upstream IDs | none; NSI is not a branch register | 0 | `null` |
| Wikidata IDs retained in `chains.csv` | 7 selected chain identities | identity-join evidence only | none | 0 | n/a |
| OSM/community evidence | Köln REWE example + Merzig-area Netto naming example | not used as canonical brand identity | 2 `evidence_only` rows without stable OSM element IDs | 0 | `null` |
| Official store locators | none imported | none | none; rights not reviewed provider-by-provider | 0 | `null` / `defer` |

This matrix intentionally exposes missing evidence. It is not a substitute for a nationwide source × Bundesland × chain report. A future production candidate should generate, per source × state/region × chain: source revision, candidate count, matched count, duplicate count, tombstone count, unmatched sample size and reviewed false-positive/false-negative sample. Missing denominator means `coverage_percent = null`, never an invented percentage.

## Operating cost / update path

The checked-in research package performs no network access and contains only 7 chain rows plus 2 evidence rows, so it has no meaningful runtime operating cost. That does **not** predict production cost. Before promoting a bounded OSM/regional source, record at least compressed download size, parsed row count, wall-clock import time, peak memory, index size, update/delta size and expected refresh cadence. Official locator cost/limits remain unknown while redistribution/API rights are unresolved and therefore stay `defer`.

No background crawler is part of this package. A production source must be a pinned, bounded extract/update path with explicit operator budgets and must never use Nominatim for bulk harvesting.

## Dedupe and lifecycle contract

Candidate branch key precedence:

1. exact `(source_namespace, source_id)` match;
2. reviewed cross-source link to an existing branch;
3. same normalized address + same unambiguous chain identity;
4. coordinate proximity is **review evidence only**, never an automatic merge rule.

The importer must preserve multiple operators at one address, avoid merging the two Netto chains, and treat rename, move and closure separately. Allowed lifecycle states for a future import are `active`, `renamed`, `moved`, `closed`, `tombstoned`. Stable IDs are never silently reused. A disappeared upstream record becomes a tombstone only after the source revision and evidence are recorded.

Rollback is package-level: disable/unpin this dataset and restore the last validated version. Manual/private store overrides live outside this public package and are never overwritten.

## Reproduction

No crawler is included. The reproducible part of this slice is the pinned source/provenance decision plus deterministic fixtures and checksums.

```bash
python3 docs/research/shopping/786-supermarket-reference/validate.py
```

Expected result:

```text
OK #786: 7 chains, 2 evidence-only real-world samples, 0 importable store records; no completeness claim.
```

A later store extraction must use a bounded/licence-reviewed OSM regional extract or equivalent source. Do **not** bulk-harvest Nominatim, bypass robots/authentication, or mirror proprietary logos.

## Review before promotion to an installable package

1. Pin exact upstream revisions and record fetched/verified timestamps.
2. Resolve source-specific redistribution rights.
3. Produce a bounded Germany/state extract with deterministic counts.
4. Manually review positive and negative samples, including closure/rename/move and duplicate-address cases.
5. Re-run validator/checksums and perform licence review of the resulting derived database.
6. Only then mark branch records importable; until then this directory remains research-only.
