# Document processing architecture

Issue: #180, roadmap: #223.

## Invariants

- `Document.canonical_file` is the immutable source of truth. Processing failures, retries, OCR, deskew and classification never rewrite or delete it. This preserves byte-identical born-digital/signed PDFs from the document core.
- Processing is local. The pipeline does not call an external OCR, cloud AI or LLM service.
- `DocumentProcessingRun` is the durable execution record. New uploads are queued and handled by `process_documents --loop`; request processes never spawn OCR threads.
- Worker claims are atomic PostgreSQL row leases with a unique `claim_token`. Expired claims can be recovered while attempts remain; stale workers are fenced from publishing. Long-running page/OCR work heartbeats the lease.
- `MAX_ATTEMPTS` bounds normal failures and hard-crash reclaim loops. Exhausted stale leases become terminal failures without touching the canonical file.

## Extraction flow

1. Upload is canonicalized by the document core and stored privately.
2. Born-digital PDF pages use embedded text first. OCR is only considered for pages without useful embedded text.
3. Images are assessed for resolution, brightness, contrast and sharpness. EXIF orientation, conservative small-angle deskew and autocontrast are applied to a transient OCR copy only.
4. Tesseract runs locally with layout-dependent PSM candidates. Strong output stops early; weak/sparse output tries alternate modes and records every candidate score.
5. Page text, confidence, page number, bounding boxes/evidence and quality data are stored on the processing run / extracted fields.
6. A deterministic classifier chooses `receipt`, `contract`, `official_letter`, `invoice`, `warranty`, `school`, `medical`, `pet`, `identity` or `generic`.
7. The typed extractor registry only emits conservative, labelled suggestions. Every typed suggestion stores page/evidence, confidence, source type and extractor version. Domain actions are never executed by the OCR core.

## Searchable content

For privacy and signature safety the canonical PDF is not rewritten merely to add a text layer. `DocumentProcessingRun.normalized_text` is the searchable representation and keeps the original PDF bytes intact. Search/index features should consume this normalized text under the same document ACL instead of exposing raw storage paths.

## Review boundary

OCR/classifier output is a proposal layer. Domain migrations such as receipt → expense (#184) consume reviewed/typed fields through the shared document core. They must not reimplement OCR, queueing, retry or canonical storage.

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
- image quality metadata and adaptive PSM fallback.

When changing OCR/preprocessing rules, add a fixture that demonstrates the regression. Avoid broad heuristics that turn unlabeled numbers/dates into high-confidence domain fields.
