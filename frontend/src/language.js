// Keep both existing language controls on the same supported locale cycle.
export const SUPPORTED_LANGUAGES=Object.freeze(['de','en','fr','nl','th']);
export function switchLanguage(i18n){
 const current=i18n.language?.split('-')[0];
 const next=SUPPORTED_LANGUAGES[(SUPPORTED_LANGUAGES.indexOf(current)+1)%SUPPORTED_LANGUAGES.length];
 i18n.changeLanguage(next);
 localStorage.setItem('famuhle-language',next);
}
