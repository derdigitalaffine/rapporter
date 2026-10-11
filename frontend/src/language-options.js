export const APP_LANGUAGES=[
 {code:'de',label:'Deutsch'},
 {code:'en',label:'English'},
 {code:'fr',label:'Français'},
 {code:'nl',label:'Nederlands'},
 {code:'th',label:'ไทย'},
];

export function normalizeAppLanguage(value='de'){
 const language=String(value||'de').toLowerCase().split('-')[0];
 return APP_LANGUAGES.some(item=>item.code===language)?language:'de';
}

export function nextAppLanguage(value='de'){
 const language=normalizeAppLanguage(value);
 const index=APP_LANGUAGES.findIndex(item=>item.code===language);
 return APP_LANGUAGES[(index+1)%APP_LANGUAGES.length].code;
}

export function languageLabel(value='de'){
 const language=normalizeAppLanguage(value);
 return APP_LANGUAGES.find(item=>item.code===language)?.label||'Deutsch';
}
