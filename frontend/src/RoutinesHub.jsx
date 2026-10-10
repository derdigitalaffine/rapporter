import {useEffect,useRef,useState} from 'react';
import {useTranslation} from 'react-i18next';
import {api} from './api';
import {Icon} from './icons';
import {toast} from './feedback';
import RoutineEditor from './RoutineEditor';
import {compareRoutines,routineIconName,routineStatusKey} from './routine-ui';
import './routine-i18n';
import './routines.css';

export default function RoutinesHub({family,userId,onChanged}){
 const {t,i18n}=useTranslation();const [rows,setRows]=useState([]);const [loading,setLoading]=useState(true);const [error,setError]=useState('');const [edit,setEdit]=useState(null);const [filter,setFilter]=useState('active');const [search,setSearch]=useState('');const [busy,setBusy]=useState({});const pending=useRef(new Set());
 const date=value=>new Date(value).toLocaleString(i18n.language,{dateStyle:'medium',timeStyle:'short'});
 async function load(){if(!family?.id)return;setError('');try{let next=`/routines/?family=${encodeURIComponent(family.id)}`;const result=[];while(next){const response=await api(next);result.push(...(Array.isArray(response)?response:response.results||[]));if(response.next){const url=new URL(response.next,location.origin);next=url.pathname.replace(/^\/api/,'')+url.search}else next=null}setRows(result);const id=new URLSearchParams(location.search).get('routine');if(id)setEdit(result.find(x=>String(x.id)===id)||null)}catch(e){setError(e.message||t('routineUi.loadFailed'))}finally{setLoading(false)}}
 useEffect(()=>{load();const refresh=()=>{if(document.visibilityState==='visible')load()};document.addEventListener('visibilitychange',refresh);window.addEventListener('popstate',load);return()=>{document.removeEventListener('visibilitychange',refresh);window.removeEventListener('popstate',load)}},[family?.id]);
 async function record(row){if(pending.current.has(row.id))return;pending.current.add(row.id);setBusy(v=>({...v,[row.id]:true}));try{const log=await api(`/routines/${row.id}/done/`,{method:'POST',body:JSON.stringify({request_id:crypto.randomUUID()})});await load();onChanged?.();toast(t('routineUi.recorded',{name:row.name}),{type:'success',actionLabel:t('routineUi.undo'),onAction:async()=>{try{await api(`/routines/${row.id}/logs/${log.id}/`,{method:'DELETE'});await load();onChanged?.()}catch(e){toast(e.message,{type:'error'})}}})}catch(e){toast(e.message,{type:'error'})}finally{pending.current.delete(row.id);setBusy(v=>({...v,[row.id]:false}))}}
 function openEditor(row){setEdit(row);if(row?.id){const url=new URL(location.href);url.searchParams.set('routine',row.id);history.replaceState(history.state,'',url.pathname+url.search)}}
 function close(){setEdit(null);const url=new URL(location.href);url.searchParams.delete('routine');history.replaceState(history.state,'',url.pathname+url.search)}
 const counts={active:rows.filter(x=>x.active!==false).length,paused:rows.filter(x=>x.active===false).length,due:rows.filter(x=>['due','overdue'].includes(routineStatusKey(x))).length};
 const normalizedSearch=search.trim().toLocaleLowerCase(i18n.language);
 const visible=rows.filter(row=>{const status=routineStatusKey(row);const matchesFilter=filter==='all'||(filter==='active'&&row.active!==false)||(filter==='paused'&&row.active===false)||(filter==='due'&&['due','overdue'].includes(status));const matchesSearch=!normalizedSearch||row.name.toLocaleLowerCase(i18n.language).includes(normalizedSearch);return matchesFilter&&matchesSearch}).sort((a,b)=>compareRoutines(a,b,i18n.language));
 return <section className="routines-page">
  <div className="routine-hero">
   <div className="page-head"><div className="grow"><small className="routine-eyebrow">{t('routineUi.overview')}</small><h1>{t('routineUi.title')}</h1><p>{t('routineUi.hint')}</p></div><button className="primary compact" onClick={()=>openEditor({})}><Icon name="plus"/>{t('routineUi.add')}</button></div>
   <div className="routine-stats" aria-label={t('routineUi.overview')}>
    <button type="button" className={filter==='due'?'selected':''} onClick={()=>setFilter('due')}><span className="routine-stat-icon due"><Icon name="clock"/></span><span><strong>{counts.due}</strong><small>{t('routineUi.dueFilter')}</small></span></button>
    <button type="button" className={filter==='active'?'selected':''} onClick={()=>setFilter('active')}><span className="routine-stat-icon active"><Icon name="check"/></span><span><strong>{counts.active}</strong><small>{t('routineUi.active')}</small></span></button>
    <button type="button" className={filter==='paused'?'selected':''} onClick={()=>setFilter('paused')}><span className="routine-stat-icon paused"><Icon name="history"/></span><span><strong>{counts.paused}</strong><small>{t('routineUi.paused')}</small></span></button>
   </div>
   <p className="routine-manage-hint"><Icon name="info"/>{t('routineUi.manageHint')}</p>
  </div>
  <div className="routine-toolbar">
   <label className="routine-search"><span className="sr-only">{t('routineUi.search')}</span><Icon name="search"/><input type="search" value={search} placeholder={t('routineUi.search')} onChange={e=>setSearch(e.target.value)}/></label>
   <div className="routine-filter-tabs" role="group" aria-label={t('routineUi.status')}>{[['active',t('routineUi.active')],['due',t('routineUi.dueFilter')],['paused',t('routineUi.paused')],['all',t('routineUi.all')]].map(([key,label])=><button type="button" key={key} aria-pressed={filter===key} className={filter===key?'selected':''} onClick={()=>setFilter(key)}>{label}</button>)}</div>
  </div>
  {error&&<div className="routine-error" role="alert"><Icon name="warning"/><span>{error}</span><button className="secondary compact" onClick={load}>{t('routineUi.reload')}</button></div>}
  {loading&&<div className="routine-loading" role="status"><Icon name="refresh"/>{t('loading')}</div>}
  <div className="routine-grid">{visible.map(row=>{const status=routineStatusKey(row);const progress=row.target_count?Math.min(100,Math.round(((row.period_count||0)/row.target_count)*100)):null;return <article className={`routine-card routine-card-${status}`} key={row.id}>
   <div className="routine-card-top">
    <span className={`routine-icon routine-icon-${status}`} aria-hidden="true"><Icon name={routineIconName(row.icon)}/></span>
    <button className="routine-card-main row-main-button" onClick={()=>openEditor(row)}><strong>{row.name}</strong><span>{row.last_done_at?t('routineUi.last',{date:date(row.last_done_at)}):t('routineUi.never')}</span></button>
    <span className={`routine-status routine-status-${status}`}>{t(`routineUi.${status}`)}</span>
   </div>
   <div className="routine-card-detail">
    {row.target_count?<div className="routine-progress"><div><span>{t('routineUi.goalSummary',{count:row.target_count,days:row.target_period_days})}</span><strong>{t('routineUi.goalProgress',{count:row.period_count||0,target:row.target_count})}</strong></div><div className="routine-progress-track" aria-hidden="true"><span style={{width:`${progress}%`}}/></div></div>:<p>{row.active!==false&&(row.prediction?.expected_at?t('routineUi.next',{date:date(row.prediction.expected_at)}):t('routineUi.learning'))}</p>}
   </div>
   <div className="routine-card-actions"><button type="button" className="secondary compact routine-edit" onClick={()=>openEditor(row)} aria-label={`${t('routineUi.edit')}: ${row.name}`}><Icon name="edit"/>{t('routineUi.edit')}</button><button type="button" className="primary compact routine-done" aria-label={t('routineUi.record',{name:row.name})} disabled={!row.active||busy[row.id]} onClick={()=>record(row)}><Icon name="check"/>{t('routineUi.done')}</button></div>
  </article>})}</div>
  {!loading&&!visible.length&&!error&&<div className="smart-empty routine-empty"><Icon name={rows.length?'filter':'history'} size={30}/><strong>{rows.length?t('routineUi.emptyFiltered'):t('routineUi.empty')}</strong>{!rows.length&&<button className="primary compact" onClick={()=>openEditor({})}><Icon name="plus"/>{t('routineUi.add')}</button>}</div>}
  {edit&&<RoutineEditor family={family} userId={userId} routine={edit.id?edit:null} onClose={close} onSaved={async()=>{close();await load();await onChanged?.()}}/>}
 </section>
}
