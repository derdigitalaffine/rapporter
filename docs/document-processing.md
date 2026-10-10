# Document processing architecture

Issue: #180, roadmap: #223. Receipt consumer migration: #184.

## Invariants

- `Document.canonical_file` is the immutable source of truth. Processing failures, retries, OCR, deskew and classification never rewrite or delete it. This preserves byte-identical born-digital/signed PDFs from the document core.
- Processing is local. The pipeline does not call an external OCR, cloud AI or LLM service.
- `DocumentProcessingRun` is the durable execution record. New uploads are queued and handled by `process_documents --loop`; request processes never spawn OCR threads.
- Worker claims are atomic PostgreSQL row leases with a unique `claim_token`. Expired claims can be recovered while attempts remain; stale workers are fenced from publishing. Long-running page/OCR work heartbeats the lease.
- `MAX_ATTEMPTS` bounds normal failures and hard-crash reclaim loops. Exhausted stale leases become terminal failures without touching the canonical file.
- Generic queue/OCR state commits before domain consumers run. A bug in Expense/Pet/School interpretation can never roll back a successful generic extraction or spend OCR CPU again. Each domain owns a redacted review/fallback state for its own projection errors.

## Extraction flow

1. Upload is canonicalized by the document core and stored privately.
2. Born-digital PDF pages use embedded text first. OCR is only considered for pages without useful embedded text.
3. Images are assessed for resolution, brightness, contrast and sharpness. EXIF orientation, conservative small-angle deskew and autocontrast are applied to a transient OCR copy only.
4. Tesseract runs locally with layout-dependent PSM candidates. Strong output stops early; weak/sparse output tries alternate modes and records every candidate score.
5. Page text, confidence, page number, bounding boxes/evidence and quality data are stored on the processing run / extracted fields.
6. A deterministic classifier chooses `receipt`, `contract`, `official_letter`, `invoice`, `warranty`, `school`, `medical`, `pet`, `identity` or `generic`.
7. The typed extractor registry only emits conservative, labelled suggestions. Every typed suggestion stores page/evidence, confidence, source type and extractor version. Domain actions are never executed by the OCR core.
8. Registered domain consumers project the committed run into their existing review models. Projection is fenced by the domain's current processing-run reference.

## Domain-managed attachments

`Document.library_visible=False` is used for attachments that belong to another canonical product, such as an Expense receipt. They still use the Document ACL, canonical storage, links and processing engine, but are excluded from the generic document library/search/duplicate-discovery path by default. This prevents a single receipt from appearing as a second independent user-facing document.

A domain endpoint may opt into domain-managed documents only after authorizing the canonical domain object. The flag never expands ACL visibility. Expense receipts use `visibility=family` because the Expense itself is family-scoped today; `library_visible=False` is what prevents them from becoming separate generic document entries.

## Receipt consumer (#184)

New Expense receipt flow:

```text
POST /api/expenses/receipt/
→ Document canonicalization/storage
→ hidden family-scoped Document + expense:receipt link
→ DocumentProcessingRun QUEUED
→ process_documents --loop
→ local OCR/classification + generic quality assessment
→ committed DocumentProcessingRun
→ Expense receipt parser (merchant/date/total)
→ existing Expense review UX
```

`expenses` no longer contains generic image normalization, Tesseract calls, quality detection or a receipt worker. It keeps only receipt-domain parsing/scoring. Worker quality warnings are projected from `DocumentProcessingRun.quality_data`; the upload request does not run its own quality pass.

Domain projection is deliberately downstream of generic processing. If the Expense parser itself fails, the successful `DocumentProcessingRun` remains `REVIEW/READY`; the receipt falls back to a redacted manual-review state with normalized text rather than retrying OCR. This preserves the architecture boundary and avoids duplicate CPU work.

Retry is idempotent against the current active Document run: retrying while OCR is already `PROCESSING` reuses that run and preserves the visible `PROCESSING` state instead of moving the UI state machine backwards to `QUEUED`.

### Migration / rollback

The receipt migration follows expand → migrate → cutover → contract:

1. additive `Expense.receipt_document` and `ReceiptExtraction.processing_run` links;
2. new uploads write only Document Core canonical storage;
3. `python manage.py migrate_receipts_to_documents` idempotently backfills legacy `receipt_content` rows, including rows whose MIME metadata is empty because content validation is byte-based;
4. file reads use Document Core first and legacy BinaryField as a temporary fallback;
5. legacy `receipt_content` bytes and their original MIME metadata are intentionally retained during this phase for rollback/audit;
6. removal of the BinaryField is a later contract migration only after backfill and production verification.

The backfill does not silently retry historical REVIEW/READY/FAILED receipts. It only recovers old QUEUED/PROCESSING work onto the durable Document worker; explicit user retry remains explicit.

## Searchable content

For privacy and signature safety the canonical PDF is not rewritten merely to add a text layer. `DocumentProcessingRun.normalized_text` is the searchable representation and keeps the original PDF bytes intact. Search/index features should consume this normalized text under the same document ACL instead of exposing raw storage paths.

## Review boundary

OCR/classifier output is a proposal layer. Domain consumers such as receipt → expense consume committed OCR output through the shared document core but keep their existing domain review semantics. They must not reimplement OCR, quality detection, queueing, retry or canonical storage and must not create domain actions automatically.

## Quality gates

The backend suite covers:

- idempotent queueing and atomic claims;
- hard-crash lease recovery and attempt exhaustion;
- stale-worker fencing and lease heartbeat;
- canonical-file survival on failure;
- born-digital multi-page PDF extraction without unnecessary OCR;
- OCR confidence/bounding-box provenance;
- synthetic classification fixtures for every registered document type;
- labelled typed-field provenance and negative false-positive fixtures;
- image quality metadata and adaptive PSM fallback;
- receipt upload → hidden Document → shared worker → Expense review;
- hidden receipt Documents are inaccessible through generic Document detail/file endpoints;
- receipt failure/retry without a second queue, including retry during active OCR;
- Expense parser failure leaves generic OCR successful and falls back to manual review without reprocessing;
- tenant-scoped receipt files and deletion lifecycle, including deletion during active processing;
- idempotent legacy receipt backfill, missing-MIME backfill, and rollback-byte preservation.

When changing OCR/preprocessing rules, add a fixture that demonstrates the regression. Avoid broad heuristics that turn unlabeled numbers/dates into high-confidence domain fields.
