import {APP_PAGES,FEATURE_QUERY_PARAMS,queryParamsForPage} from './feature-registry.js';

export {APP_PAGES};

export function pageFromLocation(search=location.search){
 const params=new URLSearchParams(search);
 if(params.has('integration_connected')||params.has('integration_error'))return'integrations';
 const requested=params.get('page');
 return APP_PAGES.has(requested)?requested:'home';
}

export function pageHref(page,current=location.href){
 const next=APP_PAGES.has(page)?page:'home';
 const url=new URL(current,globalThis.location?.origin||'http://localhost');
 const allowed=new Set(queryParamsForPage(next));
 for(const key of FEATURE_QUERY_PARAMS){if(!allowed.has(key)||url.searchParams.get('page')!==next)url.searchParams.delete(key)}
 url.searchParams.delete('integration_connected');
 url.searchParams.delete('integration_error');
 if(next==='home')url.searchParams.delete('page');
 else url.searchParams.set('page',next);
 return `${url.pathname}${url.search}${url.hash}`;
}
