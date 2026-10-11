# Child Identity & Guardians

FamilyOS treats a child as a durable family identity, not as a Baby-module record or a future login that has to be merged later.

## Canonical identity

A managed child uses the existing Django `User`, `Membership(role=child)`, `UserProfile` and `BabyProfile.membership` relation. The initial user has an internal technical username, no email address and an unusable password. Birth from `PregnancyBaby` and manual creation both keep the same contract and use a stable identity key for idempotence.

Turning the Pregnancy & Baby module off does not remove any of these identity records. Permanently deleting Baby tracking data is a separate destructive action and must not be used as an account lifecycle operation.

## Guardian versus Care Circle versus family role

These are deliberately separate concepts:

- `Membership.role` describes ordinary family tenancy and product role.
- `ManagedChildGuardian` grants authority over one concrete child identity.
- `CareCircleAccess` grants access to Pregnancy/Baby health and care data.

Owner or Adult role alone is not guardian authority. Care Circle access alone is not account-management authority. Existing legacy rows may bootstrap a per-child guardian only when the member was already explicitly marked `is_guardian` in the Care Circle; role alone is never enough.

A child must retain at least one guardian with `can_manage_account=true`. Guardian membership must belong to the same active family and remain Owner/Adult under the existing #147 policy.

## Enabling the child's own login

`POST /api/baby/profiles/<baby-id>/activate-login/` is a sensitive action and requires a fresh authenticated session.

The authorized per-child guardian supplies the target email address and a password that passes Django's configured password validators. FamilyOS writes the password to the **existing child user**, creates a pending `EmailIdentity`, and sends the normal platform verification email. The password cannot be used for email login while that identity is pending because authentication resolves only a verified primary identity. After the standard verification link promotes the address to verified primary identity, the same child user can log in.

No second user is created, no dummy email address is stored, and this flow does not create a second recovery or token system. Password recovery remains owned by #199.

## Invitation boundary

A pending or verified child email identity participates in the central email uniqueness contract. Ordinary invitation registration attempting to create another account for that email is rejected and its transaction rolls back, so an invite cannot silently create a parallel child account.

## Legacy reconciliation

`python manage.py reconcile_child_identities` is dry-run by default. `--apply` attaches a canonical managed-child User/Membership/UserProfile to unambiguous legacy `BabyProfile` rows that have no membership.

Potential duplicates with the same family, normalized display name and birth date are not merged automatically. They are listed under `REVIEW REQUIRED` and remain unchanged for explicit review. Re-running the command is idempotent.

## Security invariants

- child/guardian lookups are always scoped through the child's family membership;
- cross-family guardian membership IDs are rejected;
- health access remains governed by Care Circle permissions even for guardians;
- there is no automatic role or permission change based on birthday/age;
- the Child Identity contract is independent of Pediatric Reference Data and Wishlist capability policy.
