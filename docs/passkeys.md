# Passkeys / WebAuthn

This document describes the FamilyOS Passkey/WebAuthn implementation for roadmap issue #201.

## Architecture

Passkeys are an authentication method on top of the existing FamilyOS security cores:

- `auth_identity` remains the canonical account identity.
- `auth_sessions` remains the only login/session system. A successful passkey login creates the same revocable `AuthSession` as password login with `auth_method=passkey`.
- `auth_abuse` remains the only rate-limit implementation. Passkey endpoints consume the existing `login.passkey.*` and `webauthn.registration.options` scopes.
- `telemetry` receives only allow-listed audit events and aggregate authentication method counts; credential material never enters analytics.
- `mailing` queues the existing `passkey.added` / `passkey.removed` security notifications and links back to the user's Security Center without storing a WebAuthn credential ID in mail metadata.
- WebAuthn private keys and biometric material never reach FamilyOS. The server stores only the credential ID, public key, sign counter and minimal lifecycle metadata.

The server library is pinned to `webauthn==2.8.0` (Duo Labs `py_webauthn`) rather than implementing WebAuthn cryptography locally. This release is intentionally selected because it is compatible with the repository's existing `cryptography>=46,<47` security stack.

The browser uses the standardized WebAuthn API directly. `frontend/src/passkey-api.js` prefers the native `PublicKeyCredential.parseCreationOptionsFromJSON()` / `parseRequestOptionsFromJSON()` helpers and has a small dependency-free base64url fallback for compatible browsers that do not expose those helpers yet.

## Configuration

Passkeys are disabled until the deployment opts in:

```env
WEBAUTHN_ENABLED=true
WEBAUTHN_RP_ID=familyos.example.com
WEBAUTHN_RP_NAME=FamilyOS
WEBAUTHN_ORIGIN=https://familyos.example.com
WEBAUTHN_CHALLENGE_TTL_SECONDS=300
```

`WEBAUTHN_ORIGIN` may be omitted when `APP_URL` is the canonical browser origin. `WEBAUTHN_RP_ID` may equal the origin host or a parent domain of it. Wildcards are rejected. HTTP is accepted only for localhost development; non-local deployments require HTTPS.

`python manage.py check` reports configuration errors whenever WebAuthn is enabled with an invalid origin/RP relationship.

### Existing installations

After updating an existing installation, configure and enable Passkeys from the already configured public app URL:

```bash
./scripts/configure-passkeys.sh
```

The helper reads `APP_URL` (or falls back to `PUBLIC_SCHEME` + `PUBLIC_HOST`), derives the RP ID from its hostname, preserves an already configured compatible parent RP ID plus the RP name/challenge TTL, creates a timestamped `.env.backup.passkeys.*` before changing anything, and writes the five `WEBAUTHN_*` values idempotently. It refuses non-local plain HTTP and IP-address origins because they cannot produce a valid production WebAuthn RP configuration.

For a non-default env path, use `ENV_FILE=/path/to/.env ./scripts/configure-passkeys.sh`. The script prints the `manage.py check` and container restart commands after a successful update.

## User experience

The normal login screen offers **Mit Passkey anmelden / Sign in with a passkey** before the password form. It is discoverable/passkey-first and does not require an email address. Password login remains available during rollout and legacy login remains a separate migration path.

The Profile security area contains the Passkey management surface:

- list active passkeys with name, creation date, last use and coarse backup state;
- add and name multiple passkeys;
- rename an existing passkey;
- explicitly remove a passkey;
- use a passkey or password for fresh re-authentication before sensitive account changes.

Browser cancellation is treated as a normal status rather than a system failure. Unsupported/insecure contexts, rate limiting and disabled WebAuthn configuration have separate user-facing states. The new surface ships with DE/EN copy and uses the existing keyboard/screen-reader-friendly controls.

## API

All responses use browser-compatible JSON options. Challenges are random, short-lived and single-use.

- `GET /api/auth/passkeys/` — list the current user's active credentials.
- `POST /api/auth/passkeys/registration/options/` — create registration options; requires a fresh authenticated session.
- `POST /api/auth/passkeys/registration/verify/` — verify and persist a new credential; requires a fresh authenticated session.
- `POST /api/auth/passkeys/authentication/options/` — create discoverable/passkey-first login options without account enumeration.
- `POST /api/auth/passkeys/authentication/verify/` — verify the assertion and issue the canonical FamilyOS access/refresh cookies.
- `POST /api/auth/passkeys/reauth/options/` and `/verify/` — phishing-resistant fresh re-authentication for an already authenticated session.
- `PATCH /api/auth/passkeys/<id>/` — rename a credential; requires fresh authentication.
- `DELETE /api/auth/passkeys/<id>/` — revoke a credential; requires fresh authentication and refuses to remove the final login method from a passwordless account.

Credential identifiers and public keys are never returned by list/detail APIs.

## Audit, security mail and aggregate telemetry

Successful Passkey login records the canonical `auth.login.succeeded` event with `auth_method=passkey`; invalid assertions record `auth.login.failed` without credential material. Registration and removal record `auth.passkey.registered` / `auth.passkey.removed`. Rate-limited ceremonies use the existing `auth.rate_limited` audit key.

Registration and removal enqueue transactional security mail to the canonical account address. The queue stores only the normal user reference for the Security Center link; the WebAuthn credential ID and public key are not added to mail context.

The existing Superadmin security summary therefore exposes privacy-safe aggregate Passkey login share and lifecycle-event counts. It never returns credential IDs, public keys, challenges, request payloads or biometric/device-fingerprint data.

## Privacy and security properties

Registration requires resident/discoverable credentials and user verification. Authentication and re-authentication require user verification as well. Public login options intentionally do not enumerate an account or return an allow-list; the submitted credential ID is resolved only during verification.

Every challenge is claimed atomically before cryptographic verification, so a failed or successful verification cannot replay the same challenge. Cross-user re-authentication is rejected by binding the challenge and credential lookup to the current user.

The implementation stores no IP history, attestation trust profile, biometric data or device fingerprint. `device_type`, backup state and transports are kept only as coarse WebAuthn lifecycle hints.

## Tests and migration safety

Backend coverage includes configuration/origin checks, one-time and expired challenges, lockout protection, lifecycle audit events and security-mail queueing. Playwright uses Chromium's CDP Virtual Authenticator to exercise the actual browser flow: authenticated user → add resident passkey → leave the session → discoverable passkey login.

Migration `auth_passkeys.0001_initial` remains additive: it creates only passkey credentials and transient WebAuthn challenges. The UI completion does not change that schema. CI has an explicit `auth_passkeys` migration-drift gate (`makemigrations --check --dry-run`) plus a full `migrate && check`, so future model changes cannot silently land without a migration.

## Rollout and rollback

Existing password login, identities and sessions are unchanged. Enable WebAuthn only after the canonical browser origin/RP ID is configured and HTTPS is working for the deployment.

Rollback remains safe while password/recovery access is available: disable `WEBAUTHN_ENABLED` to stop new ceremonies. Existing password sessions and identity/recovery flows continue to work; the additive credential tables can remain in place for rollback without destructive schema work.
