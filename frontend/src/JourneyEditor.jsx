import {useEffect,useRef,useState} from 'react';
import {useTranslation} from 'react-i18next';
import {api} from './api';
import {confirmAction} from './feedback';
import {Icon} from './icons';
import {ErrorSummary,FormActions,FormField,FormSection,FormShell,ProgressiveFieldGroup} from './form-primitives';
import {vehicleError} from './VehicleEditor';
import './vehicles-i18n';
import './vehicles.css';

function localDateTime(value){
 if(!value)return'';
 const date=new Date(value);
 const local=new Date(date.getTime()-date.getTimezoneOffset()*60000);
 return local.toISOString().slice(0,16);
}

function nowDefaults(){
 const end=new Date();
 const start=new Date(end.getTime()-60*60*1000);
 return {started_at:localDateTime(start),ended_at:localDateTime(end)};
}

export default function JourneyEditor({vehicle,journey=null,mode='review',onClose,onSaved}){
 const {t}=useTranslation();
 const dialog=useRef(null);const alive=useRef(true);
 const defaults=nowDefaults();
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[fields,setFields]=useState({}),[suggestions,setSuggestions]=useState({destinations:[],business_partners:[],purposes:[]});
 const [form,setForm]=useState(()=>({
  request_id:crypto.randomUUID(),
  started_at:defaults.started_at,
  ended_at:defaults.ended_at,
  start_odometer:vehicle?.odometer||'0',
  end_odometer:vehicle?.odometer||'0',
  kind:mode==='manual'?'private':journey?.kind||'unclassified',
  destination:journey?.destination||'',
  business_partner:journey?.business_partner||'',
  purpose:journey?.purpose||'',
  note:journey?.note||'',
  detour_reason:journey?.detour_reason||'',
  reason:'',
  ...(journey?{start_odometer:journey.start_odometer,end_odometer:journey.end_odometer||journey.start_odometer}:{}),
 }));
 const reasonRequired=mode!=='review'||Boolean(journey?.review_locked)||!journey?.needs_review;
 useEffect(()=>{
  alive.current=true;const previous=document.activeElement;dialog.current?.querySelector('select,input')?.focus();
  api(`/vehicles/${vehicle.id}/journey-suggestions/`).then(rows=>alive.current&&setSuggestions(rows)).catch(()=>{});
  return()=>{alive.current=false;previous?.focus()};
 },[vehicle.id]);
 function update(name,value){setForm(current=>({...current,[name]:value}))}
 async function save(event){
  event.preventDefault();if(busy)return;setBusy(true);setError('');setFields({});
  try{
   let path,body;
   if(mode==='manual'){
    path=`/vehicles/${vehicle.id}/journeys/manual/`;
    body={...form};
   }else if(mode==='correct'){
    path=`/vehicle-journeys/${journey.id}/correct/`;
    body={start_odometer:form.start_odometer,end_odometer:form.end_odometer,kind:form.kind,destination:form.destination,business_partner:form.business_partner,purpose:form.purpose,note:form.note,detour_reason:form.detour_reason,reason:form.reason};
   }else{
    path=`/vehicle-journeys/${journey.id}/classify/`;
    body={kind:form.kind,destination:form.destination,business_partner:form.business_partner,purpose:form.purpose,note:form.note,detour_reason:form.detour_reason,reason:form.reason};
   }
   const saved=await api(path,{method:'POST',body:JSON.stringify(body)});if(alive.current)await onSaved(saved);
  }catch(e){if(alive.current){setError(vehicleError(e,t));setFields(e.payload||{})}}
  finally{if(alive.current)setBusy(false)}
 }
 async function voidJourney(){
  if(!journey||!form.reason.trim()){setFields({reason:'correction_reason_required'});return}
  if(!await confirmAction({title:t('vehiclesUi.voidConfirm'),confirmLabel:t('vehiclesUi.voidJourney'),cancelLabel:t('vehiclesUi.cancel'),danger:true}))return;
  setBusy(true);setError('');
  try{const saved=await api(`/vehicle-journeys/${journey.id}/void/`,{method:'POST',body:JSON.stringify({reason:form.reason})});if(alive.current)await onSaved(saved)}catch(e){if(alive.current)setError(vehicleError(e,t))}finally{if(alive.current)setBusy(false)}
 }
 const fieldError=name=>fields[name]?vehicleError({message:Array.isArray(fields[name])?fields[name][0]:fields[name]},t):'';
 const title=mode==='manual'?t('vehiclesUi.manualJourney'):mode==='correct'?t('vehiclesUi.correctJourney'):t('vehiclesUi.reviewJourney');
 return <div className="sheet-backdrop" onMouseDown={event=>event.target===event.currentTarget&&!busy&&onClose()}>
  <section ref={dialog} className="quick-sheet vehicle-editor journey-editor" role="dialog" aria-modal="true" aria-labelledby="journey-editor-title">
   <div className="sheet-handle"/><div className="sheet-head"><h2 id="journey-editor-title">{title}</h2><button className="sheet-close" type="button" disabled={busy} onClick={onClose} aria-label={t('vehiclesUi.cancel')}><Icon name="close"/></button></div>
   <FormShell onSubmit={save}>
    {error&&<ErrorSummary title={error} errors={[{id:'journey-kind',message:error}]}/>} 
    {mode==='manual'&&<FormSection legend={t('vehiclesUi.journeyTimes')}>
      <FormField id="journey-started-at" required label={t('vehiclesUi.startedAt')} error={fieldError('started_at')}><input type="datetime-local" value={form.started_at} onChange={e=>update('started_at',e.target.value)}/></FormField>
      <FormField id="journey-ended-at" required label={t('vehiclesUi.endedAt')} error={fieldError('ended_at')}><input type="datetime-local" value={form.ended_at} onChange={e=>update('ended_at',e.target.value)}/></FormField>
    </FormSection>}
    {(mode==='manual'||mode==='correct')&&<FormSection legend={t('vehiclesUi.odometerSection')}>
      <FormField id="journey-start-km" required label={t('vehiclesUi.start_odometer')} error={fieldError('start_odometer')}><input type="number" min="0" step="0.1" value={form.start_odometer} onChange={e=>update('start_odometer',e.target.value)}/></FormField>
      <FormField id="journey-end-km" required label={t('vehiclesUi.end_odometer')} error={fieldError('end_odometer')}><input type="number" min={form.start_odometer||0} step="0.1" value={form.end_odometer} onChange={e=>update('end_odometer',e.target.value)}/></FormField>
    </FormSection>}
    <FormSection legend={t('vehiclesUi.classification')}>
      <FormField id="journey-kind" required label={t('vehiclesUi.kind')} error={fieldError('kind')}><select value={form.kind} onChange={e=>update('kind',e.target.value)}><option value="unclassified">{t('vehiclesUi.unclassified')}</option>{['private','business','commute'].map(key=><option key={key} value={key}>{t(`vehiclesUi.${key}`)}</option>)}</select></FormField>
      {form.kind==='business'&&<>
       <FormField id="journey-destination" required label={t('vehiclesUi.destination')} error={fieldError('destination')}>{props=><input {...props} list="journey-destinations" maxLength={240} value={form.destination} onChange={e=>update('destination',e.target.value)}/>}</FormField>
       <datalist id="journey-destinations">{suggestions.destinations.map(value=><option key={value} value={value}/>)}</datalist>
       <FormField id="journey-partner" required label={t('vehiclesUi.businessPartner')} error={fieldError('business_partner')}>{props=><input {...props} list="journey-partners" maxLength={240} value={form.business_partner} onChange={e=>update('business_partner',e.target.value)}/>}</FormField>
       <datalist id="journey-partners">{suggestions.business_partners.map(value=><option key={value} value={value}/>)}</datalist>
       <FormField id="journey-purpose" required label={t('vehiclesUi.businessPurpose')} error={fieldError('purpose')}>{props=><input {...props} list="journey-purposes" maxLength={240} value={form.purpose} onChange={e=>update('purpose',e.target.value)}/>}</FormField>
       <datalist id="journey-purposes">{suggestions.purposes.map(value=><option key={value} value={value}/>)}</datalist>
      </>}
    </FormSection>
    <ProgressiveFieldGroup label={t('vehiclesUi.details')}>
      {form.kind!=='business'&&<FormField label={t('vehiclesUi.purpose')}><input maxLength={240} value={form.purpose} onChange={e=>update('purpose',e.target.value)}/></FormField>}
      <FormField label={t('vehiclesUi.journeyNote')}><textarea maxLength={1000} value={form.note} onChange={e=>update('note',e.target.value)}/></FormField>
      {form.kind==='business'&&<FormField label={t('vehiclesUi.detourReason')}><textarea maxLength={500} value={form.detour_reason} onChange={e=>update('detour_reason',e.target.value)}/></FormField>}
    </ProgressiveFieldGroup>
    {(reasonRequired||mode==='manual')&&<FormField id="journey-reason" required label={t('vehiclesUi.correctionReason')} error={fieldError('reason')} description={t('vehiclesUi.correctionReasonHint')}><textarea maxLength={500} value={form.reason} onChange={e=>update('reason',e.target.value)}/></FormField>}
    {!reasonRequired&&mode==='review'&&<FormField id="journey-reason" label={t('vehiclesUi.correctionReason')} description={t('vehiclesUi.reasonOptional')}><textarea maxLength={500} value={form.reason} onChange={e=>update('reason',e.target.value)}/></FormField>}
    <FormActions><button className="primary" type="submit" disabled={busy||form.kind==='unclassified'}>{t(`vehiclesUi.${busy?'loading':'save'}`)}</button><button className="secondary" type="button" disabled={busy} onClick={onClose}>{t('vehiclesUi.cancel')}</button>{journey&&mode==='correct'&&!journey.voided_at&&<button className="ghost danger-text" type="button" disabled={busy||!form.reason.trim()} onClick={voidJourney}>{t('vehiclesUi.voidJourney')}</button>}</FormActions>
   </FormShell>
  </section>
 </div>;
}
