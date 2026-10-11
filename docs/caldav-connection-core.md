# CalDAV connection core

This document covers the first bounded backend slice of #198. It intentionally does **not** implement event sync, remote-calendar mappings, writeback, conflict handling, scheduler jobs, or UI.

## Ownership and API boundary

`CalDavConnection.scope` is either `personal` or `family`.

- Personal connections have exactly one `owner` and no `family`. Only that user can manage or discover them.
- Family connections have exactly one `family` and no personal owner. Only current FamilyOS `owner`/`adult` members can manage or discover them.
- Scope/family cannot be changed through the normal update API. A future migration/reconnect flow must make such a transition explicit.
- The API never serializes server URL, username, password, or ciphertext. It exposes only `credential_state` (`configured`/`missing`) plus non-secret connection metadata.
- Discovery responses contain display names, component capability names and sync-token capability only. Private remote hrefs stay server-side.

Credentials (`server_url`, `username`, `password`) are stored as one Fernet-encrypted payload. The key derivation intentionally matches the existing managed-SMTP secret-storage strategy and therefore follows the deployment `DJANGO_SECRET_KEY` lifecycle. Rotating that key requires reconnecting/re-encrypting managed secrets; do not rotate it without an explicit migration plan.

## SSRF and transport policy

CalDAV discovery is server-side and fail-closed.

Defaults:

- HTTPS only.
- Port 443 only.
- Public IP addresses only.
- Loopback, link-local (including cloud metadata ranges), multicast, unspecified and reserved addresses are always rejected.
- Every DNS answer must pass policy; a public+private mixed answer is rejected.
- The validated IP is pinned for the actual TCP socket while the original hostname is retained for HTTP Host, TLS SNI and certificate validation. This closes the DNS-validation/request TOCTOU window.
- Redirects are manual, bounded, and every target is parsed, DNS-resolved and validated again.
- Response body limit: 1 MiB.
- Request timeout: 10 seconds.
- XML containing `DOCTYPE` or `ENTITY` declarations is rejected before parsing.

Operator environment overrides:

- `CALDAV_ALLOW_PRIVATE_NETWORKS=true` permits private LAN addresses, but never loopback/link-local/reserved/multicast/unspecified addresses.
- `CALDAV_ALLOW_HTTP=true` allows plain HTTP; the relevant port must also be allow-listed. This should only be used for a deliberately trusted LAN deployment.
- `CALDAV_ALLOWED_PORTS=443,8443` sets the explicit outbound port allowlist.
- `CALDAV_HTTP_TIMEOUT=10` sets the socket timeout in seconds.
- `CALDAV_MAX_RESPONSE_BYTES=1048576` bounds a single PROPFIND response.
- `CALDAV_MAX_REDIRECTS=3` bounds manual redirects.

These are security controls, not per-user settings. Changing them is an operator decision.

## Discovery contract

The service performs bounded RFC-style discovery:

1. `PROPFIND` base URL for `current-user-principal`.
2. `PROPFIND` principal for `calendar-home-set`.
3. Depth-1 `PROPFIND` home set for calendar collections, display names, supported components, privileges and `sync-token` capability.

Authentication uses Basic auth over the validated transport. Authorization headers and decrypted credentials are never returned by the API or included in error text. Stable error codes such as `caldav_address_rejected`, `caldav_authentication_failed` and `caldav_response_too_large` are persisted instead of remote response bodies.

## Migration and rollback

Migration `family.0222_caldav_connection_core` follows `family.0221_pass_core` and only creates the additive connection table plus its ownership/index constraints. It does not alter existing FamilyOS calendar/event rows or ICS sources.

Rollback of this slice is therefore limited to dropping that additive table. No canonical event data needs to be rewritten. Future #198 slices must continue the roadmap migration rule: expand first, migrate metadata explicitly, cut over reads/writes only after compatibility tests, and contract only after the fallback path is no longer needed.
