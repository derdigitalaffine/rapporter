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

// A civil date is not an instant: family dates must not shift with the browser timezone.
export function formatCivilDate(language,value){
 if(!/^\d{4}-\d{2}-\d{2}$/.test(value||''))return '';
 const date=new Date(`${value}T12:00:00Z`);
 if(Number.isNaN(date.getTime())||date.toISOString().slice(0,10)!==value)return '';
 return formatDateTime(language,date,{timeZone:'UTC',day:'2-digit',month:'2-digit',year:'numeric'});
}
