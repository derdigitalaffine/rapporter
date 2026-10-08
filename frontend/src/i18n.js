import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';

const resources = {
  de: { translation: {
    brandTagline: 'Familie. Organisiert. Gemeinsam.', today: 'Heute', tasks: 'Aufgaben', shopping: 'Einkauf', routines: 'Zuletzt', more: 'Mehr',
    greeting: 'Hallo Familie 👋', nextUp: 'Als Nächstes', add: 'Hinzufügen', addTask: 'Aufgabe hinzufügen', addItem: 'Artikel hinzufügen',
    recentlyDone: 'Zuletzt gemacht', dueSoon: 'Demnächst wieder sinnvoll', integrations: 'Integrationen', calendar: 'Kalender', inbox: 'Inbox',
    login: 'Anmelden', username: 'Benutzername', password: 'Passwort', logout: 'Abmelden', language: 'Sprache', noData: 'Noch nichts hier.',
    installHint: 'fam-uh-le kann als App installiert werden.', publicData: 'Öffentliche Daten', members: 'Familie', offline: 'Offline', online: 'Online'
  }},
  en: { translation: {
    brandTagline: 'Family. Organised. Together.', today: 'Today', tasks: 'Tasks', shopping: 'Shopping', routines: 'Recently', more: 'More',
    greeting: 'Hello family 👋', nextUp: 'Up next', add: 'Add', addTask: 'Add task', addItem: 'Add item',
    recentlyDone: 'Recently done', dueSoon: 'Worth doing soon', integrations: 'Integrations', calendar: 'Calendar', inbox: 'Inbox',
    login: 'Sign in', username: 'Username', password: 'Password', logout: 'Sign out', language: 'Language', noData: 'Nothing here yet.',
    installHint: 'fam-uh-le can be installed as an app.', publicData: 'Public data', members: 'Family', offline: 'Offline', online: 'Online'
  }}
};

i18n.use(initReactI18next).init({ resources, lng: localStorage.getItem('famuhle-language') || 'de', fallbackLng: 'de', interpolation: { escapeValue: false } });
export default i18n;
