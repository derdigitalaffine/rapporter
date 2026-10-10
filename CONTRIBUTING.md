# Contributing to FamilyOS

Danke fürs Mitentwickeln an FamilyOS.

Diese Datei ergänzt die technische Dokumentation um einen verbindlichen Issue-/PR-Workflow. Ziel ist, dass jederzeit sichtbar ist, woran aktiv gearbeitet wird, parallele Arbeit früh koordiniert wird und ein Issue erst geschlossen wird, wenn es wirklich abgeschlossen ist.

Für Menschen **und** Coding-Agenten gilt zusätzlich der detaillierte Koordinationsvertrag in [`AGENTS.md`](AGENTS.md) sowie die Erläuterung unter [`docs/development/agent-coordination.md`](docs/development/agent-coordination.md).

## Issue-Status: Arbeit sichtbar machen

Sobald du die aktive Bearbeitung eines Issues beginnst:

1. Setze das bestehende Label **`in progress`** auf das Issue.
2. Falls das Issue zusätzlich in einem GitHub Project mit Statusfeld liegt, setze dort ebenfalls **`In Progress`**.
3. Prüfe vor Implementierungsstart #223, alle offenen `in progress`-Issues und offene PRs auf Überschneidungen.
4. Hinterlasse einen strukturierten `coordination:claim:v1`-Kommentar gemäß `AGENTS.md`.
5. Verlinke den zugehörigen PR mit dem Issue, sobald er existiert.

Ein Claim reserviert nur einen **engen, konkret beschriebenen Scope**, niemals eine ganze Domain. Wenn sich zwei aktive Arbeiten überschneiden, stimmen sich die Beteiligten **vor weiterer Implementierung per GitHub-Kommentar** über Split, Reihenfolge, gemeinsamen Vertrag oder Handoff ab. Doppelimplementierungen durch stilles Parallelrennen sind nicht erwünscht.

Ein Issue bleibt `in progress`, solange aktiv daran gearbeitet wird oder ein zugehöriger PR noch fachlich/technisch aussteht.

Wenn die Arbeit bewusst pausiert oder verworfen wird, entferne `in progress` wieder und dokumentiere den Grund sowie einen kurzen Handoff im Issue.

## Zentrale Koordination über #223

#223 ist die gemeinsame Roadmap- und Koordinationsinstanz für größere Abhängigkeiten, Architekturkonflikte und die Gesamtpriorisierung.

Das automatische Koordinations-Dashboard in #223 dient als gemeinsames Lagebild. Es weist unter anderem auf parallele PRs für dasselbe Issue, exakte Dateiüberschneidungen, aktive Claims ohne sichtbaren PR und fehlende Research-Blöcke bei externen Produkt-Feature-Issues hin.

Warnungen sind zunächst ein Signal zur Abstimmung, nicht automatisch ein fachlicher Ablehnungsgrund. Bei echtem Overlap muss die Abstimmung jedoch sichtbar dokumentiert werden.

## Externe Feature-Issues: Reporter entlasten, intern gründlich recherchieren

Externe Nutzer sollen ein Problem oder einen gewünschten Workflow beschreiben können, ohne unsere interne Architektur oder den Markt selbst analysieren zu müssen.

Vor Implementierung eines extern gemeldeten Produkt-Features übernimmt deshalb ein Maintainer oder Agent die Aufbereitung:

- bestehende FamilyOS-Funktionalität und mögliche Duplikate prüfen,
- Einordnung gegen #223 und die kanonischen Cores,
- aktuelle Web-Recherche zu **3–5 relevanten Wettbewerbern**,
- bevorzugt Primärquellen/Produktdokumentation nutzen,
- wiederkehrende erfolgreiche UX-Muster, Mobile-/Accessibility-/Privacy-Aspekte und Trade-offs herausarbeiten,
- ausdrücklich dokumentieren, was FamilyOS **nicht** kopieren sollte,
- standardisierten Kommentarblock `external-research:v1` aus `AGENTS.md` hinterlegen,
- daraus einen FamilyOS-spezifischen Scope und aktualisierte Acceptance Criteria ableiten.

Diese Recherchepflicht liegt bei Maintainer/Agent, nicht beim externen Reporter.

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

- Ein nicht-trivialer PR referenziert das zugehörige Issue.
- Große Misch-PRs vermeiden; Änderungen entlang klarer fachlicher Grenzen schneiden.
- Vor Review den Collision Scan erneut durchführen, insbesondere nach Rebase oder größeren Scope-Änderungen.
- Material Overlap mit anderen aktiven PRs/Issues im jeweiligen Thread sichtbar dokumentieren.
- Security-/Permission-Änderungen benötigen negative Tests für fremde Familien/Objekte.
- User-facing Flow-, Rollen- oder Navigationsänderungen benötigen passende Doku.
- User-facing PRs referenzieren bei relevanter Interaction-/IA-Arbeit #247 bzw. `docs/product/ux-philosophy.md`.
- Externe Produkt-Feature-Issues benötigen vor Merge den `external-research:v1`-Block.
- `in progress` wird erst entfernt, wenn die Arbeit tatsächlich abgeschlossen oder bewusst pausiert ist.
