import 'fake-indexeddb/auto';
import {test,afterEach} from 'node:test';
import assert from 'node:assert/strict';
import {rememberOfflineBootstrap,setSyncTransport,offlineEngine,clearOfflineIdentity} from '../src/offline-runtime.js';
import {offlineCalendarRequest} from '../src/offline-calendar.js';
const values=new Map();globalThis.localStorage={getItem:k=>values.get(k)||null,setItem:(k,v)=>values.set(k,String(v)),removeItem:k=>values.delete(k)};Object.defineProperty(navigator,'onLine',{value:true,writable:true,configurable:true});
afterEach(async()=>{navigator.onLine=true;await clearOfflineIdentity();values.clear()});
async function setup(){
 const native={id:'native',version:1,family:'f',type:'calendar.event',source:null,title:'Series',starts_at:'2026-10-18T08:00:00Z',ends_at:'2026-10-18T09:00:00Z',payload:{recurrence:'weekly'}},external={id:'external',version:1,family:'f',type:'calendar.event',source:'ics',read_only:true,title:'ICS',starts_at:'2026-10-18T08:00:00Z'};
 setSyncTransport(async()=>({protocol_version:1,mode:'snapshot',cursor:1,mutation_results:[],visibility:{task:[],task_list:[],event:['native','external'],shopping_list:[],shopping_item:[]},snapshot:{events:[native,external]},projections:{calendar_occurrences:[{...native,recurrence_occurrence_date:'2026-10-18'},{...native,recurrence_occurrence_date:'2026-10-25',starts_at:'2026-10-25T09:00:00Z',ends_at:'2026-10-25T10:00:00Z'},external],calendar_birthdays:[{id:'birthday:one',family:'f',type:'birthday',title:'Birthday',starts_at:'2026-10-20T00:00:00Z'}],calendar_key:'2026-10-15:Europe/Berlin',calendar_window:{start:'2026-07-17',end:'2027-10-15'}}}));
 await rememberOfflineBootstrap('/auth/session/',{offline_sync_protocol:1,user:{id:crypto.randomUUID(),username:'Owner'}});await rememberOfflineBootstrap('/families/',[{id:'f',name:'Family',timezone:'Europe/Berlin'}]);localStorage.setItem('famuhle-active-family','f');const e=offlineEngine('f');await e.sync();e.schedule=()=>{};navigator.onLine=false;return e;
}
const request=(path,method='GET',data)=>offlineCalendarRequest(path,{method,body:data?JSON.stringify(data):undefined});
test('prefetched recurrence occurrences keep canonical DST times; title edits overlay every occurrence',async()=>{
 const e=await setup();let rows=(await request('/events/?family=f&start=2026-10-01&end=2026-10-31')).value;
 assert.deepEqual(rows.filter(r=>r.id==='native').map(r=>r.starts_at),['2026-10-18T08:00:00Z','2026-10-25T09:00:00Z']);
 await request('/events/native/','PATCH',{title:'Renamed series'});rows=(await request('/events/?family=f')).value;
 assert.equal(rows.filter(r=>r.id==='native'&&r.title==='Renamed series').length,2);
 assert.equal((await e.store.list('outbox')).length,1);
});
test('native create/edit/delete stay durable locally; external and virtual rows stay read-only',async()=>{
 const e=await setup();await assert.rejects(request('/events/external/','PATCH',{title:'Forbidden'}),/read_only_source/);assert.equal((await e.store.list('outbox')).length,0);
 const event=(await request('/events/','POST',{family:'f',title:'New offline',starts_at:'2026-10-22T10:00:00Z',payload:{}})).value;await request(`/events/${event.id}/`,'PATCH',{title:'Edited offline'});
 assert.equal((await e.get('event',event.id)).title,'Edited offline');assert.equal((await e.store.list('outbox')).length,1);
 await request(`/events/${event.id}/`,'DELETE');assert.equal(await e.get('event',event.id),null);assert.equal((await e.store.list('outbox')).length,0);
 const birthday=(await request('/events/?family=f')).value.find(r=>r.type==='birthday');assert.equal(birthday.read_only,true);
 await request('/events/native/','DELETE');assert.equal((await request('/events/?family=f')).value.some(r=>r.id==='native'),false);
});
test('delta metadata refresh retains prior occurrence projection when only actions change',async()=>{
 const e=await setup();await e.install({protocol_version:1,mode:'delta',cursor:2,visibility:{task:[],task_list:[],event:['native','external'],shopping_list:[],shopping_item:[]},changes:[],mutation_results:[],projections:{actions:[]}},[]);
 assert.equal((await request('/events/?family=f')).value.filter(r=>r.id==='native').length,2);
});
