import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';

const resources = {
  de: { translation: {
    brandTagline:'Familie. Organisiert. Gemeinsam.', today:'Heute', tasks:'Aufgaben', shopping:'Einkauf', routines:'Zuletzt', more:'Mehr',
    greeting:'Hallo Familie 👋', nextUp:'Als Nächstes', add:'Hinzufügen', addTask:'Aufgabe hinzufügen', addItem:'Artikel hinzufügen', recentlyDone:'Zuletzt gemacht', dueSoon:'Demnächst wieder sinnvoll',
    integrations:'Integrationen', calendar:'Kalender', inbox:'Inbox', members:'Familie', login:'Anmelden', username:'Benutzername', password:'Passwort', logout:'Abmelden', language:'Sprache', noData:'Noch nichts hier.',
    installHint:'fam-uh-le kann als App installiert werden.', publicData:'Öffentliche Daten', offline:'Offline', online:'Online', back:'Zurück', sync:'Synchronisieren', synced:'Synchronisiert', never:'Noch nie', syncing:'Synchronisiere …',
    inboxHint:'Geteilte Inhalte aus Messenger, Browser und anderen Apps landen hier.', toTask:'Als Aufgabe', toShopping:'Zum Einkauf', dismiss:'Ausblenden', newItem:'Neu', processed:'Erledigt',
    integrationsHint:'Müllkalender, Warnungen, Wetter, Kalender und Messenger direkt in fam-uh-le verbinden.', endpoint:'Quelle', lastSync:'Letzter Sync', disabled:'Deaktiviert', enabled:'Aktiv',
    calendarHint:'Familientermine, Müllabfuhr, Wetter und Warnungen an einem Ort.', membersHint:'Wer gehört zu dieser Familie und welche Rolle hat die Person?', role:'Rolle',
    owner:'Inhaber', adult:'Erwachsen', teen:'Teenager', child:'Kind', guest:'Gast', refresh:'Aktualisieren', noUpcoming:'Keine kommenden Termine.', settings:'Einstellungen',
    loginFailed:'Anmeldung fehlgeschlagen. Bitte Zugangsdaten prüfen.', pleaseWait:'Bitte warten …', save:'Speichern', saving:'Speichere …', saveFailed:'Speichern fehlgeschlagen. Bitte erneut versuchen.',
    taskTitle:'Aufgabe', itemName:'Artikel', taskPlaceholder:'Was muss erledigt werden?', itemPlaceholder:'Was wird gebraucht?', notes:'Notizen', optional:'Optional', due:'Fällig', priority:'Priorität', low:'Niedrig', normal:'Normal', high:'Hoch', quantity:'Menge', category:'Kategorie',
    connected:'Verbunden', available:'Verfügbar', connect:'Verbinden', disconnect:'Trennen', configure:'Einrichten', connectionFailed:'Verbindung fehlgeschlagen', connectionSuccess:'Integration verbunden.', openProvider:'Offizielle Seite öffnen',
    activeIntegrations:'Aktive Integrationen', addIntegration:'Integration hinzufügen', syncAll:'Alle aktualisieren', syncedItems:'Einträge synchronisiert', secretNotice:'Geheimwerte werden nach dem Speichern nicht wieder angezeigt.', noIntegrations:'Noch keine Integration verbunden.',
    waste:'Müll & Entsorgung', warnings:'Warnungen', weather:'Wetter', calendars:'Kalender', messengers:'Messenger', addressCalendarHint:'Öffne den offiziellen Abfallkalender, wähle deine Adresse und kopiere anschließend den angebotenen iCal/ICS-Link hier hinein.',
    weatherWarning:'Wetterwarnung', publicWarning:'Amtliche Warnung', forecast:'Wettervorhersage'
  }},
  en: { translation: {
    brandTagline:'Family. Organised. Together.', today:'Today', tasks:'Tasks', shopping:'Shopping', routines:'Recently', more:'More',
    greeting:'Hello family 👋', nextUp:'Up next', add:'Add', addTask:'Add task', addItem:'Add item', recentlyDone:'Recently done', dueSoon:'Worth doing soon',
    integrations:'Integrations', calendar:'Calendar', inbox:'Inbox', members:'Family', login:'Sign in', username:'Username', password:'Password', logout:'Sign out', language:'Language', noData:'Nothing here yet.',
    installHint:'fam-uh-le can be installed as an app.', publicData:'Public data', offline:'Offline', online:'Online', back:'Back', sync:'Sync', synced:'Synced', never:'Never', syncing:'Syncing …',
    inboxHint:'Content shared from messengers, browsers and other apps lands here.', toTask:'Make task', toShopping:'Add to shopping', dismiss:'Dismiss', newItem:'New', processed:'Done',
    integrationsHint:'Connect waste calendars, warnings, weather, calendars and messengers directly in fam-uh-le.', endpoint:'Source', lastSync:'Last sync', disabled:'Disabled', enabled:'Active',
    calendarHint:'Family appointments, waste collection, weather and warnings in one place.', membersHint:'Who belongs to this family and which role do they have?', role:'Role',
    owner:'Owner', adult:'Adult', teen:'Teen', child:'Child', guest:'Guest', refresh:'Refresh', noUpcoming:'No upcoming events.', settings:'Settings',
    loginFailed:'Sign-in failed. Please check your credentials.', pleaseWait:'Please wait …', save:'Save', saving:'Saving …', saveFailed:'Could not save. Please try again.',
    taskTitle:'Task', itemName:'Item', taskPlaceholder:'What needs to be done?', itemPlaceholder:'What do you need?', notes:'Notes', optional:'Optional', due:'Due', priority:'Priority', low:'Low', normal:'Normal', high:'High', quantity:'Quantity', category:'Category',
    connected:'Connected', available:'Available', connect:'Connect', disconnect:'Disconnect', configure:'Set up', connectionFailed:'Connection failed', connectionSuccess:'Integration connected.', openProvider:'Open official page',
    activeIntegrations:'Active integrations', addIntegration:'Add integration', syncAll:'Sync all', syncedItems:'items synced', secretNotice:'Secret values are not shown again after saving.', noIntegrations:'No integration connected yet.',
    waste:'Waste & recycling', warnings:'Warnings', weather:'Weather', calendars:'Calendars', messengers:'Messengers', addressCalendarHint:'Open the official waste calendar, choose your address and paste the offered iCal/ICS link here.',
    weatherWarning:'Weather warning', publicWarning:'Official warning', forecast:'Weather forecast'
  }}
};

i18n.use(initReactI18next).init({resources,lng:localStorage.getItem('famuhle-language')||'de',fallbackLng:'de',interpolation:{escapeValue:false}});
export default i18n;
