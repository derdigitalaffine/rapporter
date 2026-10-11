# Superadmin user directory

Issue: #205 (roadmap #223)

## Endpoint

The existing `GET /api/superadmin/users/` contract is enriched in place; no new route is introduced.

Existing search and pagination remain compatible. The directory additionally supports:

- `status=active|inactive`
- `sort=username|-username|created_at|-created_at|last_activity|-last_activity|last_login|-last_login|families|-families`

Unknown filter/sort values fail closed with `400` rather than being passed to arbitrary ORM ordering.

## Directory metrics

Each row adds non-sensitive operational metadata:

- account creation timestamp
- last observed usage event timestamp
- last successful login audit timestamp
- number of family memberships
- number of non-revoked, non-expired auth sessions
- whether a usable password exists
- number of non-revoked passkeys

Existing identity and membership fields remain unchanged.

## Privacy boundary

The directory never serializes session IDs, refresh JTIs, device/client labels, passkey credential IDs, public keys, transports, passkey names, raw audit metadata, login identifiers, or private family content. Passkey/session state is exposed only as aggregate counts; password state is a boolean capability, never password material.

The response is intended for Superadmin operational triage, not behavior scoring. Activity timestamps reflect canonical telemetry observations and must not be interpreted as exhaustive surveillance of user behavior.
