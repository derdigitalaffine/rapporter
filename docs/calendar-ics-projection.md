# Calendar ICS projection contract

FamilyOS projects ICS/iCalendar sources into the existing calendar domain. The canonical path is:

`IntegrationSource -> FamilyEvent -> Calendar / Today`

There is no second ICS-specific event domain. This document describes the behavior that is already implemented by the server-side ICS projector and the boundaries callers and operators should rely on.

## Source and sync model

An ICS source is represented by `IntegrationSource`. A sync reads either the stored `ics_content` snapshot or the configured ICS endpoint and materializes a bounded set of `FamilyEvent` rows for that source.

The legacy `sync_ics` entry point and Integration Hub flows use the same projector. A successful sync is applied atomically while the `IntegrationSource` row is locked. Existing projected rows are updated by stable external identity, duplicate rows for the same `(source, external_id)` are collapsed, and projections that are no longer present in the successful snapshot are removed.

If parsing, recurrence validation, or a projection limit fails before the database write, the previous successful projection remains intact. A bad refresh must not partially replace the last known-good calendar state.

## Projection window and limits

The projector intentionally materializes a bounded horizon instead of expanding an unbounded calendar forever:

- look-back: 366 days from the sync time in the family timezone
- look-ahead: 1,095 days
- maximum recurrence occurrences per series: 10,000
- maximum projected events for one source sync: 20,000

Exceeding a recurrence or global projection limit aborts the refresh before projection writes. These limits are correctness and availability guardrails, not pagination settings.

## Recurrence behavior

The projector groups `VEVENT` components by `UID`. Missing UIDs receive a deterministic generated identifier based on stable event fields so repeated imports do not create a new row solely because the feed omitted `UID`.

Supported projection behavior includes:

- `RRULE` expansion inside the bounded projection window
- `RDATE` additions, including period values with an explicit duration
- `EXDATE` removals
- `RECURRENCE-ID` exceptions that replace/move one occurrence
- `STATUS:CANCELLED` on a master or recurrence exception
- standalone recurrence exceptions when a master event is absent
- `DTEND` when present, `DURATION` as a fallback, and safe zero/default duration behavior

Before parsing, raw `RRULE` lines are checked for a valid `FREQ`. Accepted frequencies are `SECONDLY`, `MINUTELY`, `HOURLY`, `DAILY`, `WEEKLY`, `MONTHLY`, and `YEARLY`. The actual rule is then parsed by `python-dateutil`; malformed rules fail the sync rather than being silently discarded.

This is deliberately not a promise that every optional iCalendar recurrence feature is fully modeled by FamilyOS. New recurrence constructs should be added with regression coverage before being treated as a product contract.

## Identity and idempotency

Projected events use the source plus a stable `external_id` as identity.

For a non-recurring event, the UID is the external identity. For a recurring event, the identity is derived from `UID` plus an occurrence key:

- timed occurrence keys are normalized to UTC
- all-day occurrence keys are family-local civil dates

Long identifiers are deterministically shortened with a hash suffix. Re-running an unchanged source therefore updates the same rows instead of creating duplicates.

A moved `RECURRENCE-ID` occurrence retains the identity of the original recurrence slot while its projected start/end can change. A cancelled exception removes that occurrence from the materialized series.

## Timezone and civil-time semantics

The family timezone is the calendar's civil-time reference. If the configured family timezone is invalid, the projector falls back to UTC.

Timezone-aware timed events preserve their absolute instant. Floating datetimes and date-only recurrences are expanded in family civil time. This is important around daylight-saving transitions: a floating 09:00 family appointment remains a 09:00 civil-time appointment instead of drifting because the UTC offset changed.

Occurrence identity follows the same split:

- aware timed events: UTC-normalized timestamp identity
- floating/date-only recurrence: family-local recurrence semantics
- all-day events: civil-date identity

Browser-local time is not the source of truth for ICS projection.

## All-day events and exclusive end dates

Date-only `DTSTART` values are treated as all-day events. When no explicit end is present, the default duration is one day.

Projected all-day payloads include:

```json
{
  "all_day": true,
  "date_start": "2026-10-11",
  "date_end_exclusive": "2026-10-12"
}
```

`date_end_exclusive` follows iCalendar's exclusive all-day `DTEND` convention. Consumers must not render the exclusive end date as an additional occupied day. Multi-day display logic should derive the inclusive visible range from `date_start` up to, but not including, `date_end_exclusive`.

## Read-only external events

A source-backed `FamilyEvent` is owned by its integration source. The normal `/api/events/` endpoint rejects attempts to create an event with an external source and rejects update/delete operations for existing source-backed events.

This guarantees that a read-only ICS projection cannot silently become a locally editable copy. To change an external event, change it at the source and sync again. Manual FamilyOS events remain editable through the normal event API.

The same principle applies to other domain-owned read-only event types: the calendar is a projection surface, not an alternate write path into every source domain.

## Failure and recovery behavior

Expected failure behavior is fail-safe rather than destructive:

- invalid/malformed recurrence rules fail the refresh
- recurrence/global projection overflow fails the refresh
- the last successful projection remains when validation fails before the atomic write
- a later valid sync reconciles rows idempotently and removes stale projections

Integration health may report the source failure through the existing integration status flow; callers should not infer that an empty result after a failed refresh means the remote calendar is genuinely empty.

## Security and tenant boundaries

ICS projection always writes events for the source's family. Calendar API reads remain family-scoped, and cross-family event access is rejected by the normal calendar authorization layer.

Do not treat source IDs, event IDs, or external UIDs supplied by a client as authorization. Family membership and source ownership remain server-side concerns.

## What this contract does not provide

This projector is an import/projection layer. It does **not** provide:

- CalDAV discovery, credentials, sync tokens, ETags, remote writes, or two-way synchronization
- attendee invitation/scheduling semantics
- an ICS-specific editable event model
- a guarantee for every optional iCalendar extension without explicit regression coverage
- provider-specific OAuth dispatch

CalDAV work belongs to the dedicated CalDAV integration scope (#198) and must reuse the canonical FamilyOS calendar/event projection rather than creating a parallel calendar domain.

## Regression coverage

The backend regression suite covers the key contract paths, including:

- `RRULE` + `RDATE` + `EXDATE`
- moved and cancelled `RECURRENCE-ID` occurrences
- `STATUS:CANCELLED`
- civil-date all-day events across DST-sensitive dates
- date/floating recurrence `UNTIL` across Europe/Berlin DST
- stable occurrence IDs across resync
- stale cleanup and duplicate projection cleanup
- invalid recurrence preserving the last good state
- per-series and global projection limits preserving the last good state
- source-backed create/update/delete read-only behavior
- cross-family isolation
- manual events remaining editable

When extending ICS support, add a regression that demonstrates the new time/identity semantics before widening this documented contract.
