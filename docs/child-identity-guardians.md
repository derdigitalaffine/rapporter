# Child Identity, Sorgerecht & Legacy Guardian compatibility

FamilyOS treats a child as a durable family identity, not as a Baby-module record or a future login that has to be merged later.

> **Policy since #717:** active, explicitly recorded `FamilyRelationship.has_custody=true` is the canonical domain source of the protected child and health authority that older code called *Guardian* authority. `Guardian` remains a technical compatibility term only.

## Canonical identity

A managed child uses the existing Django `User`, `Membership(role=child)`, `UserProfile` and `BabyProfile.membership` relation. The initial user has an internal technical username, no email address and an unusable password. Birth from `PregnancyBaby` and manual creation both keep the same contract and use a stable identity key for idempotence.

Turning the Pregnancy & Baby module off does not remove any of these identity records. Permanently deleting Baby tracking data is a separate destructive action and must not be used as an account lifecycle operation.

## Creating a child from Family

Family owners and adults can create a managed child directly from **Family → Members → Add → Child without own access**. The only required profile data is the child's display name and birth date. This flow does not create an invitation, require an email address or enable authentication.

Creating a child does **not** infer a family relationship, parenthood, legal parenthood or custody. It also does not create a new `ManagedChildGuardian` grant. Product-level permission to create the child profile is not proof of legal custody and therefore must not silently grant protected child authority.

Once an Owner records an active relationship with `has_custody=true`, that already stored custody fact is effective immediately. No Guardian backfill, second confirmation or manual Guardian assignment is required.

## Familienbeziehungen / patchwork model

`FamilyRelationship` describes one concrete child's relationship to one existing membership in the same family. Different children may therefore have different relationships to the same adult.

The model keeps independent facts for relationship kind, biological parenthood, legal parenthood, custody (`true`, `false`, or not recorded), active/inactive status and child visibility.

Relationship labels, biological parenthood, legal parenthood and family role do not imply custody. **Only an active `has_custody=true` relationship to an Owner/Adult membership activates the protected child-authority policy.** Inactive custody rows do not grant authority.

Owners may create and edit relationship facts. Adults cannot self-assert custody through this endpoint. Cross-family child or related-membership identifiers are rejected server-side.

Because custody now changes sensitive authorization, creating, changing, activating or deactivating an effective custody grant requires a fresh authenticated session. Custody changes are recorded through the security audit contract using an opaque relationship target; health payloads and free text are not included in that audit event.

## Effective child authority

The central authorization helper resolves protected child authority in this order:

1. active `FamilyRelationship.has_custody=true` for that child and actor membership — canonical source;
2. an existing `ManagedChildGuardian` row — legacy compatibility only;
3. the pre-existing Care-Circle Guardian fallback for legacy records where no explicit Guardian row exists.

A custody-derived authority is evaluated dynamically. Existing data therefore becomes effective without a migration that copies custody into `ManagedChildGuardian`.

`Owner`, `Adult`, parent/legal-parent relationship or ordinary Care Circle membership alone do **not** grant the protected authority. A Care Circle remains an independently delegated, potentially narrower Pregnancy/Baby permission contract.

## Legacy Guardian compatibility

`ManagedChildGuardian` is retained during the Expand → Migrate → Cutover → Contract transition so existing installations do not lose access unexpectedly. An old Guardian row without custody remains a legacy access fact; FamilyOS does **not** silently convert it into a legal custody statement.

The legacy Guardian write endpoint remains available only for compatibility management. It may update existing legacy rows, but it must not be used to create new protected authority for a person who has neither an existing legacy grant nor custody. New authority is established through explicit custody instead.

`GET /api/baby/guardian-settings/?family=<family-id>` remains a privacy-minimal compatibility projection. It marks effective rows with their source (`custody` or `legacy_guardian`) and does not expose birth, medical, growth or development payloads. The Settings UI is read-only for this projection; users manage the canonical fact under the child's **Familienbeziehungen → Sorgerecht**.

There is no longer an Owner bootstrap that can create the first Guardian merely because a child has no authority rows. Owner role permits maintaining the custody fact, subject to fresh re-authentication, but Owner role alone is not child authority.

## Health, care and appointments

Care, growth, development, preventive-care and report flows consume the centralized child-scope authorization. A custody holder therefore receives the protected rights previously supplied by Guardian authority without needing a `ManagedChildGuardian` or `CareCircleAccess` row.

Existing Care Circle permissions remain usable for explicitly delegated narrower access where the domain supports them. They do not assert custody.

Preventive appointment materialization uses the same child authorization policy. A person with existing active custody can create the child's preventive calendar events even when no separate Guardian row exists; a family Adult without custody or suitable delegated Care permission cannot.

## Child profile and login

A person with effective protected child authority can use the family-facing child-profile contract. The endpoint intentionally exposes only the minimal family profile and does not turn profile access into a broader medical export.

`POST /api/baby/profiles/<baby-id>/activate-login/` remains a sensitive operation and requires a fresh authenticated session. It operates on the existing child user; no second child identity is created.

## Legal/product boundary

FamilyOS uses confirmed custody as the app's source for child access and representation authority. That product rule does **not** claim that every person with custody may make every substantive medical decision alone. Joint custody, the child's own capacity to consent, court orders and other legal constraints can require additional workflow or consent rules.

The authorization rule here answers who may access and act within FamilyOS's protected child scope; it is not a blanket legal-decision engine.

## Security invariants

- child authority is always scoped to the child's active family membership;
- cross-family relationship and authority identifiers are rejected;
- active custody is effective immediately and needs no Guardian copy/backfill;
- Owner/Adult role, parenthood and legal parenthood alone do not grant protected child access;
- new child creation does not infer custody or create a new Guardian grant;
- custody mutation requires server-side Owner authorization and fresh re-authentication;
- effective grant/revocation through custody status changes is audited;
- existing legacy Guardian rows remain compatible but do not become legal custody assertions;
- Care Circle remains separate delegated access and cannot be interpreted as custody;
- child-role readers continue to receive configured relationship redaction;
- no role or permission changes automatically because of birthday/age.

## Migration direction

The target state contains one user-facing source of full child authority: **Sorgerecht**. Once all consumers use the central policy and legacy data has been reviewed, the technical Guardian compatibility model and endpoint can be removed in a later Contract step without changing the custody semantics established by #717.
## Calendar compatibility correction (#747)

Native calendar writes through REST and offline sync now consume the same central
custody authority. This also works for historical child memberships without a
BabyProfile: an active stored custody relationship is sufficient; no new Guardian
row or user-driven backfill is required. Multiple custodians retain full child
and account-management authority. Revocation/inactive custody takes effect on the
next write unless a separately retained legacy grant still authorizes that actor.
Decorative child-profile editing preserves its existing Owner exception and now
accepts custody through this same helper for other authorized adults.

Deployment is code-only: no schema or destructive data migration, no inferred
custody and no new Guardian rows for existing custody. Keep existing custody and
legacy rows when rolling back; rollback restores the old consumer bug, so do not
roll back merely to recover local drafts.
