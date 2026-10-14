# Child Identity, Account Authority & Family Relationships

FamilyOS treats a child as a durable family identity, not as a Baby-module record or a future login that has to be merged later.

## Canonical identity

A managed child uses the existing Django `User`, `Membership(role=child)`, `UserProfile` and `BabyProfile.membership` relation. The initial user has an internal technical username, no email address and an unusable password. Birth from `PregnancyBaby` and manual creation both keep the same contract and use a stable identity key for idempotence.

Turning the Pregnancy & Baby module off does not remove any of these identity records. Permanently deleting Baby tracking data is a separate destructive action and must not be used as an account lifecycle operation.

## Creating a child from Family

Family owners and adults can create a managed child directly from **Family → Members → Add → Child without own access**. The only required profile data is the child's display name and birth date. This flow does not create an invitation, does not require an email address and does not enable authentication.

`POST /api/baby/managed-children/` deliberately reuses the canonical managed-child creation service. It is available independently of the optional Pregnancy & Baby module. The creating owner/adult becomes an explicit `ManagedChildGuardian(can_manage_account=true)` for the new child because the create action itself explicitly establishes account-management authority. This does not add the person to the Care Circle and does not grant health or development access.

Creating a managed child does **not** create a `FamilyRelationship` and does not infer biological, social or legal parenthood from the creator's family role or account-management authority. Family relationships are entered explicitly afterwards in **Familienbeziehungen**.

The child appears immediately as the same `Membership(role=child)` used by family assignments, birthday projection and other canonical family references. No shadow child object or second birthday/calendar model is created.

## Familienbeziehungen / patchwork model

`FamilyRelationship` is a per-child, per-family-member description. Only existing memberships in the same family can be related; external contacts are intentionally out of scope. Different children can therefore have completely different relationships to the same adult.

A relationship stores independent dimensions:

- a standard relationship kind (`parent`, mother/father, bonus/step, adoptive, foster, grandparent, sibling), a free label, or no label;
- biological parenthood;
- legal parenthood;
- custody (`true`, `false`, or not yet recorded);
- active/inactive status instead of destructive deletion;
- child visibility: full details, relationship label only, or hidden.

Owners may create or edit family relationships without an additional per-child permission. Adult family role alone is deliberately insufficient to modify relationship facts. Relationship labels are readable inside the family, while biological/legal/custody facts are restricted: Owners see the full record; child-role viewers receive their configured redaction; ordinary Adults do not receive those sensitive fields merely because of their family role.

`GET /api/family-relationships/?family=<family-id>&child_membership=<membership-id>` reads relationship data under those visibility rules. `POST /api/family-relationships/` and `PATCH /api/family-relationships/<relationship-id>/` require Owner role.

The API may return permission suggestions for an Owner, but those suggestions are advisory only and `automatic=false` is part of the contract. No relationship write creates, removes or modifies account guardianship, Care Circle access, family roles or other permissions.

## Family profile data

An explicit child account guardian can read and update the family-facing child profile at `GET/PATCH /api/baby/profiles/<baby-id>/family-profile/`. This endpoint intentionally returns only the minimal family profile (`id`, `membership`, `display_name`, `birth_date`). Medical birth fields, growth data and Care Circle content are not returned here.

For compatibility with the existing Family Members client, `GET /api/baby/profiles/<baby-id>/` and a PATCH to that URL containing `birth_date` are routed through the same narrow family-profile contract. The pre-existing Baby-module rename/delete behavior remains module-gated. New family-facing callers should use the explicit `/family-profile/` endpoint.

Changing the display name synchronizes `BabyProfile.display_name` and `Membership.display_name` (and the linked expected-baby label when present). Changing the birth date synchronizes `BabyProfile.birth_date` with `UserProfile.birth_year`, `birth_month` and `birth_day`, so canonical birthday consumers continue to use one source of truth.

The child-identity endpoint remains privacy-minimal and does not expose the birth date or health payload.

## Five separate concepts

These concepts must never be inferred from one another:

- `Membership.role`: ordinary family tenancy/product role such as Owner, Adult or Child;
- `FamilyRelationship`: social/biological/legal relationship facts for one concrete child;
- `FamilyRelationship.has_custody`: optional custody fact, reserved for future authorization policy but not currently an authorization grant;
- `ManagedChildGuardian`: explicit authority over one concrete child account/identity;
- `CareCircleAccess`: access to Pregnancy/Baby health and care data.

Owner or Adult role alone is not parenthood. Owner role does grant product-level authority to maintain `FamilyRelationship` records, but that administrative ability is not itself a relationship fact. A biological, legal or custodial relationship does not grant account or health permissions. Care Circle access is not account-management authority. Creating a managed child establishes account-management authority for the creator but no parenthood or family relationship.

A child must retain at least one `ManagedChildGuardian` with `can_manage_account=true`. Guardian membership must belong to the same active family and remain Owner/Adult under the existing #147 policy.

## Enabling the child's own login

`POST /api/baby/profiles/<baby-id>/activate-login/` is a sensitive action and requires a fresh authenticated session.

The authorized per-child account guardian supplies the target email address and a password that passes Django's configured password validators. FamilyOS writes the password to the **existing child user**, creates a pending `EmailIdentity`, and sends the normal platform verification email. The password cannot be used for email login while that identity is pending because authentication resolves only a verified primary identity. After the standard verification link promotes the address to verified primary identity, the same child user can log in.

No second user is created, no dummy email address is stored, and this flow does not create a second recovery or token system. Password recovery remains owned by #199.

## Invitation boundary

A pending or verified child email identity participates in the central email uniqueness contract. Ordinary invitation registration attempting to create another account for that email is rejected and its transaction rolls back, so an invite cannot silently create a parallel child account.

## Legacy reconciliation

`python manage.py reconcile_child_identities` is dry-run by default. `--apply` attaches a canonical managed-child User/Membership/UserProfile to unambiguous legacy `BabyProfile` rows that have no membership.

Potential duplicates with the same family, normalized display name and birth date are not merged automatically. They are listed under `REVIEW REQUIRED` and remain unchanged for explicit review. Re-running the command is idempotent.

## Security invariants

- child/account-authority lookups are always scoped through the child's family membership;
- cross-family relationship and guardian membership IDs are rejected;
- Owners can mutate `FamilyRelationship` records without a separate per-child grant;
- Adult family role alone does not grant relationship mutation or sensitive lineage visibility;
- child-role readers receive the configured relationship redaction;
- relationships never grant permissions automatically;
- health access remains governed by Care Circle permissions even for account guardians;
- there is no automatic role or permission change based on birthday/age;
- the Child Identity contract is independent of Pediatric Reference Data and Wishlist capability policy.
