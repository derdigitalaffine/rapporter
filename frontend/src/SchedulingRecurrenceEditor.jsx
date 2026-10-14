import {useEffect,useMemo,useState} from 'react';
import {useTranslation} from 'react-i18next';
import {api} from './api';
import {FormField,FormRow} from './form-primitives';
import './scheduling-recurrence.css';

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

function anchorDate(value){
 const raw=String(value||'').trim();
 return /^\d{4}-\d{2}-\d{2}/.test(raw)?raw.slice(0,10):new Date().toISOString().slice(0,10);
}

function recurrenceRule(value,anchor){
 return {version:'scheduling-rule-v1',time_mode:'wall_clock',anchor_date:anchorDate(anchor),recurrence:value};
}

function presetOptions(de){
 return [
  {key:'daily',label:de?'Täglich':'Daily',value:{frequency:'daily',interval:1}},
  {key:'weekly',label:de?'Wöchentlich':'Weekly',value:{frequency:'weekly',interval:1}},
  {key:'monthly',label:de?'Monatlich':'Monthly',value:{frequency:'monthly',interval:1}},
  {key:'quarterly-first-monday',label:de?'1. Montag · Quartal':'1st Monday · quarter',value:{frequency:'quarterly',interval:1,nth_weekdays:[{weekday:'MO',ordinal:1}]}},
  {key:'november-last-thursday',label:de?'Letzter Do · November':'Last Thu · November',value:{frequency:'yearly',interval:1,months:[11],nth_weekdays:[{weekday:'TH',ordinal:-1}]}},
  {key:'quarterly-first-weekend',label:de?'1. Wochenende · Quartal':'1st weekend · quarter',value:{frequency:'quarterly',interval:1,nth_weekdays:[{weekday:'SA',ordinal:1}]}}
 ];
}

