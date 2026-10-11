# Superadmin family directory

Issue: #205 (roadmap #223)

## Existing endpoint

The existing `GET /api/superadmin/families/` list contract is enriched in place; no new route or response wrapper is introduced.

Optional server-side controls:

- `q=` searches family name/slug plus owner/member display name, username and managed email identity
- `status=active|suspended`
- `sort=name|-name|created_at|-created_at|last_activity|-last_activity|members|-members`

Unknown status/sort values fail closed with `400`; arbitrary ORM field names are never accepted.

## Added operational fields

Each family row additionally exposes:

- `owner_count`
- `verified_owner_count`
- `pending_invite_count`
- `last_activity_at` from canonical usage telemetry
- owner-level `email_verified`
- `entitlements` from the canonical `resolve_entitlements()` service (`tier`, display name, capabilities, origin summary and origin classes)

Existing fields, owners and pending-owner-invite rows remain compatible.

## Privacy boundary

The directory does not serialize entitlement grant `metadata`, `source_ref`, administrative reasons, audit snapshots, private family content, tokens or credential material. Entitlement state is resolved through the same canonical service used for authorization/licensing rather than duplicated dashboard logic.

`last_activity_at` is an operational telemetry observation and must not be presented as exhaustive behavioral surveillance. Search is limited to existing administrative identity/directory fields; private module content is never searched.
