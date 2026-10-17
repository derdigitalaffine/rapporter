import {useEffect,useMemo,useState} from 'react';
import {useTranslation} from 'react-i18next';
import {api} from './api';
import {FormField,FormRow} from './form-primitives';
import './scheduling-recurrence.css';

const DAYS=['MO','TU','WE','TH','FR','SA','SU'];
const WEEKDAYS=['MO','TU','WE','TH','FR'];
const DAY_LABELS={de:['Mo','Di','Mi','Do','Fr','Sa','So'],en:['Mon','Tue','Wed','Thu','Fri','Sat','Sun']};
const MONTH_LABELS={de:['Jan','Feb','Mär','Apr','Mai','Jun','Jul','Aug','Sep','Okt','Nov','Dez'],en:['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']};
const ORDINAL_LABELS={de:{1:'Erste',2:'Zweite',3:'Dritte',4:'Vierte',5:'Fünfte','-1':'Letzte'},en:{1:'First',2:'Second',3:'Third',4:'Fourth',5:'Fifth','-1':'Last'}};
const LEGACY=new Set(['weekly','monthly','yearly']);
const INTERVAL_UNITS=['hourly','daily','business_daily','weekly','monthly','quarterly','yearly'];
const QUOTA_PERIODS=['daily','weekly','monthly'];

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

function recurrenceKind(recurrence){
 if(!recurrence)return 'none';
 if(recurrence.times_per_period)return 'quota';
 if(recurrence.business_days&&Number(recurrence.interval||1)===1)return 'business_daily';
 if(recurrence.business_days||recurrence.frequency==='hourly'||Number(recurrence.interval||1)>1)return 'interval';
 return recurrence.frequency||'none';
}

function presetOptions(de,allowActionCadence){
 const base=[
  {key:'daily',label:de?'Täglich':'Daily',value:{frequency:'daily',interval:1}},
  {key:'weekly',label:de?'Wöchentlich':'Weekly',value:{frequency:'weekly',interval:1}},
  {key:'monthly',label:de?'Monatlich':'Monthly',value:{frequency:'monthly',interval:1}},
  {key:'quarterly-first-monday',label:de?'1. Montag · Quartal':'1st Monday · quarter',value:{frequency:'quarterly',interval:1,nth_weekdays:[{weekday:'MO',ordinal:1}]},secondary:true},
 ];
 if(allowActionCadence)base.splice(3,0,
  {key:'business-days',label:de?'Werktags':'Weekdays',value:{frequency:'weekly',interval:1,weekdays:WEEKDAYS}},
  {key:'twice-daily',label:de?'2× pro Tag':'2× per day',value:{frequency:'daily',interval:1,times_per_period:2}},
  {key:'every-two-weeks',label:de?'Alle 2 Wochen':'Every 2 weeks',value:{frequency:'weekly',interval:2}},
 );
 return base;
}

