# Universal Budget Planning

Owner: #245. Delivery: #669 Slice A; this is a partial foundation, not completion of participant planning or the Travel v2 epic.

## Canonical Facts

- `ExpenseLedger.budget_amount`: planned overall spending cap; nullable means not set, zero means explicitly zero.
- `ExpenseLedger.estimated_amount`: optional overall estimate, never derived from or booked as an Expense.
- `ExpenseBudget.amount`: existing planned category cap.
- `ExpenseBudget.estimated_amount`: optional category estimate.
- Actual expenses, allocation totals, personal balances, frozen FX and settlements keep their existing contracts. Category estimates/caps are not automatically added to or substituted for the overall cap.

The global Finance surface is the only editor. Trip expenses already select the same ledger through `expense.trip` Context Links. No TripBudget, private-person budget projection, automatic ledger creation, notification or domain task is introduced.

## Interaction Contract

Dominant everyday action remains `+ Expense`. Budget planning is secondary and opens one existing StandardEditor sheet with FormShell/FormField/FormRow/FormActions/ErrorSummary. Category rows are progressively disclosed under Sub-budgets. Sheet portaling reuses the existing AccessibilityManager and GlobalCreate suppression rather than introducing another overlay/focus system.

Save failures preserve inputs and surface field errors. A conflict offers explicit reload; it does not silently overwrite the other writer. Closing restores focus; family/account changes reset the editor and stale responses cannot update a different account. Loading, empty, unavailable, retry and offline states are explicit.

## API, Retry and Isolation

Existing ledger/category PATCH accepts optional `expected_updated_at` (server-issued `updated_at`, preserving its full precision). Canonical row locking makes comparison and write atomic; stale revisions return HTTP 409. Legacy clients that omit the revision remain compatible.

Category POST accepts optional `client_request_id`. The editor keeps one UUID through retries. Ledger-scoped locking and a database uniqueness constraint return the existing category for identical duplicate requests; retries never recreate a second category or overwrite the first result. Changed retry input returns HTTP 409 rather than silently discarding the changes. The key is write-only and immutable on PATCH. Legacy creates without a key remain supported.

Existing active-family/entitlement and object isolation remain authoritative. Estimates have non-negative Decimal(12,2) serializer and database constraints. No data appears in telemetry, offline caches, Today, Pinboard or external adapters in this slice.

## Migration and Rollback

Migration `expenses.0011` is additive: nullable estimate/retry-key columns and non-negative/uniqueness constraints. No historical expenses, shares, allocations, FX values or settlements are recalculated. Deploy migration before the new API/UI. Application rollback can leave added columns in place; removing the migration discards only newly entered estimates/retry keys, so export them before schema rollback. Existing planned amounts and actual expense facts remain untouched.

## Remaining Slices

Personal limits and planned participant cost shares require their own explicit privacy/permission contract; they must never use ExpenseShare or Settlement as planning storage. Travel variants/confirmation (#668), extended preparation/destination sources (#670), and Pinboard priority/contact cards (#667) remain separate consumers. No automatic sum, distribution or decision is implied by this foundation.
