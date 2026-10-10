# Family board (#142)

Research checked 2026-10-10. FamilyWall's official feature description joins a short-message thread with a private photo gallery and supports phones, tablets and the web: https://support.familywall.com/en/support/solutions/articles/47001013681-about-familywall . The German App Store listing and customer responses emphasize a shared overview and easy coordination across family members: https://apps.apple.com/de/app/familywall-familienplaner/id496889629 . These are qualitative signals, not proof that any individual feature causes a higher rating.

Design decisions: a quiet chronological board, author and localized date on every card, a single publish action, optional photos, explicit family audience, readable original line breaks, no engagement scores or public sharing. Board sits under More. Photos are scaled on the server, lazy loaded and opened at full optimized size on demand. Editing is limited to the author; adults/owners can moderate by deleting. Push notifications omit post text and images to protect lock-screen privacy, and use the existing messages preference and family recipient resolution. Edits do not send another push.

Image uploads are decoded twice with Pillow (verification, then rendering), limited to four images, ten MB each and 24 million pixels each. Only JPEG/PNG/WebP inputs are accepted; only a metadata-free, orientation-corrected WebP up to 1600 pixels is persisted. Original names, bytes and EXIF are discarded. Random keys never become public URLs. All image reads authenticate and require an active family membership. Deletions clean up after transaction commit, including cascaded post deletion.

API: `/api/board/` supports paginated GET, POST multipart/JSON and author PATCH; DELETE also supports adult/owner moderation. `/api/board-images/{uuid}/` is a protected WebP GET and authorized DELETE. Families cannot be changed after publication. Images cannot be appended after publication; remove individual images through the media endpoint or delete/repost. No empty post is allowed after removing its final image.

## Reference pins and adapters (#219)

Reference pins store only an allow-listed `kind` plus the canonical object's UUID. The central `PinAdapter` registry re-authorizes every target on reads and creates, returns a deliberately small preview/deep link, and batch-resolves each adapter type in one query. A missing, deleted or no-longer-visible target is rendered as a neutral unavailable reference; the board never keeps a stale title snapshot as authority.

Currently registered reference kinds are calendar events, tasks, note references, shopping items, routines and shopping lists. Routine and shopping-list pins preserve lifecycle visibility for existing references: an inactive routine or archived shopping list resolves with lifecycle `archived`, but cannot be newly pinned. Deleted targets become neutral `available: false`. Cross-family target IDs are rejected before any preview data is disclosed.

`ContextRef`/`ContextLink` remains the universal cross-domain object-addressing contract. `PinAdapter` adds only board-specific preview, pin authorization and lifecycle semantics; it must not grow into a second generic-reference persistence layer. Additional adapters such as documents or trips should reuse their canonical domain ACLs and keep preview payloads minimal.
