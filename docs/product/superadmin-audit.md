# Superadmin audit explorer

Issue: #205 (roadmap #223)

## Endpoint

`GET /api/superadmin/audit/`

The first bounded audit slice supports `24h`, `7d`, `30d`, `90d`, and `365d`, plus server-side filters for actor class/id, event key, outcome, family UUID, and target type. Family filters use the canonical UUID tenant key; invalid UUIDs fail closed with `400`.

Results are ordered reverse-chronologically and use bounded offset pagination (`limit <= 100`, `offset <= 10000`). Access is restricted by the existing `IsSuperAdmin` permission.

## Privacy contract

Raw telemetry metadata is never serialized. `details` is built from a fixed allow-list and deliberately excludes `identifier_hash` even though that field is valid internal anti-abuse telemetry. Private family content, tokens, credential material and raw JSON dumps are not part of this API.

The response includes the audit `request_id` correlation value for technical investigation, as required by #205, but it does not expose request headers, IP histories or authentication material.

## Follow-up

CSV export remains a separate slice because the export must use the same allow-listed fields and the export action itself must be audited. Custom/all-time range policy and frontend Audit Explorer integration also remain outside this bounded endpoint slice.
