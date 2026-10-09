import i18n from './i18n';

const de={
 expiredTitle:'Sitzung abgelaufen',expiredMessage:'Bitte melde dich erneut an. Danach geht es im gleichen Bereich weiter.',
 loading:'Daten werden geladen …',loadFailed:'Daten konnten nicht geladen werden.',retry:'Erneut versuchen'
};
const en={
 expiredTitle:'Session expired',expiredMessage:'Please sign in again. You will return to the same area afterwards.',
 loading:'Loading data …',loadFailed:'Data could not be loaded.',retry:'Try again'
};

i18n.addResourceBundle('de','translation',{sessionUi:de},true,true);
i18n.addResourceBundle('en','translation',{sessionUi:en},true,true);
