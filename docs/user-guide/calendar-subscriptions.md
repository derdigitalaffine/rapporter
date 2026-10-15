# Familienkalender abonnieren

Im **Kalender → Kalender abonnieren** oder unter **Einstellungen →
Kalender-Abonnements** öffnest du dieselbe Verwaltung. Owner und erwachsene
Familienmitglieder verwalten ihre eigenen Abos. Gib einen Gerätenamen ein und
wähle **Abo-Link erstellen**. Bei Bedarf bestätigst du deine Identität erneut mit
Passkey oder Kontopasswort.

Der angezeigte **dauerhafte Abo-Link** ist kein Einmal-Login. Du kannst ihn kopieren
und in einer Kalender-App als Kalender-Abonnement hinzufügen oder **In Kalender-App
öffnen** wählen. Die App ruft den Kalender regelmäßig ab. Aktualisierungen können
je nach Kalender-App verzögert erscheinen.

**Jeder mit diesem Link kann die freigegebenen Termine lesen.** Behandle ihn wie
ein Passwort. Enthalten sind ausschließlich ausdrücklich gemeinsame eigene
Familientermine; die Personenauswahl beschreibt die Teilnahme und ändert die
ausdrückliche Familienmarkierung nicht. Termine ohne Familienmarkierung, importierte
Kalender, Gesundheitsinformationen und geschützte Daten werden nicht exportiert.
Übertragen werden Titel, Zeiten und Serien; Orte und Notizen bleiben in FamilyOS.

## Zusätzlich: iPhone und iPad

Der sichtbare Link bleibt verfügbar. **iPhone-Profil herunterladen** ist eine
zusätzliche Einrichtungsmöglichkeit: Öffne FamilyOS in Safari, lade das Profil
herunter und bestätige die Installation in **Einstellungen → Allgemein → VPN und
Geräteverwaltung**. iOS kann das unsignierte Profil entsprechend kennzeichnen.
Das Profil fügt nur ein lesendes Kalenderkonto hinzu. Es installiert keine
Geräteverwaltung oder Zertifikate. Ein Download bestätigt noch keine Installation.

Alternativ kannst du den Abo-Link verwenden oder unter **CalDAV manuell einrichten**
die gesonderte Principal-URL, den Benutzernamen und das Abo-Passwort übernehmen.
Das Abo-Passwort ist nicht dein FamilyOS-Kontopasswort.

## Zugriff beenden oder erneuern

**Link widerrufen** beendet zukünftige Abrufe sowohl über den Link als auch über
das zugehörige Profil. Bereits heruntergeladene Kopien können auf anderen Geräten
bleiben. Entferne das Konto oder Abo bei Bedarf zusätzlich in deiner Kalender-App.

**Neuen Link erzeugen** ersetzt den alten Schlüssel nach Bestätigung. Der alte
Link und die Zugangsdaten im alten Profil werden sofort ungültig. Binde den neuen
Link oder das neue Profil auf allen gewünschten Geräten erneut ein.

Voraussetzung ist eine vom Betreiber konfigurierte öffentliche HTTPS-App-Adresse
mit gültigem Zertifikat. Quartalsserien zeigen das kanonische Zeitfenster von einem
Jahr Vergangenheit bis drei Jahre Zukunft, das beim Abruf weiterwandert.
