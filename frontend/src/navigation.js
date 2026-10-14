import {APP_PAGES} from './feature-registry';

export {APP_PAGES};

export function pageFromLocation(search=location.search){
 const params=new URLSearchParams(search);
 if(params.has('integration_connected')||params.has('integration_error'))return'integrations';
 const requested=params.get('page');
 return APP_PAGES.has(requested)?requested:'home';
}

export function pageHref(page,current=location.href){
 const next=APP_PAGES.has(page)?page:'home';
 const url=new URL(current,location.origin);
 if(url.searchParams.get('page')!==next){for(const key of ['routine','birthday','mode','list','task','item','wishlist','family','todo','ledger','game','vehicle','stats_range','stats_view','stats_member','stats_domain','stats_from','stats_to'])url.searchParams.delete(key)}
 if(next!=='notes')url.searchParams.delete('note');
 if(next!=='games')url.searchParams.delete('game');
 url.searchParams.delete('integration_connected');
 url.searchParams.delete('integration_error');
 if(next==='home')url.searchParams.delete('page');
 else url.searchParams.set('page',next);
 return `${url.pathname}${url.search}${url.hash}`;
}
