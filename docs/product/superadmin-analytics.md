# Superadmin analytics overview

The first #205 analytics slice exposes a privacy-minimized overview at:

`GET /api/superadmin/analytics/overview/?period=30d`

Supported periods are `24h`, `7d`, `30d`, `90d`, and `365d`. The endpoint is restricted to superadmins and uses the canonical telemetry data from #204.

## Metric definitions

- **Active user**: authenticated user with at least one `activity.foreground` usage event in the selected period.
- **Active family**: family with at least one `activity.foreground` usage event in the selected period.
- **Verified email user**: user with a verified primary `EmailIdentity`.
- **New users / families**: records created within the selected time window.
- **Comparison**: the immediately preceding period with the same length.
- **Percentage change**: omitted as `null` when the previous value is zero; no artificial infinity or 0/0 percentage is displayed.
- **Daily series**: reads the global `DailyRollup` rows for distinct active users and families. It does not scan private family content.

The response intentionally contains counts, internal time boundaries, and metric definitions only. It does not include task names, calendar content, document data, notification bodies, passkey material, tokens, entered login identifiers, or other private family content.

## Scope

This slice establishes the overview contract only. Later #205 slices can add dedicated timeseries, security, delivery, operations, audit, cohort, retention, and drill-down endpoints without turning this endpoint into a monolithic payload.
