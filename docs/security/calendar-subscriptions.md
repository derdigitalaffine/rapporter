# Calendar subscription and CalDAV security

This calendar integration is an adapter around canonical `FamilyEvent`, not a second calendar domain. Read-only subscriptions and optional CalDAV are separate security surfaces and must stay separate.

## Read-only subscription grants

Each owner/adult can create named subscription grants for a family. A grant has a cryptographically random bearer token; lookup uses SHA-256 and the recoverable token is encrypted at rest with the existing CalDAV secret primitive. Normal FamilyOS account passwords/sessions never authenticate a public calendar feed.

Creation, reveal, rotation, Apple profile download and detail-level changes require the canonical fresh app session. Revocation intentionally stays available without fresh reauthentication so a compromised grant can always be stopped. Every feed request rechecks grant revocation, active creator, active family and current owner/adult membership.

The public URL is derived only from canonical HTTPS `APP_URL`, never from request `Host`. Feed responses are no-store/no-referrer/noindex and the bearer path is redacted by Django/Daphne/Caddy logging filters.

### Server-enforced detail levels

A grant stores one of three levels and the server applies it while rendering both ICS feed and the legacy read-only DAV projection:

- `availability`: summary becomes `Belegt`; location/description are absent.
- `title`: title/time/recurrence only.
- `full`: title/time/recurrence plus a bounded `LOCATION` allow-list.

Changing the level does **not** rotate the bearer token. The same URL immediately renders the new level and the change is audited as `calendar.subscription.updated`.

All levels exclude arbitrary payload fields, notes/descriptions, documents, attendees/organizers, protected health/child data, external imports and virtual projections.

### Apple subscribed-calendar profile

The Apple `.mobileconfig` uses `com.apple.subscribedcalendar.account`, never `com.apple.caldav.account`. It therefore installs the HTTPS ICS subscription and does not embed CalDAV credentials or accidentally grant writes.

For multiple active family members, the profile contains one subscribed-calendar payload per member, backed by a member-specific feed URL on the **same revocable grant**. Member feeds do not widen the export boundary: only `is_family_event=True` native events are eligible. Unassigned family events appear for every member; attendance-selected family events appear only for selected members. Selected/private events without the whole-family flag remain excluded.

## Optional CalDAV connections

CalDAV is configured independently under Settings. A family connection may optionally map to one `Membership`; a DB constraint and serializer validation allow at most one connection per `(family, member)`. The member mapping becomes immutable after connection creation; moving an account to another member requires a new connection.

Access mode is explicit:

- `read`: pull/project only; never issues PUT or DELETE.
- `read_write`: pull plus conditional outbound writes.

Credentials are write-only API inputs and encrypted at rest. The selected remote collection URL is also encrypted at rest. Discovery returns only an opaque HMAC-derived `calendar_key`, display name, supported components and sync-token support; private collection hrefs are never accepted from or returned to the browser.

Changing credentials clears the selected collection, imported projection and private bindings so stale remote identity cannot be reused against another account. Choosing a different remote collection similarly resets the old projection/bindings before registering the new collection.

## SSRF and credential forwarding

CalDAV discovery/sync uses validated HTTPS endpoints, approved ports, DNS/IP policy and pinned-IP connections. Private/loopback/link-local/reserved targets are denied unless the operator explicitly enables permitted private networks; loopback remains denied.

Sync requests follow only same-host redirects. REPORT resource hrefs are origin-bound to the selected collection by `(scheme, host, effective port)`. A malicious absolute href pointing at another origin fails with `caldav_resource_origin_rejected` before stored credentials can be reused. Persisted resource hrefs are revalidated with the same rule before PUT/DELETE.

Remote collection and resource hrefs are encrypted and never copied into `FamilyEvent.payload` or normal API responses.

## Server-side filtering and recurrence reads

Pull uses RFC 4791 `calendar-query` with a bounded `time-range`; the adapter does not download an entire remote collection and then filter locally.

The same REPORT requests `CALDAV:expand` for that bounded range. This makes the remote CalDAV server expand arbitrary recurrence rules into occurrences. FamilyOS stores those occurrences as read-only source projections instead of translating foreign RRULE semantics into its native recurrence model. Each projected occurrence gets a stable private binding identity derived from remote UID plus recurrence identity/start.

Recurring **FamilyOS write-back remains disabled**. This distinction is deliberate: recurring remote events are readable, while outbound recurrence mutation stays fail-closed until recurrence exceptions/sequence semantics can be implemented safely.

## Canonical projection and private bindings

Remote data is projected through `IntegrationSource → FamilyEvent`; there is no CalDAV-specific public event model.

Private `CalDavEventBinding` rows retain:

- connection
- remote UID / recurrence occurrence identity
- encrypted resource href
- ETag
- last acknowledged local `FamilyEvent.version`
- last-seen/deletion state

The public `FamilyEvent` payload may contain safe presentation fields such as provider, location and all-day dates, but never remote href, credentials or raw remote UID.

## Conditional writes and conflicts

Writable connections use optimistic concurrency:

- create: `If-None-Match: *`
- update: last ETag via `If-Match`
- delete: last ETag via `If-Match`

HTTP 412 is a conflict, not permission to retry blindly. If both remote ETag and local `FamilyEvent.version` changed since the binding baseline, pull preserves the local edit and records a conflict instead of applying last-write-wins.

Local deletion leaves a binding tombstone (`event=NULL`) so the subsequent remote DELETE remains conditional. Pull must not recreate a tombstoned resource before DELETE. If the remote event changed after the local delete, the old ETag causes 412 and the tombstone remains for conflict handling rather than deleting the newer remote event.

Remote deletion of a native writable FamilyEvent does not silently delete the canonical local event; it becomes a conflict. Remote deletion of a purely imported projection removes that imported projection.

## Per-member writable scope

For a connection mapped to one family member, outbound writes include:

- native events explicitly assigned to that member, including selected-only native events; and
- whole-family native events with no participant selection.

A whole-family event explicitly assigned only to another member is excluded from this external calendar. This mirrors the per-member target-calendar intent without widening subscription export privacy.

## Integration health and scheduling

Selecting a family CalDAV collection immediately creates/updates its `IntegrationSource`, so the existing integration health/backoff loop owns subsequent sync scheduling. Successful CalDAV sources use a bounded refresh cadence; failures reuse existing source health/backoff instead of introducing a second scheduler.

## Deliberate write limits

The first writable slice does **not** implement:

- outbound recurring-event mutations
- recurrence exception editing
- attendee/organizer/iTIP scheduling
- invitation delivery
- imported VALARM → FamilyOS notification promotion

These paths fail closed or stay read-only. They must not be partially translated or silently dropped on a write.

## Resource bounds and logging

Subscription feed/DAV limits remain bounded (resource count, response bytes, XML size/depth/nodes and multiget count). CalDAV transport also bounds request/response sizes. DTD/entities are rejected by XML parsing helpers.

Do not enable raw request/authorization logging on application or reverse-proxy layers. Any additional APM/proxy must redact subscription bearer paths, Authorization headers, cookies, CalDAV passwords and private remote URLs.

## Primary references

- RFC 4791 — CalDAV (`calendar-query`, `time-range`, `calendar-data/expand`)
- RFC 5545 — iCalendar
- RFC 9110 — HTTP conditional request semantics
- Apple Platform Deployment — Calendar payload settings
- Apple Support — app-specific passwords for third-party access
