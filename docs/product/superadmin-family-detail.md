# Superadmin family detail

Issue: #205 (roadmap #223)

## Existing route

`GET /api/superadmin/families/{family_id}/` extends the existing family detail route, which continues to accept sensitive `PATCH` status changes under the existing fresh re-authentication and rate-limit guard.

Read access requires `IsSuperAdmin` but does not require re-authentication because it exposes only bounded administrative metadata.

## Detail payload

The response contains:

- the existing family directory row and entitlement snapshot
- membership metadata: internal user ID, username/display name, role, account status and primary-email verification state
- invite history, capped at 50 rows, with role/address/display name and lifecycle timestamps/state
- distinct active users in the last 7 and 30 days from canonical `activity.foreground` telemetry
- 30-day optional-module adoption as module key + distinct active-user count + last use timestamp
- aggregate integration health: enabled/degraded count and latest successful sync
- the 30 most recent Superadmin audit events for the family, restricted to timestamp/event/outcome/reason/target type

## Privacy boundary

The detail endpoint never queries or serializes family tasks, inbox content, calendar entries, shopping content, baby/pet/document content, notification bodies, integration endpoints/configuration, integration error bodies, invite tokens, raw audit metadata, request IDs, authentication tokens or credential material.

Module adoption is represented only by canonical module keys and aggregate usage counts. The audit timeline intentionally omits `metadata`, correlation/request IDs and target IDs; deeper audit investigation remains in the separately permissioned global Audit Explorer.

Administrative write permissions are unchanged: GET visibility does not grant PATCH rights beyond the existing sensitive-action contract.
