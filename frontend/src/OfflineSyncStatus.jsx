import {useEffect,useRef,useState} from 'react';
import {useTranslation} from 'react-i18next';
import {storageDiagnostics} from './offline-recovery.js';
import {offlineEngine} from './offline-runtime';
import {SYNC_CHANGED} from './offline-sync-engine';
import OverlayPortal from './OverlayPortal';
import './offline-sync.css';
import {syncStatus} from './offline-status.js';
import {syncLabels} from './offline-status-i18n.js';
export default function OfflineSyncStatus({family}){
 const {i18n}=useTranslation(),t=syncLabels[i18n.language.split('-')[0]]||syncLabels.en;
 const trigger=useRef(null),sheet=useRef(null);
 const [health,setHealth]=useState({serverState:'unknown',liveState:'connecting',lastSyncAt:null});
 const [state,setState]=useState('idle'),[open,setOpen]=useState(false),[conflicts,setConflicts]=useState([]),[pending,setPending]=useState(0),[error,setError]=useState(''),[lowSpace,setLowSpace]=useState(false);
 const engine=offlineEngine(family?.id);
 const activeEngine=useRef(engine);activeEngine.current=engine;
 const refresh=async()=>{
  if(!engine)return;
  const [cursor,entries,queue]=await Promise.all([engine.store.get('syncState','cursor'),engine.store.list('conflicts'),engine.store.list('outbox')]);
  if(activeEngine.current!==engine)return;
  setState(navigator.onLine?engine.state:'offline');
  setHealth({serverState:engine.serverState||'unknown',liveState:engine.liveState||'connecting',lastSyncAt:engine.lastSyncAt||cursor?.last_sync_at||null});
  setConflicts(entries);setPending(queue.length);
 };
 useEffect(()=>{refresh();const timer=setInterval(refresh,5000);const changed=e=>{if(!e.detail?.familyId||e.detail.familyId===String(family?.id))refresh()};window.addEventListener(SYNC_CHANGED,changed);window.addEventListener('offline',changed);window.addEventListener('online',changed);storageDiagnostics().then(result=>setLowSpace(result.lowSpace));return()=>{if(activeEngine.current===engine)activeEngine.current=null;clearInterval(timer);window.removeEventListener(SYNC_CHANGED,changed);window.removeEventListener('offline',changed);window.removeEventListener('online',changed)}},[family?.id,engine]);
 useEffect(()=>{if(!open)return;const previous=document.activeElement;sheet.current?.querySelector('.sheet-close')?.focus();const key=e=>{if(e.key==='Escape'){e.preventDefault();setOpen(false)}if(e.key==='Tab'){const elements=[...sheet.current.querySelectorAll('button:not(:disabled),a[href],input:not(:disabled),[tabindex="0"]')];const first=elements[0],last=elements.at(-1);if(e.shiftKey&&document.activeElement===first){e.preventDefault();last?.focus()}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first?.focus()}}};document.addEventListener('keydown',key);return()=>{document.removeEventListener('keydown',key);previous?.focus?.()}},[open]);
 if(!engine)return null;
 const status=syncStatus({online:navigator.onLine,state,...health,pending,conflicts:conflicts.length});
 const liveText=t[health.liveState==='unavailable'?'unavailableLive':health.liveState]||t.connecting;
 const label=t[status];
 async function resolve(id,choice){try{setError('');await engine.resolve(id,choice);await refresh()}catch(e){setError(e.message)}}
 return <><button ref={trigger} type="button" className="offline-sync-pill" data-status={status} aria-haspopup="dialog" aria-expanded={open} onClick={()=>setOpen(true)}><span className="offline-sync-primary">{label}{conflicts.length?` (${conflicts.length})`:''}</span><span className="offline-live-label" data-live={health.liveState}><span className="offline-live-dot" aria-hidden="true"/>{liveText}</span></button>{open&&<OverlayPortal><div className="sheet-backdrop" onMouseDown={e=>{if(e.target===e.currentTarget)setOpen(false)}}><section ref={sheet} className="quick-sheet offline-sync-sheet" role="dialog" aria-modal="true" aria-labelledby="offline-sync-title"><div className="sheet-head"><h2 id="offline-sync-title">{t.details}</h2><button type="button" className="sheet-close" aria-label={t.close} onClick={()=>setOpen(false)}>×</button></div><div className="offline-sync-content"><p className="offline-sync-summary" role="status">{label}</p><dl className="offline-sync-facts"><div><dt>{t.serverLabel}</dt><dd>{health.serverState==='reachable'?t.reachable:health.serverState==='unreachable'?t.serverDown:health.serverState==='auth-required'?t.auth:t.unknown}</dd></div><div><dt>{t.liveLabel}</dt><dd>{liveText}</dd></div><div><dt>{t.lastLabel}</dt><dd>{health.lastSyncAt?<time dateTime={health.lastSyncAt}>{new Date(health.lastSyncAt).toLocaleString(i18n.language)}</time>:t.never}</dd></div><div><dt>{t.changesLabel}</dt><dd>{pending?`${pending} · ${t.pending}`:t.empty}</dd></div>{conflicts.length>0&&<div><dt>{t.conflictsLabel}</dt><dd>{conflicts.length}</dd></div>}</dl><p className="offline-sync-hint">{t.savedHint} {health.liveState!=='connected'&&t.liveHint}</p>{lowSpace&&<p role="alert">{t.quota}</p>}{error&&<p role="alert" className="error">{error}</p>}{state==='auth-required'?<button className="primary" onClick={()=>window.dispatchEvent(new CustomEvent('familyos:request-reauth'))}>{t.auth}</button>:<button className="secondary" disabled={!navigator.onLine||state==='synchronizing'} onClick={()=>engine.sync().then(refresh).catch(e=>setError(e.message))}>{t.now}</button>}{conflicts.map(entry=>{const server=entry.result?.server_data,local=entry.local_data||entry.mutation.data||entry.mutation.changes||{};const fields=Object.keys(entry.result?.conflicts||entry.mutation.changes||{}).filter(k=>!k.startsWith('__'));return <article className="offline-sync-conflict" key={entry.id}><h3>{local.title||local.name||server?.title||server?.name||t.attention}</h3>{!server&&<p>{t.unavailable}</p>}<dl><dt>{t.local}</dt><dd>{fields.length?fields.map(field=><p key={field}>{String(local[field]??'')}</p>):JSON.stringify(local)}</dd>{server&&<><dt>{t.server}</dt><dd>{fields.length?fields.map(field=><p key={field}>{String(server[field]??'')}</p>):server.title||server.name}</dd></>}</dl><div className="form-actions">{server&&entry.result.server_version&&['update','delete','command'].includes(entry.mutation.operation)&&<button className="primary" onClick={()=>resolve(entry.id,'local')}>{t.keep}</button>}<button className="secondary" onClick={()=>resolve(entry.id,'server')}>{server?t.use:t.discard}</button><button className="secondary" onClick={()=>navigator.clipboard.writeText(JSON.stringify(local,null,2)).catch(e=>setError(e.message))}>{t.copy}</button></div></article>})}</div></section></div></OverlayPortal>}</>;
}
