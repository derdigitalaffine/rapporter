import {useEffect,useRef,useState} from 'react';
import {useTranslation} from 'react-i18next';
import {api} from './api';
import {Icon} from './icons';
import {confirmAction,toast} from './feedback';
import FamilySheet from './ui/FamilySheet';
import BabyPreventivePanel from './BabyPreventivePanel';
import {ChoiceField,FormActions,FormField,ProgressiveFieldGroup} from './form-primitives';
import {localDateTime} from './children-context';
import {formatCivilDate,formatDateTime} from './locale';
import {featureHref} from './navigation';
import './children-i18n';

export function healthDateLabel(row,language,timeZone='UTC'){
 if(row.planned_at)return formatDateTime(language,row.planned_at,{timeZone,day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit'});
 if(row.occurred_on)return formatCivilDate(language,row.occurred_on);
 if(row.window_start&&row.window_end)return `${formatCivilDate(language,row.window_start)} – ${formatCivilDate(language,row.window_end)}`;
 return '';
}

export default function ChildHealthPanel({baby,timeZone='UTC'}){
 const {t,i18n}=useTranslation(),c=key=>t(`childrenUi.${key}`);
 const [data,setData]=useState(null),[error,setError]=useState(''),[loading,setLoading]=useState(true);
 const [kind,setKind]=useState('exam'),[view,setView]=useState('current'),[editor,setEditor]=useState(null);
 const [bulk,setBulk]=useState(false),[reminding,setReminding]=useState(false),[reminderOpen,setReminderOpen]=useState(false),[selected,setSelected]=useState([]),[busy,setBusy]=useState(false);
 const revision=useRef(0);
 async function load(){const current=++revision.current;setLoading(true);setError('');try{const next=await api(`/baby/profiles/${baby.id}/health/?language=${i18n.language.startsWith('de')?'de':'en'}`);if(current===revision.current)setData(next)}catch(err){if(current===revision.current){if([401,403,404].includes(err.status))setData(null);setError(err.message||c('accessError'))}}finally{if(current===revision.current)setLoading(false)}}
 function resetSelection(){setBulk(false);setReminding(false);setSelected([])}
 useEffect(()=>{setData(null);setView('current');setKind('exam');resetSelection();setEditor(null);setReminderOpen(false);load();return()=>{revision.current++}},[baby.id,i18n.language]);
 async function save(value){await api(`/baby/profiles/${baby.id}/health/`,{method:'POST',body:JSON.stringify(value)});setEditor(null);toast(c('saved'),{type:'success'});await load()}
 async function done(row){setBusy(true);setError('');try{await save({...row,state:'done',expected_version:row.version,reference_checksum:row.reference?.checksum||''})}catch(err){setError(err.message||c('error'))}finally{setBusy(false)}}
 async function saveHistory(){setBusy(true);setError('');try{await save({entries:data.items.filter(row=>selected.includes(row.key)).map(row=>({...row,state:'done',expected_version:row.version,reference_checksum:row.reference?.checksum||''}))});resetSelection()}catch(err){setError(err.message||c('error'))}finally{setBusy(false)}}
 async function saveReminders(remindAt){
  await api(`/baby/profiles/${baby.id}/health/reminders/`,{method:'POST',body:JSON.stringify({remind_at:remindAt,entries:data.items.filter(row=>selected.includes(row.key)).map(row=>({key:row.key,expected_version:row.version,reference_checksum:row.reference?.checksum||''}))})});
  setReminderOpen(false);resetSelection();toast(c('reminderCreated'),{type:'success'});window.dispatchEvent(new CustomEvent('familyos:actions-changed',{detail:{family:baby.family}}));await load();
 }
 const rows=(data?.items||[]).filter(row=>row.kind===kind&&(view==='history'?(row.state==='done'||row.historical&&row.state!=='planned'):(row.state!=='done'&&(!row.historical||row.state==='planned'))));
 const selectable=row=>row.kind==='vaccination'&&!row.historical&&!['done','planned'].includes(row.state)&&!row.reminder;
 const select=(key,checked)=>setSelected(value=>checked?[...value,key]:value.filter(item=>item!==key));
 const source=data?.vaccination_reference;
 return <section className="child-health" aria-labelledby="child-health-title">
  <div className="child-section-head"><h2 id="child-health-title">{c('health')}</h2>{kind==='vaccination'&&<button type="button" className="secondary" disabled={busy||loading} onClick={()=>setEditor({key:`manual:${crypto.randomUUID()}`,kind:'vaccination',title:'',state:'done',version:0})}><Icon name="plus"/>{c('vaccination')}</button>}</div>
  <div className="child-kind-switch" role="group" aria-label={c('health')}>{[['exam','checkups'],['vaccination','vaccines']].map(([value,label])=><button type="button" key={value} aria-pressed={kind===value} disabled={busy||reminderOpen} onClick={()=>{setKind(value);resetSelection()}}><Icon name={value==='exam'?'calendar':'heart'}/>{c(label)}</button>)}</div>
  {kind==='vaccination'&&data&&<aside className="child-reference">
   <div><Icon name="info"/><strong>{c('sourceVersion')}</strong></div>
   <p>{source?<><strong>{source.title} · {source.version}</strong>{source.effective_from&&<span>{formatCivilDate(i18n.language,source.effective_from)}</span>}</>:c('noReferenceVersion')}</p>
   <a href="https://www.rki.de/impfempfehlungen" target="_blank" rel="noreferrer">{c('officialStiko')}<Icon name="link" size={14}/></a>
   <small>{c('referenceNotice')}</small>
  </aside>}
  <div className="child-view-switch" role="group" aria-label={c('record')}>{['current','history'].map(value=><button type="button" key={value} disabled={busy||reminderOpen} aria-pressed={view===value} onClick={()=>{setView(value);resetSelection()}}>{c(value)}</button>)}</div>
  {loading&&!data&&<p role="status">{c('loading')}</p>}
  {error&&<div className="integration-notice" role="alert"><span>{error}</span><button type="button" className="secondary" onClick={load}>{c('reload')}</button></div>}
  {data&&view==='history'&&rows.length>0&&<div className="child-history-actions"><button className="secondary" type="button" disabled={busy} onClick={()=>{setBulk(value=>!value);setSelected([])}}><Icon name="check"/>{bulk?c('cancel'):c('backfill')}</button>{bulk&&<button type="button" className="primary" disabled={busy||!selected.length} onClick={saveHistory}>{c('backfillSave')} ({selected.length})</button>}</div>}
  {data&&kind==='vaccination'&&view==='current'&&rows.some(selectable)&&<div className="child-history-actions"><button type="button" className="secondary" disabled={busy} aria-pressed={reminding} onClick={()=>{setReminding(value=>!value);setSelected([])}}><Icon name="warning"/>{reminding?c('cancel'):c('reminders')}</button>{reminding&&<button type="button" className="primary" disabled={!selected.length} onClick={()=>setReminderOpen(true)}><Icon name="tasks"/>{c('createReminders')} ({selected.length})</button>}</div>}
  {bulk&&<h3>{c('selectHistory')}</h3>}
  {reminding&&<h3>{c('selectVaccines')}</h3>}
  <div className="child-health-list">{rows.map(row=><article className="child-health-row" key={row.key}>
   {(bulk||reminding)&&<label className="child-history-select"><input type="checkbox" aria-label={`${c(bulk?'done':'selectReminders')}: ${row.title}${row.dose?` · ${c('dose')} ${row.dose}`:''}`} checked={selected.includes(row.key)} disabled={busy||reminding&&!selectable(row)} onChange={event=>select(row.key,event.target.checked)}/></label>}
   <div className="child-record-main"><button type="button" className="child-record-open" disabled={busy} onClick={()=>setEditor(row)}><Icon name={row.kind==='exam'?'calendar':'heart'}/><span><strong>{row.title}{row.dose?` · ${c('dose')} ${row.dose}`:''}</strong><small>{healthDateLabel(row,i18n.language,timeZone)||c('record')}</small></span><span className={`child-record-state state-${row.state}`}>{c(row.state)}</span><Icon name="next" size={16}/></button>
   {row.reminder&&<a className="child-reminder-link" href={featureHref('todo',{task:row.reminder.task})}><Icon name="tasks" size={14}/>{c(row.reminder.completed?'reminderDone':'reminderTask')}{row.reminder.due_at?` · ${healthDateLabel({planned_at:row.reminder.due_at},i18n.language,timeZone)}`:''}</a>}</div>
   {!bulk&&!reminding&&row.state!=='done'&&<button type="button" className="ghost icon-button" title={c('markDone')} aria-label={`${c('markDone')}: ${row.title}`} disabled={busy} onClick={()=>done(row)}><Icon name="check"/></button>}
  </article>)}</div>
  {data&&!loading&&!error&&!rows.length&&<p className="child-empty">{c(view==='history'?'noHistory':'noCurrent')}</p>}
  {data&&kind==='exam'&&<ProgressiveFieldGroup label={t('babyUi.questionForAppointment')}><BabyPreventivePanel baby={baby} t={t} language={i18n.language.startsWith('de')?'de':'en'} timeZone={timeZone} allowPlanning={false}/></ProgressiveFieldGroup>}
  {editor&&<HealthEditor key={`${baby.id}:${editor.key}`} row={editor} c={c} onSave={save} onReload={load} onClose={()=>setEditor(null)}/>}
  {reminderOpen&&<VaccinationReminderEditor c={c} count={selected.length} onSave={saveReminders} onClose={()=>setReminderOpen(false)}/>}
 </section>;
}

export function VaccinationReminderEditor({c,count,onSave,onClose}){
 const [when,setWhen]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState('');
 async function close(){if(busy)return;if(when&&!await confirmAction({title:c('close'),message:c('unsaved'),confirmLabel:c('discard'),cancelLabel:c('keep')}))return;onClose()}
 async function submit(event){event.preventDefault();setBusy(true);setError('');try{await onSave(new Date(when).toISOString())}catch(err){setError(err.message||c('error'))}finally{setBusy(false)}}
 return <FamilySheet labelledBy="vaccination-reminder-title" busy={busy} onClose={close}>
  <div className="sheet-head"><h2 id="vaccination-reminder-title">{c('reminders')}</h2><button type="button" className="sheet-close" disabled={busy} aria-label={c('close')} onClick={close}><Icon name="close"/></button></div>
  <form className="child-record-form" onSubmit={submit}>
   <p>{c('reminderCount')}: <strong>{count}</strong></p><p className="child-muted">{c('reminderPrivacy')}</p>
   <FormField label={c('remindAt')} required><input type="datetime-local" value={when} disabled={busy} onChange={event=>setWhen(event.target.value)}/></FormField>
   {error&&<div className="integration-notice" role="alert">{error}</div>}
   <FormActions><button type="button" className="secondary" disabled={busy} onClick={close}>{c('cancel')}</button><button className="primary" disabled={busy||!when}><Icon name="tasks"/>{c('createReminders')}</button></FormActions>
  </form>
 </FamilySheet>;
}

export function HealthEditor({row,c,onSave,onClose,onReload}){
 const initial={title:row.title||'',state:row.state||'unknown',occurred_on:row.occurred_on||'',planned_at:localDateTime(row.planned_at),practice:row.practice||'',note:row.note||'',batch:row.batch||''};
 const [form,setForm]=useState(initial),[busy,setBusy]=useState(false),[error,setError]=useState(''),[conflict,setConflict]=useState(false);
 const set=(key,value)=>setForm(current=>({...current,[key]:value}));
 async function close(){if(busy)return;if(JSON.stringify(initial)!==JSON.stringify(form)&&!await confirmAction({title:c('close'),message:c('unsaved'),confirmLabel:c('discard'),cancelLabel:c('keep')}))return;onClose()}
 async function submit(event){event.preventDefault();setBusy(true);setError('');setConflict(false);try{await onSave({...form,key:row.key,expected_version:row.version,event_starts_at:row.event_starts_at||null,reference_checksum:row.reference?.checksum||'',occurred_on:form.occurred_on||null,planned_at:form.planned_at?new Date(form.planned_at).toISOString():null})}catch(err){setError(err.message||c('error'));setConflict(err.status===409)}finally{setBusy(false)}}
 return <FamilySheet labelledBy="child-health-editor-title" busy={busy} onClose={close}>
  <div className="sheet-head"><h2 id="child-health-editor-title">{row.title||c('vaccination')}</h2><button type="button" className="sheet-close" disabled={busy} aria-label={c('close')} onClick={close}><Icon name="close"/></button></div>
  <form onSubmit={submit} className="child-record-form">
   <fieldset disabled={busy} className="child-form-fields"><legend className="form-sr-only">{c('record')}</legend>
    {row.key.startsWith('manual:')&&<FormField label={c('name')} required><input maxLength={160} value={form.title} onChange={event=>set('title',event.target.value)}/></FormField>}
    <ChoiceField legend={c('record')} value={form.state} disabled={busy} options={['unknown','planned','done','later'].map(value=>({value,label:c(value)}))} onChange={value=>set('state',value)}/>
    {form.state==='done'&&<FormField label={c('date')}><input type="date" value={form.occurred_on} onChange={event=>set('occurred_on',event.target.value)}/></FormField>}
    {form.state==='planned'&&<FormField label={c('appointment')} required><input type="datetime-local" value={form.planned_at} onChange={event=>set('planned_at',event.target.value)}/></FormField>}
    <ProgressiveFieldGroup label={c('details')} defaultOpen={Boolean(row.note||row.practice||row.batch)}>
     <FormField label={c('practice')}><input maxLength={160} value={form.practice} onChange={event=>set('practice',event.target.value)}/></FormField>
     {row.kind==='vaccination'&&<FormField label={c('batch')}><input maxLength={80} value={form.batch} onChange={event=>set('batch',event.target.value)}/></FormField>}
     <FormField label={c('note')}><textarea maxLength={4000} value={form.note} onChange={event=>set('note',event.target.value)}/></FormField>
    </ProgressiveFieldGroup>
    {row.reference?.source_version&&<p className="child-muted">{c('healthSource')}: {row.reference.source_title||row.reference.source_key} · {row.reference.source_version}</p>}
   </fieldset>
   {error&&<div className="integration-notice" role="alert">{error}{conflict&&onReload&&<button className="secondary" type="button" disabled={busy} onClick={async()=>{if(await confirmAction({title:c('reload'),message:c('unsaved'),confirmLabel:c('discard'),cancelLabel:c('keep')})){onClose();await onReload()}}}>{c('reload')}</button>}</div>}
   <FormActions><button type="button" className="secondary" disabled={busy} onClick={close}>{c('cancel')}</button><button className="primary" disabled={busy}><Icon name="check"/>{c('save')}</button></FormActions>
  </form>
 </FamilySheet>;
}
