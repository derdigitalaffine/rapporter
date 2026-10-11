import {Children,cloneElement,isValidElement,useEffect,useRef,useState} from 'react';
import {api} from './api';
import i18n from './i18n';
import {Icon} from './icons';
import {WeekCompassWidget,PinboardTodayWidget} from './TodayContextWidgets';
import TodayTodoWidget from './TodayTodoWidget';
import {
 TODAY_LAYOUT_VERSION,
 cleanTodayWidget,
 defaultTodayWidgets,
 normalizeTodayLayout,
 settingsFor,
 sizeOptionsFor,
} from './todayWidgetRegistry';
import './today-layout.css';
import './today-layout-v2.css';

const strings={
 de:{
  edit:'Anpassen',heading:'Dein Heute-Raster',hint:'Ordne Widgets, blende sie ein oder aus und wähle die passende Größe. Ziehe nur am Verschiebegriff oder nutze die gleichwertigen Tastatur- und Pfeilaktionen.',save:'Speichern',cancel:'Abbrechen',reset:'Standard wiederherstellen',up:'Nach oben',down:'Nach unten',move:'Verschieben',moveHint:'Leertaste oder Eingabe startet den Tastatur-Verschiebemodus. Danach mit Pfeil hoch oder runter verschieben und erneut bestätigen.',picked:'zum Verschieben aufgenommen',dropped:'abgelegt',moveCancelled:'Verschieben abgebrochen',position:'Position',compact:'Kompakt',medium:'Mittel',wide:'Breit',size:'Größe',visible:'Anzeigen',empty:'Alle Widgets sind ausgeblendet. Passe dein Heute-Raster an, um sie einzublenden.',error:'Das Raster konnte nicht gespeichert werden. Dein Entwurf bleibt erhalten.',loadError:'Dein gespeichertes Raster konnte nicht geladen werden.',reload:'Erneut laden',conflict:'Das Raster wurde auf einem anderen Gerät geändert. Lade es erneut, bevor du weiter bearbeitest.',preview:'Vorschau',week:'Wochenkompass',pinboard:'Pinnwand',trip:'Reise',waste:'Müllabfuhr',weather:'Wetter',priority:'Prioritäten',next:'Als Nächstes',todo:'To-dos',shopping:'Einkauf',birthdays:'Geburtstage',notes:'Notizzettel',loyalty:'Bonuskarten',inbox:'Familien-Inbox',weekEvents:'Normale Termine',weekWaste:'Müllabfuhr',weekHolidays:'Ferien',weekSpecial:'Weitere Spezialereignisse',tripWishes:'Reisewünsche anzeigen'
 },
 en:{
  edit:'Customize',heading:'Your Today grid',hint:'Reorder widgets, show or hide them, and choose the right size. Drag only from the move handle, or use the equivalent keyboard and arrow controls.',save:'Save',cancel:'Cancel',reset:'Restore defaults',up:'Move up',down:'Move down',move:'Move',moveHint:'Press Space or Enter to start keyboard move mode. Then use Arrow Up or Arrow Down and confirm again to drop.',picked:'picked up for moving',dropped:'dropped',moveCancelled:'move cancelled',position:'Position',compact:'Compact',medium:'Medium',wide:'Wide',size:'Size',visible:'Show',empty:'All widgets are hidden. Customize your Today grid to show them.',error:'Could not save your grid. Your draft has been kept.',loadError:'Could not load your saved grid.',reload:'Reload',conflict:'This grid changed on another device. Reload it before continuing to edit.',preview:'Preview',week:'Week compass',pinboard:'Pinboard',trip:'Trip',waste:'Waste collection',weather:'Weather',priority:'Priorities',next:'Up next',todo:'To-dos',shopping:'Shopping',birthdays:'Birthdays',notes:'Notes',loyalty:'Loyalty cards',inbox:'Family inbox',weekEvents:'Regular events',weekWaste:'Waste collection',weekHolidays:'School holidays',weekSpecial:'Other special events',tripWishes:'Show trip wishes'
 }
};

const reorder=(rows,from,to)=>{
 if(from===to||from<0||to<0||from>=rows.length||to>=rows.length)return rows;
 const next=[...rows];
 const [item]=next.splice(from,1);
 next.splice(to,0,item);
 return next;
};

