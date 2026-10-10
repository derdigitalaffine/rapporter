import {useEffect,useMemo,useState} from 'react';
import {api} from './api';
import {Icon} from './icons';
import {toast} from './feedback';

const OUTBOX='familyos-baby-care-outbox:v1';
const TIMERS='familyos-baby-care-timers:v1';
const TIMER_KINDS=new Set(['breastfeed','sleep','pump']);
const isoNow=()=>new Date().toISOString();
const uid=()=>crypto.randomUUID?.()||`${Date.now()}-${Math.random()}`;

function readJson(key,fallback){try{const value=JSON.parse(localStorage.getItem(key)||'null');return value??fallback}catch{return fallback}}
function writeJson(key,value){localStorage.setItem(key,JSON.stringify(value))}
function pendingFor(babyId){return readJson(OUTBOX,[]).filter(row=>row.babyId===String(babyId)).length}
function queueRequest(babyId,{method='POST',path,payload}){const rows=readJson(OUTBOX,[]);rows.push({babyId:String(babyId),method,path,payload});writeJson(OUTBOX,rows);return pendingFor(babyId)}
function queueCare(babyId,payload){return queueRequest(babyId,{path:`/baby/profiles/${babyId}/care/`,payload})}
async function flushCare(babyId){
 const rows=readJson(OUTBOX,[]),keep=[];
 for(const row of rows){
  if(row.babyId!==String(babyId)){keep.push(row);continue}
  try{await api(row.path||`/baby/profiles/${babyId}/care/`,{method:row.method||'POST',body:JSON.stringify(row.payload)})}catch{keep.push(row)}
 }
 writeJson(OUTBOX,keep);return keep.filter(row=>row.babyId===String(babyId)).length;
}
function timersFor(babyId){return readJson(TIMERS,{})[String(babyId)]||{}}
function replaceTimers(babyId,next){const all=readJson(TIMERS,{});all[String(babyId)]=next;writeJson(TIMERS,all);return next}
function setTimer(babyId,kind,value){const next={...timersFor(babyId)};if(value)next[kind]=value;else delete next[kind];return replaceTimers(babyId,next)}
function clock(value){if(!value)return'–';return new Date(value).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})}

