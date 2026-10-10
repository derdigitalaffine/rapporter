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

## Schema deploy vs. commercial cutover

Migration `entitlements.0001_initial` is deliberately **commercial-cutover neutral**. It creates the entitlement schema and seeds the capability registry, but it does not grandfather any family. Deploying the technical core therefore does not decide who is legacy/VIP.

The later product/commercial release must invoke an explicit one-time cutover command with the approved timestamp:

```bash
python manage.py apply_entitlement_commercial_cutover --cutover-at '2026-10-10T20:00:00+02:00'
```

The timestamp must be timezone-aware and must not be in the future. The command persists an `EntitlementCutover` marker under `commercial-v1`. On first application it grants exactly one legacy entitlement to every family whose canonical `Family.created_at` is at or before the commercial timestamp:

- origin: `legacy_grandfathered`
- plan: `vip`
- source ref: `commercial-cutover:legacy-vip-v1`
- `starts_at`: the persisted commercial cutover timestamp

This means families created before the Entitlement Core deploy **and** families created between the Core deploy and the later commercial cutover are grandfathered. Families created after the persisted timestamp start with the Light baseline unless another grant applies.

The operation is transactional and idempotent. Re-running the command with the same timestamp does not duplicate grants or audit rows. Re-running `commercial-v1` with a different timestamp fails closed, so the historical boundary cannot silently move after it has been recorded. Each newly created legacy grant also receives an audit event with no arbitrary provider payload.

No family/task/document/travel data is copied or deleted by entitlement changes.

## Server-side authorization

Use `entitlements.services.require_capability(user, family, key)` in write/API/service paths that become premium-gated. The helper checks active tenant membership before checking entitlement state. Frontend capability display is never authorization.

This issue intentionally does **not** gate existing modules yet. Feature cutovers can migrate one domain at a time after the commercial boundary is explicitly approved; the Entitlement Core deploy itself creates no legacy/VIP flag day.

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

A future Superadmin UI/API may call these services; it must not bypass them or infer entitlement state directly from `source_ref`. Any stronger identity/audit requirements from the Superadmin/identity roadmap remain prerequisites for exposing such mutation endpoints; this core does not weaken them.

## Adding a capability

1. Add the key once to the central capability catalog.
2. Add an additive migration that creates/updates its `CapabilityDefinition`.
3. Gate server-side behavior with `require_capability` where product policy requires it.
4. Use the read-only snapshot only for UX hints/progressive disclosure.
5. Test missing/revoked/expired state and cross-family access.

Do not add provider- or tariff-specific checks to a Fachmodul.

## Rollback

The initial migration is additive and does not assign legacy status. Before a commercial cutover, rollback is simply removal/disablement of the gate and snapshot usage. After a cutover, the persisted marker and legacy grants form audit/history data and should not be rewritten merely to roll back a UI or module gate; canonical family/domain data remains untouched.
