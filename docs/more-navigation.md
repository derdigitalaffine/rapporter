# Navigation unter „Mehr“

Die Seite **Mehr** bündelt Ziele, die nicht in der primären Hauptnavigation liegen. Sie ist nach Nutzungskontext statt nach technischer Modulreihenfolge gegliedert und bleibt bewusst ein ruhiger Hub statt einer gleichgewichtigen Feature-Wand.

## Standardreihenfolge

1. **Familie & Alltag** – familienbezogene Funktionen wie Pinnwand, Geburtstage, Reisen, Entscheidungen, Wunschlisten und Spiele.
2. **Haushalt & Finanzen** – der kanonische Einstieg **Geld & Finanzen** sowie Statistik, Verträge, Dokumente, Karten und Fahrzeuge, soweit Rolle und Entitlement sie erlauben.
3. **Einstellungen & Verwaltung** – Einrichtung, Profil, Einstellungen, Familienverwaltung, Benachrichtigungen, Integrationen und Automationen.

Familienwechsel, Tarif-/Zugriffsinformation und ein gegebenenfalls verfügbarer App-Installationshinweis bleiben als eigener Kontext oberhalb dieser Gruppen. Sprache, Abmelden und Programminformation bleiben als sekundäre Systemaktionen am Ende.

Die interne persistierte Section-ID `organisation` bleibt aus Kompatibilitätsgründen erhalten. Nur die sichtbare Semantik heißt **Haushalt & Finanzen**.

## Today-Start und Legacy-Startscreen

Der normale App-Start bzw. **Heute** verwendet ausschließlich den kanonischen neuen Startscreen. Persistierte alte Today-Widget-Layouts werden dort nicht geladen und dürfen den Startscreen nicht nachträglich ersetzen.

Das bisherige konfigurierbare Today-Widget-Dashboard bleibt zur Kompatibilität erhalten, ist aber ausschließlich als sekundäre Detailseite **Mehr → Einstellungen & Verwaltung → Alter Legacy-Startscreen** erreichbar. Die Seite ist sichtbar als **Legacy** gekennzeichnet. Bestehende gespeicherte Widget-Reihenfolgen, Größen und Editor-Funktionen bleiben dort erhalten; der Legacy-Screen ist kein Eintrag der Hauptnavigation und wird beim normalen App-Start nicht gerendert.

## To-dos und Routinen: konsolidierte UX, vollständige Fachfunktionen

**To-dos** bleibt Primärnavigation und ist der gemeinsame tägliche Einstieg für Aufgaben und Routinen. Deshalb wird `Routinen` nicht zusätzlich als regulärer Eintrag unter **Mehr** wiederholt.

Dabei gehen keine Objekteigenschaften oder Einstellungen verloren:

- im To-do-Hub führt **Aufgaben & Listen** weiterhin in die vollständige Aufgaben-/Listen-/Workflow-Verwaltung,
- **Routinen verwalten** führt weiterhin in die vollständige Routinenverwaltung,
- Quick Create bietet für Aufgabe und Routine jeweils **Alle Felder** als Voll-Editor,
- bestehende Objekt-Deep-Links und `Bearbeiten` bleiben erhalten,
- objektbezogene **Zeitplan & Darstellung**-Optionen bleiben erreichbar,
- unter **Mehr** im To-do-Hub bleiben **Planung und Lernen**, Smart-To-do-Einstellungen, Verlauf und Workflows erreichbar.

Die Konsolidierung betrifft also nur Navigation und Scanbarkeit. Task-, Routine- und Finance-Domains, Datenmodelle, APIs und Berechtigungen bleiben getrennt und vollständig erhalten.

## Persönliche Anordnung

Alle drei Hauptbereiche sind einklappbar. Der Zustand wird lokal pro Familie gespeichert und nach einem Reload wiederhergestellt.

Die Standardansicht zeigt keine permanenten Drag-Griffe. Über den sekundären Button **Anpassen** wird ein expliziter Sortiermodus geöffnet. Erst dort erscheinen die 44×44-px-Griffe.

Im Sortiermodus können die Bereiche per Drag & Drop neu angeordnet werden. Die Pointer-Interaktion funktioniert mit Maus und Touch. Für Keyboard-Nutzung kann der Griff fokussiert und mit den Pfeiltasten **hoch/runter** verschoben werden; Screenreader erhalten eine Live-Ansage der neuen Position. Die Reihenfolge wird lokal pro Familie gespeichert. **Fertig** beendet den Sortiermodus, ohne die gespeicherte Ordnung zu verändern.

Die lokale Persistenz bleibt bewusst ein UI-Detail. Eine geräteübergreifende oder serverseitig abgeleitete Navigationspräferenz würde separat modelliert.

## Keine Duplikate zur Hauptnavigation

Ein Ziel, das bereits in der Hauptnavigation sichtbar ist, wird nicht nochmals unter **Mehr** angeboten. Deshalb erscheint der Kalender ausschließlich in der Hauptnavigation. To-dos bleibt ebenfalls ausschließlich Primärnavigation; die vollständigen Aufgaben-/Routine-Verwaltungswege liegen innerhalb dieses Hubs.

Die optionalen Module **Baby** und **Haustiere** erscheinen unter **Mehr** nur, wenn sie nicht bereits als eigener Hauptnavigationseintrag aktiv sind. Ist ein optionales Modul noch nicht aktiviert, aber für das aktuelle Mitglied administrierbar, bleibt sein Zugang unter **Mehr** sichtbar. Entitlement-Locks und bestehende Rollenregeln werden durch die Informationsarchitektur nicht verändert.

## UI-Vertrag

Die Seite verwendet weiterhin die bestehenden `Card`, `menu-row`- und `section-title`-Primitives. Collapse bleibt jederzeit direkt nutzbar; Reorder-Chrome wird progressiv über **Anpassen** offengelegt.

Verbindlich bleiben:

- mindestens 44 px große Interaktionsziele,
- keine Drag-only-Kernfunktion,
- sichtbarer Fokus,
- Keyboard- und Screenreader-Alternative,
- Reduced Motion,
- 320 px und 390×844 ohne horizontalen Overflow,
- vorhandene Rollen-, Entitlement-, Deep-Link- und Family-Switching-Verträge.

Die sichtbaren `Mehr`-Texte liegen in einer eigenen i18n-Ressource für DE/EN/FR/NL/TH. Die bestehende Feature-/Navigation-Registry bleibt kanonischer Owner der Zielseiten; hier wird keine zweite Fach-Registry eingeführt.

## Reihenfolge zur Offline-Readiness

Dieser Slice ist die explizit dokumentierte, eng begrenzte IA-Vorbedingung vor der Offline-first Implementierung aus #705/#706. Er ändert keinen IndexedDB-, Outbox-, Cursor-, Conflict-, Task- oder Expense-Sync-Vertrag. Nach dem Merge kann #706 auf stabilen Routen und einer stabilisierten Informationsarchitektur aufsetzen.

Refs #223 #577 #657 #698 #705 #714 #823
