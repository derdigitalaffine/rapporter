import i18n from './i18n';

const de={
 expiredTitle:'Sitzung abgelaufen',expiredMessage:'Bitte melde dich erneut an. Danach geht es im gleichen Bereich weiter.',
 loading:'Daten werden geladen …',loadFailed:'Daten konnten nicht geladen werden.',retry:'Erneut versuchen'
};
const en={
 expiredTitle:'Session expired',expiredMessage:'Please sign in again. You will return to the same area afterwards.',
 loading:'Loading data …',loadFailed:'Data could not be loaded.',retry:'Try again'
};
const identityDe={
 emailLabel:'E-Mail-Adresse',legacyHint:'Bestandskonto / Superadmin: Benutzername ist weiterhin möglich.',verified:'E-Mail bestätigt',unverified:'E-Mail noch nicht bestätigt',actionRequired:'E-Mail-Adresse hinterlegen',verificationSent:'Bestätigung wurde versendet.',resend:'Bestätigung erneut senden',pending:'Neue E-Mail wartet auf Bestätigung',change:'E-Mail-Adresse ändern',newEmail:'Neue E-Mail-Adresse',currentPassword:'Aktuelles Passwort',changeStarted:'Neue Adresse gespeichert. Bitte bestätige sie über den Link in der E-Mail.',securityTitle:'E-Mail & Anmeldung',securityHint:'Die bestätigte E-Mail-Adresse ist deine normale Anmeldung und wird für Sicherheitsnachrichten verwendet.',verifyTitle:'E-Mail-Adresse bestätigen',verifyIntro:'Bestätige diese Adresse erst nach einem bewussten Klick. Der Link allein verändert dein Konto nicht.',verifyAction:'E-Mail bestätigen',verifySuccess:'E-Mail-Adresse wurde bestätigt.',verifyInvalid:'Der Bestätigungslink ist ungültig oder abgelaufen.',backToLogin:'Zur Anmeldung',migrationAccount:'Bestandskonto / Superadmin',normalAccount:'Mit E-Mail anmelden'
};
const identityEn={
 emailLabel:'Email address',legacyHint:'Existing account / superadmin: username remains available.',verified:'Email verified',unverified:'Email not yet verified',actionRequired:'Add an email address',verificationSent:'Verification email sent.',resend:'Resend verification',pending:'New email awaiting verification',change:'Change email address',newEmail:'New email address',currentPassword:'Current password',changeStarted:'New address saved. Confirm it using the link in the email.',securityTitle:'Email & sign-in',securityHint:'Your verified email address is your normal sign-in and is used for security messages.',verifyTitle:'Verify email address',verifyIntro:'Confirm this address with an explicit click. Opening the link alone does not change your account.',verifyAction:'Verify email',verifySuccess:'Email address verified.',verifyInvalid:'The verification link is invalid or expired.',backToLogin:'Back to sign in',migrationAccount:'Existing account / superadmin',normalAccount:'Sign in with email'
};

i18n.addResourceBundle('de','translation',{username:'E-Mail-Adresse (Bestandskonto: Benutzername)',sessionUi:de,identityUi:identityDe},true,true);
i18n.addResourceBundle('en','translation',{username:'Email address (existing account: username)',sessionUi:en,identityUi:identityEn},true,true);
