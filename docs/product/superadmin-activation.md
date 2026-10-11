# Superadmin activation and engagement metrics

Issue: #205 · Roadmap: #223

## Rolling engagement

The existing Superadmin analytics overview exposes fixed rolling engagement windows anchored at `period.end`:

- DAU: distinct users with canonical `activity.foreground` in the previous 1 day
- WAU: distinct users in the previous 7 days
- MAU: distinct users in the previous 30 days
- active families in the previous 7 and 30 days

Each value compares against the immediately preceding equal-length window only when raw usage retention covers that entire comparison. Missing history is returned as `null` with an explicit coverage flag, never as a synthetic zero.

## Activation definition `invite_new_account_v1`

A cohort row starts with canonical `invite.accepted` telemetry and is considered a **new-account invite acceptance** only when the accepting account was created no more than one hour before acceptance. Existing accounts that join another family are reported as excluded from this activation cohort rather than mixed into it.

The account is activated when both conditions happen within seven days after invite acceptance:

1. canonical `auth.email.verified` for the same user;
2. canonical `activity.foreground` for the same user in the accepted family.

Only rows whose full seven-day observation window has elapsed enter the activation-rate denominator. Younger rows remain `pending_maturity`.

The response contains aggregate counts, activation rate and median time to activation only. User IDs, invite IDs, emails, family content and raw event metadata are never serialized.

## Forward-only coverage

`auth.email.verified` was originally defined in the telemetry catalog but not emitted. The activation metric therefore has an explicit instrumentation start. Cohorts before that timestamp are not treated as complete historical measurements.

For any requested period the effective measurable cohort start is the latest of:

- requested cohort start;
- email-verification instrumentation start;
- the raw-event retention cutoff shared by required audit/usage sources.

The API exposes whether coverage is complete or partial and why. Until the instrumentation start is configured, activation is fail-closed with `available=false` and null rates.

## Retention is deliberately separate

Current daily rollups preserve aggregate active-user/family counts but not signup-cohort identity. That is sufficient for DAU/WAU/MAU, but not for honest D1/D7/D30 cohort retention across long periods after raw events have expired.

Retention/cohort persistence therefore remains a separate #205 slice; this implementation does not reconstruct or estimate unavailable cohort history.

## Privacy and governance

These metrics use only #204 canonical audit/usage telemetry and account creation timestamps. They do not query task titles, calendar items, shopping data, messages, documents, mail/push bodies, credentials, tokens, IP history or free-form family content.
