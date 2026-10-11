# Superadmin audit CSV export

Issue: #205 (roadmap #223)

## Existing route

The bounded audit explorer keeps the existing `GET /api/superadmin/audit/` route. Add `export=csv` to export the same filtered event set as CSV.

Supported filters and periods are identical to the explorer. Export requests do not accept `limit` or `offset`; the export covers the complete filtered set up to a hard maximum of 5,000 rows. Larger result sets fail with `413` rather than being silently truncated. The CSV is a request-time snapshot of the filtered audit set and does not retain server-side export state.

## Security boundary

CSV export is a sensitive Superadmin action and requires the existing fresh-session / re-authentication guard in addition to `IsSuperAdmin`. The response uses `Cache-Control: no-store`.

Every successful export creates the canonical `superadmin.export.created` audit event with `export_kind=audit_csv` and a correlation export ID. The export event is written after the exported event snapshot is materialized, so it is not recursively included in its own CSV.

## Privacy and spreadsheet safety

The CSV serializes only fields already exposed by the bounded Audit Explorer. `details` is built from the same fixed allow-list; raw metadata and `identifier_hash` are excluded. Private family content, tokens and credential material are never exported.

Cells beginning with spreadsheet formula sigils (`=`, `+`, `-`, `@`) are prefixed before CSV serialization to avoid formula execution when opened in spreadsheet software.
