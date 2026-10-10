# Entitlement Core

Issue #227 introduces a provider-independent, family-scoped entitlement layer. It is a licensing/capability service only: payment providers, checkout, subscriptions and module activation stay outside this core.

## Capability model

Capability keys are centrally defined in `entitlements/catalog.py` and persisted as `CapabilityDefinition` rows. Fachmodule must depend on keys and the resolver, not on plan strings such as `vip`, `premium` or provider names.

Initial Light capabilities:

- `family_management`
- `calendar`
- `todo`
- `shopping`
- `pinboard`
- `notes`

Initial premium-capable keys include `travel`, `documents`, `school`, `children`, `pregnancy_baby`, `pets`, `advanced_integrations` and `advanced_tasks`.

A capability definition being licensed is intentionally separate from whether a module is enabled/configured for a family.

## Grants

`EntitlementGrant` belongs to exactly one Family and records its origin (`purchased_lifetime`, `admin_grant`, `legacy_grandfathered`, `subscription`, `promotion`) independently of UI labels. A grant can contribute a known capability set or a central plan key.

A grant is effective only when all of the following are true:

- `active=True`
- it is not revoked
- `starts_at` is empty or reached
- `ends_at` is empty or still in the future

`source_ref` is correlation metadata only. It never makes a grant active and is never used as provider truth.

The resolver always starts with the Light baseline, then unions effective grants. `premium` and `vip` currently mean full access to all non-deprecated capability definitions; `vip` is the UI/display tier used for full legacy access. Origins remain visible separately in the snapshot.

## Legacy migration

Migration `entitlements.0001_initial` captures families that exist **at the migration run** and adds exactly one:

- origin: `legacy_grandfathered`
- plan: `vip`
- source ref: `migration:legacy-vip-v1`

The seed uses `get_or_create`, so retrying the data step is idempotent. New families created after the migration do not run through this backfill and therefore begin with the Light baseline unless another grant is created.

No family/task/document/travel data is copied or deleted by entitlement changes.

## Server-side authorization

Use `entitlements.services.require_capability(user, family, key)` in write/API/service paths that become premium-gated. The helper checks active tenant membership before checking entitlement state. Frontend capability display is never authorization.

This issue intentionally does **not** gate existing modules yet: existing installations have legacy VIP and feature cutovers can migrate one domain at a time without creating a flag day.

## Snapshot API

Authenticated family members can read:

`GET /api/entitlements/?family=<family-uuid>`

Example:

```json
{
  "family": "...",
  "tier": "vip",
  "display_name": "VIP",
  "capabilities": ["calendar", "todo", "travel"],
  "origin_summary": "legacy_grandfathered",
  "origins": ["legacy_grandfathered"]
}
```

The family parameter is a selector, not trusted authority: the server verifies Membership first and returns the same generic 403 shape for inaccessible tenants.

## Administrative grants

`create_admin_grant()` and `revoke_admin_grant()` require `is_superuser`, require a human-readable reason and write `EntitlementGrantAudit` events. Audit snapshots contain entitlement state only, not arbitrary grant metadata/provider payloads.

Metadata accepted by the service is an object capped at 4 KiB, and capability lists are allowlisted and bounded. Administrative revocation only revokes `admin_grant` records and never deletes family data.

A future Superadmin UI/API may call these services; it must not bypass them or infer entitlement state directly from `source_ref`.

## Adding a capability

1. Add the key once to the central capability catalog.
2. Add an additive migration that creates/updates its `CapabilityDefinition`.
3. Gate server-side behavior with `require_capability` where product policy requires it.
4. Use the read-only snapshot only for UX hints/progressive disclosure.
5. Test missing/revoked/expired state and cross-family access.

Do not add provider- or tariff-specific checks to a Fachmodul.

## Rollback

The initial migration is additive. No existing domain data is rewritten. Before any future feature cutover, rollback is simply removal/disablement of the gate and snapshot usage; entitlement rows can remain without affecting canonical domain data.
