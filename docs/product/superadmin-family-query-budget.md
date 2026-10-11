# Superadmin family directory query budget

Issue: #205 (roadmap #223)

The Superadmin family directory previously had two data-dependent query multipliers:

- `resolve_entitlements()` loaded capability definitions, the commercial-cutover marker and active grants once per family row.
- each pending family invitation performed separate latest-mail and last-successful-mail queries through `invitation_delivery_summary()`.

## Batching contract

The directory now primes both data sets before serialization:

- `resolve_entitlements_for_families()` preserves the exact single-family entitlement semantics while loading definitions, cutover state and all active grants in a constant three-query batch.
- `prime_invitation_delivery_summaries()` groups invitation reference-prefix lookups in bounded batches of 200 invitations and fills the existing per-invite cache. Individual callers keep the original fallback path.

The API response shape, entitlement policy, invite lifecycle semantics and privacy boundary are unchanged.

## Regression coverage

The query-budget test compares one family with one pending invitation against six families with six pending invitations. The larger response may not add a query per family/invite; the allowed difference is at most one query. A separate semantic test verifies that bulk entitlement snapshots exactly match `resolve_entitlements()` for Light and Premium fixtures.

This optimization does not introduce private family-content reads. It only batches the same entitlement grant and transactional-mail metadata already used by the directory.
