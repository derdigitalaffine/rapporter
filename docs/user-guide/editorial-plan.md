# Redaktionsplan für das FamilyOS-Anwenderhandbuch

Dieses Dokument beschreibt, wie die Anwenderdokumentation aufgebaut, geschrieben und mit der Produktentwicklung synchron gehalten wird.

## Zielgruppe

Primäre Zielgruppe sind **normale FamilyOS-Anwender**:

- Familien-Owner,
- Erwachsene,
- Jugendliche/Kinder mit eigenem Zugang,
- Gäste bzw. eingeschränkte Mitglieder,
- neue Mitglieder, die über eine Einladung beitreten.

Nicht primär adressiert werden Serveradministratoren, Entwickler und Betreiber. Installation, Docker, TLS, Datenbank, Backups und Deployment bleiben in der technischen Dokumentation.

## Informationsarchitektur

Die Doku wird unter `docs/user-guide/` gepflegt.

### P0 – Einstieg

- [x] `README.md` – Doku-Hub und Inhaltsverzeichnis
- [x] `getting-started.md` – Anmeldung, Navigation, Familie, PWA-Grundlagen
- [ ] `troubleshooting.md` – allgemeine Selbsthilfe

### P1 – tägliche Kernabläufe

- [ ] `tasks.md`
- [ ] `shopping.md`
- [ ] `calendar.md`
- [ ] `routines.md`
- [ ] `family-and-permissions.md`

### P2 – erweiterte Funktionen

- [ ] `integrations.md`
- [ ] `automations.md`
- [ ] `inbox-notifications.md`
- [ ] `loyalty-cards.md`
- [ ] `offline-pwa.md`

### P3 – optionale Module

Optionale Module bekommen ein Kapitel, wenn sie in `main` integriert und für Nutzer sichtbar sind. Das Kapitel soll die Modulaktivierung, typische Alltagsflows, Rechte und Datenschutzbesonderheiten erklären.

## Kapitel-Template

Jedes größere Kapitel sollte möglichst diese Struktur verwenden:

```markdown
# <Bereich>

## Wofür ist der Bereich gedacht?

## Wo finde ich ihn?

## Typische Aufgabe 1
1. ...
2. ...
3. ...

## Typische Aufgabe 2
...

## Rollen und Berechtigungen

## Offline / Synchronisation

## Häufige Probleme

## Siehe auch
```

Nicht jedes Kapitel braucht jeden Abschnitt. Das Template dient als Prüfliste, nicht als starres Korsett.

## Schreibregeln

### Nutzerziel vor Technik

Schreibe zuerst, **was ein Nutzer erreichen möchte**. Interne Modelle, API-Endpunkte, Datenbanknamen oder technische Architektur gehören nur dann in die Anwenderdoku, wenn sie für die Bedienung notwendig sind.

Gut:

> Öffne **Einkauf**, wähle die Liste und tippe auf **Artikel hinzufügen**.

Nicht gut:

> Erzeuge ein neues `ShoppingItem` für die aktive `ShoppingList`.

### UI-Wörter exakt verwenden

Schaltflächen, Menüpunkte und Bereichsnamen werden in **fett** geschrieben und möglichst exakt aus der deutschen Oberfläche übernommen.

Wenn sich ein UI-Name ändert, muss die Doku im selben Feature-PR aktualisiert werden.

### Rechte am Ort der Aktion erklären

Berechtigungshinweise gehören direkt zu dem Flow, den sie beeinflussen. Nutzer sollen nicht erst ein separates Rollenmodell verstehen müssen, bevor sie eine Anleitung verwenden können.

### Keine geplanten Funktionen als vorhanden beschreiben

Offene GitHub-Issues sind keine Produktdokumentation. Ein Feature wird erst als nutzbar beschrieben, wenn es in `main` integriert ist.

### Mobile zuerst

Die Beschreibung orientiert sich primär an der mobilen/PWA-Nutzung. Desktop-Abweichungen werden nur beschrieben, wenn sie den Ablauf wesentlich verändern.

