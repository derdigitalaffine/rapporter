import {useEffect,useState} from 'react';
import {api} from './api';
import {Icon} from './icons';
import {FormField} from './form-primitives';
import SchedulingRecurrenceEditor from './SchedulingRecurrenceEditor';

export function ExistingActionSuggestions({familyId,title,enabled=true,de=true}){
 const [rows,setRows]=useState([]);
 useEffect(()=>{
  setRows([]);
  if(!enabled||!familyId||title.trim().length<3)return;
  let current=true;
  const timer=setTimeout(()=>api(`/actions/capture/?family=${encodeURIComponent(familyId)}&q=${encodeURIComponent(title.trim())}`).then(value=>{if(current)setRows((value.suggestions||[]).slice(0,3))}).catch(()=>{}),250);
  return()=>{current=false;clearTimeout(timer)};
 },[familyId,title,enabled]);
 if(!rows.length)return null;
 return <div className="task-existing-actions"><span>{de?'Bereits vorhanden':'Already exists'}</span>{rows.map(item=><a href={item.deep_link} key={item.id}><Icon name={item.icon||'tasks'} size={16}/><span>{item.title}</span><Icon name="next" size={14}/></a>)}</div>;
}

export function TaskDatePresets({onChange,de=true}){
 function choose(offset){
  const day=new Date();day.setDate(day.getDate()+offset);day.setHours(18,0,0,0);
  const pad=n=>String(n).padStart(2,'0');
  onChange(`${day.getFullYear()}-${pad(day.getMonth()+1)}-${pad(day.getDate())}T18:00`);
 }
 return <div className="task-date-presets" role="group" aria-label={de?'Zeitpunkt wählen':'Choose when'}>{[[0,de?'Heute':'Today'],[1,de?'Morgen':'Tomorrow'],[7,de?'In einer Woche':'In a week']].map(([offset,label])=><button type="button" key={offset} onClick={()=>choose(offset)}><Icon name="calendar" size={14}/>{label} · 18:00</button>)}<button type="button" onClick={()=>onChange('')}><Icon name="close" size={14}/>{de?'Ohne Termin':'No due date'}</button></div>;
}

export default function TaskPlanningFields({value={},onChange,familyId,anchor,disabled,de=true}){
 const schedule=value||{};
 return <div className="task-planning-fields">
  <SchedulingRecurrenceEditor familyId={familyId} anchor={anchor} value={schedule.recurrence||''} disabled={disabled} allowOnce onChange={recurrence=>onChange(recurrence?{...schedule,mode:schedule.mode||'static',anchor_date:anchor?.slice(0,10)||schedule.anchor_date,recurrence}:{})} onParsedRule={rule=>onChange({...schedule,mode:schedule.mode||'static',recurrence:rule.recurrence,timezone:rule.timezone,anchor_date:rule.anchor_date,segments:rule.segments||[],excluded_weekdays:rule.excluded_weekdays||[],exceptions:rule.exceptions||[]})}/>
  {schedule.recurrence&&<FormField label={de?'Planungsmodus':'Scheduling mode'}><select value={schedule.mode||'static'} onChange={event=>onChange({...schedule,mode:event.target.value})}><option value="static">{de?'Feste Regel':'Fixed rule'}</option><option value="adaptive">{de?'Feste Regel mit Lernvorschlägen':'Fixed rule with learning suggestions'}</option></select></FormField>}
 </div>;
}
