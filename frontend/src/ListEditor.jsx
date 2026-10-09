import {useState} from 'react';
import {api} from './api';
import {Icon} from './icons';

export default function ListEditor({type,list,onClose,onSaved}){
 const [form,setForm]=useState({...list});const [busy,setBusy]=useState(false);const [error,setError]=useState('');
 const path=type==='task'?'task-lists':'shopping-lists';
 const set=(key,value)=>setForm(v=>({...v,[key]:value}));
 async function save(e){e.preventDefault();setBusy(true);setError('');try{await api(`/${path}/${list.id}/`,{method:'PATCH',body:JSON.stringify({name:form.name,store:type==='shopping'?form.store||'':undefined,archived:!!form.archived,icon:form.icon|| (type==='task'?'list-check':'cart-shopping')})});await onSaved()}catch(err){setError(err.message)}finally{setBusy(false)}}
 async function archive(){setBusy(true);setError('');try{await api(`/${path}/${list.id}/`,{method:'PATCH',body:JSON.stringify({archived:true})});await onSaved()}catch(err){setError(err.message)}finally{setBusy(false)}}
 return <div className="sheet-backdrop" onMouseDown={e=>{if(e.target===e.currentTarget&&!busy)onClose()}}><section className="quick-sheet" role="dialog" aria-modal="true"><div className="sheet-handle"/><div className="sheet-head"><div><small>{type==='task'?'Aufgabenliste':'Einkaufsliste'}</small><h2>Liste bearbeiten</h2></div><button className="sheet-close" onClick={onClose} disabled={busy}><Icon name="close"/></button></div><form className="quick-form" onSubmit={save}><label>Name<input value={form.name||''} onChange={e=>set('name',e.target.value)} required autoFocus/></label>{type==='shopping'&&<label>Laden / Geschäft<input value={form.store||''} onChange={e=>set('store',e.target.value)} placeholder="z. B. REWE, dm, Baumarkt"/></label>}<label>Symbol<select value={form.icon||''} onChange={e=>set('icon',e.target.value)}><option value={type==='task'?'list-check':'cart-shopping'}>Standard</option><option value="house">Zuhause</option><option value="store">Geschäft</option><option value="star">Favoriten</option></select></label>{error&&<p className="error">{error}</p>}<button className="primary" disabled={busy}><Icon name="check"/> Speichern</button><button type="button" className="ghost-danger destructive-wide" onClick={archive} disabled={busy}><Icon name="archive"/> Liste archivieren</button></form></section></div>
}
