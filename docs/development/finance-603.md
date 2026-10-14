# Finance #603 delivery contract

Existing Expense, ExpenseLedger, settlements, budgets and hidden Document receipts remain canonical. Routes, `expenses` page/feature ID, ledger IDs and storage keys are unchanged. Accounts are the product name for ledgers. Category is an optional additive 80-character field; legacy rows retain an empty category.

`expenses` is a normal premium CapabilityDefinition. Its catalog migration preserves the entitlement resolver's pre-commercial VIP, Premium/VIP plan and explicit grant behavior. Tenant access is checked before capability state, including receipt download/delete, budgets, settlements, trip adapters, wishlist creation and context projections. No grant or data is deleted by a downgrade.

Shared `documents.images` admits 30 MiB, 60 million decoded pixels and a 16384-pixel source-side limit, checks the decoded format, applies EXIF orientation and removes metadata. `pillow-heif` supplies the server decoder; wheel distributions include libheif. Document/receipt output remains 2600px WebP, private images retain their caller's 1600px/other target, avatars retain square output variants, and the legacy JPEG adapter preserves its 2500px/contrast/hash behavior. PDF content remains byte-identical through the existing bounded PDF parser. No OCR work is added to request handling.

## Product integration

- Create: existing expense action/QuickCreateSheet and full editor; account supplied through existing create context.
- Today: existing create action consumes the entitlement snapshot; no new default widget.
- Calendar/Todo/notifications: no new time, completion or push semantics.
- Pinboard/Context Links: existing references remain canonical and entitlement-gated.
- Documents: existing hidden receipt Documents and processing queue; no new storage/OCR subsystem.
- Search: local filter over the current account/currency's loaded rows; no advertised full-history search.
- Offline: existing explicit unavailable-save behavior; no finance or receipt cache.

## Migration and rollback

Apply entitlement 0003 and expenses 0009. Neither migration rewrites or drops existing financial data. Reverting UI/runtime leaves accounts and old workflows intact. A schema rollback of category would discard new category text, so operational rollback should retain additive columns/migrations and revert code only. Existing PDF byte storage and normalized image URLs are unchanged. Upgraded image admission can be reverted without reprocessing stored files.

## Review gates

Backend tests cover Light denial, plan/grant revocation, cross-family account IDs, multiple accounts, categories and PDF content/URL behavior. Shared decoder tests use real HEIC, >10 MiB JPEG, EXIF, old PNG/WebP formats, spoofed types and byte/pixel/dimension bounds. E2E covers navigation/deep-link denial, account creation, quick capture account context, accessible transaction headers/actions, real filters, PDF UI and 320/390/768/1024/1440/1920 widths. Main CI and passkey gates remain required before merge.

## Final regression guard after account defaults

Ledger defaults may populate a new or draft entry. A posted shared booking still requires an explicit personal participant selection before it creates person-to-person debt. Rejecting a bare shared-to-personal update leaves funding, payer and shares unchanged. Transaction rows retain a named account column on desktop and the same context in the adaptive mobile row.

The `finance-regression` workflow independently exercises all Expense tests, smartphone decoding/entitlements, and the finance/travel-account browser flows on mobile and desktop. It complements the complete `ci` workflow; it does not replace or skip any global checks. Its screenshot artifacts include the transaction view at 320, 390, 768, 1024, 1440 and 1920 pixels for visual review.

The profile cropper preserves #603's HEIC/HEIF admission when a browser cannot decode a preview: an explicit Save without preview action sends the original file to the same bounded, content-validated server avatar normalizer and square crop. Browser-native formats still use the adjustable cropper. No file is uploaded before user confirmation, and unsupported/malformed content remains subject to the existing server rejection rules.
