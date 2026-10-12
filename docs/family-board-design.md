# Family board (#142)

Research checked 2026-10-10. FamilyWall's official feature description joins a short-message thread with a private photo gallery and supports phones, tablets and the web: https://support.familywall.com/en/support/solutions/articles/47001013681-about-familywall . The German App Store listing and customer responses emphasize a shared overview and easy coordination across family members: https://apps.apple.com/de/app/familywall-familienplaner/id496889629 . These are qualitative signals, not proof that any individual feature causes a higher rating.

Design decisions: a quiet chronological board, author and localized date on every card, a single publish action, optional photos, explicit family audience, readable original line breaks, no engagement scores or public sharing. Board sits under More. Photos are scaled on the server, lazy loaded and opened at full optimized size on demand. Editing is limited to the author; adults/owners can moderate by deleting. Push notifications omit post text and images to protect lock-screen privacy, and use the existing messages preference and family recipient resolution. Edits do not send another push.

Image uploads are decoded twice with Pillow (verification, then rendering), limited to four images, ten MB each and 24 million pixels each. Only JPEG/PNG/WebP inputs are accepted; only a metadata-free, orientation-corrected WebP up to 1600 pixels is persisted. Original names, bytes and EXIF are discarded. Random keys never become public URLs. All image reads authenticate and require an active family membership. Deletions clean up after transaction commit, including cascaded post deletion.

API: `/api/board/` supports paginated GET, POST multipart/JSON and author PATCH; DELETE also supports adult/owner moderation. `/api/board-images/{uuid}/` is a protected WebP GET and authorized DELETE. Families cannot be changed after publication. Images cannot be appended after publication; remove individual images through the media endpoint or delete/repost. No empty post is allowed after removing its final image.

## In-App-Fotoansicht (#515)

Pinnwand-Fotos bleiben beim normalen Klick/Tap innerhalb der FamilyOS-PWA. Ein gemeinsamer `ImageViewer` übernimmt die vorhandene autorisierte Bild-URL unverändert und zeigt Einzelbilder oder die komplette Karten-Galerie als modalen Vollbild-Viewer. Pfeiltasten sowie Vor-/Zurück-Controls navigieren, `Escape` schließt, der Fokus kehrt zum auslösenden Foto zurück, und der Hintergrund scrollt während der Ansicht nicht. Die Controls bleiben auf Touchgeräten mindestens 48 px groß; Dialog- und Navigationsnamen sind lokalisiert.

Die ursprüngliche Bild-URL bleibt als progressive Browser-Fallback-Navigation im Markup erhalten. Der Viewer erzeugt weder öffentliche Media-URLs noch einen zweiten Download-/ACL-Pfad: jeder Bildabruf läuft weiterhin über den bestehenden geschützten `/api/board-images/{uuid}/`-Endpunkt. Weitere Bildflächen können das gemeinsame Viewer-Primitiv später explizit wiederverwenden, ohne die Pinnwand-Logik zu kopieren.

## Reference pins and adapters (#219)

Reference pins store only an allow-listed `kind` plus the canonical object's UUID. The central `PinAdapter` registry re-authorizes every target on reads and creates, returns a deliberately small preview/deep link, and batch-resolves each adapter type in one query. A missing, deleted or no-longer-visible target is rendered as a neutral unavailable reference; the board never keeps a stale title snapshot as authority.

Currently registered reference kinds are calendar events, tasks, note references, shopping items, routines and shopping lists. Routine and shopping-list pins preserve lifecycle visibility for existing references: an inactive routine or archived shopping list resolves with lifecycle `archived`, but cannot be newly pinned. Deleted targets become neutral `available: false`. Cross-family target IDs are rejected before any preview data is disclosed.

`ContextRef`/`ContextLink` remains the universal cross-domain object-addressing contract. `PinAdapter` adds only board-specific preview, pin authorization and lifecycle semantics; it must not grow into a second generic-reference persistence layer. Additional adapters such as documents or trips should reuse their canonical domain ACLs and keep preview payloads minimal.

## Stable board order (#219)

`BoardPost.position` is a family/board-scoped integer order key. New pins continue to reserve a 1000-point gap before the current first pin. `/api/board/reorder/` keeps its existing `{family, ids}` contract and remains transactional: every row of that family is locked before an order plan is applied, guessed/foreign IDs fail before any position write, and guests cannot reorder.

Reordering no longer renumbers every pin for every arrow click. The backend computes a longest stable subsequence of the requested order, keeps those persisted positions unchanged, and assigns only moved segments to free integer positions between stable neighbours. A normal one-step move therefore changes one row. If repeated moves eventually consume every integer in a local gap, the backend performs a deterministic 1000-spaced full rebalance and then resumes sparse updates. This trades a rare O(n) maintenance write for O(changed pins) writes on normal interaction without introducing fractional/database-specific order values.

The current Board UI already exposes up/down arrow controls, so keyboard/touch users have a non-drag reordering path; the backend optimization does not change that interaction or response shape.

## Sichtbarkeit und verknüpfte Quellen

Neue Notizzettel und Fotos können für dich, ausgewählte Familienmitglieder oder die ganze Familie sichtbar sein. Entfernte Familienmitgliedschaften verlieren ihre ausgewählten Freigaben sofort. Verknüpfte Inhalte übernehmen beim Anpinnen die aktuelle Sichtbarkeit ihrer Quelle; du kannst den Pin anschließend enger freigeben. Ein Pin erweitert niemals die Rechte an der Quelle.