export default function SchedulingRecurrenceEditor({
 value,
 onChange,
 disabled=false,
 familyId,
 anchor,
 allowOnce=false,
 allowNone=true,
 allowActionCadence=true,
 showNaturalLanguage=true,
 onParsedRule,
 className='',
}){
 const {i18n}=useTranslation();
 const de=!i18n.language.startsWith('en');
 const language=de?'de':'en';
 const recurrence=recurrenceObject(value);
 const frequency=recurrence?.frequency||'none';
 const kind=recurrenceKind(recurrence);
 const cadenceVisible=allowActionCadence||kind==='interval'||kind==='quota'||kind==='business_daily';
 const calendarAdvanced=!recurrence?.times_per_period&&!recurrence?.business_days&&['monthly','quarterly','yearly'].includes(frequency);
 const [phrase,setPhrase]=useState('');
 const [preview,setPreview]=useState(null);
 const [previewError,setPreviewError]=useState('');
 const [previewBusy,setPreviewBusy]=useState(false);
 const presets=useMemo(()=>presetOptions(de,allowActionCadence),[de,allowActionCadence]);
 const dateFormatter=useMemo(()=>new Intl.DateTimeFormat(de?'de-DE':'en-GB',{weekday:'short',day:'2-digit',month:'short',year:'numeric'}),[de]);
 const unitLabels=de?{hourly:'Stunden',daily:'Tage',business_daily:'Werktage',weekly:'Wochen',monthly:'Monate',quarterly:'Quartale',yearly:'Jahre'}:{hourly:'hours',daily:'days',business_daily:'business days',weekly:'weeks',monthly:'months',quarterly:'quarters',yearly:'years'};
 const singleIntervalLabels=de?{hourly:'Jede Stunde',daily:'Jeden Tag',business_daily:'Jeden Werktag',weekly:'Jede Woche',monthly:'Jeden Monat',quarterly:'Jedes Quartal',yearly:'Jedes Jahr'}:{hourly:'Every hour',daily:'Every day',business_daily:'Every business day',weekly:'Every week',monthly:'Every month',quarterly:'Every quarter',yearly:'Every year'};
 const periodLabels=de?{daily:'Tag',weekly:'Woche',monthly:'Monat'}:{daily:'day',weekly:'week',monthly:'month'};
 const intervalUnit=recurrence?.business_days?'business_daily':frequency;
 const intervalCount=Math.max(1,Number(recurrence?.interval||1));
 const intervalMenuLabel=kind==='interval'?(intervalCount===1?singleIntervalLabels[intervalUnit]:(de?`Alle ${intervalCount} ${unitLabels[intervalUnit]}`:`Every ${intervalCount} ${unitLabels[intervalUnit]}`)):(de?'Eigenes Intervall':'Custom interval');
 const quotaMenuLabel=kind==='quota'?(de?`${recurrence?.times_per_period||1}× pro ${periodLabels[frequency]}`:`${recurrence?.times_per_period||1}× per ${periodLabels[frequency]}`):(de?'Anzahl pro Zeitraum festlegen …':'Set count per period …');

 function setRecurrence(next){onChange?.(next)}
 function change(changes){setRecurrence({...recurrence,...changes})}
 function changeKind(next){
  if(next==='none'){setRecurrence('');return}
  if(next==='once'){setRecurrence({frequency:'once',date:anchorDate(anchor)});return}
  if(next==='business_daily'){setRecurrence({frequency:'weekly',interval:1,weekdays:WEEKDAYS});return}
  if(next==='interval'){
   if(kind==='interval')return;
   setRecurrence({frequency:'daily',interval:2});return;
  }
  if(next==='quota'){
   if(kind==='quota')return;
   setRecurrence({frequency:'weekly',interval:1,times_per_period:2});return;
  }
  if(next===frequency&&kind===frequency)return;
  setRecurrence({frequency:next,interval:1});
 }
 function changeIntervalUnit(next){
  const interval=Math.max(1,Number(recurrence?.interval||2));
  if(next==='business_daily'){setRecurrence({frequency:'daily',interval,business_days:true});return}
  setRecurrence({frequency:next,interval});
 }
 function changeQuotaPeriod(next){setRecurrence({frequency:next,interval:1,times_per_period:Math.max(1,Number(recurrence?.times_per_period||2))})}
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
  <div className="scheduling-recurrence-presets" aria-label={de?'Schneller Rhythmus':'Quick rhythm presets'}>
   {presets.map(preset=><button type="button" key={preset.key} disabled={disabled} onClick={()=>setRecurrence(preset.value)}>{preset.label}</button>)}
  </div>

  {showNaturalLanguage&&<div className="scheduling-recurrence-phrase">
   <FormField label={de?'In eigenen Worten':'In your own words'} description={de?'Zum Beispiel: „alle drei Tage“, „jeden dritten Werktag“, „zweimal die Woche“, „montags um 8 Uhr“ oder „erster Montag im Quartal“':'For example: “every three days”, “every 3 business days”, “twice a week”, “Mondays at 8” or “first Monday of the quarter”'}>
    {fieldProps=><div className="scheduling-recurrence-phrase-input"><input {...fieldProps} value={phrase} disabled={disabled} onChange={event=>setPhrase(event.target.value)} onKeyDown={event=>{if(event.key==='Enter'){event.preventDefault();parsePhrase()}}} placeholder={de?'Rhythmus beschreiben …':'Describe rhythm …'}/><button type="button" disabled={disabled||previewBusy||!phrase.trim()||!familyId} onClick={parsePhrase}>{de?'Erkennen':'Interpret'}</button></div>}
   </FormField>
  </div>}

  <FormField label={de?'Rhythmus':'Rhythm'} description={de?'Fester Zeitplan oder flexibles Ziel – beides wird hier geplant.':'Choose a fixed schedule or a flexible target in one place.'}><select value={kind} disabled={disabled} onChange={event=>changeKind(event.target.value)}>{allowNone&&<option value="none">{de?'Kein Rhythmus':'No rhythm'}</option>}{allowOnce&&<option value="once">{de?'Einmalig':'Once'}</option>}<optgroup label={de?'Fester Rhythmus':'Fixed rhythm'}><option value="daily">{de?'Täglich':'Daily'}</option>{cadenceVisible&&<option value="business_daily">{de?'Werktags (Mo–Fr)':'Weekdays (Mon–Fri)'}</option>}<option value="weekly">{de?'Wöchentlich':'Weekly'}</option><option value="monthly">{de?'Monatlich':'Monthly'}</option><option value="quarterly">{de?'Quartalsweise':'Quarterly'}</option><option value="yearly">{de?'Jährlich':'Yearly'}</option>{cadenceVisible&&<option value="interval">{intervalMenuLabel}</option>}</optgroup>{cadenceVisible&&<optgroup label={de?'Flexibles Ziel':'Flexible target'}><option value="quota">{quotaMenuLabel}</option></optgroup>}</select></FormField>

  {kind==='interval'&&<section className="scheduling-recurrence-cadence" aria-label={de?'Eigenes Intervall':'Custom interval'}>
   <FormRow>
    <FormField label={de?'Alle':'Every'}><input type="number" min="1" max="1200" inputMode="numeric" required disabled={disabled} value={recurrence?.interval||1} onChange={event=>change({interval:Math.max(1,Number(event.target.value)||1)})}/></FormField>
    <FormField label={de?'Einheit':'Unit'}><select value={intervalUnit} disabled={disabled} onChange={event=>changeIntervalUnit(event.target.value)}>{INTERVAL_UNITS.map(unit=><option key={unit} value={unit}>{unitLabels[unit]}</option>)}</select></FormField>
   </FormRow>
   {frequency==='hourly'&&<p className="scheduling-recurrence-hint">{de?'Das Intervall startet nach jeder Erledigung neu. Es werden keine künstlichen Uhrzeiten erzeugt.':'The interval restarts after each completion. No artificial clock times are created.'}</p>}
   {recurrence?.business_days&&<p className="scheduling-recurrence-hint">{de?'Gezählt werden Montag bis Freitag; Wochenenden werden beim Intervall übersprungen.':'Only Monday through Friday are counted; weekends are skipped by the interval.'}</p>}
  </section>}

  {kind==='business_daily'&&<p className="scheduling-recurrence-hint">{de?'Bestehender Werktagsrhythmus: Montag bis Freitag. Beim nächsten Ändern wird er als fester Mo–Fr-Rhythmus gespeichert.':'Existing weekday rhythm: Monday through Friday. The next edit stores it as a fixed Mon–Fri rhythm.'}</p>}

  {kind==='quota'&&<section className="scheduling-recurrence-cadence" aria-label={de?'Flexibles Ziel':'Flexible target'}>
   <FormRow>
    <FormField label={de?'Anzahl':'Count'}><input type="number" min="1" max="50" inputMode="numeric" required disabled={disabled} value={recurrence?.times_per_period||2} onChange={event=>change({times_per_period:Math.max(1,Math.min(50,Number(event.target.value)||1))})}/></FormField>
    <FormField label={de?'Pro Zeitraum':'Per period'}><select value={frequency} disabled={disabled} onChange={event=>changeQuotaPeriod(event.target.value)}>{QUOTA_PERIODS.map(period=><option key={period} value={period}>{periodLabels[period]}</option>)}</select></FormField>
   </FormRow>
   <p className="scheduling-recurrence-hint">{de?'Flexibles Ziel im Zeitraum: Erledigungen zählen zum Fortschritt, ohne feste Einzeltermine zu erfinden.':'Flexible target in the period: completions count toward progress without inventing fixed individual slots.'}</p>
  </section>}

  {frequency==='once'&&<FormField label={de?'Datum':'Date'}><input type="date" required disabled={disabled} value={recurrence?.date||anchorDate(anchor)} onChange={event=>change({date:event.target.value})}/></FormField>}

  {calendarAdvanced&&<FormRow>
   <FormField label={frequency==='quarterly'?(de?'Wochentag im Quartal':'Weekday in quarter'):(de?'Wochentag im Zeitraum':'Weekday in period')}><select value={recurrence?.nth_weekdays?.[0]?.weekday||''} disabled={disabled} onChange={event=>change({nth_weekdays:event.target.value?[{weekday:event.target.value,ordinal:recurrence?.nth_weekdays?.[0]?.ordinal||1}]:undefined})}><option value="">{de?'Tag des Ankerdatums':'Anchor date day'}</option>{DAYS.map((day,index)=><option key={day} value={day}>{DAY_LABELS[language][index]}{day==='SA'?(de?' · Wochenende':' · weekend'):''}</option>)}</select></FormField>
   <FormField label={de?'Welche Position?':'Which position?'}><select value={recurrence?.nth_weekdays?.[0]?.ordinal||1} disabled={disabled||!recurrence?.nth_weekdays?.length} onChange={event=>change({nth_weekdays:[{...recurrence.nth_weekdays[0],ordinal:Number(event.target.value)}]})}>{[1,2,3,4,5,-1].map(ordinal=><option key={ordinal} value={ordinal}>{ORDINAL_LABELS[language][ordinal]}</option>)}</select></FormField>
  </FormRow>}

  {frequency==='weekly'&&kind!=='quota'&&<fieldset className="scheduling-recurrence-options" disabled={disabled}><legend>{de?'Wochentage (leer = Ankertag)':'Weekdays (empty = anchor day)'}</legend>{DAYS.map((day,index)=><label key={day}><input type="checkbox" checked={recurrence?.weekdays?.includes(day)||false} onChange={event=>toggleWeekday(day,event.target.checked)}/>{DAY_LABELS[language][index]}</label>)}</fieldset>}
  {frequency==='yearly'&&<fieldset className="scheduling-recurrence-options scheduling-recurrence-months" disabled={disabled}><legend>{de?'Monate (leer = Ankermonat)':'Months (empty = anchor month)'}</legend>{MONTH_LABELS[language].map((label,index)=>{const month=index+1;return <label key={month}><input type="checkbox" checked={recurrence?.months?.includes(month)||false} onChange={event=>toggleMonth(month,event.target.checked)}/>{label}</label>})}</fieldset>}
  {frequency==='quarterly'&&recurrence?.nth_weekdays?.[0]?.weekday==='SA'&&<p className="muted">{de?'Das Wochenende beginnt am ausgewählten Samstag.':'The weekend starts on the selected Saturday.'}</p>}

  {recurrence&&<section className="scheduling-recurrence-preview" aria-live="polite" aria-busy={previewBusy}>
   <div className="scheduling-recurrence-preview-head"><strong>{de?'Vorschau':'Preview'}</strong>{previewBusy&&<span>{de?'Wird berechnet …':'Calculating …'}</span>}</div>
   {preview?.summary&&<p className="scheduling-recurrence-summary">{preview.summary}</p>}
   {preview?.occurrences?.length>0&&<ol>{preview.occurrences.map(item=><li key={item}>{dateFormatter.format(new Date(`${item}T12:00:00`))}</li>)}</ol>}
   {preview&&!previewBusy&&!preview?.occurrences?.length&&kind==='quota'&&<p className="scheduling-recurrence-preview-note">{de?'Flexibles Ziel – der Fortschritt wird im Zeitraum gezählt; es entstehen keine künstlichen Termine.':'Flexible target — progress is counted in the period; no artificial dates are created.'}</p>}
   {preview&&!previewBusy&&!preview?.occurrences?.length&&frequency==='hourly'&&<p className="scheduling-recurrence-preview-note">{de?'Intervall nach Erledigung – der nächste Zeitpunkt hängt von der letzten Erledigung ab.':'Completion-based interval — the next due time depends on the last completion.'}</p>}
   {previewError&&<p className="scheduling-recurrence-error" role="status">{previewError}</p>}
  </section>}
 </div>;
}