# Einkauf

FamilyOS behandelt Einkauf als eine kanonische Shopping-Domain mit zwei bewusst unterschiedlichen Arbeitsmodi: **Planung** und **Im Laden**. Planung dient dem schnellen Ergänzen und Organisieren; der Store Mode bleibt die fokussierte, offline-taugliche Checkliste.

## Einkaufslisten

Eine Liste beschreibt primär ihren **Zweck** (`Wocheneinkauf`, `Drogerie`, `Party`). Ein Geschäft ist optional und kann separat hinterlegt werden.

Beim Anlegen wird sichtbar entschieden, **für wen** die Liste gedacht ist:

- `Ganze Familie` – bestehender Standard und Migration alter Listen.
- `Nur ich` – private Liste.
- `Ausgewählte` – eine oder mehrere Personen bzw. eine angebotene Familiengruppe wie Erwachsene oder Kinder/Jugendliche.

Diese Auswahl ist eine echte serverseitige Objektberechtigung. Eine private oder ausgewählte Liste darf über Item-Endpunkte, Dashboard, Vorlagen, Store-Zuweisungen, Context Links, Predictions, Notifications oder erratene IDs nicht für andere Personen sichtbar werden.

Bestehende Listen ohne Access-Metadaten bleiben aus Kompatibilitätsgründen familienweit sichtbar. Da ihr ursprünglicher Ersteller nicht zuverlässig bekannt ist, dürfen nur Owner/Adults diesen Legacy-Vertrag nachträglich ändern.

## Sichtbarkeit und Zuständigkeit sind getrennt

`Für wen?` beantwortet **wer die Liste sehen und gemeinsam bearbeiten darf**.

`Wer kümmert sich?` ist nur eine verständliche Zuständigkeit. Sie erweitert keine Rechte und sperrt andere berechtigte Personen nicht. Eine Person kann also für den Einkauf zuständig sein, während andere weiterhin Artikel ergänzen oder abhaken.

## Gruppen

Shopping führt keinen eigenen Gruppen-/Identity-Core ein. Die persistierte Berechtigung besteht aus konkreten Family-Memberships. Komfortauswahlen wie `Erwachsene` oder `Kinder & Jugendliche` werden beim Speichern in diese Memberships aufgelöst. Ein späterer app-weiter Saved-Groups-Core kann denselben Picker speisen, ohne die Shopping-ACL neu zu modellieren.

## Listenwechsel

Die Navigation passt sich an die Anzahl sichtbarer Listen an:

- eine Liste: kein unnötiger Switcher,
- zwei bis vier Listen: direkte kompakte Auswahl,
- ab fünf Listen: kompakter Select/Picker mit aktiver Liste im Fokus.

`Neue Liste` bleibt sekundär, solange bereits eine nutzbare Liste existiert. Quick Add bleibt die dominante Planungsaktion und fügt Vorschläge niemals autonom hinzu.

## Privacy von Memory und Predictions

Family-weite Shopping-Memory- und Prediction-Daten dürfen keine Inhalte privater oder selektiv geteilter Listen aufnehmen. Bereits familienweit gelernte Daten bleiben familienweit; ein späterer Wechsel einer Liste auf privat macht keine ehemals öffentliche Historie rückwirkend geheim.

## Weitere P0-Slices

- #655: gemeinsame Einkaufssession, smoother Live-Sync und transientes Actor-Feedback.
- #656: Einkauf abschließen, Purchase-History und optionaler Übergang in Beleg/Ausgabe.

Referenzen: #508, #654, #132, #168, #400.