### Screenshots sparsam einsetzen

Screenshots sind hilfreich bei schwer auffindbaren Funktionen, aber wartungsintensiv. Deshalb gilt:

- Anleitung muss auch ohne Bild verständlich sein,
- keine Screenshots mit persönlichen Daten,
- keine Screenshots für triviale Einzelschritte,
- bei stark veränderlicher UI lieber präziser Text als veraltetes Bild.

## Definition of Done für ein Kapitel

Ein Kapitel ist fertig, wenn:

- [ ] Ziel und Einstiegspunkt verständlich sind,
- [ ] mindestens die häufigsten 2–4 Nutzeraufgaben beschrieben sind,
- [ ] sichtbare UI-Bezeichnungen zur aktuellen deutschen Oberfläche passen,
- [ ] Rollen/Berechtigungen erwähnt sind, wenn sie den Ablauf beeinflussen,
- [ ] Offline-/Read-only-Verhalten erwähnt ist, wenn relevant,
- [ ] typische Fehlerfälle oder Grenzen genannt sind,
- [ ] keine noch nicht integrierten Features als vorhanden beschrieben werden,
- [ ] relative interne Links funktionieren,
- [ ] der Text auf Smartphonebreite gut scanbar bleibt,
- [ ] keine Secrets, Tokens, privaten URLs oder persönlichen Daten enthalten sind.

## GitHub-Pflegeprozess

### Tracking

Das zentrale Tracking-Issue für den Aufbau der Anwenderdoku ist **#176**.

Größere Kapitel können als eigene Issues umgesetzt werden, wenn sie mehrere Produktbereiche, Screenshots oder umfangreiche Verifikation benötigen. Diese Issues werden in #176 verlinkt.

### Branches und Pull Requests

- Doku-Arbeit erfolgt über kurze Branches und Pull Requests.
- Der initiale Aufbau verwendet `docs/user-guide`.
- Spätere Kapitel sollten möglichst in kleinen, prüfbaren PRs landen.
- PR-Titel für reine Doku bevorzugt nach Muster `docs: <Bereich> dokumentieren`.

### Feature-PRs

Bei jedem user-facing Feature-PR prüfen:

1. Ändert sich die Hauptnavigation oder ein Menüpunkt?
2. Ändert sich ein Nutzerflow?
3. Ändert sich Rollen-/Berechtigungsverhalten?
4. Kommt ein neuer sichtbarer Status, Dialog oder Empty State dazu?
5. Wird ein bestehender Funktionsname umbenannt?

Wenn eine Antwort **ja** ist, wird die betroffene Anwenderdoku im selben PR aktualisiert oder ein explizit verlinktes Doku-Issue angelegt.

## Prüfstrategie

Vor Merge eines Doku-PRs:

- relevante UI im aktuellen `main` gegenlesen,
- keine geplanten Issues als Quelle für vorhandene Funktionen verwenden,
- Links testen,
- Anleitung einmal aus Sicht eines neuen Familienmitglieds durchgehen,
- bei rollenabhängigen Funktionen mindestens Owner und eingeschränktere Rolle gedanklich/technisch prüfen,
- bei externen Integrationen deutlich zwischen FamilyOS und Drittanbieter unterscheiden.

## Nächste konkrete Schreibreihenfolge

Empfohlene Reihenfolge nach dem Einstieg:

1. **Aufgaben** – einer der häufigsten Kernflows
2. **Einkauf** – inklusive Offline-Verhalten
3. **Kalender** – inklusive read-only Quellen
4. **Familie & Berechtigungen** – wichtig für Einladungen und Rollenverständnis
5. **Routinen**
6. **Inbox & Benachrichtigungen**
7. **Integrationen**
8. **Wenn → Dann**
9. **Bonuskarten**
10. **Offline & PWA**
11. **Fehlerbehebung** als Querschnittskapitel aus realen Supportfällen

Diese Reihenfolge priorisiert alltägliche Nutzeraufgaben vor administrativen oder technischeren Bereichen.
