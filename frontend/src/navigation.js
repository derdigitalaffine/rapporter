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

export function featureHref(page,params={},current=location.href){
 const url=new URL(pageHref(page,current),globalThis.location?.origin||'http://localhost');
 const allowed=new Set(queryParamsForPage(page));
 for(const [key,value] of Object.entries(params)){
  if(!allowed.has(key))throw new Error(`Unsupported feature selector: ${key}`);
  if(value===null||value===undefined||value==='')url.searchParams.delete(key);
  else url.searchParams.set(key,String(value));
 }
 return `${url.pathname}${url.search}${url.hash}`;
}

export function updateFeatureLocation(page,params={}, {replace=false,notify=true}={}){
 const href=featureHref(page,params);
 if(notify){const event=new CustomEvent('famuhle:before-navigation',{cancelable:true,detail:{page}});window.dispatchEvent(event);if(event.defaultPrevented)return false;}
 const state={...history.state,page,appNavigation:!replace};
 const method=replace?'replaceState':'pushState';
 history[method](state,'',href);
 if(notify)window.dispatchEvent(new PopStateEvent('popstate',{state}));
 return true;
}
