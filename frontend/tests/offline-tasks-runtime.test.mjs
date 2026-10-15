import 'fake-indexeddb/auto';
import {test,afterEach} from 'node:test';
import assert from 'node:assert/strict';
import {rememberOfflineBootstrap,setSyncTransport,offlineEngine,clearOfflineIdentity} from '../src/offline-runtime.js';
import {offlineTaskRequest} from '../src/offline-tasks.js';
const values=new Map();globalThis.localStorage={getItem:k=>values.get(k)||null,setItem:(k,v)=>values.set(k,String(v)),removeItem:k=>values.delete(k)};Object.defineProperty(navigator,'onLine',{value:true,writable:true,configurable:true});
afterEach(async()=>{navigator.onLine=true;await clearOfflineIdentity();values.clear()});
async function setup(){
 const lists=[],tasks=[],commands=[];let cursor=0;
 setSyncTransport(async p=>{const results=[];for(const m of p.mutations){const rows=m.entity_type==='task_list'?lists:tasks;let row=rows.find(r=>r.id===m.entity_id);if(m.operation==='create'){row={id:m.entity_id,version:1,...m.data};rows.push(row)}else if(m.operation==='update'){Object.assign(row,m.changes);row.version++}else if(m.operation==='delete')rows.splice(rows.indexOf(row),1);else {if(m.base_version!==row.version){results.push({mutation_id:m.mutation_id,status:'conflict',server_version:row.version,server_data:structuredClone(row)});cursor++;continue}commands.push(m.command);row.completed_at=m.command==='complete_task'?new Date().toISOString():null;row.version++}results.push({mutation_id:m.mutation_id,status:'applied',version:row?.version||1,data:row});cursor++}return {protocol_version:1,mode:'snapshot',cursor,mutation_results:results,visibility:{task:tasks.map(r=>r.id),task_list:lists.map(r=>r.id),event:[],shopping_list:[],shopping_item:[]},snapshot:{tasks:structuredClone(tasks),task_lists:structuredClone(lists)}}});
 await rememberOfflineBootstrap('/auth/session/',{offline_sync_protocol:1,user:{id:crypto.randomUUID(),username:'Owner'}});await rememberOfflineBootstrap('/families/',[{id:'f',name:'Family',timezone:'Europe/Berlin'}]);localStorage.setItem('famuhle-active-family','f');const e=offlineEngine('f');await e.sync();e.schedule=()=>{};return {e,lists,tasks,commands};
}
const request=(path,method='GET',data)=>offlineTaskRequest(path,{method,body:data?JSON.stringify(data):undefined});
test('offline Task capture, edits, complete and reopen share durable command outbox',async()=>{
 const {e,tasks,commands}=await setup();navigator.onLine=false;
 const task=(await request('/smart/tasks/quick-add/','POST',{family:'f',title:'Offline work'})).value.task;
 await request(`/tasks/${task.id}/`,'PATCH',{notes:'Retained',priority:'high'});
 await request(`/tasks/${task.id}/toggle/`,'POST');assert.ok((await e.get('task',task.id)).completed_at);
 await request(`/tasks/${task.id}/toggle/`,'POST');assert.equal((await e.get('task',task.id)).completed_at,null);
 const actions=(await request('/actions/?family=f&scope=all')).value.actions;assert.equal(actions[0].title,'Offline work');assert.equal(actions[0].primary_action.id,'complete');
 assert.deepEqual((await e.store.list('outbox')).sort((a,b)=>a.order-b.order).filter(m=>m.operation==='command').map(m=>m.command),['complete_task','reopen_task']);
 navigator.onLine=true;for(let i=0;i<6&&(await e.store.list('outbox')).length;i++)await e.sync();
 assert.equal(tasks.length,1);assert.equal(tasks[0].notes,'Retained');assert.equal(tasks[0].completed_at,null);assert.deepEqual(commands,['complete_task','reopen_task']);
 assert.equal((await e.store.list('conflicts')).length,0);assert.equal(e.state,'synced');
});
test('task list and workflow metadata stay local; terminal movement updates local completion',async()=>{
 const {e}=await setup();navigator.onLine=false;
 const list=(await request('/task-lists/','POST',{family:'f',name:'Work',workflow_columns:[{id:'done',kind:'done',is_terminal:true}]})).value;
 const task=(await request('/tasks/','POST',{family:'f',task_list:list.id,title:'Move'})).value;
 await request(`/tasks/${task.id}/move/`,'POST',{column_id:'done'});
 const stored=await e.get('task',task.id);assert.equal(stored.workflow_column,'done');assert.ok(stored.completed_at);
 const actions=(await request('/actions/?family=f&scope=all')).value.actions;assert.equal(actions[0].state,'done_today');
});
