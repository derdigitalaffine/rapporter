# Contributing to FamilyOS

Danke fürs Mitentwickeln an FamilyOS.

Diese Datei ergänzt die technische Dokumentation um einen kleinen, verbindlichen Issue-/PR-Workflow. Ziel ist, dass jederzeit sichtbar ist, woran aktiv gearbeitet wird und wann ein Issue wirklich abgeschlossen ist.

## Issue-Status: Arbeit sichtbar machen

Sobald du die aktive Bearbeitung eines Issues beginnst:

1. Setze das bestehende Label **`in progress`** auf das Issue.
2. Falls das Issue zusätzlich in einem GitHub Project mit Statusfeld liegt, setze dort ebenfalls **`In Progress`**.
3. Verlinke den zugehörigen PR mit dem Issue.

Ein Issue bleibt `in progress`, solange aktiv daran gearbeitet wird oder ein zugehöriger PR noch fachlich/technisch aussteht.

Wenn die Arbeit bewusst pausiert oder verworfen wird, entferne `in progress` wieder und dokumentiere den Grund kurz im Issue.

## Wann ein Issue geschlossen wird

Ein Issue wird **nicht** bereits geschlossen, weil ein PR eröffnet wurde.

Schließe es erst, wenn:

- die relevanten Acceptance Criteria erfüllt sind,
- Migrationen/Backfills soweit erforderlich geprüft sind,
- Berechtigungs- und Cross-family-Tests vorhanden sind,
- relevante Backend-/Frontend-/E2E-Checks grün sind,
- notwendige Dokuänderungen enthalten oder sauber verlinkt sind,
- die Änderung gemergt ist bzw. der definierte Abschlusszustand erreicht wurde.

Danach `in progress` entfernen und das Issue mit passendem Abschlussgrund schließen.

## Architektur vor Implementierung prüfen

Bei größeren Änderungen zuerst #223 (FamilyOS Master Roadmap) prüfen.

Beantworte insbesondere:

- Welche kanonische Domain wird wiederverwendet?
- Welcher bestehende Core/Adapter ist zuständig?
- Welche Family-/Objektberechtigungen gelten?
- Wie funktioniert Migration/Rollback?
- Was ist der häufigste mobile Flow?
- Welche Accessibility-, Retry- und Idempotenzregeln gelten?
- Welche Daten dürfen in Logs/Audit/Telemetry landen?

Neue Fachmodule sollen bestehende Tasks, Kalender, Dokumente, Notizen, Shopping, Expenses und Context-Link-Infrastruktur referenzieren statt parallele Datenwelten aufzubauen.

## UX-/Navigationsvertrag

Für alle user-facing Änderungen gilt zusätzlich #247 und die kanonische Dokumentation unter `docs/product/ux-philosophy.md`.

Vor einem PR prüfen:

- Bleibt die primäre Navigation `Heute · Aufgaben · Einkauf · Kalender · Mehr` konsistent?
- Führt der häufigste eindeutige Weg möglichst direkt in den Arbeits-/Nutzungszustand statt über eine unnötige Landing Page?
- Bleiben seltene/erweiterte Funktionen per Progressive Disclosure erreichbar?
- Geht durch Vereinfachung keine bestehende Funktion verloren?
- Nutzt die Änderung bestehende Create-/Sheet-/Back-/Deep-Link-Primitives statt eine Feature-Sonderwelt zu bauen?
- Trägt ein optionales Modul höchstens einen Root-Eintrag zu `Hinzufügen` bei?
- Zeigt `Heute` Relevanz statt bloß Feature-Inventar?
- Funktioniert der Kernflow auf 390×844 ohne Horizontaloverflow mit 44px+ primären Touchzielen?
- Bleiben Keyboard, Screenreader und 200% Zoom dort nutzbar, wo sie anwendbar sind?
- Sind Rechte schon in der UI verständlich antizipiert und weiterhin serverseitig erzwungen?

Bei einem Konflikt zwischen fachlicher Darstellung und globaler Interaction-Philosophie bleibt das Fachissue für Domain-/Datenregeln zuständig; #247 entscheidet die gemeinsame Navigations-/Interactionsebene.

## PR-Konvention

- Ein PR sollte das zugehörige Issue referenzieren.
- Große Misch-PRs vermeiden; Änderungen entlang klarer fachlicher Grenzen schneiden.
- Security-/Permission-Änderungen benötigen negative Tests für fremde Familien/Objekte.
- User-facing Flow-, Rollen- oder Navigationsänderungen benötigen passende Doku.
- User-facing PRs referenzieren bei relevanter Interaction-/IA-Arbeit #247 bzw. `docs/product/ux-philosophy.md`.
- `in progress` wird erst entfernt, wenn die Arbeit tatsächlich abgeschlossen oder bewusst pausiert ist.
