import {api} from './api';

const MAX_EVENT_PAGES=200;
const unwrap=value=>value?.results||value||[];

export async function fetchCalendarEvents({familyId,start,end,includeUndated=false}={}){
 const params=new URLSearchParams();
 if(familyId)params.set('family',familyId);
 if(start)params.set('start',start);
 if(end)params.set('end',end);
 if(includeUndated)params.set('include_undated','1');
 const rows=[];
 for(let page=1;page<=MAX_EVENT_PAGES;page+=1){
  params.set('page',String(page));
  const result=await api(`/events/?${params.toString()}`);
  rows.push(...unwrap(result));
  if(Array.isArray(result)||!result?.next)return dedupe(rows);
 }
 throw new Error('calendar_event_page_limit');
}

function dedupe(rows){
 const unique=new Map();
 rows.forEach((row,index)=>unique.set(row?.id??`row-${index}`,row));
 return [...unique.values()];
}
