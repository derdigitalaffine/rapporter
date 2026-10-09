# Schulferien Rheinland-Pfalz

## Source and design research (2026-10-10)

- [RLP Ministry for Education](https://bm.rlp.de/service/ferientermine): authoritative first/last holiday dates and a downloadable ICS calendar, currently calendar years 2025–2030. The ICS `DTEND` is already exclusive; the adapter preserves that convention. Individual schools determine six additional flexible holidays; those are deliberately not inferred.
- [Official ICS export](https://bm.rlp.de/fileadmin/09/05_Service/Dokumente/Schulferien_RLP_Kalenderjahre_2025-2030.ics): live inspected against the table (including 2026 autumn and 2026/27 Christmas). The published download link is discovered on the ministry page instead of assuming the filename never changes.
- [Apple Calendar holiday subscriptions](https://support.apple.com/en-euro/guide/iphone/iph80d93ac49/ios): select a subscription, display with other calendars, and provider-controlled read-only holidays. These documented interaction patterns inform the one-connection setup, calendar source filters and read-only detail sheet. No claim is made that documentation or aggregate app ratings demonstrate feature-specific satisfaction.

## Behavior

Owner/adult connects without credentials. The backend fetches the official page/export over validated public HTTPS; no supplied endpoint is accepted. It validates all holiday blocks before modifying any events, locks the source and atomically updates stable holiday-kind/school-year identities. Provider UID changes do not duplicate events. Deleted blocks are removed only after a valid complete response. On failure, existing dates remain, source health/backoff reports the error, and manual retry is possible. Normal successful refresh waits one day, using the existing scheduler. At feed expiry an explicit error replaces a misleading successful empty calendar.

Intervals represent Rheinland-Pfalz civil days in `Europe/Berlin`, including daylight-saving changes. Payload civil dates let clients display the same dates even on devices/families in another timezone. The agenda detail shows the inclusive human date range, attribution, official link and the school-specific flexible-day explanation. Imported holidays cannot be edited/deleted individually. Disconnect removes this subscription's holiday events and preserves unrelated appointments.

Existing integrations remain unchanged apart from enforcing existing owner/adult management restrictions on manual synchronization.

## Validation

Focused backend tests cover exclusivity/timezone, daily scheduling, repeated import, changed UID/date, removed block, invalid/empty/unreachable feed preservation and health, official host restrictions, singleton connect, access isolation, read-only API and disconnect. Browser tests cover credential-free activation, calendar range/attribution and no edit affordance. Normal CI supplies PostgreSQL and Chromium execution.
