import { useEffect, useMemo, useState } from 'react';
import { ArrowLeft, CheckCircle2, ExternalLink, PlugZap, RefreshCw, ShieldAlert, Trash2, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { api } from './api';
import './integration-hub.css';

const unwrap=x=>x?.results||x||[];
const groups={waste:'waste',warning:'warnings',weather:'weather',ics:'calendars',messenger:'messengers'};

export default function IntegrationHub({family,onBack}){
 const {t}=useTranslation();
 const [catalog,setCatalog]=useState([]);const [items,setItems]=useState([]);const [busy,setBusy]=useState('');const [selected,setSelected]=useState(null);const [notice,setNotice]=useState('');
 const load=async()=>{const [c,i]=await Promise.all([api('/integrations/catalog/'),api('/integrations/')]);setCatalog(c);setItems(unwrap(i))};
 useEffect(()=>{load()},[]);
 const connectedAdapters=useMemo(()=>new Set(items.map(x=>x.config?.adapter).filter(Boolean)),[items]);
 async function sync(x){setBusy(x.id);setNotice('');try{const r=await api(`/integrations/${x.id}/sync/`,{method:'POST',body:'{}'});setNotice(`${x.name}: ${r.synced} ${t('syncedItems')}`);await load()}catch(e){setNotice(e.message||t('connectionFailed'))}finally{setBusy('')}}
 async function syncAll(){setBusy('all');setNotice('');try{const r=await api('/integrations/sync_all/',{method:'POST',body:'{}'});setNotice(`${r.synced} ${t('syncedItems')}${r.errors?.length?` · ${r.errors.length} Fehler`:''}`);await load()}finally{setBusy('')}}
 async function remove(x){if(!confirm(`${t('disconnect')} · ${x.name}?`))return;setBusy(x.id);try{await api(`/integrations/${x.id}/`,{method:'DELETE'});await load()}finally{setBusy('')}}
 return <><div className="page-head"><button className="back-button" onClick={onBack}><ArrowLeft/></button><h1 className="grow">{t('integrations')}</h1><button className="small-action" onClick={syncAll} disabled={busy==='all'}><RefreshCw size={15} className={busy==='all'?'spin':''}/>{t('syncAll')}</button></div><p className="page-intro">{t('integrationsHint')}</p>{notice&&<div className="integration-notice">{notice}</div>}
 <h2 className="integration-section-title">{t('activeIntegrations')}</h2><div className="stack">{items.length?items.map(x=><section className="card integration-card" key={x.id}><div className="integration-row"><div className="round-icon"><CheckCircle2 size={18}/></div><div className="grow"><strong>{x.name}</strong><span>{x.kind} · {x.enabled?t('enabled'):t('disabled')}</span><small>{t('lastSync')}: {x.last_synced_at?new Intl.DateTimeFormat(undefined,{dateStyle:'short',timeStyle:'short'}).format(new Date(x.last_synced_at)):t('never')}</small></div><button className="small-action" onClick={()=>sync(x)} disabled={busy===x.id}><RefreshCw size={15} className={busy===x.id?'spin':''}/>{t('sync')}</button><button className="icon-button" onClick={()=>remove(x)} disabled={busy===x.id} aria-label={t('disconnect')}><Trash2 size={17}/></button></div></section>):<div className="empty">{t('noIntegrations')}</div>}</div>
 <h2 className="integration-section-title">{t('addIntegration')}</h2>{Object.entries(groupCatalog(catalog)).map(([kind,rows])=><div key={kind} className="integration-group"><h3>{t(groups[kind]||kind)}</h3><div className="stack">{rows.map(x=><section className="card catalog-card" key={x.id}><div className="catalog-top"><div className="round-icon"><PlugZap size={18}/></div><div className="grow"><strong>{x.name}</strong><p>{x.description}</p></div>{connectedAdapters.has(x.defaults?.adapter)&&<span className="role-pill">{t('connected')}</span>}</div><div className="catalog-actions">{x.help_url&&<a className="text-link" href={x.help_url} target="_blank" rel="noreferrer"><ExternalLink size={15}/>{t('openProvider')}</a>}<button className="primary compact" onClick={()=>setSelected(x)}>{t('configure')}</button></div></section>)}</div></div>)}
 {selected&&<ConnectSheet item={selected} family={family} t={t} onClose={()=>setSelected(null)} onConnected={async()=>{setSelected(null);setNotice(t('connectionSuccess'));await load()}}/>}</>
}

function groupCatalog(items){return items.reduce((acc,x)=>{(acc[x.kind]??=[]).push(x);return acc},{})}

function ConnectSheet({item,family,t,onClose,onConnected}){
 const initial={};for(const f of item.fields||[])initial[f.key]=f.default??'';
 const [values,setValues]=useState(initial);const [busy,setBusy]=useState(false);const [error,setError]=useState('');
 async function submit(e){e.preventDefault();setBusy(true);setError('');try{await api('/integrations/connect/',{method:'POST',body:JSON.stringify({family:family.id,catalog_id:item.id,values})});await onConnected()}catch(e){setError(e.message||t('connectionFailed'));setBusy(false)}}
 const waste=item.id?.startsWith('waste_');
 return <div className="sheet-backdrop"><section className="quick-sheet integration-sheet" role="dialog" aria-modal="true"><div className="sheet-handle"/><div className="sheet-head"><div><small>{t('configure')}</small><h2>{item.name}</h2></div><button className="sheet-close" onClick={onClose} disabled={busy}><X/></button></div><p className="page-intro">{item.description}</p>{waste&&<div className="helper-box"><ShieldAlert size={18}/><span>{t('addressCalendarHint')}</span></div>}{item.help_url&&<a className="provider-button" href={item.help_url} target="_blank" rel="noreferrer"><ExternalLink size={16}/>{t('openProvider')}</a>}<form className="quick-form" onSubmit={submit}>{(item.fields||[]).map(f=><label key={f.key}>{f.label}<input type={f.type||'text'} value={values[f.key]??''} onChange={e=>setValues(v=>({...v,[f.key]:f.type==='number'?Number(e.target.value):e.target.value}))} required={!!f.required} placeholder={f.default??''}/></label>)}{(item.fields||[]).some(f=>f.type==='password')&&<small className="secret-notice">{t('secretNotice')}</small>}{error&&<p className="error" role="alert">{error}</p>}<button className="primary" type="submit" disabled={busy||!family}>{busy?t('pleaseWait'):t('connect')}</button></form></section></div>
}
