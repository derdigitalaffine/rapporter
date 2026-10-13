import {useEffect,useRef,useState} from 'react';
import {useTranslation} from 'react-i18next';
import {api} from './api';
import {Icon} from './icons';
import {FormField,FormShell} from './form-primitives';
import './unified-actions.css';

export default function ActionCapture({family,onSaved}){
 const {i18n}=useTranslation();const de=!i18n.language.startsWith('en');
 const [query,setQuery]=useState('');const [rows,setRows]=useState([]);const [busy,setBusy]=useState(false);const [error,setError]=useState('');const [result,setResult]=useState(null);const [duration,setDuration]=useState('');const [customDuration,setCustomDuration]=useState('');const [icons,setIcons]=useState([]);const [icon,setIcon]=useState('');const [enabled,setEnabled]=useState(true);const request=useRef(null);const revision=useRef(0);const familyRef=useRef(family?.id);familyRef.current=family?.id;
 useEffect(()=>{setQuery('');setRows([]);setResult(null);setError('');request.current=null;revision.current++;},[family?.id]);
 useEffect(()=>{
  const version=++revision.current;if(!family?.id||!enabled){setRows([]);return;}
  const timer=setTimeout(()=>api(`/actions/capture/?family=${encodeURIComponent(family.id)}&q=${encodeURIComponent(query)}`).then(value=>{if(version===revision.current){setRows(value.suggestions||[]);setIcons(value.icon_suggestions||[]);if(value.suggestions_enabled===false)setEnabled(false)}}).catch(err=>{if(version===revision.current)setError(err.message)}),query?180:0);
  return()=>{clearTimeout(timer);revision.current++;};
 },[family?.id,query,enabled]);
 async function capture(item){
  if(busy||(!item&&!query.trim()))return;setBusy(true);setError('');
  const familyId=family.id;
  const values={...(item?{action_id:item.id}:{title:query.trim(),create_new:true,...(icon?{icon}:{})}),duration_minutes:duration===''?null:Number(duration==='custom'?customDuration:duration)};
  const fingerprint=JSON.stringify(values);
  if(request.current?.fingerprint!==fingerprint)request.current={fingerprint,id:crypto.randomUUID()};
  try{
   const value=await api(`/actions/capture/?family=${familyId}`,{method:'POST',body:JSON.stringify({...values,request_id:request.current.id})});
   if(familyId!==familyRef.current)return;
   setResult({...value,typedId:item?.id||value.action_id});request.current=null;setQuery('');onSaved?.();window.dispatchEvent(new CustomEvent('familyos:actions-changed',{detail:{family:familyId}}));
  }catch(err){if(familyId===familyRef.current)setError(err.message)}finally{setBusy(false)}
 }
 async function undo(){if(!result||busy)return;setBusy(true);setError('');try{await api('/actions/execute/',{method:'POST',body:JSON.stringify({action_id:result.typedId,operation:'undo',completion_id:result.id,request_id:crypto.randomUUID()})});setResult(null);onSaved?.();window.dispatchEvent(new CustomEvent('familyos:actions-changed',{detail:{family:family.id}}));}catch(err){setError(err.message)}finally{setBusy(false)}}
 return <section className="action-capture" aria-label={de?'Ich habe gerade …':'I just …'}>
  <FormShell onSubmit={event=>{event.preventDefault();capture(null)}}>
   <FormField label={de?'Ich habe gerade …':'I just …'}><input value={query} onChange={event=>{setQuery(event.target.value);setError('')}} maxLength={160} disabled={busy} placeholder={de?'Zum Beispiel: Betten gemacht':'For example: made the beds'}/></FormField>
   <div className="action-capture-chips">{rows.map(item=><button type="button" key={item.id} disabled={busy} onClick={()=>capture(item)} title={de?(item.capture_reason==='title_match'?'Passender Titel':'Sichtbare Aufgabe deiner Familie'):(item.capture_reason==='title_match'?'Matching title':'Visible action in your family')}><Icon name={item.icon||'tasks'}/><span>{item.title}</span><Icon name="check"/></button>)}</div>
   <details><summary>{de?'Dauer und Vorschläge':'Duration and suggestions'}</summary><FormField label={de?'Dauer (optional)':'Duration (optional)'}><select value={duration} onChange={event=>setDuration(event.target.value)}><option value="">{de?'Ohne Angabe':'Not recorded'}</option>{[5,10,15,30,60].map(value=><option key={value} value={value}>{value} min</option>)}<option value="custom">{de?'Andere':'Other'}</option></select></FormField>{duration==='custom'&&<FormField label={de?'Dauer in Minuten':'Duration in minutes'}><input type="number" min="0" max="10080" required value={customDuration} onChange={event=>setCustomDuration(event.target.value)}/></FormField>}<label><input type="checkbox" checked={enabled} onChange={async event=>{const next=event.target.checked;setEnabled(next);try{await api(`/actions/settings/?family=${family.id}`,{method:'PATCH',body:JSON.stringify({capture_suggestions:next})})}catch(err){setEnabled(!next);setError(err.message)}}}/>{de?'Intelligente Vorschläge':'Smart suggestions'}</label></details>
   {query.trim()&&<fieldset className="action-icon-options"><legend>Icon</legend>{icons.map(choice=><button type="button" key={choice} aria-label={choice} aria-pressed={icon===choice} onClick={()=>setIcon(choice)}><Icon name={choice}/></button>)}</fieldset>}
   {query.trim()&&<button type="submit" disabled={busy}>{de?'Neu anlegen und jetzt erledigen':'Create new and complete now'}</button>}
  </FormShell>
  <div role="status">{result&&<p>{de?'Erledigt gespeichert.':'Completion saved.'} <button type="button" onClick={undo} disabled={busy}>{de?'Rückgängig':'Undo'}</button></p>}</div>
  {error&&<p role="alert">{error}</p>}
 </section>;
}
