# Superadmin activation and retention

Issue: #205 (roadmap #223)

## Activation definition `membership-v1`

Activation is measured per accepted family membership, using `FamilyInvitation.accepted_at` as the cohort timestamp.

A membership is activated when all of the following are true:

1. the invitation has been accepted by an account,
2. that account has a verified primary `EmailIdentity` no later than seven days after acceptance,
3. the same user emits at least one canonical `activity.foreground` usage event in the same family within seven days after acceptance.

The selected period defines the `accepted_at` cohort. Counts and activation rate are compared with the immediately preceding equal-length period. The definition is explicitly versioned so future product changes do not silently rewrite historical meaning.

This definition does not use page requests, SMTP delivery or mail-open tracking as a proxy for activation.

## Returning activity / retention

User retention uses account `date_joined` as the cohort timestamp and family retention uses `Family.created_at`.

Reported horizons:

- users: D1 / D7 / D30
- families: D7 / D30 / D90

A subject is retained at day N when at least one canonical `activity.foreground` event occurs inside the exact UTC interval `[cohort + N days, cohort + N + 1 days)`.

Only subjects old enough for the complete observation interval are eligible for a horizon. This prevents young accounts/families from being counted as false non-retained cases.

For non-empty mature cohorts smaller than five, `eligible` and `retained` counts remain visible but `rate_pct` is `null` and `small_cohort_suppressed=true`. This avoids misleading precision on tiny samples.

## Privacy boundary

The endpoint returns aggregates only. It does not serialize user IDs, family IDs, email addresses, invite IDs/tokens, event rows, request metadata, content titles/bodies or any private family-domain content.

Activity is sourced from the canonical telemetry model introduced by #204; identity verification and membership acceptance use their canonical domain state rather than reconstructed request logs.

## Remaining analytics work

This slice intentionally does not add weekly/monthly cohort tables, custom/all-time date ranges, global family/auth/locale filters or frontend visualization. Those remain separate bounded #205 work so the metric definitions can land and stabilize independently.

## Snapshot and query budget

Activation ignores verification/activity timestamps after the selected observation snapshot, including a future-dated canonical row. Current and previous cohorts therefore cannot borrow observations from after their respective period ends. Each activation cohort and each retention cohort/horizon uses one conditional aggregate query; query count is independent of the number of subjects. No per-subject queries or identifiers are emitted.

Retention eligibility is additionally limited to complete observation windows inside `TELEMETRY_USAGE_RETENTION_DAYS` (default 60). Older signup subjects whose day-N observations may have been purged are excluded rather than counted as non-returning. The response exposes configured retention days, the observation cutoff, and the coverage definition. A 90d/365d selection therefore measures only the observable mature subset, not an exhaustive historic retention claim.
