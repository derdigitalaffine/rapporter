import {Children,cloneElement,isValidElement,useEffect,useState,useRef} from 'react';
import {api} from './api';
import i18n from './i18n';
import {Icon} from './icons';
import {WeekCompassWidget,PinboardTodayWidget} from './TodayContextWidgets';
import TodayTodoWidget from './TodayTodoWidget';
import './today-layout.css';

const legacyIds=['weather','priority','waste','next','tasks','shopping','routines','birthdays','notes'];
const deprecatedTodoIds=new Set(['tasks','routines']);
const baseIds=['weather','priority','waste','next','todo','shopping','birthdays','notes'];
const prePinboardIds=[...baseIds,'loyalty','inbox'];
const ids=[...prePinboardIds,'trip','week','pinboard'];
const inputIds=new Set([...ids,...deprecatedTodoIds]);
const squareIds=new Set(['trip','next','weather','waste','inbox','birthdays','notes','loyalty']);
const inputSquareIds=new Set([...squareIds,'routines']);
const requiredStableIds=legacyIds.filter(id=>!deprecatedTodoIds.has(id));
const weekSettings=()=>({events:true,waste:true,holidays:true,special:true});
const tripSettings=()=>({show_wishes:false});
const settingsFor=id=>id==='week'?weekSettings():id==='trip'?tripSettings():null;
const defaultOrder=['week','priority','trip','next','pinboard','weather','todo','shopping','waste','inbox','birthdays','notes','loyalty'];
const defaults=()=>defaultOrder.map(id=>({id,visible:true,size:'full',...(settingsFor(id)?{settings:settingsFor(id)}:{})}));
function cleanWidget(widget){const row={...widget};const settings=settingsFor(row.id);if(settings)row.settings={...settings,...(row.settings||{})};else delete row.settings;return row}
function validSettings(widget){const values=settingsFor(widget.id);if(!values)return widget.settings===undefined;const keys=Object.keys(values);return widget.settings&&typeof widget.settings==='object'&&!Array.isArray(widget.settings)&&Object.keys(widget.settings).length===keys.length&&keys.every(key=>typeof widget.settings[key]==='boolean')}
function migrateTodoWidgets(rows){
 const todo=rows.find(row=>row.id==='todo');
 if(todo)return rows.filter(row=>!deprecatedTodoIds.has(row.id));
 const legacy=rows.map((row,index)=>({row,index})).filter(({row})=>deprecatedTodoIds.has(row.id));
 if(!legacy.length)return rows;
 const visible=legacy.some(({row})=>row.visible===true);const tasks=legacy.find(({row})=>row.id==='tasks')?.row;
 const preferred=tasks&&['full','compact'].includes(tasks.size)?tasks.size:(legacy.map(({row})=>row.size).find(size=>['full','compact'].includes(size))||'full');
 const first=Math.min(...legacy.map(({index})=>index));const cleaned=rows.filter(row=>!deprecatedTodoIds.has(row.id));
 const insertAt=rows.slice(0,first).filter(row=>!deprecatedTodoIds.has(row.id)).length;
 cleaned.splice(insertAt,0,{id:'todo',visible,size:preferred});return cleaned;
}
function normalizeLayout(value){
 if(value?.version!==1||!Number.isInteger(value.revision)||value.revision<0||!Array.isArray(value.widgets))return null;
 const rawWidgets=[];const seen=new Set();
 for(const raw of value.widgets){
  if(!raw||typeof raw!=='object')return null;
  const widget=cleanWidget(raw);const hasSettings=Boolean(settingsFor(widget.id));const allowed=hasSettings?['id','visible','size','settings']:['id','visible','size'];
  if(Object.keys(raw).some(key=>!allowed.includes(key))||!inputIds.has(widget.id)||seen.has(widget.id)||typeof widget.visible!=='boolean'||!['full','compact','square'].includes(widget.size)||(widget.size==='square'&&!inputSquareIds.has(widget.id))||!validSettings(widget))return null;
  seen.add(widget.id);rawWidgets.push(widget);
 }
 if(requiredStableIds.some(id=>!seen.has(id))||(!seen.has('todo')&&![...deprecatedTodoIds].every(id=>seen.has(id))))return null;
 const widgets=migrateTodoWidgets(rawWidgets);const canonicalSeen=new Set(widgets.map(widget=>widget.id));
 if(!canonicalSeen.has('week')){widgets.unshift({id:'week',visible:true,size:'full',settings:weekSettings()});canonicalSeen.add('week')}
 if(!canonicalSeen.has('trip')){const index=widgets.findIndex(widget=>widget.id==='priority');widgets.splice(index>=0?index+1:1,0,{id:'trip',visible:true,size:'full',settings:tripSettings()});canonicalSeen.add('trip')}
 if(!canonicalSeen.has('pinboard')){const index=widgets.findIndex(widget=>widget.id==='next');widgets.splice(index>=0?index+1:Math.min(5,widgets.length),0,{id:'pinboard',visible:true,size:'full'});canonicalSeen.add('pinboard')}
 prePinboardIds.forEach(id=>{if(!canonicalSeen.has(id)){widgets.push({id,visible:false,size:'full'});canonicalSeen.add(id)}});
 return {...value,widgets};
}
const strings={de:{edit:'Anpassen',heading:'Dein Heute-Raster',hint:'Ordne Widgets, blende sie ein oder aus und wähle die passende Größe. Geeignete Widgets können halbbreit als Quadrat nebeneinander stehen.',save:'Speichern',cancel:'Abbrechen',reset:'Standard wiederherstellen',up:'Nach oben',down:'Nach unten',compact:'Kompakt',full:'Ausführlich',square:'Quadrat',size:'Größe',visible:'Anzeigen',empty:'Alle Widgets sind ausgeblendet. Passe dein Heute-Raster an, um sie einzublenden.',error:'Das Raster konnte nicht gespeichert werden. Dein Entwurf bleibt erhalten.',loadError:'Dein gespeichertes Raster konnte nicht geladen werden.',reload:'Erneut laden',conflict:'Das Raster wurde auf einem anderen Gerät geändert. Lade es erneut, bevor du weiter bearbeitest.',preview:'Vorschau',week:'Wochenkompass',pinboard:'Pinnwand',trip:'Reise',waste:'Müllabfuhr',weather:'Wetter',priority:'Prioritäten',next:'Als Nächstes',todo:'To-dos',shopping:'Einkauf',birthdays:'Geburtstage',notes:'Notizzettel',loyalty:'Bonuskarten',inbox:'Familien-Inbox',weekEvents:'Normale Termine',weekWaste:'Müllabfuhr',weekHolidays:'Ferien',weekSpecial:'Weitere Spezialereignisse',tripWishes:'Reisewünsche anzeigen'},en:{edit:'Customize',heading:'Your Today grid',hint:'Reorder widgets, show or hide them, and choose the right size. Suitable widgets can sit side by side as half-width squares.',save:'Save',cancel:'Cancel',reset:'Restore defaults',up:'Move up',down:'Move down',compact:'Compact',full:'Detailed',square:'Square',size:'Size',visible:'Show',empty:'All widgets are hidden. Customize your Today grid to show them.',error:'Could not save your grid. Your draft has been kept.',loadError:'Could not load your saved grid.',reload:'Reload',conflict:'This grid changed on another device. Reload it before continuing to edit.',preview:'Preview',week:'Week compass',pinboard:'Pinboard',trip:'Trip',waste:'Waste collection',weather:'Weather',priority:'Priorities',next:'Up next',todo:'To-dos',shopping:'Shopping',birthdays:'Birthdays',notes:'Notes',loyalty:'Loyalty cards',inbox:'Family inbox',weekEvents:'Regular events',weekWaste:'Waste collection',weekHolidays:'School holidays',weekSpecial:'Other special events',tripWishes:'Show trip wishes'}};
export default function TodayLayout({family,header,onboarding,widgets}){
 const language=i18n.language;const s=strings[language.startsWith('de')?'de':'en'];
 const availableWidgets=widgets||{};
 const editButton=useRef(null);const editorHeading=useRef(null);
 const [saved,setSaved]=useState({version:1,revision:0,widgets:defaults()});const [draft,setDraft]=useState(null);const [busy,setBusy]=useState(false);const [error,setError]=useState('');const [loaded,setLoaded]=useState(false);const [conflict,setConflict]=useState(false);
 const load=async()=>{setBusy(true);try{const result=normalizeLayout(await api(`/today-layout/?family=${family.id}`));if(!result)throw new Error('layout');setSaved(result);setDraft(null);setError('');setConflict(false);setLoaded(true)}catch{setError(s.loadError);setLoaded(false)}finally{setBusy(false)}};
 useEffect(()=>{let current=true;setLoaded(false);setDraft(null);setError('');setSaved({version:1,revision:0,widgets:defaults()});api(`/today-layout/?family=${family.id}`).then(result=>{if(current){const normalized=normalizeLayout(result);if(!normalized)throw new Error('layout');setSaved(normalized);setLoaded(true)}}).catch(()=>{if(current)setError(s.loadError)});return()=>{current=false}},[family.id]);
 useEffect(()=>{if(draft)editorHeading.current?.focus()},[Boolean(draft)]);
 const finish=()=>{setDraft(null);editButton.current?.focus()};
 const change=(index,patch)=>setDraft(draft.map((widget,i)=>i===index?{...widget,...patch}:widget));
 const changeSetting=(index,key,value)=>setDraft(draft.map((widget,i)=>i===index?{...widget,settings:{...settingsFor(widget.id),...(widget.settings||{}),[key]:value}}:widget));
 const move=(index,delta)=>{const next=[...draft];[next[index],next[index+delta]]=[next[index+delta],next[index]];setDraft(next)};
 const save=async()=>{setBusy(true);setError('');try{const result=normalizeLayout(await api(`/today-layout/?family=${family.id}`,{method:'PUT',body:JSON.stringify({...saved,widgets:draft})}));if(!result)throw new Error('layout');setSaved(result);finish()}catch(e){const stale=e.message.includes('another device');setConflict(stale);setError(stale?s.conflict:s.error)}finally{setBusy(false)}};
 const builtin=id=>id==='week'||id==='pinboard'||id==='todo';
 const active=(draft||saved.widgets).filter(widget=>widget.visible&&(builtin(widget.id)||availableWidgets[widget.id]));
 const content=widget=>widget.id==='week'?<WeekCompassWidget family={family} language={language} settings={widget.settings||weekSettings()} compact={widget.size==='compact'}/>:widget.id==='pinboard'?<PinboardTodayWidget family={family} language={language} compact={widget.size==='compact'}/>:widget.id==='todo'?<TodayTodoWidget family={family} language={language} compact={widget.size==='compact'}/>:availableWidgets[widget.id];
 const render=widget=>{const value=content(widget);if(isValidElement(value)&&value.type?.todayWidgetSelfManaged)return cloneElement(value,{key:widget.id,widgetSize:widget.size,widgetSettings:widget.settings||settingsFor(widget.id)||undefined});return <div key={widget.id} data-today-widget={widget.id} data-widget-size={widget.size} className={`app-widget today-widget today-widget-${widget.size}`}>{value}</div>};
 const editAction=<button ref={editButton} className="today-layout-edit" data-testid="today-layout-edit" disabled={busy||!loaded||Boolean(draft)} onClick={()=>{setDraft(saved.widgets.map(cleanWidget));setError('')}}><Icon name="edit" size={15}/><span>{s.edit}</span></button>;
 const headerWithAction=isValidElement(header)?(()=>{const children=Children.toArray(header.props.children);if(!children.length)return cloneElement(header,{},editAction);const [lead,...rest]=children;return cloneElement(header,{},<div className="today-hero-heading-row">{lead}{editAction}</div>,...rest)})():header;
 return <div className="today-page">{headerWithAction}{error&&<div className="today-layout-error" role="alert">{error}{(!loaded||conflict)&&<button onClick={load} disabled={busy}>{s.reload}</button>}</div>}{onboarding}{draft&&<section className="today-layout-editor" aria-label={s.edit}><h2 ref={editorHeading} tabIndex={-1}>{s.heading}</h2><p>{s.hint}</p><ol>{draft.map((widget,index)=><li key={widget.id} className={settingsFor(widget.id)?'today-layout-week-row':''}><div className="today-layout-widget-main"><label><input type="checkbox" checked={widget.visible} onChange={event=>change(index,{visible:event.target.checked})} disabled={busy}/><span>{s[widget.id]}</span></label><div className="today-layout-controls"><select aria-label={`${s[widget.id]} · ${s.size}`} value={widget.size} onChange={event=>change(index,{size:event.target.value})} disabled={busy}><option value="full">{s.full}</option><option value="compact">{s.compact}</option>{squareIds.has(widget.id)&&<option value="square">{s.square}</option>}</select><button aria-label={`${s[widget.id]} · ${s.up}`} onClick={()=>move(index,-1)} disabled={busy||index===0}>↑</button><button aria-label={`${s[widget.id]} · ${s.down}`} onClick={()=>move(index,1)} disabled={busy||index===draft.length-1}>↓</button></div></div>{widget.id==='week'&&widget.visible&&<fieldset className="today-week-settings"><legend>{s.week}</legend>{[['events','weekEvents'],['waste','weekWaste'],['holidays','weekHolidays'],['special','weekSpecial']].map(([key,label])=><label key={key}><input type="checkbox" checked={widget.settings?.[key]!==false} onChange={event=>changeSetting(index,key,event.target.checked)} disabled={busy}/><span>{s[label]}</span></label>)}</fieldset>}{widget.id==='trip'&&widget.visible&&<fieldset className="today-week-settings"><legend>{s.trip}</legend><label><input type="checkbox" checked={widget.settings?.show_wishes===true} onChange={event=>changeSetting(index,'show_wishes',event.target.checked)} disabled={busy}/><span>{s.tripWishes}</span></label></fieldset>}</li>)}</ol><div className="today-layout-actions"><button disabled={busy} onClick={()=>setDraft(defaults())}>{s.reset}</button><button disabled={busy} onClick={()=>{finish();setError('');setConflict(false)}}>{s.cancel}</button><button className="primary" disabled={busy||conflict} onClick={save}>{s.save}</button></div><h3>{s.preview}</h3></section>}{active.length>0?<div className="app-widget-grid today-widget-grid">{active.map(render)}</div>:<p className="today-calm">{s.empty}</p>}</div>
}