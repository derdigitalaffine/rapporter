import {useEffect,useRef,useState} from 'react';
import {useTranslation} from 'react-i18next';
import {api,apiDownload,AUTH_CHANGED_EVENT} from './api';
import {Icon} from './icons';
import {FormActions,FormField,FormSection,FormShell} from './form-primitives';
import VehicleEditor,{vehicleError} from './VehicleEditor';
import JourneyEditor from './JourneyEditor';
import VehicleMap from './VehicleMap';
import {clearTracking,gpsPoint,readPending,trackingKey,writePending} from './vehicle-tracking';
import './vehicles-i18n';
import './vehicles.css';

const EMPTY_SUMMARY={count:0,open_review:0,distance_km:'0.0',by_kind_km:{business:'0.0',private:'0.0',commute:'0.0',unclassified:'0.0'}};
const EMPTY_FILTERS={from:'',to:'',kind:'',review:''};

function filterQuery(filters,format=''){
 const params=new URLSearchParams();
 if(filters.from)params.set('from',filters.from);
 if(filters.to)params.set('to',filters.to);
 if(filters.kind)params.set('kind',filters.kind);
 if(filters.review)params.set('review',filters.review);
 if(format)params.set('format',format);
 const query=params.toString();
 return query?`?${query}`:'';
}

