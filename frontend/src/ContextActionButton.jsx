import {useState} from 'react';
import {useTranslation} from 'react-i18next';
import {api} from './api';
import {Icon} from './icons';
import {FormField,FormShell} from './form-primitives';
export default function ContextActionButton({family,context,title=''}){
 const {i18n}=useTranslation();const de=!i18n.language.startsWith('en');const [open,setOpen]=useState(false);const [name,setName]=useState(title.slice(0,160));const [recurring,setRecurring]=useState(false);const [busy,setBusy]=useState(false);const [error,setError]=useState('');const [result,setResult]=useState(null);
 async function save(event){event.preventDefault();setBusy(true);setError('');try{const value=await api(`/actions/from-context/?family=${family.id}`,{method:'POST',body:JSON.stringify({context,title:name.trim(),recurring})});setResult(value);setOpen(false)}catch(err){setError(err.message)}finally{setBusy(false)}}
 return <div><button type="button" className="secondary" onClick={()=>setOpen(v=>!v)} aria-expanded={open}><Icon name="tasks"/>{de?'Aufgabe daraus':'Create action'}</button>{open&&<FormShell onSubmit={save}><FormField label={de?'Titel':'Title'}><input value={name} onChange={event=>setName(event.target.value)} required maxLength={160}/></FormField><label><input type="checkbox" checked={recurring} onChange={event=>setRecurring(event.target.checked)}/>{de?'Regelmäßig erledigen':'Recurring action'}</label>{error&&<p role="alert">{error}</p>}<button type="submit" disabled={busy}>{de?'Anlegen und verknüpfen':'Create and link'}</button></FormShell>}{result&&<p role="status"><a href={`/?page=${recurring?'routines':'tasks'}&family=${family.id}&${recurring?'routine':'task'}=${result.action_id.split(':')[1]}`}>{de?'Aufgabe öffnen':'Open action'}</a></p>}</div>
}
