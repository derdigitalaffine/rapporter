# Persönliche Nachrichten und Freundesduelle

Das **Nachrichten-Symbol im globalen Header** öffnet persönliche Chats, Freunde sowie die nativen Kanäle **Familie** und **System**. Der Familienchat ist für berechtigte Mitglieder beschreibbar; Systemhinweise bleiben nur lesbar. Die fünf sichtbaren Hauptziele bleiben Heute, To-dos, Einkauf, Kalender und Mehr.

Unter **Hinzufügen → Alle Aktionen → Mitteilung** öffnet sich der beschreibbare Familienchat der aktuell ausgewählten Familie mit fokussierter Nachrichteneingabe. Gesendet wird erst ausdrücklich. Ein fehlender beschreibbarer Familienchat führt nie zu einem persönlichen Chat oder einer anderen Familie.

Die persönliche Freundschaft ist kein Familienbeitritt: Aufgaben, Kalender, Dokumente und Familien-Spiele behalten ihre bisherigen Berechtigungen. Der interne Familienchat braucht keine externe Freundschaftseinladung; der persönliche Kontakt- und Zustimmungsvertrag bleibt davon getrennt.

## Freunde und Einladungen

**Freunde → Per E-Mail einladen** verschickt eine sieben Tage gültige Einladung. Der Empfänger entscheidet ausdrücklich über die Annahme. Nur die eingeladene, bestätigte E-Mail-Adresse kann zustimmen. Wer noch kein Konto hat, kann über die an sein Postfach gelieferte Einladung eines erstellen; dabei entsteht keine Familienmitgliedschaft. Bestätigte Erwachsene/Teens können persönliche Chats verwenden; Kinder, Gäste und unbestätigte Konten erhalten keinen persönlichen Chat-Zugang. Ein ausdrücklich begonnenes bzw. angenommenes persönliches Profil bleibt auch nach Verlassen der Familie nutzbar. Eine ausgesetzte Familie sperrt ihre Familieninhalte, nicht den persönlichen Messenger. Bestehende Kinder-/Gastrollen und global gesperrte Konten bleiben ausgeschlossen.

Einladungen können zurückgezogen werden. Die Oberfläche zeigt dem Sender nicht, ob eine fremde Adresse bereits registriert oder blockiert ist. Entfernen und Blockieren sperren neue Nachrichten, Tippanzeige und Duelle. Entblocken stellt die Freundschaft nicht wieder her. Dafür braucht es erneut eine angenommene Einladung.

## Gespräche

Einzelchats entstehen nur zwischen bestätigten Freunden. Gruppen laden Freunde ein; jedes Mitglied muss selbst beitreten. Nachrichten vor dem Beitritt sind nicht sichtbar. Nach dem Verlassen ist der bisherige Verlauf nur noch lesbar; später bearbeitete Nachrichten werden nicht nachträglich sichtbar.

Text, Emoji, Antworten, Bearbeiten, Löschen für alle, Reaktionen, Suche, ältere Nachrichten und Lesebestätigungen stehen im Chat zur Verfügung. Lesebestätigungen und Push können in den Chat-Einstellungen abgeschaltet werden; einzelne Chats lassen sich stummschalten. Tippanzeige läuft nach acht Sekunden ab und wird nur für berechtigte aktive Teilnehmer gezeigt.

Bilder und PDFs sind private Anhänge (höchstens fünf Dateien zu je 30 MB); Bilder werden über den vorhandenen Dokument-Validator neu kodiert und von Metadaten bereinigt. PDFs werden als Download ausgeliefert. Sprachnachrichten brauchen eine ausdrückliche Mikrofonfreigabe; die Aufnahme endet spätestens nach zwei Minuten. App-Wechsel und Verlassen beenden die Aufnahme. Audio wird vor dem Senden als Entwurf angezeigt. Es gibt keine Aufnahme im Hintergrund.

Nachrichten werden auf dem FamilyOS-Server gespeichert. Es wird keine Ende-zu-Ende-Verschlüsselung zugesagt. Chattexte, Anhänge und Einladungstokens werden nicht für Offline-Caches oder Analytics verwendet. Offline bleiben Eingaben nur im aktuell geöffneten Chat; beim Verlassen oder Abmelden werden sie verworfen. Push enthält nur generische Hinweise, keine Chattexte. Bestehende Ruhezeiten werden berücksichtigt.

## Spiele

Den Kontaktkopf eines Einzelchats öffnen und **Freundesduelle** wählen. Schere/Stein/Papier, Schiffe versenken, Quiz und Vier Gewinnt verwenden dieselben vorhandenen Spiele wie die Familie. Persönliche Duelle sind ausschließlich **just for fun**; Familienaufgaben und Einsätze sind ausgeschlossen. Nur die exakten beiden Spieler mit aktiver Freundschaft können das Duell lesen oder spielen. Ein Familien-Owner erhält dadurch keine Zusatzrechte.

## Betrieb und Migration

Die bestehende WSGI-Architektur bleibt: begrenztes Vordergrund-Polling und in der Datenbank gespeicherte Typing-TTL funktionieren über mehrere Worker. `/api/chat/` und `/api/games/` sind grundsätzlich `private, no-store`. Einladungen nutzen EmailIdentity, MailOutbox und AuthAbuse; persönliche Benachrichtigungen erweitern den bestehenden Notification-Core um einen expliziten User-Empfänger mit XOR-Scope-Constraint.

Additive Migrationen: neue Messenger-Tabellen, persönliche Game-Spieler-FKs neben vorhandenen Membership-Spielern und nullable Family/Recipient plus User-Recipient in Notifications. Bestehende Familiendaten werden nicht umgeschrieben. Zuerst Migrationen, dann neuer Code. Bei einem Rollback persönlichen Chat-/Game-Traffic deaktivieren; ältere Server verstehen persönliche Game-/Notification-Zeilen nicht. Keine Contract-Migration und kein Löschen bestehender Daten.
