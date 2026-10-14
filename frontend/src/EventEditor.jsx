import {useEffect,useMemo,useRef,useState} from 'react';
import {useTranslation} from 'react-i18next';
import {api} from './api';
import {Icon} from './icons';
import {confirmAction,toast} from './feedback';
import {useDirtyForm} from './dirty-state';
import MemberAvatar from './MemberAvatar';
import EventRecurrenceEditor from './EventRecurrenceEditor';
import {eventParticipantIds,membershipCalendarColor,membershipDisplayName} from './calendar-members';
import {ChoiceField,ErrorSummary,FormActions,FormField,FormRow,FormSection,FormShell,ProgressiveFieldGroup} from './form-primitives';
import './event-editor.css';

const DEFAULT_DURATION=60;
const DURATION_PRESETS=[30,60,90,120];
const unwrap=value=>value?.results||value||[];
const localValue=value=>value?new Date(new Date(value).getTime()-new Date(value).getTimezoneOffset()*60000).toISOString().slice(0,16):'';
const iso=value=>value?new Date(value).toISOString():null;
const parseLocal=value=>value?new Date(value):null;
function durationBetween(start,end){
  const startDate=parseLocal(start);const endDate=parseLocal(end);
  if(!startDate||!endDate||Number.isNaN(startDate.getTime())||Number.isNaN(endDate.getTime())||endDate<=startDate)return DEFAULT_DURATION;
  return Math.max(5,Math.round((endDate-startDate)/60000));
}
function endFromDuration(start,minutes){
  const startDate=parseLocal(start);const duration=Number(minutes);
  if(!startDate||Number.isNaN(startDate.getTime())||!Number.isFinite(duration)||duration<=0)return '';
  return localValue(new Date(startDate.getTime()+duration*60000));
}
function freshEvent(currentMembershipId=''){
  const start=new Date();start.setMinutes(Math.ceil(start.getMinutes()/30)*30,0,0);
  const end=new Date(start.getTime()+DEFAULT_DURATION*60000);
  return{title:'',starts_at:localValue(start),ends_at:localValue(end),location:'',description:'',recurrence:'',payloadBase:{},participants:currentMembershipId?[String(currentMembershipId)]:[],is_family_event:false};
}
function editablePayload(event){
  const payload={...(event?.payload||{})};
  if(event?.recurrence_master_date_start!==undefined){if(event.recurrence_master_date_start)payload.date_start=event.recurrence_master_date_start;else delete payload.date_start}
  if(event?.recurrence_master_date_end_exclusive!==undefined){if(event.recurrence_master_date_end_exclusive)payload.date_end_exclusive=event.recurrence_master_date_end_exclusive;else delete payload.date_end_exclusive}
  return payload;
}
function eventForm(event,currentMembershipId=''){
  if(!event)return freshEvent(currentMembershipId);
  const payload=editablePayload(event);
  const startsAt=event.recurrence_master_starts_at||event.starts_at;
  const endsAt=event.recurrence_master_ends_at||event.ends_at;
  return{id:event.id,title:event.title||'',starts_at:localValue(startsAt),ends_at:localValue(endsAt),location:payload.location||'',description:payload.description||'',recurrence:payload.recurrence||'',payloadBase:payload,participants:eventParticipantIds(event),is_family_event:Boolean(event.is_family_event)};
}