export default function VehiclesHub({family,userId,onBack}){
 const {t,i18n}=useTranslation();
 const live=useRef(true),watch=useRef(null),record=useRef(null),pending=useRef([]),key=useRef(''),route=useRef([]),flushing=useRef(null),readVersion=useRef(0);
 const [vehicles,setVehicles]=useState([]),[selected,setSelected]=useState(()=>new URLSearchParams(location.search).get('vehicle')||''),[fuel,setFuel]=useState([]),[journeys,setJourneys]=useState([]),[summary,setSummary]=useState(EMPTY_SUMMARY),[openCount,setOpenCount]=useState(0),[active,setActive]=useState(null),[points,setPoints]=useState([]),[pendingCount,setPendingCount]=useState(0),[recording,setRecording]=useState(false),[loading,setLoading]=useState(true),[error,setError]=useState(''),[denied,setDenied]=useState(false),[busy,setBusy]=useState(false),[editor,setEditor]=useState(null),[journeyEditor,setJourneyEditor]=useState(null),[online,setOnline]=useState(navigator.onLine),[showMap,setShowMap]=useState(false);
 const [filters,setFilters]=useState(EMPTY_FILTERS),[appliedFilters,setAppliedFilters]=useState(EMPTY_FILTERS);
 const [startKm,setStartKm]=useState(''),[endKm,setEndKm]=useState(''),[consent,setConsent]=useState(false);
 const vehicle=vehicles.find(v=>String(v.id)===String(selected));

 const fail=e=>{if(live.current){setError(vehicleError(e,t));if(e.status===403||e.status===404){pause();setDenied(true);setVehicles([]);setFuel([]);setJourneys([]);setSummary(EMPTY_SUMMARY);setActive(null);setPoints([]);pending.current=[];record.current=null;route.current=[];if(key.current)sessionStorage.removeItem(key.current)}if(['point_conflict','point_order','journey_finished'].includes(e.code||e.message))pause()}};
 function pause(){if(watch.current!==null)navigator.geolocation?.clearWatch(watch.current);watch.current=null;if(live.current)setRecording(false)}
 function installJourney(detail){record.current=detail;key.current=trackingKey(userId,family.id,detail.id);pending.current=readPending(key.current);route.current=[...(detail.points||[]),...pending.current.filter(p=>p.sequence>=detail.point_count)];setActive(detail);setPoints([...route.current]);setPendingCount(pending.current.length);setEndKm(String(detail.start_odometer))}
 async function flush(){
  if(flushing.current)return flushing.current;
  if(!record.current||!pending.current.length)return;
  const journey=record.current,currentKey=key.current;
  const run=(async()=>{while(pending.current.length&&record.current?.id===journey.id){const batch=pending.current.slice(0,100);const updated=await api(`/vehicle-journeys/${journey.id}/points/`,{method:'POST',body:JSON.stringify({points:batch})});if(!live.current||key.current!==currentKey)return;pending.current=pending.current.slice(batch.length);writePending(currentKey,pending.current);record.current={...record.current,...updated};setActive(record.current);setPendingCount(pending.current.length)}})();
  flushing.current=run;
  try{await run}finally{if(flushing.current===run)flushing.current=null}
 }
 async function resume(){
  if(!record.current||watch.current!==null)return;if(!consent){setError(t('vehiclesUi.consent'));return}if(!navigator.geolocation||!window.isSecureContext){setError(t('vehiclesUi.gpsError'));return}
  try{await flush();if(!live.current||!record.current)return;const detail=await api(`/vehicle-journeys/${record.current.id}/`);if(!live.current)return;if(detail.ended_at){record.current=null;setActive(null);await refreshVehicles();await loadVehicle(selected);return}installJourney(detail);setError('');setRecording(true);
   watch.current=navigator.geolocation.watchPosition(position=>{if(!live.current||!record.current)return;if(pending.current.length>=1000||route.current.length>=20000){pause();setError(t('vehiclesUi.bufferFull'));return}const previous=route.current.at(-1);const sequence=previous?previous.sequence+1:0;const point=gpsPoint(position,record.current,previous,sequence);if(!point)return;try{const next=[...pending.current,point];writePending(key.current,next);pending.current=next;route.current.push(point);setPoints([...route.current]);setPendingCount(next.length)}catch{pause();setError(t('vehiclesUi.bufferFull'))}},()=>{pause();setError(t('vehiclesUi.gpsError'))},{enableHighAccuracy:true,maximumAge:0,timeout:15000});
  }catch(e){fail(e)}
 }
 async function refreshVehicles(){const rows=await api(`/vehicles/?family=${encodeURIComponent(family.id)}`);if(live.current){setVehicles(rows);return rows}return[]}
 async function loadVehicle(id,currentFilters=appliedFilters){
  const version=++readVersion.current;if(!id){setFuel([]);setJourneys([]);setSummary(EMPTY_SUMMARY);setOpenCount(0);return}
  try{
   const query=filterQuery(currentFilters);
   const [purchases,trips,report,openReport]=await Promise.all([
    api(`/vehicles/${id}/fuel/`),
    api(`/vehicles/${id}/journeys/${query}`),
    api(`/vehicles/${id}/journey-report/${query}`),
    api(`/vehicles/${id}/journey-report/?review=open`),
   ]);
   if(live.current&&version===readVersion.current){setFuel(purchases);setJourneys(trips);setSummary(report?.summary||EMPTY_SUMMARY);setOpenCount(Number(openReport?.summary?.open_review||0))}
  }catch(e){if(version===readVersion.current)fail(e)}
 }
 useEffect(()=>{
  live.current=true;let cancelled=false;setLoading(true);
  Promise.all([api(`/vehicles/?family=${encodeURIComponent(family.id)}`),api(`/vehicles/active/?family=${encodeURIComponent(family.id)}`)]).then(async([rows,trip])=>{if(cancelled)return;setVehicles(rows);const id=trip?.vehicle||(rows.some(v=>String(v.id)===selected)?selected:rows[0]?.id||'');setSelected(id);if(trip){const detail=await api(`/vehicle-journeys/${trip.id}/`);if(!cancelled)installJourney(detail)}}).catch(e=>{if(!cancelled)fail(e)}).finally(()=>{if(!cancelled)setLoading(false)});
  const connection=()=>{setOnline(navigator.onLine);if(navigator.onLine)flush().catch(fail)};const auth=e=>{if(e.detail?.authenticated===false){pause();clearTracking();pending.current=[];record.current=null;setActive(null);setPoints([]);setPendingCount(0)}};
  window.addEventListener('online',connection);window.addEventListener('offline',connection);window.addEventListener(AUTH_CHANGED_EVENT,auth);const interval=setInterval(()=>{if(navigator.onLine)flush().catch(fail)},10000);
  return()=>{cancelled=true;live.current=false;pause();readVersion.current++;clearInterval(interval);window.removeEventListener('online',connection);window.removeEventListener('offline',connection);window.removeEventListener(AUTH_CHANGED_EVENT,auth)};
 },[family.id,userId]);
 useEffect(()=>{setFuel([]);setJourneys([]);setShowMap(false);setStartKm('');loadVehicle(selected,appliedFilters)},[selected,appliedFilters.from,appliedFilters.to,appliedFilters.kind,appliedFilters.review]);

 async function start(event){event.preventDefault();if(busy||!vehicle||!consent)return;setBusy(true);setError('');const startKey=`vehicle-start:${userId}:${family.id}:${vehicle.id}`;try{let requestId=sessionStorage.getItem(startKey);if(!requestId){requestId=crypto.randomUUID();sessionStorage.setItem(startKey,requestId)}const trip=await api(`/vehicles/${vehicle.id}/journeys/`,{method:'POST',body:JSON.stringify({request_id:requestId,start_odometer:startKm||vehicle.odometer,purpose:'',kind:'unclassified'})});if(!live.current)return;sessionStorage.removeItem(startKey);installJourney({...trip,points:[]});await resume();await loadVehicle(vehicle.id)}catch(e){fail(e);if(e.status&&e.status<500)sessionStorage.removeItem(startKey)}finally{if(live.current)setBusy(false)}}
 async function stop(event){event.preventDefault();if(busy||!record.current)return;setBusy(true);setError('');pause();try{await flush();if(!live.current)return;await api(`/vehicle-journeys/${record.current.id}/`,{method:'POST',body:JSON.stringify({end_odometer:endKm})});if(!live.current)return;writePending(key.current,[]);record.current=null;pending.current=[];setActive(null);setPoints([]);setConsent(false);setPendingCount(0);await refreshVehicles();await loadVehicle(selected)}catch(e){fail(e)}finally{if(live.current)setBusy(false)}}
 async function saved(created){const isNew=editor==='vehicle';setEditor(null);await refreshVehicles();if(isNew&&created?.id&&!record.current)selectVehicle(created.id);else await loadVehicle(selected)}
 async function journeySaved(){setJourneyEditor(null);await refreshVehicles();await loadVehicle(selected)}
 function selectVehicle(id){setSelected(id);const url=new URL(location.href);url.searchParams.set('vehicle',id);url.searchParams.set('family',family.id);history.replaceState(history.state,'',url)}
 async function preview(trip){setBusy(true);try{const detail=await api(`/vehicle-journeys/${trip.id}/`);if(live.current){setPoints(detail.points);setShowMap(true)}}catch(e){fail(e)}finally{if(live.current)setBusy(false)}}
 async function downloadReport(format){
  if(!vehicle||busy)return;setBusy(true);setError('');
  try{const {blob,filename}=await apiDownload(`/vehicles/${vehicle.id}/journey-report/${filterQuery(appliedFilters,format)}`);const url=URL.createObjectURL(blob),anchor=document.createElement('a');const fallback=format==='pdf'?'fahrtenbuch.pdf':format==='audit'?'fahrtenbuch-audit.csv':'fahrtenbuch.csv';anchor.href=url;anchor.download=filename==='download'?fallback:filename;anchor.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}catch(e){fail(e)}finally{if(live.current)setBusy(false)}
 }
 function applyFilters(event){event?.preventDefault();setAppliedFilters({...filters})}
 function showOpenReview(){const next={...EMPTY_FILTERS,review:'open'};setFilters(next);setAppliedFilters(next)}
 function resetFilters(){setFilters(EMPTY_FILTERS);setAppliedFilters(EMPTY_FILTERS)}
 const formatDate=value=>new Date(value).toLocaleString(i18n.language,{timeZone:family.timezone||'Europe/Berlin',dateStyle:'short',timeStyle:'short'});

 return <div className="vehicles-hub">
  <div className="page-head"><button className="back-button" onClick={onBack} aria-label={t('vehiclesUi.back')}><Icon name="back"/></button><h1>{t('vehiclesUi.title')}</h1></div>
  {!denied&&(loading?<p role="status">{t('vehiclesUi.loading')}</p>:<><div className="vehicle-actions"><button className="secondary" onClick={()=>setEditor('vehicle')}>{t('vehiclesUi.add')}</button>{vehicles.length>0&&<FormField label={t('vehiclesUi.select')}><select value={selected} disabled={Boolean(active)} onChange={e=>selectVehicle(e.target.value)}>{vehicles.map(v=><option key={v.id} value={v.id}>{v.name}{v.plate?` · ${v.plate}`:''}{v.archived?` · ${t('vehiclesUi.archived')}`:''}</option>)}</select></FormField>}</div>{!vehicles.length&&!error&&<p>{t('vehiclesUi.empty')}</p>}</>)}
  {error&&<div className="vehicle-panel" role="alert"><p>{error}</p><button className="secondary" disabled={busy} onClick={async()=>{setError('');try{await flush();const rows=await refreshVehicles();const id=rows.some(v=>String(v.id)===String(selected))?selected:rows[0]?.id||'';setSelected(id);const trip=await api(`/vehicles/active/?family=${encodeURIComponent(family.id)}`);if(trip){const detail=await api(`/vehicle-journeys/${trip.id}/`);if(live.current){installJourney(detail);setSelected(trip.vehicle)}}await loadVehicle(id)}catch(e){fail(e)}}}>{t('vehiclesUi.retry')}</button></div>}
  {!online&&<p role="status">{t('vehiclesUi.offline')}</p>}
  {vehicle&&<>
   <section className="vehicle-panel"><div className="vehicle-summary"><div><h2>{vehicle.name}</h2><p>{[vehicle.plate,vehicle.manufacturer,vehicle.model].filter(Boolean).join(' · ')}</p><p>{t('vehiclesUi.odometer')}: {vehicle.odometer}</p></div><button className="ghost" onClick={()=>setEditor('edit')}>{t('vehiclesUi.edit')}</button></div></section>

   <section className="vehicle-panel vehicle-review" aria-labelledby="vehicle-review-title"><div className="vehicle-review-head"><div><h2 id="vehicle-review-title">{t('vehiclesUi.reviewInbox')}</h2><p className="vehicle-review-count">{openCount?t('vehiclesUi.reviewCount',{count:openCount}):t('vehiclesUi.reviewEmpty')}</p></div>{openCount>0&&<button className="secondary" onClick={showOpenReview}>{t('vehiclesUi.reviewOpen')}</button>}</div></section>

   <section className="vehicle-panel"><div className="vehicle-summary"><div><h2>{t('vehiclesUi.logbook')}</h2><p className="vehicle-muted">{t('vehiclesUi.privacy')}</p></div><button className="secondary" disabled={busy||Boolean(active)||!online} onClick={()=>setJourneyEditor({mode:'manual',trip:null})}>{t('vehiclesUi.manualAdd')}</button></div>
    {active?<><div className="vehicle-status" role="status"><strong>{t('vehiclesUi.active')} · {formatDate(active.started_at)}</strong><p>{t(`vehiclesUi.${recording?'recording':'paused'}`)}</p><p>{t('vehiclesUi.gpsDistance')}: {(active.distance_m/1000).toFixed(2)} km</p>{pendingCount>0&&<p>{t('vehiclesUi.pending',{count:pendingCount})}</p>}</div><label className="vehicle-checkbox"><input type="checkbox" checked={consent} onChange={e=>{setConsent(e.target.checked);if(!e.target.checked)pause()}}/>{t('vehiclesUi.consent')}</label><div className="vehicle-actions"><button className="secondary" disabled={busy||(!recording&&!consent)} onClick={recording?pause:resume}>{t(`vehiclesUi.${recording?'pause':'resume'}`)}</button><button className="ghost" onClick={()=>{setPoints([...route.current]);setShowMap(true)}}>{t('vehiclesUi.map')}</button></div><FormShell onSubmit={stop}><FormField required label={t('vehiclesUi.end_odometer')}><input type="number" required min={active.start_odometer} step="0.1" value={endKm} onChange={e=>setEndKm(e.target.value)}/></FormField><FormActions><button className="primary" disabled={busy||!online}>{t(`vehiclesUi.${busy?'loading':'stop'}`)}</button></FormActions></FormShell></>:!vehicle.archived&&<FormShell onSubmit={start}><FormSection legend={t('vehiclesUi.start')}><FormField label={t('vehiclesUi.start_odometer')}><input type="number" min={vehicle.odometer} step="0.1" placeholder={String(vehicle.odometer)} value={startKm} onChange={e=>setStartKm(e.target.value)}/></FormField><p className="vehicle-muted">{t('vehiclesUi.reviewInbox')}: {t('vehiclesUi.reasonOptional')}</p><label className="vehicle-checkbox"><input type="checkbox" checked={consent} onChange={e=>setConsent(e.target.checked)}/>{t('vehiclesUi.consent')}</label></FormSection><FormActions><button className="primary" disabled={busy||!online||!consent}>{t(`vehiclesUi.${busy?'loading':'start'}`)}</button></FormActions></FormShell>}
    {showMap&&<><p className="vehicle-muted">{t('vehiclesUi.mapPrivacy')}</p><VehicleMap familyId={family.id} points={points}/></>}

    <ul className="vehicle-list">{journeys.map(trip=><li key={trip.id}><details><summary><time>{formatDate(trip.started_at)}</time><span>{t(`vehiclesUi.${trip.kind}`)} · {t(`vehiclesUi.${trip.ended_at?'finished':'active'}`)}</span><span className="vehicle-badges">{trip.needs_review&&<span className="vehicle-badge attention">{t('vehiclesUi.reviewOpen')}</span>}{trip.legacy_record&&<span className="vehicle-badge warning">{t('vehiclesUi.legacy')}</span>}{trip.source==='manual'&&<span className="vehicle-badge">{t('vehiclesUi.manualSource')}</span>}</span></summary>
     <div className="vehicle-trip-meta">{trip.kind==='business'&&<><p><strong>{t('vehiclesUi.destination')}:</strong> {trip.destination||'–'}</p><p><strong>{t('vehiclesUi.businessPartner')}:</strong> {trip.business_partner||'–'}</p></>} {trip.purpose&&<p><strong>{t('vehiclesUi.purpose')}:</strong> {trip.purpose}</p>}{trip.note&&<p>{trip.note}</p>}<p>{t('vehiclesUi.gpsDistance')}: {(trip.distance_m/1000).toFixed(2)} km</p>{trip.ended_at&&<p>{t('vehiclesUi.meterDistance')}: {(Number(trip.end_odometer)-Number(trip.start_odometer)).toFixed(1)} km · {formatDate(trip.ended_at)}</p>}{trip.needs_review&&trip.review_due_at&&<p className="vehicle-muted">{trip.review_locked?t('vehiclesUi.reviewLocked'):t('vehiclesUi.reviewDue',{date:formatDate(trip.review_due_at)})}</p>}{trip.legacy_record&&<p className="vehicle-muted">{t('vehiclesUi.legacyHint')}</p>}</div>
     {trip.ended_at&&<div className="vehicle-actions">{trip.point_count>0&&<button className="secondary" disabled={busy||Boolean(active)} onClick={()=>preview(trip)}>{t('vehiclesUi.map')}</button>}<button className={trip.needs_review?'primary':'secondary'} disabled={busy} onClick={()=>setJourneyEditor({mode:trip.needs_review?'review':'correct',trip})}>{t(`vehiclesUi.${trip.needs_review?'reviewJourney':'correctJourney'}`)}</button></div>}
    </details></li>)}</ul>
    {!journeys.length&&<div className="vehicle-empty-action"><p>{t('vehiclesUi.noJourneys')}</p>{appliedFilters.review&&<button className="ghost" onClick={resetFilters}>{t('vehiclesUi.resetFilters')}</button>}</div>}{journeys.length>=500&&<p>{t('vehiclesUi.limit')}</p>}
   </section>

   <section className="vehicle-panel" aria-labelledby="vehicle-report-title"><h2 id="vehicle-report-title">{t('vehiclesUi.reports')}</h2><form className="vehicle-filters" onSubmit={applyFilters}>
    <FormField label={t('vehiclesUi.fromDate')}><input type="date" value={filters.from} onChange={e=>setFilters(current=>({...current,from:e.target.value}))}/></FormField>
    <FormField label={t('vehiclesUi.toDate')}><input type="date" value={filters.to} onChange={e=>setFilters(current=>({...current,to:e.target.value}))}/></FormField>
    <FormField label={t('vehiclesUi.kind')}><select value={filters.kind} onChange={e=>setFilters(current=>({...current,kind:e.target.value}))}><option value="">{t('vehiclesUi.allKinds')}</option>{['unclassified','private','business','commute'].map(value=><option key={value} value={value}>{t(`vehiclesUi.${value}`)}</option>)}</select></FormField>
    <FormField label={t('vehiclesUi.reviewFilter')}><select value={filters.review} onChange={e=>setFilters(current=>({...current,review:e.target.value}))}><option value="">{t('vehiclesUi.reviewAll')}</option><option value="open">{t('vehiclesUi.reviewOpen')}</option><option value="done">{t('vehiclesUi.reviewDone')}</option></select></FormField>
    <div className="vehicle-filter-actions"><button className="secondary" type="submit" disabled={busy}>{t('vehiclesUi.applyFilters')}</button><button className="ghost" type="button" onClick={resetFilters}>{t('vehiclesUi.resetFilters')}</button></div>
   </form>
   <div className="vehicle-stats" aria-live="polite"><div className="vehicle-stat"><strong>{summary.distance_km} km</strong><span>{t('vehiclesUi.totalDistance')}</span></div><div className="vehicle-stat"><strong>{summary.by_kind_km?.business||'0.0'} km</strong><span>{t('vehiclesUi.businessDistance')}</span></div><div className="vehicle-stat"><strong>{summary.by_kind_km?.private||'0.0'} km</strong><span>{t('vehiclesUi.privateDistance')}</span></div><div className="vehicle-stat"><strong>{summary.open_review||0}</strong><span>{t('vehiclesUi.openReviews')}</span></div></div>
   <div className="vehicle-export-actions"><button className="secondary" disabled={busy||!online} onClick={()=>downloadReport('csv')}>{t('vehiclesUi.export')}</button><button className="secondary" disabled={busy||!online} onClick={()=>downloadReport('pdf')}>{t('vehiclesUi.exportPdf')}</button><button className="secondary" disabled={busy||!online} onClick={()=>downloadReport('audit')}>{t('vehiclesUi.exportAudit')}</button></div>
   <p className="vehicle-compliance">{t('vehiclesUi.complianceNotice')}</p>
   </section>

   <section className="vehicle-panel"><div className="vehicle-summary"><h2>{t('vehiclesUi.fuel')}</h2>{!vehicle.archived&&<button className="secondary" disabled={!online} onClick={()=>setEditor('fuel')}>{t('vehiclesUi.addFuel')}</button>}</div><ul className="vehicle-list">{fuel.map(entry=><li key={entry.id}><strong>{entry.date} · {entry.quantity} {entry.unit}</strong><p>{entry.total_cost} {entry.currency} · {entry.odometer} km{entry.full_tank?` · ${t('vehiclesUi.full_tank')}`:''}</p>{entry.station&&<p>{entry.station}</p>}</li>)}</ul>{!fuel.length&&<p>{t('vehiclesUi.noFuel')}</p>}{fuel.length>=500&&<p>{t('vehiclesUi.limit')}</p>}</section>
  </>}
  {editor&&<VehicleEditor key={`${editor}-${selected}`} family={family} vehicle={editor==='vehicle'?null:vehicle} fuel={editor==='fuel'} onClose={()=>setEditor(null)} onSaved={saved}/>} 
  {journeyEditor&&<JourneyEditor key={`${journeyEditor.mode}-${journeyEditor.trip?.id||'new'}-${selected}`} vehicle={vehicle} journey={journeyEditor.trip} mode={journeyEditor.mode} onClose={()=>setJourneyEditor(null)} onSaved={journeySaved}/>} 
 </div>;
}
