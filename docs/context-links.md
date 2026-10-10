# Universal Context Links

`ContextLink` is FamilyOS' shared metadata edge for connecting canonical objects without copying their domain data. It is intentionally **not** a free-form Django `GenericForeignKey`: every endpoint type and relation must be registered in `family.context_links.ContextRegistry`.

## Foundation contract

A stored link contains only `family`, typed source/context UUIDs, `relation_key`, creator and timestamps. The source domains remain authoritative for content, lifecycle and permissions. Every read resolves both endpoints through their current adapters; a deleted object or revoked ACL therefore becomes unavailable without leaking a stale title or preview.

The initial allowlist is deliberately small:

| Type | Visibility reused | Deep link |
| --- | --- | --- |
| `task` | family + `hidden_from_user` | object-level Tasks link |
| `note` | author or `NoteShare` | object-level Notes link |
| `trip` | active family membership | Trips hub (object focus is a later UI slice) |
| `board_post` | active family membership | object-level Pinboard link |

The initial `context` relation treats Task, Note or BoardPost as the source and Trip as the context. Guests can view visible links but cannot create/remove them. New domains extend the registry explicitly; they must not accept client-provided model names or raw content types.

## Security and lifecycle

- Both endpoints are resolved inside the requested active family. A guessed UUID from another family is indistinguishable from an inaccessible/missing object.
- A link never grants visibility. Note shares and hidden-task rules are evaluated again on every resolution.
- Source-domain mutation rights remain authoritative too. In particular, a read-only `NoteShare` may view a visible link but cannot create or remove one; `edit` or note ownership is required.
- `list_context_links()` batches by adapter type and caps scans; it never performs one object query per link.
- Deleting or archiving a domain object does not mutate another domain. Missing/revoked endpoints are filtered from reads; an archived Trip resolves with lifecycle `archived`.
- `remove_context_link()` deletes metadata only. It requires the source to remain visible and link-manageable, but deliberately allows cleanup when the context disappeared or its ACL was revoked.

## Adding a type or relation

Before adding a new parallel reference field, check whether the object should be addressable through this registry. A type adapter must provide a family-scoped visible queryset, family identity, canonical deep link, source mutation/link permission and (where relevant) lifecycle mapping. A relation must explicitly allow its source/context type pairs and may tighten create permissions.

Do not put serializer payloads, URLs with credentials, tokens, document contents or other snapshots into `ContextLink`. Presentation-specific Pinboard preview/lifecycle remains the responsibility of #219 and should consume this addressing/ACL contract rather than create a second generic-reference system.

## Migration and rollback

Migration `0210_context_links` is additive and does not backfill or remove any existing foreign/reference fields. Rollback is safe while no downstream feature depends on the table: reverse that migration and remove the registry/service code. Legacy Pinboard fields remain unchanged until their dedicated #219 migration.
