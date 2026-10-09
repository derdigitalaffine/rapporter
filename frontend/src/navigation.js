export const APP_PAGES=new Set(['home','tasks','shopping','routines','more','calendar','weather','inbox','integrations','members','profile','automations','notifications','loyalty']);

export function pageFromLocation(search=location.search){
 const params=new URLSearchParams(search);
 if(params.has('integration_connected')||params.has('integration_error'))return'integrations';
 const requested=params.get('page');
 return APP_PAGES.has(requested)?requested:'home';
}

export function pageHref(page,current=location.href){
 const next=APP_PAGES.has(page)?page:'home';
 const url=new URL(current,location.origin);
 url.searchParams.delete('integration_connected');
 url.searchParams.delete('integration_error');
 if(next==='home')url.searchParams.delete('page');
 else url.searchParams.set('page',next);
 return `${url.pathname}${url.search}${url.hash}`;
}
