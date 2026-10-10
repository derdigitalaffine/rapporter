# Document processing architecture

Issues: #180 / #184, roadmap: #223.

## Invariants

- `Document.canonical_file` is the immutable source of truth. Processing failures, retries, OCR, deskew and classification never rewrite or delete it. This preserves byte-identical born-digital/signed PDFs from the document core.
- Processing is local. The pipeline does not call an external OCR, cloud AI or LLM service.
- `DocumentProcessingRun` is the durable execution record. New uploads are queued and handled by `process_documents --loop`; request processes never spawn OCR threads.
- Worker claims are atomic PostgreSQL row leases with a unique `claim_token`. Expired claims can be recovered while attempts remain; stale workers are fenced from publishing. Long-running page/OCR work heartbeats the lease.
- `MAX_ATTEMPTS` bounds normal failures and hard-crash reclaim loops. Exhausted stale leases become terminal failures without touching the canonical file.
- Domain consumers receive processing state/results through the small `documents.consumers` registry. The document core never imports Expense/Pet/School models and domain consumers never execute OCR themselves.

## Extraction flow

1. Upload is canonicalized by the document core and stored privately.
2. Born-digital PDF pages use embedded text first. OCR is only considered for pages without useful embedded text.
3. Images are assessed for resolution, brightness, contrast and sharpness. EXIF orientation, conservative small-angle deskew and autocontrast are applied to a transient OCR copy only.
4. Tesseract runs locally with layout-dependent PSM candidates. Strong output stops early; weak/sparse output tries alternate modes and records every candidate score.
5. Page text, confidence, page number, bounding boxes/evidence and quality data are stored on the processing run / extracted fields.
6. A deterministic classifier chooses `receipt`, `contract`, `official_letter`, `invoice`, `warranty`, `school`, `medical`, `pet`, `identity` or `generic`.
7. The typed extractor registry only emits conservative, labelled suggestions. Every typed suggestion stores page/evidence, confidence, source type and extractor version. Domain actions are never executed by the OCR core.
8. Registered domain consumers may project a finished run into their own review model. They are fenced by the current processing-run reference, so an older finished run cannot overwrite a newer retry.

## Receipt / Expense cutover

New Expense receipt uploads no longer populate `Expense.receipt_content` and do not use a Receipt-specific OCR worker. The flow is:

`Expense draft → private Document → DocumentProcessingRun → Expense receipt parser → ReceiptExtraction review`.

Expense remains the owner of merchant/date/total semantics and review UX. `Expense.receipt_document` points at the canonical document and `ReceiptExtraction.processing_run` points at the current shared run. The receipt consumer maps queued/processing/retry/failure/review state back into the existing Expense API contract and keeps raw OCR evidence out of the serializer.

Legacy `receipt_content` remains temporarily as a dual-read rollback source. `python manage.py migrate_receipt_documents` idempotently creates canonical private documents and queues shared processing without deleting those legacy bytes. A later contract-removal migration may drop the BinaryField only after operators have completed/verified the backfill.

The official Compose topology has no Receipt OCR worker. The legacy `process_receipts` command remains only as a transition for PetDocument OCR plus abandoned Expense-draft cleanup; receipts themselves are exclusively consumed by `document-worker`.

## Searchable content

For privacy and signature safety the canonical PDF is not rewritten merely to add a text layer. `DocumentProcessingRun.normalized_text` is the searchable representation and keeps the original PDF bytes intact. Search/index features should consume this normalized text under the same document ACL instead of exposing raw storage paths.

## Review boundary

OCR/classifier output is a proposal layer. Domain consumers consume normalized text/typed evidence through the shared document core and must not reimplement OCR, queueing, retry or canonical storage. Expense intentionally performs its own receipt-specific candidate scoring after generic extraction because that is business-domain behavior, not OCR infrastructure.

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
- receipt upload without a BinaryField copy;
- Expense projection of shared processing success/failure;
- stale receipt-run fencing, active-run retry idempotency, delete lifecycle and legacy backfill idempotency.

When changing OCR/preprocessing rules, add a fixture that demonstrates the regression. Avoid broad heuristics that turn unlabeled numbers/dates into high-confidence domain fields.
