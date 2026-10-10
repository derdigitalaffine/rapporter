import {useEffect,useState,useRef} from 'react';
import {api} from './api';
import i18n from './i18n';
import './today-layout.css';

const legacyIds=['weather','priority','waste','next','tasks','shopping','routines','birthdays','notes'];
const ids=[...legacyIds,'loyalty','inbox'];
const defaultOrder=['priority','next','weather','tasks','shopping','routines','waste','inbox','birthdays','notes','loyalty'];
const defaults=()=>defaultOrder.map(id=>({id,visible:true,size:'full'}));
function normalizeLayout(value){
 if(value?.version!==1||!Number.isInteger(value.revision)||value.revision<0||!Array.isArray(value.widgets))return null;
 const widgets=[];const seen=new Set();
 for(const widget of value.widgets){
  if(!widget||typeof widget!=='object'||!ids.includes(widget.id)||seen.has(widget.id)||typeof widget.visible!=='boolean'||!['full','compact'].includes(widget.size))return null;
  seen.add(widget.id);widgets.push({...widget});
 }
 if(legacyIds.some(id=>!seen.has(id)))return null;
 ids.forEach(id=>{if(!seen.has(id))widgets.push({id,visible:false,size:'full'})});
 return {...value,widgets};
}
const strings={de:{edit:'Heute bearbeiten',heading:'Dein Heute',hint:'Nur für dich in dieser Familie. Die Vorschau aktualisiert sich sofort.',save:'Speichern',cancel:'Abbrechen',reset:'Standard wiederherstellen',up:'Nach oben',down:'Nach unten',compact:'Kompakt',full:'Ausführlich',visible:'Anzeigen',empty:'Alle Widgets sind ausgeblendet. Bearbeite Heute, um sie einzublenden.',error:'Die Ansicht konnte nicht gespeichert werden. Dein Entwurf bleibt erhalten.',loadError:'Deine gespeicherte Ansicht konnte nicht geladen werden.',reload:'Erneut laden',conflict:'Die Ansicht wurde auf einem anderen Gerät geändert. Lade sie erneut, bevor du weiter bearbeitest.',preview:'Vorschau',waste:'Müllabfuhr',weather:'Wetter',priority:'Prioritäten',next:'Als Nächstes',tasks:'Aufgaben',shopping:'Einkauf',routines:'Zuletzt gemacht',birthdays:'Geburtstage',notes:'Notizzettel',loyalty:'Bonuskarten',inbox:'Familien-Inbox'},en:{edit:'Edit Today',heading:'Your Today',hint:'Only for you in this family. The preview updates immediately.',save:'Save',cancel:'Cancel',reset:'Restore defaults',up:'Move up',down:'Move down',compact:'Compact',full:'Detailed',visible:'Show',empty:'All widgets are hidden. Edit Today to show them.',error:'Could not save your layout. Your draft has been kept.',loadError:'Your saved layout could not be loaded.',reload:'Reload',conflict:'This layout changed on another device. Reload it before continuing to edit.',preview:'Preview',waste:'Waste collection',weather:'Weather',priority:'Priorities',next:'Up next',tasks:'Tasks',shopping:'Shopping',routines:'Recently done',birthdays:'Birthdays',notes:'Notes',loyalty:'Loyalty cards',inbox:'Family inbox'}};
export default function TodayLayout({family,header,onboarding,widgets}){
 const s=strings[i18n.language.startsWith('de')?'de':'en'];
 const editButton=useRef(null);const editorHeading=useRef(null);
 const [saved,setSaved]=useState({version:1,revision:0,widgets:defaults()});const [draft,setDraft]=useState(null);const [busy,setBusy]=useState(false);const [error,setError]=useState('');const [loaded,setLoaded]=useState(false);const [conflict,setConflict]=useState(false);
 const load=async()=>{setBusy(true);try{const result=normalizeLayout(await api(`/today-layout/?family=${family.id}`));if(!result)throw new Error('layout');setSaved(result);setDraft(null);setError('');setConflict(false);setLoaded(true)}catch{setError(s.loadError);setLoaded(false)}finally{setBusy(false)}};
 useEffect(()=>{let current=true;setLoaded(false);setDraft(null);setError('');setSaved({version:1,revision:0,widgets:defaults()});api(`/today-layout/?family=${family.id}`).then(result=>{if(current){const normalized=normalizeLayout(result);if(!normalized)throw new Error('layout');setSaved(normalized);setLoaded(true)}}).catch(()=>{if(current)setError(s.loadError)});return()=>{current=false}},[family.id]);
 useEffect(()=>{if(draft)editorHeading.current?.focus()},[Boolean(draft)]);
 const finish=()=>{setDraft(null);editButton.current?.focus()};
 const change=(index,patch)=>setDraft(draft.map((widget,i)=>i===index?{...widget,...patch}:widget));
 const move=(index,delta)=>{const next=[...draft];[next[index],next[index+delta]]=[next[index+delta],next[index]];setDraft(next)};
 const save=async()=>{setBusy(true);setError('');try{const result=normalizeLayout(await api(`/today-layout/?family=${family.id}`,{method:'PUT',body:JSON.stringify({...saved,widgets:draft})}));if(!result)throw new Error('layout');setSaved(result);finish()}catch(e){const stale=e.message.includes('another device');setConflict(stale);setError(stale?s.conflict:s.error)}finally{setBusy(false)}};
 const active=(draft||saved.widgets).filter(w=>w.visible&&widgets[w.id]);
 const render=widget=><div key={widget.id} data-today-widget={widget.id} className={`today-widget ${widget.size==='compact'?'today-widget-compact':''}`}>{widgets[widget.id]}</div>;
 const pairClass=(left,right)=>left==='next'&&right==='weather'?'today-context-grid':left==='tasks'&&right==='shopping'?'today-main-grid':left==='routines'&&right==='waste'?'today-secondary-grid':'';
 const elements=[];for(let i=0;i<active.length;i++){const widget=active[i],next=active[i+1];const group=next&&pairClass(widget.id,next.id);if(group){elements.push(<div className={group} key={`${widget.id}-${next.id}`}>{render(widget)}{render(next)}</div>);i++}else elements.push(render(widget))}
 return <div className="today-page">{header}<div className="today-layout-toolbar"><button ref={editButton} className="ghost" disabled={busy||!loaded||Boolean(draft)} onClick={()=>{setDraft(saved.widgets.map(w=>({...w})));setError('')}}>{s.edit}</button></div>{error&&<div className="today-layout-error" role="alert">{error}{(!loaded||conflict)&&<button onClick={load} disabled={busy}>{s.reload}</button>}</div>}{onboarding}{draft&&<section className="today-layout-editor" aria-label={s.edit}><h2 ref={editorHeading} tabIndex={-1}>{s.heading}</h2><p>{s.hint}</p><ol>{draft.map((widget,index)=><li key={widget.id}><label><input type="checkbox" checked={widget.visible} onChange={event=>change(index,{visible:event.target.checked})} disabled={busy}/><span>{s[widget.id]}</span></label><div className="today-layout-controls"><select aria-label={`${s[widget.id]} · ${s.compact}`} value={widget.size} onChange={event=>change(index,{size:event.target.value})} disabled={busy}><option value="full">{s.full}</option><option value="compact">{s.compact}</option></select><button aria-label={`${s[widget.id]} · ${s.up}`} onClick={()=>move(index,-1)} disabled={busy||index===0}>↑</button><button aria-label={`${s[widget.id]} · ${s.down}`} onClick={()=>move(index,1)} disabled={busy||index===draft.length-1}>↓</button></div></li>)}</ol><div className="today-layout-actions"><button disabled={busy} onClick={()=>setDraft(defaults())}>{s.reset}</button><button disabled={busy} onClick={()=>{finish();setError('');setConflict(false)}}>{s.cancel}</button><button className="primary" disabled={busy||conflict} onClick={save}>{s.save}</button></div><h3>{s.preview}</h3></section>}{elements}{active.length===0&&<p className="today-calm">{s.empty}</p>}</div>
}