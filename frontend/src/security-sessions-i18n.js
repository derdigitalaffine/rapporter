import i18n from './i18n';

const de={
 eyebrow:'Sicherheit',title:'Aktive Sitzungen',intro:'Hier siehst du deine aktuellen Anmeldungen. Eine widerrufene Sitzung verliert sofort den Zugriff.',
 loading:'Sitzungen werden geladen …',loadFailed:'Sitzungen konnten nicht geladen werden.',retry:'Erneut laden',current:'Dieses Gerät',other:'Weitere Sitzung',
 created:'Angemeldet',lastSeen:'Zuletzt aktiv',method:'Anmeldung',password:'Passwort',passkey:'Passkey',recovery:'Wiederherstellung',
 revoke:'Abmelden',revoked:'Sitzung wurde abgemeldet.',revokeFailed:'Sitzung konnte nicht abgemeldet werden.',
 revokeOthers:'Alle anderen abmelden',revokeOthersHint:'Beendet alle anderen aktiven Sitzungen sofort.',revokeOthersDone:'Alle anderen Sitzungen wurden abgemeldet.',
 fresh:'Identität kürzlich bestätigt',stale:'Bestätigung für sensible Aktionen erforderlich',
 reauthTitle:'Identität bestätigen',reauthText:'Gib dein aktuelles Passwort ein, um diese sensible Aktion freizugeben.',passwordLabel:'Aktuelles Passwort',confirm:'Bestätigen',cancel:'Abbrechen',confirmed:'Identität bestätigt.',reauthFailed:'Bestätigung fehlgeschlagen.',
 noOthers:'Keine weiteren aktiven Sitzungen.',privacy:'Es werden keine Standortdaten oder Geräte-Fingerprints gespeichert. Die Gerätebezeichnung wird nur grob aus Browserinformationen abgeleitet.'
};
const en={
 eyebrow:'Security',title:'Active sessions',intro:'Review your current sign-ins here. Revoked sessions lose access immediately.',
 loading:'Loading sessions …',loadFailed:'Could not load sessions.',retry:'Reload',current:'This device',other:'Other session',
 created:'Signed in',lastSeen:'Last active',method:'Sign-in',password:'Password',passkey:'Passkey',recovery:'Recovery',
 revoke:'Sign out',revoked:'Session signed out.',revokeFailed:'Could not sign out session.',
 revokeOthers:'Sign out all others',revokeOthersHint:'Immediately ends every other active session.',revokeOthersDone:'All other sessions were signed out.',
 fresh:'Identity recently confirmed',stale:'Confirmation required for sensitive actions',
 reauthTitle:'Confirm your identity',reauthText:'Enter your current password to approve this sensitive action.',passwordLabel:'Current password',confirm:'Confirm',cancel:'Cancel',confirmed:'Identity confirmed.',reauthFailed:'Confirmation failed.',
 noOthers:'No other active sessions.',privacy:'No location data or device fingerprint is stored. The device label is only a coarse hint derived from browser information.'
};

i18n.addResourceBundle('de','translation',{securitySessions:de},true,true);
i18n.addResourceBundle('en','translation',{securitySessions:en},true,true);
