# Redaktionsleitfaden für die Anwenderdoku

Dieser Leitfaden ist für alle gedacht, die `docs/user-guide/` pflegen.

## Ziel

Die Doku soll sich wie gute Aufbauanleitung anfühlen: ruhig, direkt, konkret.

Nicht: „Das Subsystem unterstützt verschiedene Entitäten.“

Sondern: „Öffne **Aufgaben**. Wähle deine Liste. Füge die Aufgabe hinzu.“

## Ton

- immer **Du**
- kurze Sätze
- aktive Verben
- zuerst die Handlung, dann die Erklärung
- keine internen Modell-, API- oder Datenbankbegriffe
- keine Werbesprache
- keine Beruhigungsfloskeln
- lieber ein konkretes Beispiel als drei abstrakte Absätze

## Standardaufbau eines Kapitels

1. Ein Satz: Wofür ist der Bereich da?
2. Der häufigste Ablauf in wenigen Schritten.
3. Nur danach: Sonderfälle und Einstellungen.
4. Ein kurzer „Tipp“ oder eine wichtige Grenze.
5. Link zum nächsten passenden Kapitel.

## UI-Bezeichnungen

Schreib Buttons, Menüpunkte und sichtbare Begriffe **fett** und übernimm ihre Bezeichnung aus der aktuellen deutschen UI.

Wenn die UI geändert wird, muss die Doku im selben PR aktualisiert werden oder ein klar verlinktes Doku-Issue entstehen.

## Screenshots

Screenshots sollen:

- aus aktuellen automatisierten E2E-Tests stammen, wenn eine passende Ansicht vorhanden ist,
- nur Test-/Fixture-Daten zeigen,
- mobile Ansichten bevorzugen,
- nicht mehr Daten zeigen als für den Zweck nötig,
- unter `docs/user-guide/screenshots/` liegen,
- als WebP klein gehalten werden,
- einen sinnvollen Alt-Text besitzen.

Ein Screenshot ist Hilfe, nicht Voraussetzung. Der Text muss auch ohne Bild verständlich bleiben.

## Was nicht in die Anwenderdoku gehört

- API-Pfade
- Datenbankmodelle
- Secrets oder Beispiel-Secrets
- interne Architekturentscheidungen
- Features, die nur in offenen Issues geplant sind
- Betreiber-Setup, Docker, Caddy und Backup-Kommandos

Diese Inhalte bleiben in technischer Dokumentation bzw. README.

## Definition of Done für ein Anwenderkapitel

- [ ] aktueller Stand von `main` geprüft
- [ ] UI-Begriffe stimmen
- [ ] in Du-Form geschrieben
- [ ] häufigster Ablauf zuerst
- [ ] Rechte/Grenzen nur dort erklärt, wo sie den Ablauf beeinflussen
- [ ] keine geplanten Funktionen als fertig beschrieben
- [ ] relative Links geprüft
- [ ] Screenshot aktuell, wenn ein Bild sinnvoll ist
- [ ] keine echten privaten Daten im Screenshot

## Pflege bei Feature-PRs

Bei jeder sichtbaren Änderung kurz fragen:

1. Ändert sich ein Menüpunkt?
2. Ändert sich ein Ablauf?
3. Ändert sich, wer etwas darf?
4. Kommt eine neue nutzbare Funktion hinzu?
5. Wird ein Screenshot sichtbar falsch?

Wenn eine Antwort **ja** ist, gehört die passende Doku-Änderung in denselben PR oder in ein verlinktes Folge-Issue.
