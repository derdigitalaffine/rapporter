import SymbolPicker from './SymbolPicker';
import FamilySheet from './ui/FamilySheet';
import {useEffect,useState,useId} from 'react';
import {useTranslation} from 'react-i18next';
import {api} from './api';
import {Icon} from './icons';
import SchedulingRecurrenceEditor from './SchedulingRecurrenceEditor';
import SchedulingDependenciesEditor from './SchedulingDependenciesEditor';
import {FormShell,FormField,FormSection,FormRow} from './form-primitives';
import './unified-actions.css';
const days=['MO','TU','WE','TH','FR','SA','SU'];
const labels={de:['Mo','Di','Mi','Do','Fr','Sa','So'],en:['Mon','Tue','Wed','Thu','Fri','Sat','Sun']};
export default function ActionOptionsEditor({item,onClose,onSaved}){
 const {i18n}=useTranslation();const de=!i18n.language.startsWith('en');const titleId=useId();
 const [value,setValue]=useState(null);const [error,setError]=useState('');const [busy,setBusy]=useState(false);
 const [kind,id]=String(item.id).split(':');const path=`/actions/${kind}/${id}/`;
 useEffect(()=>{let active=true;api(path).then(data=>{if(active)setValue(data)}).catch(err=>{if(active)setError(err.message)});return()=>{active=false}},[path]);
 const schedule=value?.schedule&&Object.keys(value.schedule).length?value.schedule:{version:'action-schedule-v1',mode:'learning',segments:[]};
 const recurrence=schedule.recurrence||{frequency:'daily',interval:1};
 function changeSchedule(changes){setValue(current=>{const currentSchedule=current?.schedule&&Object.keys(current.schedule).length?current.schedule:{version:'action-schedule-v1',mode:'learning',segments:[]};return({...current,schedule:{...currentSchedule,...changes}})})}
 function changeRecurrence(next){changeSchedule({recurrence:next||undefined})}
 function applyParsedRule(rule){changeSchedule({recurrence:rule.recurrence,timezone:rule.timezone,anchor_date:rule.anchor_date,segments:rule.segments||[],excluded_weekdays:rule.excluded_weekdays||[],exceptions:rule.exceptions||[]})}
 async function save(event){event.preventDefault();if(!value)return;setBusy(true);setError('');try{const data={icon:value.icon||'tasks',accent_token:value.accent_token||'',schedule:{...schedule,timezone:schedule.timezone||undefined}};await api(path,{method:'PATCH',body:JSON.stringify(data)});onSaved?.();onClose();window.dispatchEvent(new CustomEvent('familyos:actions-changed',{detail:{family:item.family}}));}catch(err){setError(err.message)}finally{setBusy(false)}}
 async function feedback(choice){const proposal=value.prediction?.suggested_schedule_change;if(!proposal)return;setBusy(true);try{setValue(await api(path,{method:'PATCH',body:JSON.stringify({feedback:choice,proposal_id:proposal.proposal_id})}));onSaved?.()}catch(err){setError(err.message)}finally{setBusy(false)}}
 function updateTime(day,field,v){const segment=schedule.segments?.find(s=>(s.weekdays||days).includes(day))||{};const others=(schedule.segments||[]).flatMap(s=>{const rest=(s.weekdays||days).filter(d=>d!==day);return rest.length?[{...s,weekdays:rest}]:[]});const next={...segment,weekdays:[day]};if(field==='preferred_time'){if(v)next.preferred_time=v;else delete next.preferred_time;}else{next.window={start:segment.window?.start||'00:00',end:segment.window?.end||'23:59',[field]:v||(field==='start'?'00:00':'23:59')};}changeSchedule({segments:[...others,next]})}
 async function newRound(template){setBusy(true);setError('');try{const result=await api('/actions/decision-round/',{method:'POST',body:JSON.stringify({action_id:item.id,template_id:template.id,request_id:crypto.randomUUID()})});location.href=result.deep_link}catch(err){setError(err.message)}finally{setBusy(false)}}
 const proposal=value?.prediction?.suggested_schedule_change;const language=de?'de':'en';
 return <FamilySheet labelledBy={titleId} onClose={onClose} busy={busy}>
  <div className="sheet-head"><h2 id={titleId}>{item.title}</h2><button type="button" onClick={onClose} aria-label={de?'Schließen':'Close'}><Icon name="close"/></button></div>
  {!value&&!error&&<p role="status">{de?'Wird geladen …':'Loading …'}</p>}
  {value&&<FormShell onSubmit={save}>
   <SymbolPicker value={value.icon||'tasks'} options={value.icon_choices||value.icon_suggestions||[]} onChange={icon=>setValue(current=>({...current,icon}))} disabled={busy}/>
   <SchedulingDependenciesEditor familyId={item.family} anchorType="action" anchorId={value.id} anchorTitle={item.title} disabled={busy}/>
   <details><summary>{de?'Mehr Optionen':'More options'}</summary>
    <FormSection legend={de?'Wiederholung und Lernen':'Repeat and learning'}>
     <FormField label={de?'Planungsmodus':'Scheduling mode'}><select value={schedule.mode} onChange={event=>{const mode=event.target.value;changeSchedule({mode,...(mode==='learning'?{}:{recurrence:schedule.recurrence||recurrence})})}}>{['static','learning','adaptive'].map(mode=><option key={mode} value={mode}>{({static:de?'Statisch':'Static',learning:de?'Lernend':'Learning',adaptive:de?'Adaptiv':'Adaptive'})[mode]}</option>)}</select></FormField>
     <SchedulingRecurrenceEditor value={schedule.recurrence||''} onChange={changeRecurrence} familyId={item.family} anchor={schedule.anchor_date} allowOnce allowNone={schedule.mode==='learning'} disabled={busy} onParsedRule={applyParsedRule}/>
     {schedule.mode==='learning'&&!schedule.recurrence&&<p className="muted">{de?'Ohne feste Wiederholung lernt FamilyOS weiterhin aus deinem Verlauf.':'Without a fixed recurrence, FamilyOS keeps learning from your history.'}</p>}
     <label><input type="checkbox" checked={schedule.continue_learning!==false} onChange={event=>changeSchedule({continue_learning:event.target.checked})}/>{de?'Automatisch weiterlernen':'Continue learning'}</label>
     <FormField label={de?'Zeitzone (Familienstandard bei leerem Feld)':'Timezone (family default when empty)'}><input value={schedule.timezone||''} onChange={event=>changeSchedule({timezone:event.target.value})}/></FormField>
     <fieldset className="action-day-options"><legend>{de?'Ausgeschlossene Tage':'Excluded days'}</legend>{days.map((day,index)=><label key={day}><input type="checkbox" checked={schedule.excluded_weekdays?.includes(day)||false} onChange={event=>changeSchedule({excluded_weekdays:event.target.checked?[...(schedule.excluded_weekdays||[]),day]:(schedule.excluded_weekdays||[]).filter(d=>d!==day)})}/>{labels[language][index]}</label>)}</fieldset>
     <fieldset className="action-weekday-times"><legend>{de?'Uhrzeit und Zeitfenster je Wochentag':'Preferred time and window per weekday'}</legend>{days.map((day,index)=>{const segment=schedule.segments?.find(s=>(s.weekdays||days).includes(day))||{};return <div key={day}><strong>{labels[language][index]}</strong>{[['preferred_time',de?'Bevorzugt':'Preferred'],['start',de?'Von':'From'],['end',de?'Bis':'To']].map(([field,label])=><label key={field}>{label}<input type="time" value={(field==='preferred_time'?segment.preferred_time:segment.window?.[field])||''} onChange={event=>updateTime(day,field,event.target.value)}/></label>)}</div>})}</fieldset>
    </FormSection>
    <FormSection legend={de?'Darstellung':'Appearance'}><FormField label={de?'Akzentfarbe':'Accent color'}><select value={value.accent_token||''} onChange={event=>setValue(current=>({...current,accent_token:event.target.value}))}>{value.accent_choices?.map(token=><option key={token} value={token}>{token||(de?'Standard':'Default')}</option>)}</select></FormField></FormSection>
   </details>
   {value.decision_templates?.map(template=><button key={template.id} type="button" disabled={busy} onClick={()=>newRound(template)}>{de?'Neue Abstimmungsrunde: ':'New voting round: '}{template.question}</button>)}
   {value.prediction&&<p>{de?'Beobachtungen':'Observations'}: {value.prediction.sample_count} · {de?'Sicherheit':'Confidence'}: {Math.round(value.prediction.confidence*100)}%</p>}
   {proposal&&<div role="status"><p>{de?'Neue bevorzugte Zeit vorschlagen':'Suggested preferred time'}: {proposal.proposed.weekday} {proposal.proposed.preferred_time}</p><button type="button" disabled={busy} onClick={()=>feedback('accept')}>{de?'Übernehmen':'Accept'}</button><button type="button" disabled={busy} onClick={()=>feedback('reject')}>{de?'Nein':'Reject'}</button></div>}
   {error&&<p role="alert">{error}</p>}<div className="action-sticky-submit"><button type="submit" disabled={busy}>{de?'Speichern':'Save'}</button></div>
  </FormShell>}{!value&&error&&<p role="alert">{error}</p>}
 </FamilySheet>;
}
