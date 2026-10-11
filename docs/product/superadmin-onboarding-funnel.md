# Superadmin onboarding invite funnel

Issue: #205 (roadmap #223)

## Existing endpoint

The existing `GET /api/superadmin/analytics/overview/?period=...` response gains an additive `onboarding` section. No new route is introduced.

## Cohort definition

The funnel is based on canonical #204 audit events that share `target_type=invite` and the same invite UUID as `target_id`.

For a selected period, the cohort contains invites with `invite.created` inside that period. Funnel stages are counted only when the matching event for the same invite UUID also occurs inside the selected period. The immediately preceding period of equal length is calculated with the same rule.

Reported stages:

- created
- SMTP sent
- accepted
- email failed
- expired
- revoked

`send_to_accept_rate_pct` is accepted invites divided by sent invites in the same created-in-period cohort. A zero denominator returns `null`.

`median_seconds_to_accept` is the median elapsed time between `invite.created` and `invite.accepted` for accepted invites in the cohort. No value is returned when nothing was accepted.

Owner invitations are reported separately using the canonical allow-listed `role=owner` metadata. Expired/revoked owner-only counts are deliberately omitted because those terminal event keys do not carry role metadata in the canonical telemetry contract.

## Measurement limits

The dashboard does **not** report email-open or read rates. There is no privacy-safe canonical open/read event, and SMTP `sent` must not be presented as proof that a person read a message.

This first bounded slice also does not yet claim account-registration, email-verification, first-meaningful-activity, activation-version or retention stages; those require separately defined join semantics rather than inferred correlations.

## Privacy boundary

Only aggregate counts, rates and durations are returned. Invite UUIDs, invite email addresses, tokens, message content, recipient hashes and private family content are never serialized by the overview response.

The cohort rule is intentionally explicit because invites created near the end of a period may be right-censored when acceptance occurs after the window. The UI must expose the definition rather than present the metric as an all-time conversion probability.
