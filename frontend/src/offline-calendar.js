import {offlineIdentity,readyOfflineEngine} from './offline-runtime.js';
const schedule=data=>JSON.stringify([data?.starts_at,data?.ends_at,data?.payload?.recurrence,data?.payload?.all_day,data?.payload?.date_start,data?.payload?.date_end_exclusive]);
export async function offlineCalendarRows(engine){
 const projection=(await engine.store.get('meta','projections'))?.data||{};
 const records=await engine.store.list('events'),rows=[];
 for(const record of records){
  if(record.deleted||!record.data)continue;const master={...record.data,_offlinePending:record.sync_status==='pending'};
  const projected=(projection.calendar_occurrences||[]).filter(row=>row.id===master.id);
  if(projected.length&&schedule(master)===schedule(record.server_data||master)){
   for(const occurrence of projected)rows.push({...occurrence,...master,starts_at:occurrence.starts_at,ends_at:occurrence.ends_at,
    payload:{...master.payload,...Object.fromEntries(Object.entries(occurrence.payload||{}).filter(([key])=>['date_start','date_end_exclusive'].includes(key)))}});
  }else rows.push(master);
 }
 for(const birthday of projection.calendar_birthdays||[])rows.push({...birthday,read_only:true});
 return rows;
}
export async function offlineCalendarRequest(path,options={}){
 const identity=offlineIdentity();if(!identity)return {handled:false};const url=new URL(path,'https://local.invalid');
 const match=url.pathname.match(/^\/events\/(?:([^/]+)\/)?$/);if(!match)return {handled:false};
 const method=(options.method||'GET').toUpperCase();let data={};if(options.body){try{data=JSON.parse(options.body)}catch{return {handled:false}}}
 const familyId=String(data.family||url.searchParams.get('family')||localStorage.getItem('famuhle-active-family')||identity.families?.[0]?.id||''),engine=await readyOfflineEngine(familyId),id=match[1];
 if(id&&!await engine.get('event',id)&&navigator.onLine)return {handled:false};
 if(method==='GET'){
  if(id)return {handled:true,value:await engine.get('event',id)};
  const start=url.searchParams.get('start'),end=url.searchParams.get('end'),includeUndated=url.searchParams.get('include_undated')==='1';
  const cached=(await engine.store.get('meta','projections'))?.data?.calendar_window;
  if(start&&end&&cached&&(start<cached.start||end>cached.end)){if(navigator.onLine)return {handled:false};throw new Error(localStorage.getItem('famuhle-language')?.startsWith('en')?'This date range has not been saved for offline use.':'Dieser Zeitraum wurde noch nicht für die Offline-Nutzung gespeichert.')}
  let rows=await offlineCalendarRows(engine);
  const zone=identity.families?.find(f=>String(f.id)===familyId)?.timezone||'UTC';
  const day=value=>{const parts=new Intl.DateTimeFormat('en',{timeZone:zone,year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date(value));return ['year','month','day'].map(key=>parts.find(p=>p.type===key).value).join('-')};
  if(start&&end)rows=rows.filter(row=>row.starts_at?day(row.starts_at)<=end&&day(row.ends_at&&new Date(row.ends_at)>new Date(row.starts_at)?new Date(new Date(row.ends_at).getTime()-1):row.starts_at)>=start:includeUndated);
  if(url.searchParams.get('birthdays')==='0')rows=rows.filter(row=>row.type!=='birthday');
  return {handled:true,value:rows.sort((a,b)=>String(a.starts_at||'9999').localeCompare(String(b.starts_at||'9999')))};
 }
 if(['POST','PATCH','PUT','DELETE'].includes(method))return {handled:true,value:await engine.mutate('event',id,method==='POST'?'create':method==='DELETE'?'delete':'update',{...data,...(method==='POST'?{family:familyId,type:'calendar.event',source:null}:{})})};
 return {handled:false};
}
