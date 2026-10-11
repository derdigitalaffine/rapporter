import i18n from './i18n';

const de={
 loginAction:'Mit Passkey anmelden',loginHint:'Nutze Face ID, Fingerabdruck, Geräte-PIN oder deinen Passwortmanager. Biometrische Daten verlassen dein Gerät nicht.',
 unsupported:'Passkeys werden in diesem Browser oder Kontext nicht unterstützt. Nutze bitte die Passwort-Anmeldung.',
 unavailable:'Passkeys sind für diese Installation noch nicht aktiviert.',cancelled:'Passkey-Anmeldung abgebrochen.',failed:'Passkey-Anmeldung fehlgeschlagen. Bitte versuche es erneut.',
 eyebrow:'Sicherheit',title:'Passkeys',intro:'Passkeys ermöglichen eine phishing-resistente Anmeldung ohne Passwort. Geräte-PIN und Biometrie bleiben beim Gerät oder Passwortmanager.',
 loading:'Passkeys werden geladen …',loadFailed:'Passkeys konnten nicht geladen werden.',empty:'Noch kein Passkey eingerichtet.',add:'Passkey hinzufügen',nameLabel:'Name des Passkeys',namePlaceholder:'z. B. iPhone oder Arbeits-Laptop',addHint:'Wähle einen Namen, damit du mehrere Passkeys später unterscheiden kannst.',
 created:'Passkey wurde hinzugefügt.',createdAt:'Erstellt',lastUsed:'Zuletzt verwendet',neverUsed:'Noch nie verwendet',backup:'Synchronisiert',deviceBound:'Gerätegebunden',
 rename:'Umbenennen',saveName:'Namen speichern',renamed:'Passkey wurde umbenannt.',remove:'Entfernen',removeConfirm:'Diesen Passkey wirklich entfernen?',removed:'Passkey wurde entfernt.',
 reauthTitle:'Identität bestätigen',reauthText:'Diese Sicherheitsänderung benötigt eine aktuelle Bestätigung.',reauthPasskey:'Mit Passkey bestätigen',reauthPassword:'Mit Passwort bestätigen',passwordLabel:'Aktuelles Passwort',confirmPassword:'Passwort bestätigen',cancel:'Abbrechen',confirmed:'Identität bestätigt.',
 actionFailed:'Aktion konnte nicht abgeschlossen werden.',rateLimited:'Zu viele Passkey-Versuche. Bitte warte kurz und versuche es erneut.',
 privacy:'FamilyOS speichert nur den öffentlichen WebAuthn-Credential-Datensatz und minimale Lebenszyklus-Metadaten – niemals private Schlüssel oder biometrische Daten.'
};
const en={
 loginAction:'Sign in with a passkey',loginHint:'Use Face ID, fingerprint, device PIN, or your password manager. Biometric data never leaves your device.',
 unsupported:'Passkeys are not supported in this browser or context. Please use password sign-in.',
 unavailable:'Passkeys are not enabled for this installation yet.',cancelled:'Passkey sign-in cancelled.',failed:'Passkey sign-in failed. Please try again.',
 eyebrow:'Security',title:'Passkeys',intro:'Passkeys provide phishing-resistant sign-in without a password. Device PIN and biometrics stay with the device or credential provider.',
 loading:'Loading passkeys …',loadFailed:'Could not load passkeys.',empty:'No passkey configured yet.',add:'Add passkey',nameLabel:'Passkey name',namePlaceholder:'e.g. iPhone or Work laptop',addHint:'Choose a name so you can distinguish multiple passkeys later.',
 created:'Passkey added.',createdAt:'Created',lastUsed:'Last used',neverUsed:'Never used',backup:'Synced',deviceBound:'Device-bound',
 rename:'Rename',saveName:'Save name',renamed:'Passkey renamed.',remove:'Remove',removeConfirm:'Remove this passkey?',removed:'Passkey removed.',
 reauthTitle:'Confirm your identity',reauthText:'This security change requires a recent confirmation.',reauthPasskey:'Confirm with passkey',reauthPassword:'Confirm with password',passwordLabel:'Current password',confirmPassword:'Confirm password',cancel:'Cancel',confirmed:'Identity confirmed.',
 actionFailed:'Could not complete the action.',rateLimited:'Too many passkey attempts. Wait briefly and try again.',
 privacy:'FamilyOS stores only the public WebAuthn credential record and minimal lifecycle metadata — never private keys or biometric data.'
};

i18n.addResourceBundle('de','translation',{passkeys:de},true,true);
i18n.addResourceBundle('en','translation',{passkeys:en},true,true);
