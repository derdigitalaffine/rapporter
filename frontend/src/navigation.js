export const APP_PAGES=new Set(['notes','board','birthdays','home','tasks','shopping','routines','baby','more','calendar','weather','expenses','inbox','integrations','members','profile','automations','notifications','loyalty']);

export function pageFromLocation(search=location.search){
 const params=new URLSearchParams(search);
 if(params.has('integration_connected')||params.has('integration_error'))return'integrations';
 const requested=params.get('page');
 return APP_PAGES.has(requested)?requested:'home';
}

export function pageHref(page,current=location.href){
 const next=APP_PAGES.has(page)?page:'home';
 const url=new URL(current,location.origin);
 if(url.searchParams.get('page')!==next){for(const key of ['routine','birthday','mode','list','task','item','family'])url.searchParams.delete(key)}
 if(next!=='notes')url.searchParams.delete('note');
 url.searchParams.delete('integration_connected');
 url.searchParams.delete('integration_error');
 if(next==='home')url.searchParams.delete('page');
 else url.searchParams.set('page',next);
 return `${url.pathname}${url.search}${url.hash}`;
}
