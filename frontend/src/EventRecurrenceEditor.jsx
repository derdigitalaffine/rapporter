import {useTranslation} from 'react-i18next';
import {FormField,FormRow} from './form-primitives';

const DAYS=['MO','TU','WE','TH','FR','SA','SU'];
const DAY_LABELS={de:['Mo','Di','Mi','Do','Fr','Sa','So'],en:['Mon','Tue','Wed','Thu','Fri','Sat','Sun']};
const MONTH_LABELS={de:['Jan','Feb','Mär','Apr','Mai','Jun','Jul','Aug','Sep','Okt','Nov','Dez'],en:['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']};
const ORDINAL_LABELS={de:{1:'Erste',2:'Zweite',3:'Dritte',4:'Vierte',5:'Fünfte','-1':'Letzte'},en:{1:'First',2:'Second',3:'Third',4:'Fourth',5:'Fifth','-1':'Last'}};
const LEGACY=new Set(['weekly','monthly','yearly']);

export function recurrenceObject(value){
 if(!value)return null;
 if(typeof value==='string')return LEGACY.has(value)?{frequency:value,interval:1}:null;
 return value&&typeof value==='object'?value:null;
}

export default function EventRecurrenceEditor({value,onChange,disabled=false}){
 const {i18n}=useTranslation();const de=!i18n.language.startsWith('en');const language=de?'de':'en';const recurrence=recurrenceObject(value);const frequency=recurrence?.frequency||'none';const advanced=['monthly','quarterly','yearly'].includes(frequency);
 function change(changes){onChange({...recurrence,...changes})}
 function changeFrequency(next){if(next==='none'){onChange('');return}onChange({frequency:next,interval:1})}
 function toggleMonth(month,checked){const current=recurrence?.months||[];const next=checked?[...new Set([...current,month])].sort((a,b)=>a-b):current.filter(value=>value!==month);change({months:next.length?next:undefined})}
 return <div className="event-recurrence-editor">
  <FormRow>
   <FormField label={de?'Wiederholung':'Repeat'}><select value={frequency} disabled={disabled} onChange={event=>changeFrequency(event.target.value)}><option value="none">{de?'Keine':'None'}</option><option value="weekly">{de?'Wöchentlich':'Weekly'}</option><option value="monthly">{de?'Monatlich':'Monthly'}</option><option value="quarterly">{de?'Quartalsweise':'Quarterly'}</option><option value="yearly">{de?'Jährlich':'Yearly'}</option></select></FormField>
   {frequency!=='none'&&<FormField label={de?'Alle N Intervalle':'Every N intervals'}><input type="number" min="1" max="1200" required disabled={disabled} value={recurrence?.interval||1} onChange={event=>change({interval:Number(event.target.value)})}/></FormField>}
  </FormRow>
  {advanced&&<FormRow>
   <FormField label={frequency==='quarterly'?(de?'Wochentag im Quartal':'Weekday in quarter'):(de?'Wochentag im Zeitraum':'Weekday in period')}><select value={recurrence?.nth_weekdays?.[0]?.weekday||''} disabled={disabled} onChange={event=>change({nth_weekdays:event.target.value?[{weekday:event.target.value,ordinal:recurrence?.nth_weekdays?.[0]?.ordinal||1}]:undefined})}><option value="">{de?'Tag des Startdatums':'Start date day'}</option>{DAYS.map((day,index)=><option key={day} value={day}>{DAY_LABELS[language][index]}{day==='SA'?(de?' · Wochenende':' · weekend'):''}</option>)}</select></FormField>
   <FormField label={de?'Welche Position?':'Which position?'}><select value={recurrence?.nth_weekdays?.[0]?.ordinal||1} disabled={disabled||!recurrence?.nth_weekdays?.length} onChange={event=>change({nth_weekdays:[{...recurrence.nth_weekdays[0],ordinal:Number(event.target.value)}]})}>{[1,2,3,4,5,-1].map(ordinal=><option key={ordinal} value={ordinal}>{ORDINAL_LABELS[language][ordinal]}</option>)}</select></FormField>
  </FormRow>}
  {frequency==='weekly'&&<fieldset className="event-recurrence-days" disabled={disabled}><legend>{de?'Wochentage (leer = Starttag)':'Weekdays (empty = start day)'}</legend>{DAYS.map((day,index)=><label key={day}><input type="checkbox" checked={recurrence?.weekdays?.includes(day)||false} onChange={event=>{const current=recurrence?.weekdays||[];const next=event.target.checked?[...new Set([...current,day])]:current.filter(value=>value!==day);change({weekdays:next.length?next:undefined})}}/>{DAY_LABELS[language][index]}</label>)}</fieldset>}
  {frequency==='yearly'&&<fieldset className="event-recurrence-months" disabled={disabled}><legend>{de?'Monate (leer = Startmonat)':'Months (empty = start month)'}</legend>{MONTH_LABELS[language].map((label,index)=>{const month=index+1;return <label key={month}><input type="checkbox" checked={recurrence?.months?.includes(month)||false} onChange={event=>toggleMonth(month,event.target.checked)}/>{label}</label>})}</fieldset>}
  {frequency==='quarterly'&&recurrence?.nth_weekdays?.[0]?.weekday==='SA'&&<p className="muted">{de?'Das Wochenende beginnt am ausgewählten Samstag; die Termin-Dauer kann bis Sonntag reichen.':'The weekend starts on the selected Saturday; the event duration may extend into Sunday.'}</p>}
 </div>;
}
