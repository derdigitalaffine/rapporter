# Children Hub deliveries #807 / #868

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
Existing preventive events are projected without writes using their original immutable
provenance. FamilyEvent.starts_at is canonical on reads. Planned edits send the observed
event_starts_at; a locked comparison rejects stale calendar dates with 409. Identical
lost-response retries remain safe and unrelated calendar payload fields are preserved.
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

## Navigation / opt-in reminder follow-up #868

The lazy registry adds `pregnancy` (family/view selectors); `baby` remains the Children
route with existing child/event selectors. Legacy `baby&view=pregnancy` remains usable.
Both route adapters use the same existing module/identity/permission APIs. The in-app
back button explicitly navigates to the feature overview, then More, never history.back.
Pregnancy reads do not preload children, and Children does not preload pregnancy contents.

POST `/api/baby/profiles/:id/health/reminders/` accepts unique entries (1..100), each with
key, expected_version and reference_checksum, plus explicit future remind_at. It locks
the BabyProfile and rechecks development permission. Only open current/future published
vaccination references are accepted. Historical/done/planned/stale/foreign selections fail
atomically. One canonical Task serves the whole selection, with generic title, no notes
or clinical source/deep link, assigned to the requesting member. Baby 0007 adds only the
private nullable ChildHealthRecord.reminder_task FK. Idempotent retries return existing
links; changing an existing reminder is a Task operation, not silent rescheduling.
Task completion and clinical documentation remain separate. No new push scheduler,
notification preference, Task model or local health persistence is introduced.

Rollback UI first and retain 0007 while needed: its reverse guard refuses to drop private
associations until explicitly reconciled. Generic Tasks and clinical records survive. Task deletion sets the
link null. Child removal does not delete shared Tasks. Published vaccine-only packages
retain the explicit bundled U-exam fallback; they no longer hide all check-ups.

The module GET projects a minimal active_pregnancy only when the separate pregnancy
permission is present. Today registers an optional health-sensitive pregnancy widget,
off by default, without reordering existing layouts. Its consumer revalidates on mount,
focus, visible-day polling and auth changes, never persists clinical values and clears
old contents during revalidation/errors/family changes. The Today layout contains only
widget presentation settings. Source package metadata is displayed as recorded; never
label a synthetic test package as verified STIKO or assert an unverified latest year.

Fresh official STIKO/competitor research is blocked by the current environment egress
policy (CONNECT 403). Required domains were saved as an environment draft for review
and publication. No new medical payload is bundled, seeded or auto-published. Completing
that content acceptance requires verified official sources and the existing superadmin
draft/validate/publish workflow. This limitation is a merge/release consideration, not a
claim that a newly dated official dataset has been researched or delivered.

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

The focused navigation gate selects the two changed optional-care-module cases in
more-page.spec.js. The complete file still runs in general CI, including older To-do
expectations outside this delivery. No unrelated test is deleted or skipped. The new
backend job uses the official Docker Hub PostgreSQL image after ECR pulls repeatedly
failed before test execution; it retains PostgreSQL and all migration/test assertions.