export default function BabyCarePanel({baby,t}){
 const [data,setData]=useState(null);const [pending,setPending]=useState(()=>pendingFor(baby.id));const [timers,setTimers]=useState(()=>timersFor(baby.id));const [busy,setBusy]=useState(false);const [feedSide,setFeedSide]=useState('unknown');const [bottle,setBottle]=useState('');const [pumpAmount,setPumpAmount]=useState('');const [temperature,setTemperature]=useState('');const [medication,setMedication]=useState({name:'',dose:'',unit:''});const [note,setNote]=useState('');
 const summary=data?.summary||{};
 const activeSleep=timers.sleep;
 const dayTiles=useMemo(()=>[
  [t('babyUi.bottle'),summary.totals?.bottle_ml!=null?`${Math.round(summary.totals.bottle_ml)} ml`:`${summary.counts?.bottle||0}×`],
  [t('babyUi.diaper'),`${summary.counts?.diaper||0}×`],
  [t('babyUi.sleep'),`${summary.sleep_minutes||0} min`],
  [t('babyUi.medication'),`${summary.counts?.medication||0}×`],
 ],[summary,t]);

 function syncActiveTimers(events=[]){
  const local={...timersFor(baby.id)};
  const serverActive={};
  for(const row of events){if(TIMER_KINDS.has(row.kind)&&!row.ended_at&&!serverActive[row.kind])serverActive[row.kind]={started_at:row.started_at,value:row.value||{},server_id:row.id,version:row.version}}
  for(const kind of TIMER_KINDS){
   const current=local[kind];
   if(serverActive[kind])local[kind]=serverActive[kind];
   else if(current?.server_id&&events.some(row=>row.id===current.server_id&&row.ended_at))delete local[kind];
  }
  setTimers(replaceTimers(baby.id,local));
 }
 async function load({mark=true}={}){const next=await api(`/baby/profiles/${baby.id}/care/?hours=24`);setData(next);syncActiveTimers(next.events||[]);if(mark)await api(`/baby/profiles/${baby.id}/viewed/`,{method:'POST',body:'{}'})}
 async function replay(){if(!navigator.onLine)return;const left=await flushCare(baby.id);setPending(left);if(left===0)await load()}
 useEffect(()=>{setTimers(timersFor(baby.id));setPending(pendingFor(baby.id));load().catch(()=>{});replay().catch(()=>{});const online=()=>replay().catch(()=>{});window.addEventListener('online',online);const poll=setInterval(()=>{if(navigator.onLine)load({mark:false}).catch(()=>{})},15000);return()=>{window.removeEventListener('online',online);clearInterval(poll)}},[baby.id]);

 async function record(kind,value={},timing={}){
  const payload={kind,started_at:timing.started_at||isoNow(),ended_at:timing.ended_at||null,value,client_event_id:timing.client_event_id||uid()};
  if(!navigator.onLine){setPending(queueCare(baby.id,payload));toast(`${baby.display_name}: ${t('babyUi.offlineQueued')}`,{type:'info'});return null}
  setBusy(true);
  try{const row=await api(`/baby/profiles/${baby.id}/care/`,{method:'POST',body:JSON.stringify(payload)});toast(`${baby.display_name}: ${t('babyUi.saved')}`,{type:'success'});await load({mark:false});return row}
  catch(error){if(!navigator.onLine){setPending(queueCare(baby.id,payload));toast(`${baby.display_name}: ${t('babyUi.offlineQueued')}`,{type:'info'});return null}toast(error.message||t('babyUi.error'),{type:'error'});throw error}
  finally{setBusy(false)}
 }

 async function toggleTimer(kind,value={}){
  const current=timersFor(baby.id)[kind];
  if(!current){
   const next={started_at:isoNow(),client_event_id:uid(),value};
   if(!navigator.onLine){setTimers(setTimer(baby.id,kind,next));return}
   setBusy(true);
   try{
    const row=await api(`/baby/profiles/${baby.id}/care/`,{method:'POST',body:JSON.stringify({kind,started_at:next.started_at,ended_at:null,value,client_event_id:next.client_event_id})});
    setTimers(setTimer(baby.id,kind,{...next,server_id:row.id,version:row.version}));
    await load({mark:false});
   }catch(error){toast(error.message||t('babyUi.error'),{type:'error'})}finally{setBusy(false)}
   return;
  }
  const endedAt=isoNow();
  if(current.server_id){
   const payload={expected_version:current.version||1,ended_at:endedAt,value:current.value||{}};
   if(!navigator.onLine){setPending(queueRequest(baby.id,{method:'PATCH',path:`/baby/care/${current.server_id}/`,payload}));setTimers(setTimer(baby.id,kind,null));toast(`${baby.display_name}: ${t('babyUi.offlineQueued')}`,{type:'info'});return}
   setBusy(true);
   try{await api(`/baby/care/${current.server_id}/`,{method:'PATCH',body:JSON.stringify(payload)});setTimers(setTimer(baby.id,kind,null));await load({mark:false});toast(`${baby.display_name}: ${t('babyUi.saved')}`,{type:'success'})}catch(error){toast(error.message||t('babyUi.error'),{type:'error'})}finally{setBusy(false)}
   return;
  }
  await record(kind,current.value||{}, {started_at:current.started_at,ended_at:endedAt,client_event_id:current.client_event_id});
  setTimers(setTimer(baby.id,kind,null));
 }
 function updateFeedSide(side){setFeedSide(side);const current=timersFor(baby.id).breastfeed;if(current)setTimers(setTimer(baby.id,'breastfeed',{...current,value:{...(current.value||{}),side}}))}
 async function quickBottle(ml){await record('bottle',{ml});setBottle(String(ml))}
 async function editStart(row){const initial=new Date(row.started_at).toISOString().slice(0,16);const value=window.prompt(t('babyUi.correctStart'),initial);if(!value)return;const parsed=new Date(value);if(Number.isNaN(parsed.getTime()))return;setBusy(true);try{await api(`/baby/care/${row.id}/`,{method:'PATCH',body:JSON.stringify({expected_version:row.version,started_at:parsed.toISOString()})});await load({mark:false});toast(t('babyUi.saved'),{type:'success'})}catch(error){toast(error.message||t('babyUi.error'),{type:'error'})}finally{setBusy(false)}}

 return <>
  <section className="card baby-panel"><div className="baby-section-head"><div><small>{t('babyUi.last24')}</small><h2>{baby.display_name} · {t('babyUi.now')}</h2></div>{pending>0&&<button className="secondary compact" disabled={!navigator.onLine||busy} onClick={replay}>{t('babyUi.syncOffline')}</button>}</div>{pending>0&&<p className="baby-reference-note">{t('babyUi.offlinePending',{count:pending})}</p>}
   <div className="baby-quick-grid">
    <button className={timers.breastfeed?'active':''} disabled={busy} onClick={()=>toggleTimer('breastfeed',{side:feedSide})}><Icon name="heart"/><strong>{t('babyUi.breastfeed')}</strong><small>{timers.breastfeed?t('babyUi.timerStop'):t('babyUi.timerStart')}</small></button>
    <button className={activeSleep?'active':''} disabled={busy} onClick={()=>toggleTimer('sleep')}><Icon name="clock"/><strong>{t('babyUi.sleep')}</strong><small>{activeSleep?t('babyUi.timerStop'):t('babyUi.timerStart')}</small></button>
    <button className={timers.pump?'active':''} disabled={busy} onClick={()=>toggleTimer('pump')}><Icon name="refresh"/><strong>{t('babyUi.pump')}</strong><small>{timers.pump?t('babyUi.timerStop'):t('babyUi.timerStart')}</small></button>
   </div>
   <div className="segmented" aria-label={t('babyUi.breastfeed')}>{[['left',t('babyUi.left')],['right',t('babyUi.right')],['both',t('babyUi.both')]].map(([value,label])=><button key={value} className={feedSide===value?'active':''} onClick={()=>updateFeedSide(value)}>{label}</button>)}</div>
  </section>

  <section className="card baby-panel"><h3>{t('babyUi.quickLog')}</h3><div className="baby-chip-row"><button className="chip" disabled={busy} onClick={()=>quickBottle(60)}>{t('babyUi.bottle')} 60 ml</button><button className="chip" disabled={busy} onClick={()=>quickBottle(90)}>{t('babyUi.bottle')} 90 ml</button><button className="chip" disabled={busy} onClick={()=>quickBottle(120)}>{t('babyUi.bottle')} 120 ml</button></div><div className="baby-chip-row"><button className="chip" disabled={busy} onClick={()=>record('diaper',{type:'wet'})}>{t('babyUi.wet')}</button><button className="chip" disabled={busy} onClick={()=>record('diaper',{type:'dirty'})}>{t('babyUi.dirty')}</button><button className="chip" disabled={busy} onClick={()=>record('diaper',{type:'mixed'})}>{t('babyUi.mixed')}</button></div></section>

  <section className="card baby-panel"><h3>{t('babyUi.todaySummary')}</h3><div className="baby-quick-grid">{dayTiles.map(([label,value])=><div className="baby-summary-tile" key={label}><small>{label}</small><strong>{value}</strong></div>)}</div><p className="baby-reference-note">{t('babyUi.lastFeed')}: {clock(summary.last?.bottle||summary.last?.breastfeed)} · {t('babyUi.lastDiaper')}: {clock(summary.last?.diaper)}{activeSleep?` · ${t('babyUi.sleepingSince')} ${clock(activeSleep.started_at)}`:''}</p></section>

  <section className="card baby-panel"><h3>{t('babyUi.careDetails')}</h3><div className="form-grid">
   <label>{t('babyUi.bottle')} · {t('babyUi.amountMl')}<div className="baby-inline-form"><input inputMode="decimal" value={bottle} onChange={e=>setBottle(e.target.value)}/><button className="primary compact" disabled={busy||!bottle} onClick={()=>record('bottle',{ml:Number(bottle)})}>{t('babyUi.record')}</button></div></label>
   <label>{t('babyUi.pump')} · {t('babyUi.amountMl')}<div className="baby-inline-form"><input inputMode="decimal" value={pumpAmount} onChange={e=>setPumpAmount(e.target.value)}/><button className="secondary compact" disabled={busy||!pumpAmount} onClick={()=>record('pump',{ml:Number(pumpAmount)}).then(()=>setPumpAmount(''))}>{t('babyUi.record')}</button></div></label>
   <label>{t('babyUi.temperatureC')}<div className="baby-inline-form"><input inputMode="decimal" value={temperature} onChange={e=>setTemperature(e.target.value)}/><button className="secondary compact" disabled={busy||!temperature} onClick={()=>record('temperature',{celsius:Number(temperature)}).then(()=>setTemperature(''))}>{t('babyUi.record')}</button></div></label>
   <label>{t('babyUi.medicationName')}<input value={medication.name} onChange={e=>setMedication(current=>({...current,name:e.target.value}))}/></label><label>{t('babyUi.dose')}<div className="baby-inline-form"><input value={medication.dose} onChange={e=>setMedication(current=>({...current,dose:e.target.value}))}/><input value={medication.unit} onChange={e=>setMedication(current=>({...current,unit:e.target.value}))} placeholder={t('babyUi.unit')}/><button className="secondary compact" disabled={busy||!medication.name.trim()} onClick={()=>record('medication',{name:medication.name.trim(),dose:medication.dose,unit:medication.unit}).then(()=>setMedication({name:'',dose:'',unit:''}))}>{t('babyUi.record')}</button></div></label>
   <label>{t('babyUi.note')}<div className="baby-inline-form"><input value={note} onChange={e=>setNote(e.target.value)}/><button className="secondary compact" disabled={busy||!note.trim()} onClick={()=>record('note',{text:note.trim()}).then(()=>setNote(''))}>{t('babyUi.record')}</button></div></label>
  </div></section>

  <section className="card baby-panel"><div className="baby-section-head"><h3>{t('babyUi.last24')}</h3><span>{data?.events?.length||0}</span></div><div className="baby-timeline">{(data?.events||[]).slice(0,60).map((row,index)=><div className="baby-event" key={row.id}><Icon name={row.kind==='sleep'?'clock':'heart'}/><div><strong>{t(`babyUi.${row.kind}`,{defaultValue:row.kind})}</strong><small>{new Date(row.started_at).toLocaleString()}</small></div><div className="baby-event-actions"><button className="text-button" disabled={busy} onClick={()=>editStart(row)}>{t('babyUi.edit')}</button>{index===0&&<button className="text-button" disabled={busy} onClick={async()=>{await api(`/baby/care/${row.id}/`,{method:'DELETE'});toast(t('babyUi.undo'),{type:'success'});await load({mark:false})}}>{t('babyUi.undo')}</button>}</div></div>)}</div></section>
 </>;
}
