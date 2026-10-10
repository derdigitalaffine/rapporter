# Integrationen

Integrationen holen Informationen aus anderen Quellen nach FamilyOS.

Du findest sie unter **Mehr → Integrationen**.

![Integrationsübersicht von FamilyOS](screenshots/integrations.webp)

## So gehst du vor

1. Öffne den Integrationskatalog.
2. Wähle die Quelle, die du verbinden möchtest.
3. Folge dem geführten Einrichtungsablauf.
4. Speichere die Verbindung.
5. Starte bei Bedarf eine Synchronisierung.

FamilyOS zeigt dir den Status der Quelle. Wenn eine Synchronisierung fehlschlägt, bleiben Fehlerstatus und ein möglicher neuer Versuch sichtbar.

## Typische Quellen

Je nach Installation stehen unter anderem zur Verfügung:

- ICS/iCal-Kalender,
- Google Calendar,
- Microsoft 365,
- WebUntis und Moodle über iCal,
- Abfallkalender für Stadt/Landkreis Kaiserslautern,
- Wetter und Warnungen,
- Home Assistant,
- VRN-Abfahrten,
- Telegram und PWA-Teilen.

Nicht jede Quelle braucht denselben Einrichtungsweg.

## Kalender über ICS

Bei einem privaten Kalender-Link gilt: Behandle ihn wie ein Passwort.

Gib ihn nur in der vorgesehenen Integrationsmaske ein und teile ihn nicht in Mitteilungen oder Screenshots.

Nach einer erfolgreichen Synchronisierung erscheinen die Termine im gemeinsamen **Kalender**. FamilyOS verarbeitet dabei auch wiederkehrende ICS-Termine, ausgelassene oder verschobene Einzeltermine und abgesagte Vorkommen. Entfernt die Quelle einen Termin, verschwindet dessen FamilyOS-Projektion nach der nächsten erfolgreichen Synchronisierung ebenfalls.

Ganztägige ICS-Einträge bleiben an ihrem Kalendertag verankert. Externe Kalendertermine sind in FamilyOS schreibgeschützt; ändere sie in der Originalquelle.

## Google oder Microsoft

Wenn OAuth für eure Installation eingerichtet ist, führt dich FamilyOS durch die Verbindung. Alternativ können – je nach Anbieter und Einrichtung – iCal/ICS-Links genutzt werden.

Der Kalenderzugriff ist für die unterstützten externen Kalenderintegrationen auf Lesen ausgerichtet. Termine aus solchen Quellen bearbeitest du in der Originalanwendung.

## Darstellung einer Kalenderquelle anpassen

Owner und Erwachsene können im **Kalender** unter **Quellen anpassen** eine Farbe und ein unterstütztes Font-Awesome-Symbol für eine verbundene Kalenderquelle auswählen.

Das ändert nur die Darstellung. Die Verbindung, der private Link und andere Zugangsdaten werden dadurch nicht überschrieben.

## Wenn Termine fehlen oder falsch wirken

1. Öffne **Mehr → Integrationen** und prüfe den Status der betroffenen Kalenderquelle.
2. Starte eine erneute Synchronisierung, wenn die Aktion angeboten wird.
3. Öffne danach den **Kalender** und prüfe, ob die Quelle dort eingeblendet ist.
4. Bei wiederkehrenden Terminen: Prüfe auch in der Originalquelle, ob ein einzelnes Vorkommen verschoben, ausgelassen oder abgesagt wurde.

Eine erfolgreiche Neusynchronisierung gleicht den aktuellen Feed mit den vorhandenen Projektionen ab. Veraltete ICS-Projektionen werden dabei entfernt.

## Wenn eine Integration rot oder fehlerhaft ist

1. Öffne die betroffene Quelle.
2. Lies den angezeigten Status.
3. Prüfe Zugang, URL oder Verbindung.
4. Nutze **Erneut versuchen** bzw. synchronisiere erneut, wenn die Aktion angeboten wird.

Wenn der Fehler bleibt, hilft dir **[Fehlerhilfe](troubleshooting.md)** weiter.