export default function TodayLayout({family,header,onboarding,widgets}){
 const language=i18n.language;
 const s=strings[language.startsWith('de')?'de':'en'];
 const availableWidgets=widgets||{};
 const editButton=useRef(null);
 const editorHeading=useRef(null);
 const dragHandles=useRef(new Map());
 const dragState=useRef(null);
 const longPress=useRef(null);
 const draftRef=useRef(null);
 const fresh=()=>({version:TODAY_LAYOUT_VERSION,revision:0,widgets:defaultTodayWidgets()});
 const [saved,setSaved]=useState(fresh);
 const [draft,setDraft]=useState(null);
 const [busy,setBusy]=useState(false);
 const [error,setError]=useState('');
 const [loaded,setLoaded]=useState(false);
 const [conflict,setConflict]=useState(false);
 const [draggingId,setDraggingId]=useState('');
 const [announcement,setAnnouncement]=useState('');
 const [focusWidgetId,setFocusWidgetId]=useState('');
 const editing=Boolean(draft);
 draftRef.current=draft;

 const labelFor=id=>s[id]||id;
 const clearLongPress=()=>{
  if(longPress.current?.timer)clearTimeout(longPress.current.timer);
  longPress.current=null;
 };
 const clearDrag=()=>{
  const current=dragState.current;
  if(current?.handle&&current.pointerId!==undefined&&current.handle.hasPointerCapture?.(current.pointerId)){
   try{current.handle.releasePointerCapture(current.pointerId)}catch{}
  }
  dragState.current=null;
  setDraggingId('');
 };
 const finish=()=>{
  clearLongPress();
  clearDrag();
  setFocusWidgetId('');
  setDraft(null);
  requestAnimationFrame(()=>editButton.current?.focus());
 };
 const openEditor=(widgetId='')=>{
  clearLongPress();
  setError('');
  setConflict(false);
  setFocusWidgetId(widgetId);
  setDraft(saved.widgets.map(cleanTodayWidget));
 };
 const cancelEditor=()=>{
  setError('');
  setConflict(false);
  finish();
 };

 const load=async()=>{
  setBusy(true);
  try{
   const result=normalizeTodayLayout(await api(`/today-layout/?family=${family.id}`));
   if(!result)throw new Error('layout');
   setSaved(result);
   setDraft(null);
   setError('');
   setConflict(false);
   setLoaded(true);
  }catch{
   setError(s.loadError);
   setLoaded(false);
  }finally{
   setBusy(false);
  }
 };
 useEffect(()=>{
  let current=true;
  clearLongPress();
  clearDrag();
  setLoaded(false);
  setDraft(null);
  setError('');
  setSaved(fresh());
  api(`/today-layout/?family=${family.id}`).then(result=>{
   if(current){
    const normalized=normalizeTodayLayout(result);
    if(!normalized)throw new Error('layout');
    setSaved(normalized);
    setLoaded(true);
   }
  }).catch(()=>{if(current)setError(s.loadError)});
  return()=>{current=false;clearLongPress()};
 },[family.id]);
 useEffect(()=>{
  if(!editing)return;
  if(focusWidgetId){
   requestAnimationFrame(()=>{
    dragHandles.current.get(focusWidgetId)?.focus();
    setFocusWidgetId('');
   });
  }else{
   editorHeading.current?.focus();
  }
 },[editing,focusWidgetId]);

 const change=(index,patch)=>setDraft(rows=>rows.map((widget,i)=>i===index?{...widget,...patch}:widget));
 const changeSetting=(index,key,value)=>setDraft(rows=>rows.map((widget,i)=>i===index?{...widget,settings:{...settingsFor(widget.id),...(widget.settings||{}),[key]:value}}:widget));
 const positionText=(id,index,total=draftRef.current?.length||0)=>`${labelFor(id)}: ${s.position} ${index+1} / ${total}`;
 const moveByDelta=(id,delta,shouldAnnounce=true)=>{
  const rows=draftRef.current||[];
  const from=rows.findIndex(widget=>widget.id===id);
  const to=from+delta;
  if(from<0||to<0||to>=rows.length)return false;
  setDraft(current=>reorder(current,current.findIndex(widget=>widget.id===id),to));
  if(dragState.current?.id===id)dragState.current.position=to;
  if(shouldAnnounce)setAnnouncement(positionText(id,to,rows.length));
  requestAnimationFrame(()=>dragHandles.current.get(id)?.focus());
  return true;
 };
 const moveToWidget=(id,targetId,targetIndex)=>{
  if(id===targetId)return;
  const rows=draftRef.current||[];
  const from=rows.findIndex(widget=>widget.id===id);
  const to=rows.findIndex(widget=>widget.id===targetId);
  if(from<0||to<0||from===to)return;
  setDraft(current=>{
   const currentFrom=current.findIndex(widget=>widget.id===id);
   const currentTo=current.findIndex(widget=>widget.id===targetId);
   return reorder(current,currentFrom,currentTo);
  });
  if(dragState.current)dragState.current.position=to;
  setAnnouncement(positionText(id,Number.isFinite(targetIndex)?targetIndex:to,rows.length));
 };
 const cancelActiveDrag=()=>{
  const current=dragState.current;
  if(!current)return false;
  if(current.snapshot)setDraft(current.snapshot.map(cleanTodayWidget));
  const id=current.id;
  clearDrag();
  setAnnouncement(`${labelFor(id)}: ${s.moveCancelled}`);
  requestAnimationFrame(()=>dragHandles.current.get(id)?.focus());
  return true;
 };
 const dropActiveDrag=()=>{
  const current=dragState.current;
  if(!current)return;
  const rows=draftRef.current||[];
  const index=rows.findIndex(widget=>widget.id===current.id);
  const id=current.id;
  clearDrag();
  setAnnouncement(`${positionText(id,Math.max(0,index),rows.length)} · ${s.dropped}`);
  requestAnimationFrame(()=>dragHandles.current.get(id)?.focus());
 };
 const edgeAutoScroll=clientY=>{
  const edge=Math.min(96,Math.max(56,window.innerHeight*.12));
  if(clientY<edge)window.scrollBy(0,-Math.max(8,Math.ceil((edge-clientY)/4)));
  else if(clientY>window.innerHeight-edge)window.scrollBy(0,Math.max(8,Math.ceil((clientY-(window.innerHeight-edge))/4)));
 };
 const pointerDragStart=(widget,index,event)=>{
  if(busy||dragState.current||event.button!==0)return;
  event.preventDefault();
  event.currentTarget.focus();
  try{event.currentTarget.setPointerCapture(event.pointerId)}catch{}
  dragState.current={mode:'pointer',id:widget.id,pointerId:event.pointerId,handle:event.currentTarget,position:index,snapshot:(draftRef.current||[]).map(cleanTodayWidget)};
  setDraggingId(widget.id);
  setAnnouncement(`${labelFor(widget.id)}: ${s.picked} · ${s.position} ${index+1} / ${draftRef.current?.length||0}`);
 };
 const pointerDragMove=event=>{
  const current=dragState.current;
  if(!current||current.mode!=='pointer'||current.pointerId!==event.pointerId)return;
  edgeAutoScroll(event.clientY);
  const target=document.elementFromPoint(event.clientX,event.clientY)?.closest?.('[data-editor-widget-id]');
  if(!target)return;
  const targetId=target.dataset.editorWidgetId;
  const targetIndex=Number(target.dataset.editorIndex);
  moveToWidget(current.id,targetId,targetIndex);
 };
 const pointerDragEnd=event=>{
  const current=dragState.current;
  if(!current||current.mode!=='pointer'||current.pointerId!==event.pointerId)return;
  dropActiveDrag();
 };
 const dragKeyDown=(widget,index,event)=>{
  const current=dragState.current;
  const active=current?.mode==='keyboard'&&current.id===widget.id;
  if((event.key===' '||event.key==='Enter')&&!event.repeat){
   event.preventDefault();
   event.stopPropagation();
   if(active){dropActiveDrag();return}
   if(current)return;
   dragState.current={mode:'keyboard',id:widget.id,position:index,snapshot:(draftRef.current||[]).map(cleanTodayWidget)};
   setDraggingId(widget.id);
   setAnnouncement(`${labelFor(widget.id)}: ${s.picked} · ${s.position} ${index+1} / ${draftRef.current?.length||0}`);
   return;
  }
  if(!active)return;
  if(event.key==='ArrowUp'||event.key==='ArrowDown'){
   event.preventDefault();
   event.stopPropagation();
   moveByDelta(widget.id,event.key==='ArrowUp'?-1:1,true);
  }else if(event.key==='Escape'){
   event.preventDefault();
   event.stopPropagation();
   cancelActiveDrag();
  }
 };
 useEffect(()=>{
  if(!editing)return undefined;
  const onKeyDown=event=>{
   if(event.key!=='Escape')return;
   if(dragState.current){
    event.preventDefault();
    cancelActiveDrag();
   }else if(!busy){
    event.preventDefault();
    cancelEditor();
   }
  };
  document.addEventListener('keydown',onKeyDown);
  return()=>document.removeEventListener('keydown',onKeyDown);
 },[editing,busy]);

 const longPressStart=(widget,event)=>{
  if(editing||busy||!loaded||!['touch','pen'].includes(event.pointerType))return;
  if(event.target.closest?.('button,a,input,select,textarea,summary,label'))return;
  clearLongPress();
  const startX=event.clientX;
  const startY=event.clientY;
  const pointerId=event.pointerId;
  const timer=setTimeout(()=>{
   if(!longPress.current||longPress.current.pointerId!==pointerId)return;
   longPress.current=null;
   openEditor(widget.id);
  },520);
  longPress.current={pointerId,startX,startY,timer};
 };
 const longPressMove=event=>{
  const current=longPress.current;
  if(!current||current.pointerId!==event.pointerId)return;
  if(Math.hypot(event.clientX-current.startX,event.clientY-current.startY)>10)clearLongPress();
 };
 const longPressEnd=()=>clearLongPress();
 const longPressProps=widget=>({
  onPointerDown:event=>longPressStart(widget,event),
  onPointerMove:longPressMove,
  onPointerUp:longPressEnd,
  onPointerCancel:longPressEnd,
  'data-long-press-editable':'true'
 });

 const save=async()=>{
  setBusy(true);
  setError('');
  try{
   const body={version:TODAY_LAYOUT_VERSION,revision:saved.revision,widgets:draft.map(cleanTodayWidget)};
   const result=normalizeTodayLayout(await api(`/today-layout/?family=${family.id}`,{method:'PUT',body:JSON.stringify(body)}));
   if(!result)throw new Error('layout');
   setSaved(result);
   finish();
  }catch(e){
   const stale=e.message.includes('another device');
   setConflict(stale);
   setError(stale?s.conflict:s.error);
  }finally{
   setBusy(false);
  }
 };
 const builtin=id=>id==='week'||id==='pinboard'||id==='todo';
 // Missing module/permission implementations stay in the saved layout but never
 // render a preview. This is what makes disabled and future widgets lossless.
 const active=(draft||saved.widgets).filter(widget=>widget.visible&&(builtin(widget.id)||availableWidgets[widget.id]));
 const content=widget=>widget.id==='week'?<WeekCompassWidget family={family} language={language} settings={widget.settings||settingsFor('week')} compact={widget.size==='compact'}/>:widget.id==='pinboard'?<PinboardTodayWidget family={family} language={language} compact={widget.size==='compact'}/>:widget.id==='todo'?<TodayTodoWidget family={family} language={language} compact={widget.size==='compact'}/>:availableWidgets[widget.id];
 const render=widget=>{
  const value=content(widget);
  const editProps=longPressProps(widget);
  if(isValidElement(value)&&value.type?.todayWidgetSelfManaged)return cloneElement(value,{key:widget.id,widgetSize:widget.size,widgetSettings:widget.settings||settingsFor(widget.id)||undefined,...editProps});
  const legacyMediumClass=widget.size==='medium'?' today-widget-square':'';
  return <div key={widget.id} data-today-widget={widget.id} data-widget-size={widget.size} className={`app-widget today-widget today-widget-${widget.size}${legacyMediumClass}`} {...editProps}>{value}</div>;
 };
 const editAction=<button type="button" ref={editButton} className="secondary today-layout-edit" data-testid="today-layout-edit" disabled={busy||!loaded||editing} onClick={()=>openEditor()}><Icon name="edit" size={15}/><span>{s.edit}</span></button>;
 const headerWithAction=isValidElement(header)?(()=>{
  const children=Children.toArray(header.props.children);
  if(!children.length)return cloneElement(header,{},editAction);
  const [lead,...rest]=children;
  return cloneElement(header,{},<div className="today-hero-heading-row">{lead}{editAction}</div>,...rest);
 })():header;

 return <div className="today-page">
  {headerWithAction}
  {error&&<div className="today-layout-error" role="alert">{error}{(!loaded||conflict)&&<button type="button" className="secondary" onClick={load} disabled={busy}>{s.reload}</button>}</div>}
  {onboarding}
  {draft&&<section className="today-layout-editor" aria-label={s.edit}>
   <h2 ref={editorHeading} tabIndex={-1}>{s.heading}</h2>
   <p>{s.hint}</p>
   <p id="today-layout-move-help" className="today-layout-sr-only">{s.moveHint}</p>
   <div className="today-layout-sr-only" role="status" aria-live="polite" aria-atomic="true" data-testid="today-layout-live">{announcement}</div>
   <ol>{draft.map((widget,index)=><li key={widget.id} data-editor-widget-id={widget.id} data-editor-index={index} data-dragging={draggingId===widget.id?'true':'false'} className={settingsFor(widget.id)?'today-layout-settings-row':''}>
    <div className="today-layout-widget-main">
     <div className="today-layout-widget-identity">
      <button
       type="button"
       ref={element=>{if(element)dragHandles.current.set(widget.id,element);else dragHandles.current.delete(widget.id)}}
       className="ghost icon-button today-layout-drag-handle"
       data-testid={`today-drag-${widget.id}`}
       data-drag-handle="true"
       aria-label={`${labelFor(widget.id)} · ${s.move}`}
       aria-describedby="today-layout-move-help"
       aria-pressed={draggingId===widget.id}
       title={s.move}
       disabled={busy}
       onPointerDown={event=>pointerDragStart(widget,index,event)}
       onPointerMove={pointerDragMove}
       onPointerUp={pointerDragEnd}
       onPointerCancel={event=>{if(dragState.current?.pointerId===event.pointerId)cancelActiveDrag()}}
       onKeyDown={event=>dragKeyDown(widget,index,event)}
      ><span aria-hidden="true">⋮⋮</span></button>
      <label><input type="checkbox" checked={widget.visible} onChange={event=>change(index,{visible:event.target.checked})} disabled={busy}/><span>{labelFor(widget.id)}</span></label>
     </div>
     <div className="today-layout-controls">
      <select aria-label={`${labelFor(widget.id)} · ${s.size}`} value={widget.size} onChange={event=>change(index,{size:event.target.value})} disabled={busy}>{sizeOptionsFor(widget.id).map(size=><option key={size} value={size}>{s[size]}</option>)}</select>
      <button type="button" className="ghost icon-button" aria-label={`${labelFor(widget.id)} · ${s.up}`} onClick={()=>moveByDelta(widget.id,-1,true)} disabled={busy||index===0}>↑</button>
      <button type="button" className="ghost icon-button" aria-label={`${labelFor(widget.id)} · ${s.down}`} onClick={()=>moveByDelta(widget.id,1,true)} disabled={busy||index===draft.length-1}>↓</button>
     </div>
    </div>
    {widget.id==='week'&&widget.visible&&<fieldset className="today-week-settings"><legend>{s.week}</legend>{[['events','weekEvents'],['waste','weekWaste'],['holidays','weekHolidays'],['special','weekSpecial']].map(([key,label])=><label key={key}><input type="checkbox" checked={widget.settings?.[key]!==false} onChange={event=>changeSetting(index,key,event.target.checked)} disabled={busy}/><span>{s[label]}</span></label>)}</fieldset>}
    {widget.id==='trip'&&widget.visible&&<fieldset className="today-week-settings"><legend>{s.trip}</legend><label><input type="checkbox" checked={widget.settings?.show_wishes===true} onChange={event=>changeSetting(index,'show_wishes',event.target.checked)} disabled={busy}/><span>{s.tripWishes}</span></label></fieldset>}
   </li>)}</ol>
   <div className="today-layout-actions">
    <button type="button" className="ghost" disabled={busy} onClick={()=>{clearDrag();setDraft(defaultTodayWidgets());setAnnouncement('')}}>{s.reset}</button>
    <button type="button" className="secondary" disabled={busy} onClick={cancelEditor}>{s.cancel}</button>
    <button type="button" className="primary" disabled={busy||conflict} onClick={save}>{s.save}</button>
   </div>
   <h3>{s.preview}</h3>
  </section>}
  {active.length>0?<div className="app-widget-grid today-widget-grid">{active.map(render)}</div>:<p className="today-calm">{s.empty}</p>}
 </div>;
}
