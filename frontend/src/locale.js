const LOCALES={de:'de-DE',en:'en-GB',fr:'fr-FR',nl:'nl-NL',th:'th-TH'};

export function appLocale(language='de'){
 const code=String(language||'de').toLowerCase().split('-')[0];
 return LOCALES[code]||LOCALES.de;
}

export function formatDateTime(language,value,options={}){
 if(!value)return'';
 return new Intl.DateTimeFormat(appLocale(language),options).format(value instanceof Date?value:new Date(value));
}

export function formatRelative(language,value,unit,options={numeric:'auto'}){
 return new Intl.RelativeTimeFormat(appLocale(language),options).format(value,unit);
}
