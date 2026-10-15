# Offline-first operational notes

## Components introduced by the program

- PostgreSQL sync journal and mutation-idempotency records
- `/api/sync/`
- versioned IndexedDB local domain store
- ASGI + Django Channels + Redis live wake-up transport

## Journal retention

Target retention is 90 days. Pruning must never remove entries newer than the documented retention boundary and must preserve the ability to detect stale cursors. Clients older than retained history recover through snapshot mode.

## Failure behavior

- Redis unavailable: WebSocket wakeups degrade; normal HTTP sync remains authoritative.
- WebSocket unavailable: startup/online/foreground/manual sync remains authoritative.
- authentication expired: local writes continue; network sync pauses until re-authentication.
- sync request interrupted: client retries with the same mutation IDs.
- server committed but response was lost: idempotency returns the prior semantic result without repeating side effects.
- client cursor too old: preserve local outbox and install a fresh snapshot.

## ASGI / Redis deployment

The standard Compose topology runs Django through Daphne/ASGI and adds a transient Redis 7 service. Redis contains wake-up messages only; it is not a database and does not need persistence. The channel layer uses `OFFLINE_REDIS_URL` (default `redis://redis:6379/0`) when `OFFLINE_LIVE_ENABLED=true`.

Caddy's existing reverse proxy supports WebSocket upgrades on `/ws/sync/<family>/`; no separate public port is required. WebSocket authentication reuses the application JWT cookie and checks active family membership before joining the family channel group. Messages contain only `sync_available`, the family id, and a cursor hint. Domain payloads and writes never travel over WebSocket.

### Safe rollback

Set `OFFLINE_LIVE_ENABLED=false` or remove Redis availability and redeploy. Clients continue to converge through the same startup, online, foreground and manual HTTP sync triggers. Because the live layer has no schema and stores no authoritative data, rollback requires no data migration and must not clear IndexedDB/outbox state.

### Redis outage

Do not reset clients or PostgreSQL. Restore Redis when convenient; missed wake-ups are harmless because HTTP sync compares cursors. Post-commit publication is best-effort and cannot roll back a committed domain mutation.

## Deployment rule

Roll out core delta sync before enabling WebSocket live transport. Do not make correctness depend on Redis or Channels.

## Privacy rule

Explicit logout/account switch clears account-scoped private offline entities, outbox, conflicts, cursor state, live leader leases/channels, and private cached shell metadata on the client.

## Diagnostics to expose/log

Without logging sensitive field payloads unnecessarily, diagnostics should make it possible to determine:

- account/family scope identifier where safe for server logs
- client protocol version
- starting/ending cursor
- mutation count and result statuses
- snapshot/reset occurrence
- conflict count
- server processing duration
- journal prune boundary
- live transport enabled/disabled and connection/takeover state without domain payloads

## Recovery principles

Prefer replay/idempotency and snapshot recovery over destructive client resets. Never instruct users to clear browser storage as the primary recovery mechanism while pending offline work may exist.

## Retention job and stale clients

Run daily through the host's existing scheduled-job mechanism:

```bash
docker compose exec -T backend python manage.py prune_sync_journal --dry-run
docker compose exec -T backend python manage.py prune_sync_journal
```

The command enforces a minimum of 90 days (`--days` may increase it). It takes
exactly the same sequence lock as domain writes, deletes only an expired cursor
prefix, and updates `retained_after` in the same transaction. Recent entries are
preserved even across timestamp/clock reversals. Repeating the command is safe.
Dry-run never changes journal rows or the reset boundary. The command does **not**
remove processed mutation receipts: an old retry must remain idempotent.

A client behind the retained boundary receives a snapshot with `snapshot_cursor`.
Its pending mutations are processed through the same authorization/version checks;
local outbox and true conflicts survive base replacement. Missing retained field
history produces a conflict rather than an unproven automatic merge.

## Recovery runbook

1. Keep IndexedDB and pending drafts intact. Never start by clearing browser data.
2. Check the account/family and the synchronization sheet: pending work, expired
   login, field conflicts and low storage are distinct states.
3. For expired authentication, sign in again as the same account, then synchronize.
   Explicit sign-out is destructive to that account's private local drafts.
4. Restore HTTP/API/PostgreSQL first. Retrying uses stable mutation IDs, including
   when the server committed but its response was lost.
5. For stale cursors, allow automatic snapshot recovery; do not manually advance
   the client cursor. If a server journal transaction fails, fix its database or
   migration error and retry the entire transaction.
6. For a conflict, compare the preserved local and server values in Synchronization.
   Keep the server value, retry the local change against the returned version, or
   copy a deleted/unavailable draft before explicitly discarding it.
7. Restore Redis later. It contains no authoritative records. A WebSocket close
   reconnects on a leader heartbeat; online/resume/manual HTTP works independently.
