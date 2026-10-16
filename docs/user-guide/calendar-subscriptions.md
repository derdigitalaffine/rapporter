# Familienkalender in anderen Kalender-Apps

FamilyOS trennt zwei Funktionen bewusst voneinander:

1. **Kalender abonnieren** ist ein einfacher, widerrufbarer **Nur-Lesen-Link**. Dafür ist kein CalDAV-Konto nötig.
2. **Apple Kalender & CalDAV** ist optional. Damit kann pro Familienmitglied genau ein externer Kalender verbunden und – wenn ausdrücklich gewählt – auch beschrieben werden.

## Kalender abonnieren

Im Kalender ist **Abonnieren** nur eine dezente Zusatzaktion. Dieselbe Verwaltung findest du unter **Einstellungen → Kalender-Abonnements**. Owner und erwachsene Familienmitglieder verwalten ihre eigenen Abo-Links.

Beim Erstellen wählst du einen Namen und die **freigegebene Detailtiefe**:

- **Nur Belegt-Zeiten** – Titel, Ort und Notizen werden nicht übertragen.
- **Titel und Zeit** – Titel und Terminzeit werden übertragen.
- **Titel, Zeit und Ort** – zusätzlich darf der Ort übertragen werden.

Die Detailtiefe kann später am bestehenden Link geändert werden. Der Link bleibt dabei gleich und muss nicht neu eingerichtet werden. Die neue Stufe wirkt beim nächsten Abruf der Kalender-App. Notizen, Dokumente, Gesundheitsdaten, importierte Kalender und andere beliebige Event-Payloads werden in keiner Stufe exportiert.

Der angezeigte dauerhafte Link ist ein Zugangsschlüssel. **Jeder mit diesem Link kann die dafür freigegebenen Termine lesen**, bis du ihn widerrufst. Behandle ihn deshalb wie ein Passwort.

Exportiert werden ausschließlich eigene FamilyOS-Termine, die ausdrücklich für die ganze Familie markiert sind. Persönliche bzw. nur ausgewählte Termine ohne Familienfreigabe und importierte Kalender bleiben ausgeschlossen.

## iPhone und iPad

**Auf iPhone/iPad installieren** lädt ein Apple-Konfigurationsprofil für **abonnierte Kalender**. Es richtet keinen beschreibbaren CalDAV-Account ein und enthält keine CalDAV-Zugangsdaten.

Bei einer Familie mit mehreren aktiven Mitgliedern enthält das Profil **einen lesenden Kalender pro Familienmitglied**. Dabei wird die bestehende Familienfreigabe nicht erweitert:

- Familientermine ohne Teilnehmerauswahl erscheinen bei allen Mitgliedern.
- Familientermine mit Teilnehmerauswahl erscheinen nur in den Kalendern der ausgewählten Mitglieder.
- Termine ohne Familienfreigabe erscheinen in keinem dieser Abo-Kalender.

Öffne FamilyOS in Safari, lade das Profil und bestätige die Installation anschließend in den iOS/iPadOS-Einstellungen. Das Profil ist kein Geräte-Management-Profil; es fügt nur abonnierte Kalender hinzu. Ein Download allein bedeutet noch nicht, dass das Profil installiert wurde.

## Optional: Apple Kalender / CalDAV verbinden

Unter **Einstellungen → Apple Kalender & CalDAV** kannst du optional pro Familienmitglied eine CalDAV-Verbindung einrichten. Das Abo oben funktioniert auch ohne diese Verbindung.

Für eine Verbindung brauchst du Server-Adresse, Benutzername und das vom Anbieter vorgesehene Passwort bzw. App-spezifische Passwort. FamilyOS zeigt die gespeicherten Zugangsdaten und die private Remote-Kalender-URL später nicht wieder an.

Nach der Anmeldung sucht FamilyOS serverseitig nach den verfügbaren Kalendern. Du wählst einen Kalender aus und legst den Modus fest:

- **Nur lesen** – Remote-Termine werden in FamilyOS eingeblendet; FamilyOS schreibt nichts zurück.
- **Lesen & Schreiben** – zusätzlich werden passende FamilyOS-Termine dieses Familienmitglieds in den ausgewählten Remote-Kalender geschrieben.

Pro Familienmitglied kann höchstens ein Remote-Kalender verbunden sein. Wechselst du Zugangsdaten oder den ausgewählten Remote-Kalender, verwirft FamilyOS die alte lokale Projektion und synchronisiert die neue Verbindung sauber neu.

### Was im Schreibmodus passiert

Neue einfache Termine werden mit einer stabilen UID angelegt. Änderungen und Löschungen werden nur mit dem zuletzt bekannten ETag (`If-Match`) geschrieben. Hat sich der Termin auf der Gegenseite inzwischen ebenfalls geändert, meldet FamilyOS einen Konflikt statt eine Seite still zu überschreiben.

Wiederkehrende **Remote-Termine** werden im abgefragten Zeitraum serverseitig expandiert und lesbar in FamilyOS projiziert. Das Zurückschreiben von FamilyOS-Serienterminen, Einladungen/Teilnehmern und iTIP-Scheduling ist in diesem ersten Write-Slice bewusst deaktiviert.

## Zugriff beenden oder erneuern

**Link widerrufen** beendet künftige Abo-Abrufe über diesen Link und die daraus installierten Apple-Abo-Kalender. Bereits heruntergeladene Kopien können auf Geräten verbleiben.

**Neuen Link erzeugen** macht den bisherigen Abo-Schlüssel ungültig. Geräte, die den alten Link bzw. das alte Profil verwenden, müssen anschließend neu eingerichtet werden.

Eine CalDAV-Verbindung wird separat entfernt. Dabei löscht FamilyOS die zugehörige lokale Import-Projektion und gespeicherten Verbindungsinformationen; andere FamilyOS-Termine bleiben bestehen.

Voraussetzung für abonnierte Kalender ist eine vom Betreiber konfigurierte öffentliche HTTPS-App-Adresse mit gültigem Zertifikat.
