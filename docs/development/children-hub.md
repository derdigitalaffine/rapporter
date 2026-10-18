# Children Hub delivery #807

## Canonical contracts

BabyProfile remains the child context over the existing User/Membership/UserProfile
identity. Existing-child attachment preserves credentials. Active, confirmed
FamilyRelationship custody is full per-child authority, including Care Circle.
Existing legacy Guardian records are compatibility only, not inferred legal custody.
Owner/Adult, parenthood and module activation do not create child authority.

CareCircleAccess gains an optional baby FK. Null rows preserve existing family grants;
scoped rows can delegate care/development, never pregnancy or account management.
Effective permissions are projected in a bounded-query module/profile discovery.
Every endpoint rechecks authority server-side, including private media and event links.
Care Circle writes require Fresh Reauth and transactional strict audit. The only new
audit key is baby.care_circle.changed with scope metadata, no names or health content.

## API and consistency

- GET/POST /api/baby/profiles/:id/health/: neutral reference/history projection and
  versioned record writes. Bulk entries are atomic, unique-keyed and limited to 100.
  expected_version is mandatory; conflicting writes return 409. An identical retry
  after a lost response succeeds. Published source snapshots remain on saved records.
- GET/PUT /api/baby/profiles/:id/care-circle/: derived readonly authorities, scoped
  delegations and inherited global grants. Cross-family/scoped-right escalation denied.
- GET /api/baby/health-events/:event/: authorized child resolution without exposing a
  child identifier in the public FamilyEvent payload. Generic event titles only.
- Existing managed-child creation accepts optional membership and custody_for_self.
  Explicit initial custody is Owner-only, Fresh Reauth and atomic audit; retries never
  reactivate an existing revoked relationship. No implicit custody on birth/create.

Health records are documentation, not a new clinical/risk, calendar or reminder core.
Only explicit planned state creates/updates a canonical FamilyEvent. Recording done,
unknown or later does not cancel an independent calendar appointment. Calendar owns
reschedule/cancellation; central reminders and reference publication remain in #238.
No GET-time backfill, historical alarm flood, invented STIKO data or automated decisions.
Day boundaries use the family's timezone. No extra offline queue or sensitive telemetry.

## UI and navigation

The existing lazy baby feature owns baby/view/event URL parameters. Existing navigation
helpers and Global Create are reused. FamilySheet consumes Base UI; FormField,
ChoiceField, ProgressiveFieldGroup and FormActions consume the shared form contract.
HealthEditor is a StandardEditor; child creation is the existing create action.
Per-child permissions override aggregate module flags. Invalid requested children fail
closed instead of falling back to a sibling. Child/family changes invalidate stale reads.
Older-child lifecycle changes presentation only, never identity or membership role.

## Migration and rollback

Baby 0005 adds scoped grants and ChildHealthRecord, preserving all legacy rows and
identities. Conditional uniqueness separates global and per-child grants. Baby 0006
expands preventive provenance keys to support vaccine dose identifiers.

Rollback the UI independently while **retaining the scoped backend and schema**.
An old unscoped backend is unsafe once multiple grants exist for one membership.
The reverse migration explicitly refuses to drop health records/scoped grants; export,
reconcile and obtain an explicit destructive-data decision before schema contraction.
No automatic deletion/backfill or claim of a lossless schema downgrade.

## Verification and remaining gates

Dedicated children-hub-regressions runs the complete baby backend suite plus shared
custody/calendar and child relationship privacy regressions, migration
drift/migration/system checks, desktop/mobile domain E2E, sibling/delegation/deny/error
flows and 320/390/1024/1440 English axe/overflow/screenshots. Production-backed Children
stories join the existing Workbench viewport, reduced-motion and a11y matrix.
No local Chromium installation or execution. CI results and exact head belong in the PR.

Real virtual-keyboard, VoiceOver/TalkBack and genuine browser 200% zoom acceptance
remain #773. Automated screenshots are not physical acceptance. #753, #235 and #238
remain open for their broader scope. General CI #599 is evaluated independently;
focused green jobs do not establish a globally green release.
