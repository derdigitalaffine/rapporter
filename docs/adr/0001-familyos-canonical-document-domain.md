# ADR-0001: FamilyOS owns the canonical document domain

- **Status:** Accepted
- **Date:** 2026-10-10
- **Related:** #178, #179, #180, #184, #185

## Context

FamilyOS is adding a shared private document core, a reusable OCR/document-processing engine, and domain-specific document workflows. Paperless-ngx was evaluated as a possible mandatory sidecar or canonical backend because it already provides mature OCR, PDF/A generation, full-text search, document types, correspondents, tags, custom fields, permissions, workflows, and a REST API.

FamilyOS, however, is domain-first rather than document-first. Contracts, expenses, pets, school records, calendar items, tasks, and other structured objects can exist without a source document and already use FamilyOS family, membership, child, and domain permissions.

## Decision

FamilyOS remains the **canonical system of record for documents, document metadata, permissions, storage, lifecycle state, and links to FamilyOS domains**.

Paperless-ngx will **not** be:

- a required dependency or mandatory sidecar,
- the canonical FamilyOS document store,
- the authority for FamilyOS document permissions,
- a shadow metadata database that FamilyOS must continuously synchronize,
- the place where FamilyOS domain relationships are modeled as custom fields.

An optional **Paperless-ngx → FamilyOS import connector** may be added later. Import is a boundary integration, not a second canonical document layer.

## Decision drivers

### One authorization model

FamilyOS already scopes data through family membership and domain-specific permissions. Mirroring Paperless user/group/object permissions would create two authorization authorities and a synchronization problem for sensitive family data. Imported objects must be authorized by FamilyOS after import; source permissions never become FamilyOS ACLs implicitly.

### Domain-first data model

A contract, pet medication, school record, expense, calendar item, or task must remain a native FamilyOS object. A document can support or originate such an object, but must not become the only way that object can exist.

### Operational simplicity

FamilyOS already operates Django, PostgreSQL, application workers, private media handling, and its own deployment lifecycle. Requiring Paperless would add another application stack, worker/broker lifecycle, storage policy, upgrade cadence, monitoring surface, and incident mode.

### FamilyOS storage policy

FamilyOS document processing should have an explicit canonical-file policy controlled by FamilyOS. It must not inherit a second system's requirement to retain an original plus a separate archive representation when that is not needed by the FamilyOS use case.

### Native relationships and auditability

Links to tasks, events, shopping, expenses, pets, school, members, and future domains belong in typed FamilyOS relationships. This keeps authorization, deletion, audit, search, and lifecycle behavior inspectable in one model.

## Patterns adopted from Paperless-ngx

The decision is not a rejection of Paperless product patterns. FamilyOS should deliberately reuse the following architectural ideas where they fit:

- prefer existing embedded text before invoking OCR,
- use OCRmyPDF/Tesseract-class tooling for local OCR where appropriate,
- typed document categories rather than an unstructured file pile,
- correspondent/source metadata when it improves retrieval,
- tags only when they add user value rather than replacing typed relationships,
- full-text search over extracted text and useful metadata,
- content-hash/deduplication safeguards,
- asynchronous, observable processing with explicit states and retry behavior,
- clear document lifecycle rules,
- confidence/review flows before extracted data mutates structured FamilyOS domains.

No Paperless source code is copied into FamilyOS without a separate license and dependency review.

## Constraints for the Document Core

### #179 — Private Document Core

The core must own:

- private canonical file storage,
- family/domain authorization,
- document identity and metadata,
- content hash and deduplication policy,
- typed links to native FamilyOS entities,
- deletion/retention semantics,
- authorized download/preview paths,
- audit-safe lifecycle state.

It must not require Paperless IDs, Paperless users/groups, or Paperless custom fields to function.

### #180 — OCR / Document Processing Engine v2

The processing engine must be provider-neutral and operate on FamilyOS document identities. It should expose deterministic processing states, extracted text, structured candidates, confidence, warnings, and provenance. Embedded text should be used before OCR where possible; OCR and normalization run as FamilyOS-controlled background processing.

### #184 — Receipt OCR migration

Receipt OCR must migrate onto the common processing core without making the expense domain depend on a general DMS UI. Expense-specific extraction remains an expense-domain adapter consuming the common document-processing result.

## Future Paperless import connector

A later connector may read from the Paperless REST API and offer an explicit reviewed import of:

- the document file,
- title,
- created/document date,
- correspondent,
- document type,
- selected tags,
- selected custom fields.

The connector must:

1. preserve a stable source-system/source-object identifier for idempotency,
2. copy/import data into FamilyOS rather than make runtime correctness depend on Paperless availability,
3. run FamilyOS authorization and storage rules after import,
4. never translate Paperless object permissions into FamilyOS permissions automatically,
5. never overwrite structured FamilyOS domain data without an explicit review/action,
6. avoid sync-back or bidirectional conflict semantics in the initial implementation.

This connector is explicitly outside the P1 Document Core scope.

## Consequences

### Positive

- one permission authority for sensitive family data,
- one canonical storage/lifecycle model,
- no mandatory second DMS stack,
- document processing can serve expenses, pets, school, contracts, and future domains consistently,
- structured FamilyOS objects remain usable without source documents,
- optional Paperless users can still be supported later through import.

### Trade-offs

- FamilyOS must implement and maintain its own document metadata, search integration, processing states, and private-file lifecycle,
- mature Paperless features cannot simply be assumed to exist in FamilyOS,
- future connector work needs explicit mapping and idempotency rules.

These trade-offs are accepted because duplicating authorization and canonical storage would create a larger long-term security and maintenance risk.

## Guardrail for future changes

Any proposal that introduces another canonical document database, permission authority, or required document sidecar must supersede this ADR explicitly. Feature work must not bypass this decision by storing FamilyOS domain relationships only in external custom fields.

## References

- Paperless-ngx documentation: https://docs.paperless-ngx.com/
- Paperless-ngx REST API: https://docs.paperless-ngx.com/api/
- Paperless-ngx basic usage: https://docs.paperless-ngx.com/usage/
- Paperless-ngx configuration: https://docs.paperless-ngx.com/configuration/
