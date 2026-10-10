# Universal Context Links

`ContextLink` is FamilyOS' shared metadata edge for connecting canonical objects without copying their domain data. It is intentionally **not** a free-form Django `GenericForeignKey`: every endpoint type and relation must be registered in `family.context_links.ContextRegistry`.

## Foundation contract

A stored link contains only `family`, typed source/context UUIDs, `relation_key`, creator and timestamps. The source domains remain authoritative for content, lifecycle and permissions. Every read resolves both endpoints through their current adapters; a deleted object or revoked ACL therefore becomes unavailable without leaking a stale title or preview.

The allowlist is deliberately explicit:

| Type | Visibility reused | Deep link |
| --- | --- | --- |
| `task` | family + `hidden_from_user` | object-level Tasks link |
| `note` | author or `NoteShare` | object-level Notes link |
| `trip` | active family membership | Trips hub (object focus is a later UI slice) |
| `shopping_list` | active family membership | object-level Shopping list link |
| `shopping_item` | family + `hidden_from_user` | object-level Shopping item link |
| `board_post` | active family membership | object-level Pinboard link |
| `birthday_occasion` | birthday planners only; never the birthday member; hidden/inactive targets stay unavailable | Birthdays hub |

The `context` relation currently treats Task, Note, ShoppingList, ShoppingItem or BoardPost as the source and Trip as the context. Birthday planning adds two narrower relations with `birthday_occasion` as source: `birthday.gift_task` -> `task` and `birthday.shopping_item` -> `shopping_item`. Guests can view otherwise-visible generic links but cannot create/remove them; BirthdayOccasion visibility is tighter and follows the Birthday planning roles (owner/adult/teen). New domains extend the registry explicitly; they must not accept client-provided model names or raw content types.

## Birthday occasion contract

`BirthdayOccasion` is an additive yearly context anchor. It stores only the family, exactly one canonical target (`Membership` or `BirthdayPerson`), the occurrence year and optional planning metadata. It deliberately stores **no birth month/day/year** and creates no `FamilyEvent`; the canonical Birthday projection remains the only calendar/date truth.

Existing `BirthdayGiftPlan` foreign keys and the legacy `Task.birthday_context` / `ShoppingItem.birthday_context` UUIDs remain supported. New gift-plan writes also create/reuse the matching BirthdayOccasion and idempotently dual-write the two supported ContextLinks. The legacy UUID continues to contain the `BirthdayGiftPlan.id`; this migration does not silently reinterpret it as an occasion id.

BirthdayOccasion itself is not a new surprise ACL. Resolution is limited to existing Birthday planners and excludes the birthday member. Linked Task and ShoppingItem visibility is then checked independently through their canonical `hidden_from_user` adapters on every read. A ContextLink therefore never makes a hidden gift visible.

Additional Birthday relations such as party events, notes, documents, expenses or wishlists are intentionally not registered until those endpoint types/contracts are available in the canonical ContextLink registry. They must extend this same allowlist rather than create another reference system.

## HTTP API

The authenticated API is a thin transport layer over the same registry/services; it does not implement a second ACL path.

### Create

`POST /api/context-links/`

```json
{
  "family": "<family-uuid>",
  "source": {"type": "task", "id": "<task-uuid>"},
  "context": {"type": "trip", "id": "<trip-uuid>"},
  "relation": "context"
}
```

Creation is idempotent. A new link returns `201` with `created: true`; an identical existing link returns `200` with `created: false` and the same link id.

### List around an object

`GET /api/context-links/?family=<family-uuid>&anchor_type=trip&anchor_id=<trip-uuid>&limit=50`

The response contains only links whose source and context are both still visible to the caller. `limit` is bounded to `1..100`; resolution remains batched by registered type.

### Remove metadata

`DELETE /api/context-links/<link-uuid>/?family=<family-uuid>`

Removal deletes only the ContextLink row. The source and context objects are never deleted. A stale/missing context can still be cleaned up if the caller retains permission to manage the source link.

### Error contract

- malformed family/ref/limit input: `400`
- unsupported type or relation allowlist entry: `400`
- inaccessible/missing family, endpoint or link: neutral `404` with `context_object_unavailable`
- visible but non-mutable relation/source (for example Guest or read-only Note share): `403` with `context_link_forbidden`

The API intentionally does not reveal whether a neutral `404` was caused by a missing UUID, another family, or revoked object visibility.

## Security and lifecycle

- Both endpoints are resolved inside the requested active family. A guessed UUID from another family is indistinguishable from an inaccessible/missing object.
- A link never grants visibility. Note shares plus hidden Task and ShoppingItem gift rules are evaluated again on every resolution.
- BirthdayOccasion additionally reuses Birthday planning visibility: owner/adult/teen planners may resolve active/visible targets, but the birthday member cannot resolve their own surprise-planning occasion.
- Source-domain mutation rights remain authoritative too. In particular, a read-only `NoteShare` may view a visible link but cannot create or remove one; `edit` or note ownership is required.
- `list_context_links()` batches by adapter type and caps scans; it never performs one object query per link.
- Deleting or archiving a domain object does not mutate another domain. Missing/revoked endpoints are filtered from reads; archived Trips and ShoppingLists resolve with lifecycle `archived`.
- `remove_context_link()` deletes metadata only. It requires the source to remain visible and link-manageable, but deliberately allows cleanup when the context disappeared or its ACL was revoked.

## Adding a type or relation

Before adding a new parallel reference field, check whether the object should be addressable through this registry. A type adapter must provide a family-scoped visible queryset, family identity, canonical deep link, source mutation/link permission and (where relevant) lifecycle mapping. A relation must explicitly allow its source/context type pairs and may tighten create permissions.

Do not put serializer payloads, URLs with credentials, tokens, document contents or other snapshots into `ContextLink`. Presentation-specific Pinboard preview/lifecycle remains the responsibility of #219 and should consume this addressing/ACL contract rather than create a second generic-reference system.

## Migration and rollback

Migration `0210_context_links` is additive and does not backfill or remove any existing foreign/reference fields. Legacy Pinboard fields remain unchanged until their dedicated #219 migration.

Migration `0215_birthday_occasion_context` is also additive. It creates/reuses one BirthdayOccasion per valid legacy `BirthdayGiftPlan` target/year and idempotently backfills existing linked Task/ShoppingItem edges. Dirty legacy rows whose target or linked object belongs to another family are skipped rather than converted into a cross-family edge. Existing BirthdayGiftPlan and `birthday_context` values are not rewritten.

Rollback of `0215` removes ContextLinks that reference `birthday_occasion` before dropping the occasion table; legacy BirthdayGiftPlan/Task/ShoppingItem data remains intact, so the pre-migration Birthday workflow continues to work. Legacy Birthday FKs/UUIDs are removed only in a separate future contract phase.
