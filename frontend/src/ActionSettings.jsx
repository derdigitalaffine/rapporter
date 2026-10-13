import {useEffect,useState} from 'react';
import {useTranslation} from 'react-i18next';
import {api} from './api';
export default function ActionSettings({family}){
 const {i18n}=useTranslation();const de=!i18n.language.startsWith('en');const [value,setValue]=useState(null);const [error,setError]=useState('');const [busy,setBusy]=useState(false);
 const path=`/actions/settings/?family=${family.id}`;
 useEffect(()=>{let active=true;api(path).then(data=>{if(active)setValue(data)}).catch(err=>{if(active)setError(err.message)});return()=>{active=false}},[path]);
 async function update(changes){setBusy(true);setError('');try{setValue(await api(path,{method:'PATCH',body:JSON.stringify(changes)}));window.dispatchEvent(new CustomEvent('familyos:actions-changed',{detail:{family:family.id}}));}catch(err){setError(err.message)}finally{setBusy(false)}}
 const fields=[['capture_suggestions',de?'Quick-Capture-Vorschläge':'Quick capture suggestions'],['personal_calendar_aware',de?'Eigene flexible Planung mit Kalender':'Use calendar for my flexible planning']];
 if(value?.can_manage_family)fields.push(['adaptive_enabled',de?'Familie: adaptive Vorschläge erlauben':'Family: allow adaptive proposals'],['calendar_aware',de?'Familie: Kalenderplanung erlauben':'Family: allow calendar planning']);
 return <section className="todo-smart-settings"><h2>{de?'Planung und Lernen':'Planning and learning'}</h2>{value&&fields.map(([key,label])=><label key={key}><input type="checkbox" checked={value[key]} disabled={busy} onChange={event=>update({[key]:event.target.checked})}/>{label}</label>)}{value?.can_manage_family&&<label>{de?'Lernhistorie in Tagen':'Learning history in days'}<input type="number" min="7" max="3650" defaultValue={value.learning_history_days} disabled={busy} onBlur={event=>{const days=Number(event.target.value);if(days!==value.learning_history_days)update({learning_history_days:days})}}/></label>}{error&&<p role="alert">{error}</p>}</section>
}
