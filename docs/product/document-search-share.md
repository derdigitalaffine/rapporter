# Dokumentensuche und PWA-Share-Target

Issue: #183 · Dokument-Core: #179/#180

## Ziel

FamilyOS bleibt das kanonische Dokument-System. Die P1-Suche nutzt PostgreSQL und die bereits lokal extrahierten Dokumentdaten; es gibt keinen externen Search-Server, keine semantische Suche und keinen Dokumentenchat.

Der mobile Share-Target ist Progressive Enhancement. Normale Kamera-/Dateiauswahl im Dokument-Eingang bleibt unabhängig davon immer verfügbar.

## Suchvertrag

`GET /api/documents/search/?family=<uuid>` startet immer mit `visible_documents(user, family)`. Erst auf diesem ACL-gefilterten QuerySet werden Filter und Volltextsuche angewandt. Der repo-weite `ActiveTenantAccess` validiert einen expliziten `family`-Parameter bereits davor; fremde Familien werden daher nach dem kanonischen API-Vertrag mit `403` abgelehnt, ohne dass die Such-View oder Suchmaterial für diesen Tenant ausgewertet werden.

Unterstützte Suchquellen:

- Dokumenttitel
- Korrespondent
- Dokumenttyp
- lokaler OCR-/PDF-Text aus dem letzten verarbeiteten `DocumentProcessingRun`
- eng erlaubte strukturierte Felder wie Referenz-/Aktenzeichen, Vertragsnummer/-anbieter, Belegdaten und IBAN

`DocumentSearchIndex` ist ausschließlich abgeleitetes Suchmaterial. Er besitzt keine eigene ACL und ist nie eine Quelle für die Aufzählung von Dokumenten. Fehlende oder veraltete Suchzeilen werden nur für bereits sichtbare Dokumente erneuert. Ein GIN-Index auf dem PostgreSQL-`SearchVectorField` beschleunigt die Volltextsuche.

Filter:

- `kind`
- `person` (Membership-ID; Eigentümer oder expliziter Zugriff)
- `visibility` (`private`, `family`, `selected`)
- `date_from` / `date_to`
- `correspondent`
- `pinned`

Treffer-Snippets werden aus dem abgeleiteten Inhalt eines bereits autorisierten Treffers gebaut. Private oder nicht freigegebene Dokumente können daher weder als Treffer noch als Snippet/Autocomplete-Signal erscheinen.

## PWA Share Target

`manifest.webmanifest` registriert `/share.html` als `POST multipart/form-data` Share Target für:

- `application/pdf`
- `image/jpeg`
- `image/png`
- `image/webp`

Der aktive Service Worker fängt den POST ab. Mehrere Dateien werden nur same-origin in einem dedizierten Cache (`familyos-share-target-v1`) unter einer zufälligen Batch-ID zwischengespeichert und anschließend nach `/?page=documents&share_batch=…` umgeleitet.

`DocumentsHub` liest diesen Batch, rekonstruiert Browser-`File`-Objekte und löscht die temporären Cache-Einträge direkt nach der Übernahme in den Review-Bereich. Die Dateien werden **nicht** direkt aus dem Service Worker an einen neuen Backend-Endpunkt geschickt. Der Nutzer prüft Titel/Typ/Sichtbarkeit und bestätigt den Import; danach läuft jede Datei sequenziell durch den bestehenden `POST /api/documents/`-Pfad mit dessen Canonicalization, Duplicate-Check, ACL, Storage und Processing Queue.

So bleibt der vorhandene Dokument-Core die einzige Schreibstrecke.

### Text- und URL-Fallback

Shares ohne unterstützte Datei werden weiterhin nach `/share.html?...` geleitet und in der Family Inbox gespeichert. Der Fallback nutzt die aktuelle Cookie-Session (`/api/auth/session/` + `/api/auth/refresh/`) und keine historischen Bearer-Tokens aus Local Storage.

Browser ohne Web Share Target bzw. ohne installierte PWA sehen weiterhin den normalen Mehrfach-Datei-Input im Dokument-Eingang.

## Privacy und Sicherheit

- Der globale Tenant-Guard prüft explizite Family-Parameter vor der View; anschließend wird Dokument-ACL serverseitig **vor** der Suche ausgewertet.
- Search-Index-Inhalte werden nicht über einen separaten Endpoint ausgeliefert.
- Dateien im Share Target verlassen den Origin nicht, bevor der Nutzer den normalen Dokument-Import bestätigt.
- Download bleibt über den bestehenden ACL-geschützten `/api/documents/<id>/file/`-Endpoint mit `private, no-store`.
- Der Share Cache wird vom Service-Worker-Cache-Cleanup explizit getrennt, damit ein gerade gestarteter Share nicht durch einen Worker-Aktivierungswechsel verloren geht; konsumierte Batches werden unmittelbar entfernt.

## Migration und Rollback

`documents.0004_document_search_index` fügt nur die abgeleitete `DocumentSearchIndex`-Tabelle und den GIN-Index hinzu. Bestehende Library-Dokumente werden aus Metadaten, lokalem OCR-Text und erlaubten strukturierten Feldern backfilled; danach wird der Suchvektor in PostgreSQL aufgebaut.

Rollback löscht ausschließlich das abgeleitete Suchmaterial. `Document`, kanonische Dateien, OCR-Läufe, extrahierte Felder und ACLs bleiben unverändert. Ein späteres Roll-forward kann den Index vollständig aus diesen kanonischen Daten rekonstruieren.

## Validierung

Backend-Tests decken insbesondere ab:

- OCR-Text und Referenzfelder sind auffindbar
- privater OCR-Text bleibt für andere Familienmitglieder vollständig unsichtbar
- `selected` wird erst nach explizitem Zugriff sichtbar
- Cross-Family-Suche wird vom kanonischen Tenant-Guard mit `403` geschlossen abgelehnt und liefert keine Dokumentkennung zurück
- Filter werden auf dem autorisierten QuerySet angewandt
- neues Processing macht Suchmaterial erkennbar veraltet und löst sichere Erneuerung aus

Der Repo-CI läuft zusätzlich in Mobile Chromium und Desktop Chromium. Der PWA-Manifestvertrag und der responsive Dokument-Eingang werden mit dem normalen Frontend-Build/E2E-Gate ausgeliefert.
