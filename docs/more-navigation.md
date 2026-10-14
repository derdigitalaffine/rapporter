# Navigation unter „Mehr“

Die Seite **Mehr** bündelt Ziele, die nicht in der primären Hauptnavigation liegen. Sie ist nach Nutzungskontext statt nach technischer Modulreihenfolge gegliedert.

## Reihenfolge

1. **Familie & Alltag** – häufige familienbezogene Funktionen wie Pinnwand, Routinen, Geburtstage, Reisen, Entscheidungen, Wunschlisten und Spiele.
2. **Organisation** – strukturierende Bereiche wie Ausgaben, Statistik, Verträge, Dokumente, Karten und Fahrzeuge, soweit Rolle und Entitlement sie erlauben.
3. **Einstellungen & Verwaltung** – Einrichtung, Profil, Einstellungen, Familienverwaltung, Benachrichtigungen, Integrationen und Automationen.

Familienwechsel, Tarif-/Zugriffsinformation und ein gegebenenfalls verfügbarer App-Installationshinweis bleiben als eigener Kontext oberhalb dieser Gruppen. Sprache, Abmelden und Programminformation bleiben als sekundäre Systemaktionen am Ende.

## Keine Duplikate zur Hauptnavigation

Ein Ziel, das bereits in der Hauptnavigation sichtbar ist, wird nicht nochmals unter **Mehr** angeboten. Deshalb erscheint der Kalender ausschließlich in der Hauptnavigation. Die optionalen Module **Baby** und **Haustiere** erscheinen unter **Mehr** nur, wenn sie nicht bereits als eigener Hauptnavigationseintrag aktiv sind.

Die Einrichtbarkeit bleibt dabei erhalten: Ist ein optionales Modul noch nicht aktiviert, aber für das aktuelle Mitglied administrierbar, bleibt sein Zugang unter **Mehr** sichtbar. Entitlement-Locks und bestehende Rollenregeln werden durch die Informationsarchitektur nicht verändert.

## UI-Vertrag

Die Seite verwendet weiterhin die bestehenden `Card`, `menu-row`- und `section-title`-Primitives. Dadurch bleiben Touchziele, Keyboard-Navigation, Fokusdarstellung und die visuelle Sprache konsistent mit dem restlichen FamilyOS.

Diese Ordnung ist der fokussierte Consumer-Slice aus #657. Die geplante zentrale Ableitung der Navigation aus der Feature Registry bleibt Eigentum von #577; hier wird keine zweite Registry eingeführt.

Refs #223 #577 #657
