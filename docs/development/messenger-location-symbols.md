# Messenger interaction contract (#777)

The canonical Messenger domain and its visibility/write services remain owners.
`ChatMessage.location` is an optional JSON object with exactly latitude, longitude
and accuracy (metres). Only finite JSON numbers are accepted; booleans and strings
are invalid. Coordinates are range checked and rounded to five decimal places.
Accuracy is limited to 0–100000 m. Server validation applies to JSON and multipart.
The existing client UUID/digest includes the normalized point; payloads without a
point retain the old digest format. No coordinates are copied to notification
content, reply previews, conversation lists, telemetry or third-party map previews.
Deletion clears the persisted point and the serializer hides deleted content.
Ordinary message retention applies; there is no additional location history.

Migration 0006 adds a nullable column without backfill. Deploy migration/backend
before the new client. Older messages/clients remain compatible. Roll back code
without removing the column; reverse migration would discard stored points and is
not the default rollback procedure.

The client only calls getCurrentPosition after an explicit action, never watchPosition.
Late geolocation results are ignored after closing the sheet. No map SDK is imported:
LocationCard renders coordinates/accuracy and an external, user-activated OSM link.
A point is added to a draft and sent by the normal composer, with the same ACL/retry.
Location errors are local to the sheet. Send errors are separate from poll errors.

History paging serializes against polling and restores scrollHeight delta in a
layout effect. Existing rows retain identity when event_sequence is unchanged.
New messages only auto-scroll at the tail; otherwise an explicit jump is available.
The parent updates a conversation in place instead of re-sorting and re-fetching
contacts on every thread poll. Polling frequency is unchanged; no new per-row requests.
Search keeps the header/composer mounted while results load. Image previews reserve
an aspect ratio; full original media remains reachable through the existing link.

SymbolPicker is a small native fieldset/radio group with local filtering, not a second
Combobox or modal implementation. Consumers own allowed choices and saved values.
Aliases change rendering/labels only. ActionOptionsEditor consumes FamilySheet for
modality; shared wrappers remain unchanged. Unknown existing values are retained.

Evidence lives in the Messenger quality workflow: PostgreSQL messenger suite,
production build, import/bundle gates, mobile/desktop Messenger E2E and production
stories at 320/390/1024/1440 with axe. Physical iOS/Android keyboard, native AT and
real browser zoom remain tracked by #773; CSS zoom/emulation does not replace them.
