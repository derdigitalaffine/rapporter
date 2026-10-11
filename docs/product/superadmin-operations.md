# Superadmin operations health

Issue: #205 (roadmap #223)

## Endpoint

`GET /api/superadmin/operations/health/`

Access is restricted by the existing `IsSuperAdmin` permission. The response is a request-time operational snapshot and returns only aggregate, non-secret health metadata. It does not mutate queues, migrations, integrations, telemetry, or worker state, and it does not retain a server-side dashboard snapshot.

## Reliable sources

The first bounded slice reports:

- database reachability via a minimal `SELECT 1`
- Django migration state and bounded pending migration names
- enabled integration count, degraded integration count and latest successful sync timestamp
- transactional mail backlog/status counts, delivery latency aggregates, last success and redacted error classes from the existing mail health contract
- latest audit/usage telemetry timestamps plus latest DailyRollup day/update and observed ages

Component states use `healthy`, `degraded`, `failing`, or `unknown` with a stable machine-readable reason.

## Unknown is intentional

The current repository has no canonical persisted heartbeat source for scheduler, notification worker, mail worker, or OCR worker. Those worker states therefore return `unknown` / `no_canonical_heartbeat_source`. The endpoint must not infer `healthy` from process assumptions, queue emptiness, or absence of errors.

A later slice may replace an `unknown` worker component only after that worker exposes a reliable canonical heartbeat contract.

## Privacy boundary

The endpoint never serializes integration endpoint/config values, SMTP credentials, recipients, mail context/body, notification content, tokens, push keys, or private family content. Database/migration exceptions are reduced to stable reason codes rather than raw exception strings.

## Deliberate omissions

- App version/commit is omitted until build metadata is exposed through a canonical runtime source.
- Storage/DB size is omitted until a reliable cross-deployment source exists.
- No arbitrary shell/process inspection is performed by the request handler.