8. For low storage, free unrelated device space, reopen the app and retry. Do not
   delete the FamilyOS origin while pending drafts remain.

## Local upgrades and rollback

IndexedDB v2 adds ordered outbox lookup. The additive upgrade backfills only missing
local ordering metadata; mutation IDs, attempted/sending state, payloads, conflicts,
account/family scopes and cursor data remain unchanged in the upgrade transaction.
An unsupported future database version fails with VersionError and is never wiped.
After v2 activation, rolling back to a v1-only client requires a forward-compatible
client or exporting/draining pending work first; do not downgrade by deleting the DB.
Application assets and the service-worker build change independently of private data.

## Optional browser capabilities

Persistent storage is requested best-effort after login; browsers may deny it.
Storage diagnostics tolerate unavailable/denied APIs and show a low-space warning
at 90% usage. A stored draft is reported saved only after its IndexedDB transaction
commits; quota failure must leave entity/outbox/cursor unchanged.

Background Sync registers `familyos-outbox-v1` where supported. Its worker only
wakes open window clients, which use their active account and normal authenticated
HTTP engine. It stores no tokens, fetches no private API data, and never clears or
acknowledges an outbox itself. With all windows closed, synchronization resumes on
next app startup. Browsers without Background Sync retain online/resume/manual sync.

Explicit logout/account switch stops writers before cleanup. Other tabs react to
the shared account-key change, stop the old account's engines, clear its private
stores and reload; they do not erase a newly selected account's bootstrap.

Legacy `famuhle-offline-v1` queues were not account-scoped and are never silently
assigned to the new account. Existing pre-cutover records remain untouched until
explicit logout. For an installation upgrade, finish its old pending queue on the
old client before switching accounts/upgrading; do not clear its origin as recovery.

## Live Sync behind Nginx Proxy Manager

For the standard `Nginx Proxy Manager → FamilyOS Caddy → Daphne` deployment:

1. Select **Websockets Support** for the NPM Proxy Host and save it. Forward the
   host to the normal FamilyOS HTTP port; no separate public WebSocket port is
   required. TLS terminates at NPM; the public browser URL remains HTTPS.
2. Use `CADDYFILE=Caddyfile.proxy`, `PUBLIC_SCHEME=https` and
   `PUBLIC_HOST=<your public hostname>`. Include that exact public hostname in
   `DJANGO_ALLOWED_HOSTS` (without scheme or path). Keep origin validation enabled.
3. Keep `OFFLINE_LIVE_ENABLED=true`, `OFFLINE_REDIS_URL=redis://redis:6379/0` and a
   healthy Redis/backend. Compose already supplies these live defaults. Daphne is
   the shipped ASGI server; a WSGI-only replacement cannot serve `/ws/sync/`.
4. Update the deployment to a revision containing #742, then restart/recreate
   Caddy after changing its mounted Caddyfile, e.g. `docker compose up -d --build
   backend caddy`. Earlier Caddyfiles omitted `/ws/*`, so NPM's toggle alone did
   not fix the internal routing.
5. In browser Network → WS, `/ws/sync/<family-id>/` should upgrade with **101** and
   remain open. A 200 HTML response suggests the SPA fallback; 403 suggests
   cookie/session/family/origin validation; 502 suggests an upstream problem.
   Use status codes and sanitized logs; never paste session cookies into issues.

The shipped CSP explicitly permits WSS to the current host (including its port),
because `connect-src 'self'` does not cover WebSocket schemes in every browser.
The external proxy must preserve the browser's public Host header.

Caddy's reverse_proxy handles the WebSocket upgrade automatically once `/ws/*`
is routed to Daphne. NPM must preserve `Upgrade` / `Connection` upstream; the UI
Websockets Support option supplies this contract. Custom advanced snippets should
not duplicate generated directives. Match the configured public host to the
browser origin rather than disabling `AllowedHostsOriginValidator`.

An idle external proxy may close a socket according to its timeout; it should
reconnect. A permanently interrupted connection has a different cause. The
30-second authoritative HTTP fallback continues to synchronize while Live is
unavailable. Do not describe polling as an active Live connection.

CI `live-proxy` proves a cookie-authenticated HTTP101 handshake and Redis wakeup
through real Nginx and the shipped Caddy.proxy into Daphne, including rejection
of anonymous, wrong-origin and unknown-family handshakes. This exercises the NPM
upgrade-header contract; it does not claim to inspect an owner's NPM instance.

Primary references:
- https://caddyserver.com/docs/caddyfile/directives/reverse_proxy
- https://github.com/NginxProxyManager/nginx-proxy-manager/blob/develop/backend/templates/proxy_host.conf

- https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/connect-src