export default function EventEditor({family,event=null,currentUserId=null,onClose,onSaved}){
  const {t}=useTranslation();
  const isNew=!event?.id;
  const ownMembership=family?.memberships?.find(member=>currentUserId!=null&&String(member.user)===String(currentUserId));
  const currentMembershipId=family?.current_membership_id?String(family.current_membership_id):(ownMembership?.id?String(ownMembership.id):'');
  const initial=useRef(eventForm(event,currentMembershipId));
  const [edit,setEdit]=useState(()=>initial.current);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const [timeMode,setTimeMode]=useState(isNew?'duration':'end');
  const [durationMinutes,setDurationMinutes]=useState(()=>isNew?DEFAULT_DURATION:durationBetween(initial.current.starts_at,initial.current.ends_at));
  const [memberQuery,setMemberQuery]=useState('');
  const [memberDetails,setMemberDetails]=useState([]);
  useDirtyForm(JSON.stringify(edit)!==JSON.stringify(initial.current));

  useEffect(()=>{
    let live=true;
    if(!family?.id)return()=>{live=false};
    api('/memberships/').then(rows=>{
      if(live)setMemberDetails(unwrap(rows).filter(member=>String(member.family)===String(family.id)));
    }).catch(()=>{});
    return()=>{live=false};
  },[family?.id]);

  const members=useMemo(()=>{
    const base=family?.memberships||[];
    if(!memberDetails.length)return base;
    const details=new Map(memberDetails.map(member=>[String(member.id),member]));
    const merged=base.map(member=>({...member,...details.get(String(member.id))}));
    for(const member of memberDetails)if(!merged.some(row=>String(row.id)===String(member.id)))merged.push(member);
    return merged;
  },[family?.memberships,memberDetails]);
  const normalizedQuery=memberQuery.trim().toLocaleLowerCase();
  const filteredMembers=useMemo(()=>members.filter(member=>{
    if(!normalizedQuery)return true;
    return String(membershipDisplayName(member)||member.username||member.id).toLocaleLowerCase().includes(normalizedQuery);
  }),[members,normalizedQuery]);
  const selectedSet=useMemo(()=>new Set(edit.participants.map(String)),[edit.participants]);

  function toggleParticipant(memberId){
    const id=String(memberId);
    setEdit(value=>({...value,participants:value.participants.includes(id)?value.participants.filter(item=>item!==id):[...value.participants,id]}));
  }
  function setParticipants(ids){setEdit(value=>({...value,participants:ids.map(String)}))}
  function changeStart(value){
    setEdit(current=>({...current,starts_at:value,ends_at:timeMode==='duration'?endFromDuration(value,durationMinutes):current.ends_at}));
  }
  function changeDuration(value){
    setDurationMinutes(value);
    const minutes=Number(value);
    setEdit(current=>({...current,ends_at:value!==''&&Number.isFinite(minutes)&&minutes>=5?endFromDuration(current.starts_at,minutes):''}));
  }
  function changeTimeMode(mode){
    if(mode==='duration'){
      const minutes=durationBetween(edit.starts_at,edit.ends_at);
      setDurationMinutes(minutes);
      setEdit(current=>({...current,ends_at:endFromDuration(current.starts_at,minutes)}));
    }
    setTimeMode(mode);
  }
  function validationError(){
    if(!edit.starts_at)return t('eventEditor.startRequired');
    if(!edit.ends_at)return t('eventEditor.endRequired');
    const start=parseLocal(edit.starts_at);const end=parseLocal(edit.ends_at);
    if(!start||!end||Number.isNaN(start.getTime())||Number.isNaN(end.getTime())||end<=start)return t('eventEditor.endAfterStart');
    return '';
  }
  async function save(e){
    e.preventDefault();
    const validation=validationError();
    if(validation){setError(validation);return}
    setBusy(true);setError('');
    try{
      const eventPayload={...(edit.payloadBase||{}),location:edit.location,description:edit.description,recurrence:edit.recurrence,provider:'FamilyOS'};
      const payload={family:family.id,type:'calendar.event',title:edit.title.trim(),starts_at:iso(edit.starts_at),ends_at:iso(edit.ends_at),actionable:false,participants:edit.participants,is_family_event:edit.is_family_event,payload:eventPayload};
      const saved=await api(isNew?'/events/':`/events/${event.id}/`,{method:isNew?'POST':'PATCH',body:JSON.stringify(payload)});
      toast(isNew?t('addEvent'):t('save'),{type:'success'});await onSaved(saved);
    }catch(err){setError(err.message);toast(err.message||t('saveFailed'),{type:'error'});setBusy(false)}
  }
  async function remove(){
    if(isNew)return;
    const ok=await confirmAction({title:t('deleteEvent'),message:`„${edit.title}“`,confirmLabel:t('deleteEvent'),danger:true});
    if(!ok)return;
    setBusy(true);
    try{await api(`/events/${event.id}/`,{method:'DELETE'});toast(t('deleteEvent'),{type:'success'});await onSaved(null,{deleted:true})}
    catch(err){setError(err.message);toast(err.message||t('saveFailed'),{type:'error'});setBusy(false)}
  }

  const errors=error?[{id:'event-start',label:t('eventEditor.when'),message:error}]:[];
  const selectedCount=edit.participants.length;
  return <div className="sheet-backdrop" onMouseDown={e=>{if(e.target===e.currentTarget&&!busy)onClose()}}>
    <section className="quick-sheet event-editor-sheet" role="dialog" aria-modal="true" aria-labelledby="event-editor-title">
      <div className="sheet-handle"/>
      <div className="sheet-head"><div><small>{family?.name}</small><h2 id="event-editor-title">{isNew?t('addEvent'):t('editEvent')}</h2></div><button type="button" className="sheet-close" onClick={onClose} disabled={busy} aria-label={t('dismiss')}><Icon name="close"/></button></div>
      <FormShell className="quick-form event-editor-form" onSubmit={save}>
        <ErrorSummary errors={errors}/>

        <FormSection legend={t('eventEditor.appointment')} className="event-editor-section event-editor-section--title">
          <FormField id="event-title" label={t('eventTitle')} required><input value={edit.title} onChange={e=>setEdit(v=>({...v,title:e.target.value}))} autoFocus placeholder={t('eventEditor.titlePlaceholder')}/></FormField>
        </FormSection>

        <FormSection legend={t('eventEditor.when')} description={t('eventEditor.whenHint')} className="event-editor-section">
          <ChoiceField className="event-editor-time-mode" legend={t('eventEditor.timeEntry')} name="event-time-mode" value={timeMode} onChange={changeTimeMode} options={[{value:'duration',label:t('eventEditor.startDuration'),description:t('eventEditor.startDurationHint')},{value:'end',label:t('eventEditor.startEnd'),description:t('eventEditor.startEndHint')}]} disabled={busy}/>
          <FormRow className="event-editor-time-grid">
            <FormField id="event-start" label={t('startsAt')} required><input type="datetime-local" value={edit.starts_at} onChange={e=>changeStart(e.target.value)} disabled={busy}/></FormField>
            {timeMode==='end'&&<FormField id="event-end" label={t('endsAt')} required><input type="datetime-local" value={edit.ends_at} onChange={e=>setEdit(v=>({...v,ends_at:e.target.value}))} disabled={busy}/></FormField>}
          </FormRow>
          {timeMode==='duration'&&<div className="event-editor-duration" aria-labelledby="event-duration-label">
            <div className="event-editor-duration-head"><strong id="event-duration-label">{t('eventEditor.duration')}</strong><span>{durationMinutes||'–'} {t('eventEditor.minutesShort')}</span></div>
            <div className="event-editor-duration-presets">
              {DURATION_PRESETS.map(minutes=><button key={minutes} type="button" className={Number(durationMinutes)===minutes?'is-active':''} aria-pressed={Number(durationMinutes)===minutes} onClick={()=>changeDuration(minutes)} disabled={busy}>{minutes<60?`${minutes} ${t('eventEditor.minutesShort')}`:minutes%60===0?`${minutes/60} ${minutes===60?t('eventEditor.hour'):t('eventEditor.hours')}`:`${minutes/60} ${t('eventEditor.hours')}`}</button>)}
            </div>
            <FormField id="event-duration-custom" label={t('eventEditor.customDuration')} description={t('eventEditor.customDurationHint')}>{fieldProps=><div className="event-editor-duration-custom"><input {...fieldProps} type="number" min="5" step="5" inputMode="numeric" value={durationMinutes} onChange={e=>changeDuration(e.target.value)} disabled={busy}/><span>{t('eventEditor.minutes')}</span></div>}</FormField>
            <p className="event-editor-time-summary"><Icon name="clock"/>{t('eventEditor.endsAtSummary',{time:edit.ends_at?new Date(edit.ends_at).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'}):'–'})}</p>
          </div>}
        </FormSection>

        <FormSection legend={t('eventEditor.who')} description={t('eventEditor.whoHint')} className="event-editor-section">
          {members.length>0&&<>
            <div className="event-editor-participants-head">
              <span className="event-editor-selection-count" aria-live="polite">{t('eventEditor.selectedCount',{count:selectedCount})}</span>
              <div className="event-editor-participant-actions" aria-label={t('eventEditor.quickSelection')}>
                {currentMembershipId&&<button type="button" className="secondary" onClick={()=>setParticipants([currentMembershipId])} disabled={busy}>{t('eventEditor.onlyMe')}</button>}
                <button type="button" className="secondary" onClick={()=>setParticipants(members.map(member=>member.id))} disabled={busy}>{t('eventEditor.everyone')}</button>
                <button type="button" className="secondary" onClick={()=>setParticipants([])} disabled={busy}>{t('eventEditor.noOne')}</button>
              </div>
            </div>
            {members.length>=7&&<FormField id="event-participant-search" label={t('eventEditor.searchParticipants')}><input type="search" value={memberQuery} onChange={e=>setMemberQuery(e.target.value)} placeholder={t('eventEditor.searchParticipantsPlaceholder')} disabled={busy}/></FormField>}
            <div className="event-editor-participant-grid">
              {filteredMembers.map(member=>{const id=String(member.id);const selected=selectedSet.has(id);const isCurrent=id===currentMembershipId;const name=membershipDisplayName(member)||member.username||member.id;return <label className={`event-editor-participant-card${selected?' is-selected':''}`} key={id}>
                <input className="event-editor-participant-input" type="checkbox" checked={selected} onChange={()=>toggleParticipant(id)} disabled={busy}/>
                <MemberAvatar person={member} color={membershipCalendarColor(member)} size={42} decorative/>
                <span className="event-editor-participant-copy"><strong>{name}</strong>{isCurrent&&<small>{t('eventEditor.you')}</small>}</span>
                <span className="event-editor-participant-check" aria-hidden="true">{selected&&<Icon name="check"/>}</span>
              </label>})}
            </div>
            {filteredMembers.length===0&&<p className="event-editor-empty">{t('eventEditor.noParticipantMatches')}</p>}
          </>}
          <label className={`event-editor-family-toggle${edit.is_family_event?' is-selected':''}`}>
            <input type="checkbox" checked={edit.is_family_event} onChange={e=>setEdit(v=>({...v,is_family_event:e.target.checked}))} disabled={busy}/>
            <span className="event-editor-family-icon" aria-hidden="true"><Icon name="members"/></span>
            <span><strong>{t('eventEditor.familyEvent')}</strong><small>{t('eventEditor.familyEventHint')}</small></span>
            <span className="event-editor-family-check" aria-hidden="true">{edit.is_family_event&&<Icon name="check"/>}</span>
          </label>
        </FormSection>

        <ProgressiveFieldGroup label={t('eventEditor.moreDetails')} summary={t('eventEditor.moreDetailsHint')} defaultOpen={!isNew} className="event-editor-more">
          <FormField id="event-location" label={t('location')}><input value={edit.location} onChange={e=>setEdit(v=>({...v,location:e.target.value}))} placeholder={t('eventEditor.locationPlaceholder')} disabled={busy}/></FormField>
          <FormField id="event-notes" label={t('notes')}><textarea value={edit.description} onChange={e=>setEdit(v=>({...v,description:e.target.value}))} disabled={busy}/></FormField>
          <EventRecurrenceEditor value={edit.recurrence} onChange={recurrence=>setEdit(v=>({...v,recurrence}))} disabled={busy} familyId={family?.id} anchor={edit.starts_at}/>
        </ProgressiveFieldGroup>

        <FormActions className="event-editor-actions"><button className="primary event-editor-save" disabled={busy||!edit.title.trim()}><Icon name="check"/>{busy?t('pleaseWait'):t('save')}</button>{!isNew&&<button type="button" className="ghost-danger destructive-wide" onClick={remove} disabled={busy}><Icon name="delete"/>{t('deleteEvent')}</button>}</FormActions>
      </FormShell>
    </section>
  </div>;
}
