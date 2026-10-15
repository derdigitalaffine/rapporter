# Read-only calendar subscriptions

Delivery #738; outbound exception to #198 authorized in #223. This is an adapter
of canonical FamilyEvent, not a second calendar, inbound connector or scheduling
server. Research: issue #738 external-research:v1 (2026-10-15).

## Credentials and access

Each owner/adult creates up to ten **own** named subscriptions per family. Secrets
are 32 cryptographically random bytes, URL-safe encoded; lookup uses SHA-256 and
reveal uses existing CalDAV Fernet encryption derived from SECRET_KEY. Losing that
key requires revoking/recreating grants. Never replace subscription secrets with
account cookies, session tokens or one-time login links.

Creation, reveal, rotation and profile download require the canonical fresh app
AuthSession. Existing abuse buckets bound management/public reads. Management is
creator-scoped, including other adult family members. Revocation does not require
freshness: an authenticated owner must always be able to stop a compromised link.
Every feed/DAV request rechecks non-revoked grant, active creator, active family and
current creator owner/adult membership. Account deletion cascades grants.

Revocation or rotation immediately prevents subsequent use of the old secret in
both the feed and DAV account. It cannot remove copies already downloaded by a
calendar application. Subscription access intentionally survives ordinary logout.
Secrets never appear in ordinary list responses or audit metadata. Normal app
credentials cannot authenticate to DAV. All write/ACL/scheduling methods are denied.

## Export boundary

Only `calendar.event` with no integration source, explicit `is_family_event=True`,
no selected participants and a start time is exported. No inferred legacy/private
visibility. Export allow-list is UID, escaped title, start/end, timezone and native
recurrence. Arbitrary payload, participants, organizer, notes, location, documents,
protected health/child references, imports and virtual projections are excluded.

Stable UUID-based UIDs and content ETags reflect changes/deletions. iCalendar's
serializer escapes content and folds lines. Local times/VTIMEZONE preserve DST;
all-day DTEND is exclusive. Ordinary daily/weekly/monthly/yearly native rules map
to RRULE. Canonical quarterly rules may use clamped dates or nth weekdays of a
quarter and are **not** approximated with monthly interval=3. They reuse native
projection as RDATE over a rolling one-year past / three-year future window.
Subscribed clients refresh that window on retrieval; other native events are not
limited to that window. No imported source's recurrence is reinterpreted.

## Protocol and resource limits

HTTPS APP_URL must be a canonical origin without credentials/path/query/fragment;
never derive issued URLs from request Host. Deploy a publicly reachable trusted
TLS certificate. Self-signed local deployments are not advertised as iPhone-ready.

`/.well-known/caldav` redirects to `/caldav/`. Basic-authenticated discovery exposes
principal → home → read-only family collection. OPTIONS/PROPFIND Depth 0/1,
calendar-query, calendar-multiget, GET/HEAD and conditional ETags are supported.
Unknown properties get 404 propstats. Unsupported filters/expansion fail closed;
no sync-token, scheduling, write or full CalDAV compliance claim is made. Clients
can list ETags and multiget changed resources. Refresh timing is client-controlled.

At most 2,000 resources / 8 MiB per calendar response; capacity returns 507 rather
than a silently incomplete feed. XML is bounded to 64 KiB, depth 12 and 1,000 nodes;
DTD/entities/UTF-16 declarations are rejected. Multiget is bounded to 200 hrefs,
never fetches remote URLs and denies another grant's path. Explicit two-sided query ranges and recurring event durations are bounded
to five years. RFC start-only/end-only time ranges are supported without unbounded
series expansion; native recurrence has no UNTIL/COUNT. Unsupported filter types
are rejected explicitly.

## Delivery and logs

The shipped Caddy routes forward DAV/feed/discovery to Django, and global JSON
log filters redact feed bearer paths even on upstream errors. Authorization/cookie
logging remains redacted by Caddy defaults; referrers are removed. Daphne uses its
normal CLI with a redacting action logger; Django request/server logs also filter
bearer paths. Additional operator-managed reverse proxies, APM and access logs
must apply equivalent redaction before enabling links. Do not enable raw request
or credential capture. No-store/no-referrer/noindex applies to feeds, DAV and
management responses including errors. Service workers bypass all these routes.

The additional `.mobileconfig` contains exactly one `com.apple.caldav.account`,
HTTPS host/port/principal and the same dedicated read-only credential. It contains
no management/enrollment/root certificate/removal restriction. It is unsigned;
iOS may display that status. Safari receives a real attachment response, not a
Blob impersonating an installed account. Users explicitly install it in Settings.
No download event is represented as successful installation.

## Operations / rollback

Apply additive migration 0241, set APP_URL, deploy backend/proxy/frontend together,
and verify discovery/REPORT plus feed before offering setup. Roll back by revoking
all grants, then removing UI/provider routes; native events remain unchanged. Do
not drop the grant table while outstanding links must still be managed/audited.

## Primary references

- https://www.rfc-editor.org/rfc/rfc4791
- https://www.rfc-editor.org/rfc/rfc5545
- https://support.apple.com/guide/deployment/calendar-payload-settings-depd57d3a18/web
- https://support.apple.com/en-us/102400
- https://caddyserver.com/docs/caddyfile/options#log
- https://caddyserver.com/docs/caddyfile/directives/log#filter
- https://github.com/django/daphne/blob/main/daphne/access.py
