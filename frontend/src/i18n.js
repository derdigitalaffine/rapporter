import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';

const resources = {
  de: { translation: {
    brandTagline:'Familie. Organisiert. Gemeinsam.', today:'Heute', tasks:'Aufgaben', shopping:'Einkauf', routines:'Zuletzt', more:'Mehr',
    greeting:'Hallo Familie 👋', nextUp:'Als Nächstes', add:'Hinzufügen', addTask:'Aufgabe hinzufügen', addItem:'Artikel hinzufügen', recentlyDone:'Zuletzt gemacht', dueSoon:'Demnächst wieder sinnvoll',
    integrations:'Integrationen', calendar:'Kalender', inbox:'Inbox', members:'Familie', login:'Anmelden', username:'Benutzername', password:'Passwort', logout:'Abmelden', language:'Sprache', noData:'Noch nichts hier.',
    installHint:'fam-uh-le kann als App installiert werden.', publicData:'Öffentliche Daten', offline:'Offline', online:'Online', back:'Zurück', sync:'Synchronisieren', synced:'Synchronisiert', never:'Noch nie', syncing:'Synchronisiere …',
    inboxHint:'Geteilte Inhalte aus Messenger, Browser und anderen Apps landen hier.', toTask:'Als Aufgabe', toShopping:'Zum Einkauf', dismiss:'Ausblenden', newItem:'Neu', processed:'Erledigt',
    integrationsHint:'Kalender, Mülltermine und weitere öffentliche Datenquellen zentral verbinden.', endpoint:'Quelle', lastSync:'Letzter Sync', disabled:'Deaktiviert', enabled:'Aktiv',
    calendarHint:'Familientermine und externe Kalender an einem Ort.', membersHint:'Wer gehört zu dieser Familie und welche Rolle hat die Person?', role:'Rolle',
    owner:'Inhaber', adult:'Erwachsen', teen:'Teenager', child:'Kind', guest:'Gast', refresh:'Aktualisieren', noUpcoming:'Keine kommenden Termine.', settings:'Einstellungen',
    loginFailed:'Anmeldung fehlgeschlagen. Bitte Zugangsdaten prüfen.', pleaseWait:'Bitte warten …', save:'Speichern', saving:'Speichere …', saveFailed:'Speichern fehlgeschlagen. Bitte erneut versuchen.',
    taskTitle:'Aufgabe', itemName:'Artikel', taskPlaceholder:'Was muss erledigt werden?', itemPlaceholder:'Was wird gebraucht?', notes:'Notizen', optional:'Optional', due:'Fällig', priority:'Priorität', low:'Niedrig', normal:'Normal', high:'Hoch', quantity:'Menge', category:'Kategorie'
  }},
  en: { translation: {
    brandTagline:'Family. Organised. Together.', today:'Today', tasks:'Tasks', shopping:'Shopping', routines:'Recently', more:'More',
    greeting:'Hello family 👋', nextUp:'Up next', add:'Add', addTask:'Add task', addItem:'Add item', recentlyDone:'Recently done', dueSoon:'Worth doing soon',
    integrations:'Integrations', calendar:'Calendar', inbox:'Inbox', members:'Family', login:'Sign in', username:'Username', password:'Password', logout:'Sign out', language:'Language', noData:'Nothing here yet.',
    installHint:'fam-uh-le can be installed as an app.', publicData:'Public data', offline:'Offline', online:'Online', back:'Back', sync:'Sync', synced:'Synced', never:'Never', syncing:'Syncing …',
    inboxHint:'Content shared from messengers, browsers and other apps lands here.', toTask:'Make task', toShopping:'Add to shopping', dismiss:'Dismiss', newItem:'New', processed:'Done',
    integrationsHint:'Connect calendars, waste collection and other public data sources in one place.', endpoint:'Source', lastSync:'Last sync', disabled:'Disabled', enabled:'Active',
    calendarHint:'Family appointments and external calendars in one place.', membersHint:'Who belongs to this family and which role do they have?', role:'Role',
    owner:'Owner', adult:'Adult', teen:'Teen', child:'Child', guest:'Guest', refresh:'Refresh', noUpcoming:'No upcoming events.', settings:'Settings',
    loginFailed:'Sign-in failed. Please check your credentials.', pleaseWait:'Please wait …', save:'Save', saving:'Saving …', saveFailed:'Could not save. Please try again.',
    taskTitle:'Task', itemName:'Item', taskPlaceholder:'What needs to be done?', itemPlaceholder:'What do you need?', notes:'Notes', optional:'Optional', due:'Due', priority:'Priority', low:'Low', normal:'Normal', high:'High', quantity:'Quantity', category:'Category'
  }}
};

i18n.use(initReactI18next).init({resources,lng:localStorage.getItem('famuhle-language')||'de',fallbackLng:'de',interpolation:{escapeValue:false}});
export default i18n;
