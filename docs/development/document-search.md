# Document search contract

Document search is a derived read model on top of the canonical `documents` domain. It must never become a second document truth or a second permission system.

## Authorization order

Every request follows this order:

1. `ActiveTenantAccess` / active family membership.
2. `visible_documents(...)` from `documents.access`.
3. Optional document filters.
4. Join the derived `DocumentSearchIndex`.
5. PostgreSQL full-text query/ranking.
6. Build a snippet only from a document that survived the ACL query.

The search index itself is not an authorization source. Direct access to `DocumentSearchIndex` is not exposed through the API.

## Indexed material

`DocumentSearchIndex` is disposable and contains:

- document title,
- correspondent,
- document kind,
- normalized text from the latest `review`/`ready` `DocumentProcessingRun`,
- a narrow allowlist of structured extracted fields such as reference, invoice, contract, customer, policy, claim, order and tracking numbers plus merchant/provider/issuer/recipient/subject.

The row stores the processing-run id used to create the index. A successfully finished processing run deterministically rebuilds the row. Metadata changes to title, correspondent or kind also rebuild it.

The search configuration is PostgreSQL `simple` so mixed German/English identifiers and reference numbers are not forced through one language-specific stemmer.

## API

`GET /api/documents/search/?family=<uuid>`

Optional parameters:

- `q` — PostgreSQL web-style full-text query (max 500 characters),
- `kind`,
- `person` — membership association through ownership or explicit document access,
- `visibility=private|family|selected|shared`,
- `date_from=YYYY-MM-DD`,
- `date_to=YYYY-MM-DD`,
- `correspondent`,
- `pinned=true|false`,
- `limit=1..100`.

A `person` id must belong to the requested active family. Foreign family/person ids fail closed with the same not-found behavior as the canonical document API.

Results are compact and contain only document metadata already visible to the caller, the existing protected `file_url`, and a plain-text snippet. The server does not return HTML highlights.

## Migration and rollback

Migration `documents.0004_document_search_index` is additive. It backfills only derived search rows from canonical document metadata and already stored processing data, then creates a GIN index over the `SearchVectorField`.

Rolling the migration back drops only `DocumentSearchIndex` and its GIN index. `Document`, canonical files, ACLs, processing runs and extracted fields remain unchanged.

Because the search material is derived, it can be rebuilt from canonical data after restore or repair without changing document semantics.

## Privacy regression rules

Tests must keep these invariants green:

- private OCR text never produces a hit/snippet for another member,
- selected documents are visible only to explicitly authorized members,
- cross-family requests and foreign membership filters fail closed,
- filters are applied only to the already-authorized document queryset,
- finishing a new processing run replaces the searchable OCR/reference material deterministically.
