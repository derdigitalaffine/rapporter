# Passkeys / WebAuthn

This document describes the first server-side Passkey/WebAuthn slice for roadmap issue #201.

## Architecture

Passkeys are an authentication method on top of the existing FamilyOS security cores:

- `auth_identity` remains the canonical account identity.
- `auth_sessions` remains the only login/session system. A successful passkey login creates the same revocable `AuthSession` as password login with `auth_method=passkey`.
- `auth_abuse` remains the only rate-limit implementation. Passkey endpoints consume the existing `login.passkey.*` and `webauthn.registration.options` scopes.
- WebAuthn private keys and biometric material never reach FamilyOS. The server stores only the credential ID, public key, sign counter and minimal lifecycle metadata.

The server library is pinned to `webauthn==3.0.1` (Duo Labs `py_webauthn`) rather than implementing WebAuthn cryptography locally.

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

## Privacy and security properties

Registration requires resident/discoverable credentials and user verification. Authentication and re-authentication require user verification as well. Public login options intentionally do not enumerate an account or return an allow-list; the submitted credential ID is resolved only during verification.

Every challenge is claimed atomically before cryptographic verification, so a failed or successful verification cannot replay the same challenge. Cross-user re-authentication is rejected by binding the challenge and credential lookup to the current user.

The implementation stores no IP history, attestation trust profile, biometric data or device fingerprint. `device_type`, backup state and transports are kept only as coarse WebAuthn lifecycle hints.

## Rollout and rollback

Migration `auth_passkeys.0001_initial` is additive: it creates only passkey credentials and transient WebAuthn challenges. Existing password login, identities and sessions are unchanged.

Rollback is safe while password/recovery access remains available: disable `WEBAUTHN_ENABLED`, remove the passkey routes/app, and reverse the additive migration. Disabling WebAuthn immediately prevents new ceremonies without invalidating existing password sessions.

## Follow-up scope

This merge slice intentionally does not close #201. The remaining issue work is the Security Center/Login frontend (including browser cancellation/accessibility states), security-mail/audit presentation, adoption telemetry, and browser E2E with virtual authenticators.
