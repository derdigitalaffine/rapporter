export function appLocale(language='de'){
 return String(language).toLowerCase().startsWith('en')?'en-GB':'de-DE';
}

export function formatDateTime(language,value,options={}){
 if(!value)return'';
 return new Intl.DateTimeFormat(appLocale(language),options).format(value instanceof Date?value:new Date(value));
}

export function formatRelative(language,value,unit,options={numeric:'auto'}){
 return new Intl.RelativeTimeFormat(appLocale(language),options).format(value,unit);
}