export default function SchedulingRecurrenceEditor({
 value,
 onChange,
 disabled=false,
 familyId,
 anchor,
 allowOnce=false,
 allowNone=true,
 showNaturalLanguage=true,
 onParsedRule,
 className='',
}){
 const {i18n}=useTranslation();
 const de=!i18n.language.startsWith('en');
 const language=de?'de':'en';
 const recurrence=recurrenceObject(value);
 const frequency=recurrence?.frequency||'none';
 const advanced=['monthly','quarterly','yearly'].includes(frequency);
 const [phrase,setPhrase]=useState('');
 const [preview,setPreview]=useState(null);
 const [previewError,setPreviewError]=useState('');
 const [previewBusy,setPreviewBusy]=useState(false);
 const presets=useMemo(()=>presetOptions(de),[de]);
 const dateFormatter=useMemo(()=>new Intl.DateTimeFormat(de?'de-DE':'en-GB',{weekday:'short',day:'2-digit',month:'short',year:'numeric'}),[de]);

 function setRecurrence(next){onChange?.(next)}
 function change(changes){setRecurrence({...recurrence,...changes})}
 function changeFrequency(next){
  if(next==='none'){setRecurrence('');return}
  if(next==='once'){setRecurrence({frequency:'once',date:anchorDate(anchor)});return}
  setRecurrence({frequency:next,interval:1});
 }
 function toggleMonth(month,checked){
  const current=recurrence?.months||[];
  const next=checked?[...new Set([...current,month])].sort((a,b)=>a-b):current.filter(item=>item!==month);
  change({months:next.length?next:undefined});
 }
 function toggleWeekday(day,checked){
  const current=recurrence?.weekdays||[];
  const next=checked?[...new Set([...current,day])]:current.filter(item=>item!==day);
  change({weekdays:next.length?next:undefined});
 }

 useEffect(()=>{
  if(!familyId||!recurrence){setPreview(null);setPreviewError('');return undefined}
  let active=true;
  const timer=setTimeout(async()=>{
   setPreviewBusy(true);setPreviewError('');
   try{
    const data=await api(`/scheduling/preview/?family=${encodeURIComponent(familyId)}`,{method:'POST',body:JSON.stringify({rule:recurrenceRule(recurrence,anchor),language,limit:5})});
    if(active)setPreview(data);
   }catch(error){if(active){setPreview(null);setPreviewError(error.message)}}finally{if(active)setPreviewBusy(false)}
  },180);
  return()=>{active=false;clearTimeout(timer)};
 },[familyId,anchor,language,JSON.stringify(recurrence)]);

 async function parsePhrase(){
  const text=phrase.trim();
  if(!text||!familyId)return;
  setPreviewBusy(true);setPreviewError('');
  try{
   const data=await api(`/scheduling/preview/?family=${encodeURIComponent(familyId)}`,{method:'POST',body:JSON.stringify({text,anchor_date:anchorDate(anchor),language,limit:5})});
   setPreview(data);
   setRecurrence(data.rule.recurrence);
   onParsedRule?.(data.rule);
  }catch(error){setPreviewError(error.message)}finally{setPreviewBusy(false)}
 }

 return <div className={`scheduling-recurrence-editor ${className}`.trim()}>
  <div className="scheduling-recurrence-presets" aria-label={de?'Schnelle Wiederholungen':'Quick recurrence presets'}>
   {presets.map(preset=><button type="button" key={preset.key} disabled={disabled} onClick={()=>setRecurrence(preset.value)}>{preset.label}</button>)}
  </div>

  {showNaturalLanguage&&<div className="scheduling-recurrence-phrase">
   <FormField label={de?'In eigenen Worten':'In your own words'} description={de?'Zum Beispiel: „immer am ersten Montag im Quartal“':'For example: “every first Monday of the quarter”'}>
    {fieldProps=><div className="scheduling-recurrence-phrase-input"><input {...fieldProps} value={phrase} disabled={disabled} onChange={event=>setPhrase(event.target.value)} onKeyDown={event=>{if(event.key==='Enter'){event.preventDefault();parsePhrase()}}} placeholder={de?'Wiederholung beschreiben …':'Describe recurrence …'}/><button type="button" disabled={disabled||previewBusy||!phrase.trim()||!familyId} onClick={parsePhrase}>{de?'Erkennen':'Interpret'}</button></div>}
   </FormField>
  </div>}

  <FormRow>
   <FormField label={de?'Wiederholung':'Repeat'}><select value={frequency} disabled={disabled} onChange={event=>changeFrequency(event.target.value)}>{allowNone&&<option value="none">{de?'Keine':'None'}</option>}{allowOnce&&<option value="once">{de?'Einmalig':'Once'}</option>}<option value="daily">{de?'Täglich':'Daily'}</option><option value="weekly">{de?'Wöchentlich':'Weekly'}</option><option value="monthly">{de?'Monatlich':'Monthly'}</option><option value="quarterly">{de?'Quartalsweise':'Quarterly'}</option><option value="yearly">{de?'Jährlich':'Yearly'}</option></select></FormField>
   {frequency!=='none'&&frequency!=='once'&&<FormField label={de?'Alle N Intervalle':'Every N intervals'}><input type="number" min="1" max="1200" required disabled={disabled} value={recurrence?.interval||1} onChange={event=>change({interval:Number(event.target.value)})}/></FormField>}
  </FormRow>

  {frequency==='once'&&<FormField label={de?'Datum':'Date'}><input type="date" required disabled={disabled} value={recurrence?.date||anchorDate(anchor)} onChange={event=>change({date:event.target.value})}/></FormField>}

  {advanced&&<FormRow>
   <FormField label={frequency==='quarterly'?(de?'Wochentag im Quartal':'Weekday in quarter'):(de?'Wochentag im Zeitraum':'Weekday in period')}><select value={recurrence?.nth_weekdays?.[0]?.weekday||''} disabled={disabled} onChange={event=>change({nth_weekdays:event.target.value?[{weekday:event.target.value,ordinal:recurrence?.nth_weekdays?.[0]?.ordinal||1}]:undefined})}><option value="">{de?'Tag des Ankerdatums':'Anchor date day'}</option>{DAYS.map((day,index)=><option key={day} value={day}>{DAY_LABELS[language][index]}{day==='SA'?(de?' · Wochenende':' · weekend'):''}</option>)}</select></FormField>
   <FormField label={de?'Welche Position?':'Which position?'}><select value={recurrence?.nth_weekdays?.[0]?.ordinal||1} disabled={disabled||!recurrence?.nth_weekdays?.length} onChange={event=>change({nth_weekdays:[{...recurrence.nth_weekdays[0],ordinal:Number(event.target.value)}]})}>{[1,2,3,4,5,-1].map(ordinal=><option key={ordinal} value={ordinal}>{ORDINAL_LABELS[language][ordinal]}</option>)}</select></FormField>
  </FormRow>}

  {frequency==='weekly'&&<fieldset className="scheduling-recurrence-options" disabled={disabled}><legend>{de?'Wochentage (leer = Ankertag)':'Weekdays (empty = anchor day)'}</legend>{DAYS.map((day,index)=><label key={day}><input type="checkbox" checked={recurrence?.weekdays?.includes(day)||false} onChange={event=>toggleWeekday(day,event.target.checked)}/>{DAY_LABELS[language][index]}</label>)}</fieldset>}
  {frequency==='yearly'&&<fieldset className="scheduling-recurrence-options scheduling-recurrence-months" disabled={disabled}><legend>{de?'Monate (leer = Ankermonat)':'Months (empty = anchor month)'}</legend>{MONTH_LABELS[language].map((label,index)=>{const month=index+1;return <label key={month}><input type="checkbox" checked={recurrence?.months?.includes(month)||false} onChange={event=>toggleMonth(month,event.target.checked)}/>{label}</label>})}</fieldset>}
  {frequency==='quarterly'&&recurrence?.nth_weekdays?.[0]?.weekday==='SA'&&<p className="muted">{de?'Das Wochenende beginnt am ausgewählten Samstag.':'The weekend starts on the selected Saturday.'}</p>}

  {recurrence&&<section className="scheduling-recurrence-preview" aria-live="polite" aria-busy={previewBusy}>
   <div className="scheduling-recurrence-preview-head"><strong>{de?'Vorschau':'Preview'}</strong>{previewBusy&&<span>{de?'Wird berechnet …':'Calculating …'}</span>}</div>
   {preview?.summary&&<p className="scheduling-recurrence-summary">{preview.summary}</p>}
   {preview?.occurrences?.length>0&&<ol>{preview.occurrences.map(item=><li key={item}>{dateFormatter.format(new Date(`${item}T12:00:00`))}</li>)}</ol>}
   {previewError&&<p className="scheduling-recurrence-error" role="status">{previewError}</p>}
  </section>}
 </div>;
}