Die Karte zeigt die tatsächlich wirksame Sichtbarkeit. Wird ein Quellzugriff entzogen oder die Quelle gelöscht, bleibt nur ein neutraler Hinweis ohne Beschriftung, Bilder, Autor- oder Aktivitätsdaten. Bei eigenen Notizen öffnet **Quelle zusätzlich freigeben** ausdrücklich die bestehende Notiz-Freigabe; die Pinnwand ändert diese Rechte nicht beim Speichern.

### Technischer Abnahmevertrag

Die Seitenauflösung kombiniert vorhandene kanonische Adapter-Querysets für aktuelle Memberships in einer gebündelten Query pro Adaptertyp. Die exakte Schnittmenge und Vorschauen werden daraus berechnet; die Abfragezahl wächst nicht pro Pin. Direkte ACL-Prüfungen für Bilder, Reorder und einzelne Objekte bleiben serverseitig. Die neue Pin-Sichtbarkeit ist eine additive Migration; bestehende Pins behalten zunächst ihre Familien-Shell und bleiben durch Quellrechte begrenzt.

## Legacy-Migration und stabile Pin-Identität (#222)

Die universelle Pinnwand migriert das frühere Schwarze Brett **in place**. `0202_board` hat `BoardPost` und `BoardImage` bereits mit UUID-Primärschlüsseln angelegt; `0209_pinboard`, `0220_pinboard_adapter_keys` und die späteren Sichtbarkeitsmigrationen erweitern genau diese Zeilen additiv. Es gibt deshalb bewusst keine zweite Pin-Tabelle und kein Titel-/Text-Matching: **die frühere `BoardPost.id` ist dieselbe kanonische Pin-ID**. `BoardImage.post_id`, der private Storage-Key und Bildmetadaten bleiben beim Upgrade unverändert.

Dieser Identitätsvertrag hält alte Deep Links stabil: `?page=board&post=<BoardPost-UUID>&family=<Family-UUID>` adressiert nach dem Upgrade denselben Pin. Die Detail-API autorisiert ihn weiterhin über die aktuelle Pin-/Source-ACL; eine bekannte UUID ist kein Zugriffsrecht. Referenz-Pins behalten während des Compatibility-Fensters zusätzlich den alten `kind` und `target_id`. Der Read-Pfad kann deshalb bei einem noch leeren `adapter_key` deterministisch auf den Legacy-Kind zurückfallen, während neue/aktualisierte Zeilen den kanonischen Adapter-Key tragen.

### Retry, Diagnose und Rollback

`python manage.py report_pinboard_migration` ist standardmäßig read-only und gibt ausschließlich Zähler aus. `--json` liefert dieselben Werte maschinenlesbar. Mit `--repair-adapter-keys` werden nur fehlende, aus dem vorhandenen Legacy-Kind eindeutig ableitbare Adapter-Keys in begrenzten Batches ergänzt; `--batch-size` begrenzt die Batchgröße. Die Updates sind konditional auf `adapter_key=''`, deshalb sind Abbruch, Wiederaufnahme und Wiederholung idempotent. `kind`, `target_id`, Pin-UUID, Text, Bilddaten und Sichtbarkeit werden dabei nicht verändert.

Der Report nennt die Identitätsstrategie `boardpost_uuid_in_place`, Gesamt-/bereits kompatible Zeilen, in diesem Lauf reparierte Adapter-Keys, noch ausstehende Backfills, Adapter-/Identitätsfehler, verwaiste Bild-/Zielreferenzen und Sichtbarkeitsanomalien. Er protokolliert weder Pinnwandtext noch Zielnamen, Dateinamen oder private Storage-Keys. Die rohe Ziel-Existenzprüfung dient ausschließlich diesen Zählern; API-Reads und Interaktionen bleiben vollständig an die kanonischen `PinAdapter`-/Source-ACL-Prüfungen gebunden.

Vor der späteren Contract-Phase bleiben die Legacy-Felder lesbar. Ein Regressionstest migriert echte historische `0202_board`-Zeilen bis zum aktuellen Pin-Schema und wieder zurück und beweist dabei die unveränderten BoardPost-/BoardImage-IDs, Texte, Bild-FKs und Storage-Keys. Dadurch kann #386 Interaktionszeilen anschließend dauerhaft an `BoardPost` referenzieren, ohne bei Retry, Upgrade oder Rollback auf eine neu erzeugte Pin-ID zu zeigen. Die Contract-/Cleanup-Phase darf diese Kompatibilität erst nach einem separaten, messbaren Cutover entfernen.

### Canonical source picker admission and limits

`GET /api/board/picker/?family=<uuid>&adapter_key=<key>` uses each registered
adapter's `pinnable_queryset(user, family_id)` for both picker selection and
single-target `can_pin`. Source ACL stays in the existing source/Context/Document
selectors. Routine activity and ShoppingList/Document archive rules apply before
pagination; existing archived pins retain their previous readable lifecycle.

The endpoint requires authentication and an active-family membership with a
non-guest role, including for superadmins. Invalid family UUIDs and non-positive
or malformed page parameters return 400; inaccessible families/guest roles return
403. `page_size` defaults to 20 and clamps to 50. The zero-based offset is limited
to 10,000; larger offsets return 400 and require narrowing `q`, rather than loading
all earlier candidates. Ordering is `updated_at DESC, id DESC`; each request reads
only its admitted page plus one `has_next` sentinel, and projects previews only
for returned rows. As with ordinary offset pagination, source updates may move
rows between requests; this is not a snapshot cursor. All eight source groups and
legacy kind aliases remain available.

No schema migration. Rollback can restore the endpoint/adapter implementation
without changing sources, existing Pins, interactions, UUIDs or personal layouts.
