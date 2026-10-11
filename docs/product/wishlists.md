# Wishlist Core

Issue: #280. Dependencies: #229 Context Links and #277 Birthday Occasion.

## Purpose

The Wishlist Core is a universal family domain. It is deliberately **not** a Birthday-specific model: birthdays, Christmas or other occasions attach through canonical Context Links. A wishlist has an owner membership, visibility, items and a separate gift-coordination layer.

## Visibility and surprise contract

Wishlist content is server-authorized:

- `family`: every active family member can read the wishlist.
- `selected`: only the owner plus explicit `WishlistAccess` memberships can read it. An empty selected list is owner-only.
- only the owner can edit the list or its items.
- the initial core permits adult/owner memberships to create their own lists. Teen ownership is introduced by the dedicated capability/guardian slice (#281) rather than hard-coding age policy here.
- gift coordination is available only to visible non-owner owner/adult/teen memberships.

`WishlistReservation` is a separate model with exactly one current holder per item. Reservation, purchase status, reserver identity and coordination notes are **omitted entirely** from owner API projections. They are not sent as `null`, hidden with CSS, or exposed through a second endpoint to the owner. Mutating the reservation endpoint as the owner also fails closed.

Reservation writes use a database transaction plus row locks. Repeating the same holder's reservation is idempotent/updateable; a second holder gets `409 already_reserved`.

## External links

An item may store an arbitrary normal HTTPS URL. The server:

1. requires `https`,
2. requires a hostname,
3. rejects embedded username/password credentials,
4. normalizes the hostname/IDNA representation,
5. removes URL fragments.

FamilyOS does **not** fetch the URL, scrape product data, claim live price/availability, or create a server-side preview request. This keeps the core free of SSRF and merchant-catalog coupling.

## Canonical follow-up actions

Actions are always explicit (`confirmed=true`) and use existing domains:

- **Task**: normal `Task`, linked with `ContextLink(wishlist_item → task, wishlist.action)`. Existing `hidden_from_user` hides the surprise task from the wishlist owner.
- **Shopping**: normal `ShoppingItem`, linked the same way and using existing `hidden_from_user`.
- **Expense**: normal posted `Expense`, linked through Context Links. The current Expense domain is family-wide and has no surprise ACL, so this projection additionally requires `acknowledge_family_visibility=true`. The UI states that clearly. The Wishlist Core does not invent a parallel Expense permission model.

Selected-only wishlists cannot be projected into family-wide Task/Shopping/Expense objects because doing so would silently expand the source ACL.

## Occasion links

The `birthday.wishlist` Context Link relation connects `wishlist → birthday_occasion`. Creating or deleting the context metadata does not change wishlist visibility. Future occasions can register their own allowed relation without adding duplicate foreign keys.

## API

- `GET|POST /api/wishlists/`
- `GET|PATCH|DELETE /api/wishlists/{id}/`
- `POST /api/wishlists/{id}/items/`
- `PATCH|DELETE /api/wishlist-items/{id}/`
- `POST|DELETE /api/wishlist-items/{id}/reservation/`
- `POST /api/wishlist-items/{id}/actions/`
- `POST /api/wishlists/{id}/context/`

Cross-family and invisible object lookups fail closed.

## Migration / rollback

`wishlists.0001_initial` is additive and creates Wishlist, WishlistAccess, WishlistItem and WishlistReservation only. It does not change Family, Birthday, Task, Shopping or Expense schemas.

Reversing the migration removes wishlist-owned state and reservations. Canonical Task/Shopping/Expense objects explicitly created by users remain canonical objects; Context Links to removed wishlist sources become unresolved metadata and are naturally suppressed by the Context Link resolver. Operational rollback should therefore disable the UI/API before reversing the app migration if preserving wishlist data matters.
