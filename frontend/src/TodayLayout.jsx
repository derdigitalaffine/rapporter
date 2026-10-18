import {Children,cloneElement,isValidElement,useEffect,useRef,useState} from 'react';
import {scrollAppNearEdge} from './app-scroll';
import {api} from './api';
import i18n from './i18n';
import {Icon} from './icons';
import {WeekCompassWidget,PinboardTodayWidget} from './TodayContextWidgets';
import {TodayFocusWidget,TodaySituation,TodayTimelineWidget} from './TodayCoreWidgets';
import {TodayFamilyLoadWidget,TodayTomorrowWidget,contextWidgetLabels} from './TodayContextSummaryWidgets';
import TodayTodoWidget from './TodayTodoWidget';
import {
 TODAY_LAYOUT_VERSION,
 TodayWidgetRegistry,
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
  edit:'Anpassen',heading:'Today anpassen',hint:'Stelle dein persönliches Today aus wenigen klaren Widgets zusammen. Reihenfolge und Größe bleiben über Gerätebreiten semantisch stabil.',placedHeading:'Dein Heute',placedHint:'Diese Widgets liegen auf deinem Today. Verschiebe, skaliere oder blende sie aus.',libraryHeading:'Widgets hinzufügen',libraryHint:'Die Library zeigt nur Widgets, die in diesem Familienkontext verfügbar sind. Die Vorschauen sind rein illustrativ und laden keine zusätzlichen Inhalte.',add:'Hinzufügen',added:'hinzugefügt',hide:'Ausblenden',hidden:'ausgeblendet',allPlaced:'Alle verfügbaren Widgets sind bereits auf deinem Today.',supportedSizes:'Unterstützte Größen',safePreview:'Illustrative Vorschau ohne Live-Daten',categoryPlanning:'Jetzt & Planung',categoryFamily:'Familie & Kommunikation',categoryHousehold:'Haushalt',categoryTravel:'Unterwegs',save:'Speichern',cancel:'Abbrechen',reset:'Standard wiederherstellen',up:'Nach oben',down:'Nach unten',move:'Verschieben',moveHint:'Leertaste oder Eingabe startet den Tastatur-Verschiebemodus. Danach mit Pfeil hoch oder runter verschieben und erneut bestätigen.',picked:'zum Verschieben aufgenommen',dropped:'abgelegt',moveCancelled:'Verschieben abgebrochen',position:'Position',compact:'Kompakt',medium:'Mittel',wide:'Breit','wide-compact':'Breit & flach',size:'Größe',empty:'Alle Widgets sind ausgeblendet. Passe dein Today an, um sie einzublenden.',error:'Das Raster konnte nicht gespeichert werden. Dein Entwurf bleibt erhalten.',loadError:'Dein gespeichertes Raster konnte nicht geladen werden.',reload:'Erneut laden',conflict:'Das Raster wurde auf einem anderen Gerät geändert. Lade es erneut, bevor du weiter bearbeitest.',preview:'Live-Vorschau',situation:'Tageslage',focus:'Jetzt wichtig',timeline:'Tagesverlauf',tomorrow:'Morgen','family-load':'Engpässe heute',week:'Wochenkompass',pinboard:'Pinnwand',trip:'Reise',waste:'Müllabfuhr',weather:'Wetter',priority:'Prioritäten',next:'Als Nächstes',todo:'To-dos','quick-actions':'Schnellaktionen',shopping:'Einkauf',birthdays:'Geburtstage',notes:'Notizzettel',loyalty:'Bonuskarten',inbox:'Familien-Inbox',weekEvents:'Normale Termine',weekWaste:'Müllabfuhr',weekHolidays:'Ferien',weekSpecial:'Weitere Spezialereignisse',tripWishes:'Reisewünsche anzeigen',descriptions:{'quick-actions':'Deine erlaubten Schnellaktionen aus Hinzufügen – mit derselben persönlichen Reihenfolge.',situation:'Kompakte Tageslage mit direkten Aktionen für überfällige Routinen.',focus:'Maximal drei erklärbare Punkte, die jetzt wirklich Aufmerksamkeit brauchen.',timeline:'Termine und echte Task-Uhrzeiten in einem chronologischen Tagesverlauf.',tomorrow:'Sieh den ersten Termin und fällige To-dos des nächsten lokalen Kalendertags.','family-load':'Zeigt nur konkrete Terminüberschneidungen und dringende Dinge – ohne Familien-Score.',week:'Behalte die wichtigsten Punkte der Woche im Blick.',priority:'Sieh dringende und hoch priorisierte Dinge zuerst.',trip:'Öffne deine aktuelle Reise und ihren Status direkt von Today.',next:'Sieh den nächsten relevanten Termin oder Tagespunkt.',pinboard:'Springe kompakt zu eurer gemeinsamen Pinnwand.',weather:'Sieh die aktuelle Wetterlage für euren Alltag.',todo:'Arbeite die heute relevanten Aufgaben und Routinen ab.',shopping:'Behalte offene Einkaufspunkte griffbereit.',waste:'Sieh anstehende Abholungen und Mülltermine.',inbox:'Sieh neue Mitteilungen aus der Familien-Inbox.',birthdays:'Behalte anstehende Geburtstage im Blick.',notes:'Öffne eure Notizzettel direkt von Today.',loyalty:'Greife schnell auf wichtige Bonuskarten zu.'}
 },
 en:{
  edit:'Customize',heading:'Customize Today',hint:'Build your personal Today from a small set of clear widgets. Order and size stay semantically stable across screen widths.',placedHeading:'Your Today',placedHint:'These widgets are on your Today. Reorder, resize, or hide them.',libraryHeading:'Add widgets',libraryHint:'The library only shows widgets available in this family context. Previews are illustrative and never load additional content.',add:'Add',added:'added',hide:'Hide',hidden:'hidden',allPlaced:'All available widgets are already on your Today.',supportedSizes:'Supported sizes',safePreview:'Illustrative preview without live data',categoryPlanning:'Now & planning',categoryFamily:'Family & communication',categoryHousehold:'Household',categoryTravel:'On the go',save:'Save',cancel:'Cancel',reset:'Restore defaults',up:'Move up',down:'Move down',move:'Move',moveHint:'Press Space or Enter to start keyboard move mode. Then use Arrow Up or Arrow Down and confirm again to drop.',picked:'picked up for moving',dropped:'dropped',moveCancelled:'Move cancelled',position:'Position',compact:'Compact',medium:'Medium',wide:'Wide','wide-compact':'Wide & shallow',size:'Size',empty:'All widgets are hidden. Customize your Today to show them.',error:'Could not save your grid. Your draft has been kept.',loadError:'Could not load your saved grid.',reload:'Reload',conflict:'This grid changed on another device. Reload it before continuing to edit.',preview:'Live preview',situation:'Day status',focus:'Important now',timeline:'Day timeline',tomorrow:'Tomorrow','family-load':'Today’s bottlenecks',week:'Week compass',pinboard:'Pinboard',trip:'Trip',waste:'Waste collection',weather:'Weather',priority:'Priorities',next:'Up next',todo:'To-dos','quick-actions':'Quick actions',shopping:'Shopping',birthdays:'Birthdays',notes:'Notes',loyalty:'Loyalty cards',inbox:'Family inbox',weekEvents:'Regular events',weekWaste:'Waste collection',weekHolidays:'School holidays',weekSpecial:'Other special events',tripWishes:'Show trip wishes',descriptions:{'quick-actions':'Your available Add actions in the same personal order.',situation:'Compact day status with direct actions for overdue routines.',focus:'At most three explainable items that genuinely need attention now.',timeline:'Events and real task times in one chronological day timeline.',tomorrow:'See the first event and due to-dos for the next local calendar day.','family-load':'Shows only concrete calendar overlaps and urgent items — never a family score.',week:'Keep the key points of the week in view.',priority:'See urgent and high-priority items first.',trip:'Open your current trip and its status from Today.',next:'See the next relevant event or point in your day.',pinboard:'Jump to your shared pinboard from a compact entry.',weather:'See the current weather context for your day.',todo:'Work through today’s relevant tasks and routines.',shopping:'Keep open shopping items close at hand.',waste:'See upcoming collection and waste dates.',inbox:'See new messages from the family inbox.',birthdays:'Keep upcoming birthdays in view.',notes:'Open your shared notes directly from Today.',loyalty:'Quickly access important loyalty cards.'}
 }
};

const categoryOrder=['planning','family','household','travel'];
const reorder=(rows,from,to)=>{
 if(from===to||from<0||to<0||from>=rows.length||to>=rows.length)return rows;
 const next=[...rows];
 const [item]=next.splice(from,1);
 next.splice(to,0,item);
 return next;
};

export default function TodayLayout({family,header,onboarding,widgets,persistence='remote',storageKey='',topNotice=null,editorExtras=null,editIcon='edit',gridTestId='',gridClassName=''}){
 const language=i18n.language;
 const baseStrings=strings[language.startsWith('de')?'de':'en'];
 const contextLabels=contextWidgetLabels(language);
 const contextDescriptions={
  de:{tomorrow:'Termine und fällige To-dos des nächsten lokalen Kalendertags.',load:'Konkrete Terminüberschneidungen und dringende Dinge ohne Familien-Score.'},
  en:{tomorrow:'Events and due to-dos for the next local calendar day.',load:'Concrete calendar overlaps and urgent items without a family score.'},
  fr:{tomorrow:'Rendez-vous et tâches à échéance du prochain jour local.',load:'Chevauchements et éléments urgents concrets, sans score familial.'},
  nl:{tomorrow:'Afspraken en taken voor de volgende lokale kalenderdag.',load:'Concrete overlappende afspraken en dringende items, zonder gezinsscore.'},
  th:{tomorrow:'นัดหมายและงานที่ครบกำหนดในวันถัดไปตามเวลาครอบครัว',load:'นัดหมายที่ทับซ้อนและรายการเร่งด่วนที่ชัดเจน ไม่มีคะแนนครอบครัว'}
 }[String(language||'de').split('-')[0]];
 const s={...baseStrings,pregnancy:language.startsWith('de')?'Schwangerschaft':'Pregnancy',tomorrow:contextLabels.tomorrow,'family-load':contextLabels.load,descriptions:{...baseStrings.descriptions,pregnancy:language.startsWith('de')?'Aktiver Schwangerschaftsstand aus deinem geschützten Bereich.':'Active pregnancy from your protected area.',tomorrow:contextDescriptions?.tomorrow||baseStrings.descriptions.tomorrow,'family-load':contextDescriptions?.load||baseStrings.descriptions['family-load']}};
 const availableWidgets=widgets||{};
 const localPersistence=persistence==='local';
 const editButton=useRef(null);
 const editorHeading=useRef(null);
 const dragHandles=useRef(new Map());
 const libraryButtons=useRef(new Map());
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

 const labelFor=id=>id==='overview'?(language.startsWith('de')?'Überblick':'Overview'):s[id]||id;
 const descriptionFor=id=>s.descriptions[id]||'';
 const builtin=id=>['situation','focus','timeline','tomorrow','family-load','week','pinboard','todo'].includes(id);
 const isProvided=id=>Object.prototype.hasOwnProperty.call(availableWidgets,id);
 const definitionFor=id=>TodayWidgetRegistry.find(definition=>definition.id===id);
 const isAvailableDefinition=definition=>{
  if(!definition)return false;
  if(definition.moduleGate||definition.permissionGate)return isProvided(definition.id);
  return builtin(definition.id)||isProvided(definition.id);
 };
 const placedRowsFrom=rows=>(rows||[]).filter(widget=>widget.visible&&isAvailableDefinition(definitionFor(widget.id)));
 const reorderPlacedRows=(rows,fromId,toId)=>{
  const slots=[];const placed=[];
  rows.forEach((widget,index)=>{if(widget.visible&&isAvailableDefinition(definitionFor(widget.id))){slots.push(index);placed.push(widget)}});
  const from=placed.findIndex(widget=>widget.id===fromId);const to=placed.findIndex(widget=>widget.id===toId);
  if(from<0||to<0||from===to)return rows;
  const reordered=reorder(placed,from,to);const next=[...rows];
  slots.forEach((slot,index)=>{next[slot]=reordered[index]});
  return next;
 };
 const categoryFor=definition=>definition.category==='planning'?'planning':definition.category==='household'?'household':['collaboration','family'].includes(definition.category)?'family':'travel';
 const categoryLabel=category=>s[{planning:'categoryPlanning',family:'categoryFamily',household:'categoryHousehold',travel:'categoryTravel'}[category]];
 const sizeOptions=id=>sizeOptionsFor(id).filter(size=>localPersistence||size!=='wide-compact');
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
  clearLongPress();clearDrag();setFocusWidgetId('');setDraft(null);
  requestAnimationFrame(()=>editButton.current?.focus());
 };
 const openEditor=(widgetId='')=>{
  clearLongPress();setError('');setConflict(false);setFocusWidgetId(widgetId);setDraft(saved.widgets.map(cleanTodayWidget));
 };
 const cancelEditor=()=>{setError('');setConflict(false);finish()};
 const readLocalLayout=()=>{
  if(!storageKey)return fresh();
  try{
   const raw=localStorage.getItem(storageKey);
   if(!raw)return fresh();
   return normalizeTodayLayout(JSON.parse(raw))||fresh();
  }catch{return fresh()}
 };
 const load=async()=>{
  setBusy(true);
  try{
   const result=localPersistence?readLocalLayout():normalizeTodayLayout(await api(`/today-layout/?family=${family.id}`));
   if(!result)throw new Error('layout');
   setSaved(result);setDraft(null);setError('');setConflict(false);setLoaded(family.id);
  }catch{setError(s.loadError);setLoaded(false)}finally{setBusy(false)}
 };
 useEffect(()=>{
  let current=true;clearLongPress();clearDrag();setLoaded(false);setDraft(null);setError('');setSaved(fresh());
  if(localPersistence){
   const result=readLocalLayout();
   if(current){setSaved(result);setLoaded(family.id)}
   return()=>{current=false;clearLongPress()};
  }
  api(`/today-layout/?family=${family.id}`).then(result=>{
   if(current){const normalized=normalizeTodayLayout(result);if(!normalized)throw new Error('layout');setSaved(normalized);setLoaded(family.id)}
  }).catch(()=>{if(current)setError(s.loadError)});
  return()=>{current=false;clearLongPress()};
 },[family.id,localPersistence,storageKey]);
 useEffect(()=>{
  if(!editing)return;
  if(focusWidgetId){requestAnimationFrame(()=>{dragHandles.current.get(focusWidgetId)?.focus();setFocusWidgetId('')})}
  else editorHeading.current?.focus();
 },[editing,focusWidgetId]);

 const change=(index,patch)=>setDraft(rows=>rows.map((widget,i)=>i===index?{...widget,...patch}:widget));
 const changeSetting=(index,key,value)=>setDraft(rows=>rows.map((widget,i)=>i===index?{...widget,settings:{...settingsFor(widget.id),...(widget.settings||{}),[key]:value}}:widget));
 const positionText=(id,index,total=placedRowsFrom(draftRef.current).length)=>`${labelFor(id)}: ${s.position} ${index+1} / ${total}`;
 const moveByDelta=(id,delta,shouldAnnounce=true)=>{
  const rows=draftRef.current||[];const placed=placedRowsFrom(rows);const placedFrom=placed.findIndex(widget=>widget.id===id);const placedTo=placedFrom+delta;
  if(placedFrom<0||placedTo<0||placedTo>=placed.length)return false;
  const targetId=placed[placedTo].id;
  setDraft(current=>reorderPlacedRows(current,id,targetId));
  if(dragState.current?.id===id)dragState.current.position=placedTo;
  if(shouldAnnounce)setAnnouncement(positionText(id,placedTo,placed.length));
  requestAnimationFrame(()=>dragHandles.current.get(id)?.focus());
  return true;
 };
 const moveToWidget=(id,targetId,targetIndex)=>{
  if(id===targetId)return;const rows=draftRef.current||[];const placed=placedRowsFrom(rows);const from=placed.findIndex(widget=>widget.id===id);const to=placed.findIndex(widget=>widget.id===targetId);
  if(from<0||to<0||from===to)return;const total=placed.length;
  setDraft(current=>reorderPlacedRows(current,id,targetId));
  if(dragState.current)dragState.current.position=to;
  setAnnouncement(positionText(id,Number.isFinite(targetIndex)?targetIndex:to,total));
 };
 const hideWidget=id=>{
  clearDrag();setDraft(rows=>rows.map(widget=>widget.id===id?{...widget,visible:false}:widget));setAnnouncement(`${labelFor(id)}: ${s.hidden}`);
  requestAnimationFrame(()=>requestAnimationFrame(()=>libraryButtons.current.get(id)?.focus()));
 };
 const addWidget=id=>{
  const definition=definitionFor(id);if(!isAvailableDefinition(definition))return;
  setDraft(rows=>{
   const found=rows.find(widget=>widget.id===id);const item=found?{...found,visible:true}:cleanTodayWidget({id,visible:true,size:definition.defaultSize});const next=rows.filter(widget=>widget.id!==id);let insertAt=0;
   next.forEach((widget,index)=>{if(widget.visible&&isAvailableDefinition(definitionFor(widget.id)))insertAt=index+1});next.splice(insertAt,0,item);return next;
  });
  setAnnouncement(`${labelFor(id)}: ${s.added}`);setFocusWidgetId(id);
 };
 const cancelActiveDrag=()=>{
  const current=dragState.current;if(!current)return false;if(current.snapshot)setDraft(current.snapshot.map(cleanTodayWidget));const id=current.id;clearDrag();setAnnouncement(`${labelFor(id)}: ${s.moveCancelled}`);requestAnimationFrame(()=>dragHandles.current.get(id)?.focus());return true;
 };
 const dropActiveDrag=()=>{
  const current=dragState.current;if(!current)return;const placed=placedRowsFrom(draftRef.current);const index=placed.findIndex(widget=>widget.id===current.id);const id=current.id;clearDrag();setAnnouncement(`${positionText(id,Math.max(0,index),placed.length)} · ${s.dropped}`);requestAnimationFrame(()=>dragHandles.current.get(id)?.focus());
 };
 const edgeAutoScroll=clientY=>{scrollAppNearEdge(clientY)};
 const pointerDragStart=(widget,index,event)=>{
  if(busy||dragState.current||event.button!==0)return;event.preventDefault();event.currentTarget.focus();try{event.currentTarget.setPointerCapture(event.pointerId)}catch{}
  dragState.current={mode:'pointer',id:widget.id,pointerId:event.pointerId,handle:event.currentTarget,position:index,snapshot:(draftRef.current||[]).map(cleanTodayWidget)};setDraggingId(widget.id);setAnnouncement(`${labelFor(widget.id)}: ${s.picked} · ${s.position} ${index+1} / ${placedRowsFrom(draftRef.current).length}`);
 };
 const editorRowAtPoint=(clientX,clientY)=>{
  const rows=[...document.querySelectorAll('[data-editor-widget-id]')];
  const geometric=rows.find(row=>{const rect=row.getBoundingClientRect();return clientX>=rect.left&&clientX<=rect.right&&clientY>=rect.top&&clientY<=rect.bottom});
  return geometric||document.elementFromPoint(clientX,clientY)?.closest?.('[data-editor-widget-id]')||null;
 };
 const pointerDragMove=event=>{
  const current=dragState.current;if(!current||current.mode!=='pointer'||current.pointerId!==event.pointerId)return;edgeAutoScroll(event.clientY);const target=editorRowAtPoint(event.clientX,event.clientY);if(!target)return;moveToWidget(current.id,target.dataset.editorWidgetId,Number(target.dataset.editorIndex));
 };
 const pointerDragEnd=event=>{const current=dragState.current;if(!current||current.mode!=='pointer'||current.pointerId!==event.pointerId)return;dropActiveDrag()};
 const dragKeyDown=(widget,index,event)=>{
  const current=dragState.current;const active=current?.mode==='keyboard'&&current.id===widget.id;
  if((event.key===' '||event.key==='Enter')&&!event.repeat){event.preventDefault();event.stopPropagation();if(active){dropActiveDrag();return}if(current)return;dragState.current={mode:'keyboard',id:widget.id,position:index,snapshot:(draftRef.current||[]).map(cleanTodayWidget)};setDraggingId(widget.id);setAnnouncement(`${labelFor(widget.id)}: ${s.picked} · ${s.position} ${index+1} / ${placedRowsFrom(draftRef.current).length}`);return}
  if(!active)return;
  if(event.key==='ArrowUp'||event.key==='ArrowDown'){event.preventDefault();event.stopPropagation();moveByDelta(widget.id,event.key==='ArrowUp'?-1:1,true)}
  else if(event.key==='Escape'){event.preventDefault();event.stopPropagation();cancelActiveDrag()}
 };
 useEffect(()=>{
  if(!editing)return undefined;
  const onKeyDown=event=>{if(event.key!=='Escape')return;if(dragState.current){event.preventDefault();cancelActiveDrag()}else if(!busy){event.preventDefault();cancelEditor()}};
  document.addEventListener('keydown',onKeyDown);return()=>document.removeEventListener('keydown',onKeyDown);
 },[editing,busy]);

 const longPressStart=(widget,event)=>{
  if(editing||busy||!loaded||!['touch','pen'].includes(event.pointerType))return;if(event.target.closest?.('button,a,input,select,textarea,summary,label'))return;clearLongPress();const startX=event.clientX;const startY=event.clientY;const pointerId=event.pointerId;
  const timer=setTimeout(()=>{if(!longPress.current||longPress.current.pointerId!==pointerId)return;longPress.current=null;openEditor(widget.id)},520);longPress.current={pointerId,startX,startY,timer};
 };
 const longPressMove=event=>{const current=longPress.current;if(!current||current.pointerId!==event.pointerId)return;if(Math.hypot(event.clientX-current.startX,event.clientY-current.startY)>10)clearLongPress()};
 const longPressEnd=()=>clearLongPress();
 const longPressProps=widget=>({onPointerDown:event=>longPressStart(widget,event),onPointerMove:longPressMove,onPointerUp:longPressEnd,onPointerCancel:longPressEnd,'data-long-press-editable':'true'});

 const save=async()=>{
  setBusy(true);setError('');
  try{
   const body={version:TODAY_LAYOUT_VERSION,revision:saved.revision,widgets:draft.map(cleanTodayWidget)};
   if(localPersistence){
    const result=normalizeTodayLayout({...body,revision:saved.revision+1});if(!result)throw new Error('layout');
    if(storageKey)localStorage.setItem(storageKey,JSON.stringify(result));setSaved(result);finish();return;
   }
   const result=normalizeTodayLayout(await api(`/today-layout/?family=${family.id}`,{method:'PUT',body:JSON.stringify(body)}));if(!result)throw new Error('layout');setSaved(result);finish();
  }catch(e){const stale=!localPersistence&&e.message.includes('another device');setConflict(stale);setError(stale?s.conflict:s.error)}finally{setBusy(false)}
 };
 // Missing module/permission implementations stay in the saved layout but never
 // render a preview or a Library card. This keeps disabled/future widgets lossless.
 const active=(draft||saved.widgets).filter(widget=>widget.visible&&(!['games','pinboard'].includes(widget.id)||loaded===family.id)&&(builtin(widget.id)||availableWidgets[widget.id]));
 const content=widget=>widget.id==='situation'?<TodaySituation family={family} language={language} widgetSize={widget.size} summaryOnly={active.some(row=>row.id==='overview')}/>:widget.id==='focus'?<TodayFocusWidget family={family} language={language} compact={active.some(row=>row.id==='overview')}/>:widget.id==='timeline'?<TodayTimelineWidget family={family} language={language}/>:widget.id==='tomorrow'?<TodayTomorrowWidget family={family} language={language} widgetSize={widget.size}/>:widget.id==='family-load'?<TodayFamilyLoadWidget family={family} language={language} widgetSize={widget.size}/>:widget.id==='week'?<WeekCompassWidget family={family} language={language} settings={widget.settings||settingsFor('week')} compact={widget.size==='compact'}/>:widget.id==='pinboard'?<PinboardTodayWidget family={family} language={language} compact={widget.size==='compact'}/>:widget.id==='todo'?<TodayTodoWidget family={family} language={language} compact={widget.size==='compact'}/>:availableWidgets[widget.id];
 const render=widget=>{
  const value=content(widget);const editProps=longPressProps(widget);
  if(isValidElement(value)&&value.type?.todayWidgetSelfManaged)return cloneElement(value,{key:widget.id,widgetSize:widget.size,widgetSettings:widget.settings||settingsFor(widget.id)||undefined,...editProps});
  const legacyMediumClass=widget.size==='medium'?' today-widget-square':'';
  return <div key={widget.id} data-today-widget={widget.id} data-widget-size={widget.size} className={`app-widget today-widget today-widget-${widget.size}${legacyMediumClass}`} {...editProps}>{value}</div>;
 };
 const editAction=<button type="button" ref={editButton} className="secondary today-layout-edit" data-testid="today-layout-edit" aria-label={s.edit} title={s.edit} disabled={busy||!loaded||editing} onClick={()=>openEditor()}><Icon name={editIcon} size={15}/><span>{s.edit}</span></button>;
 const headerWithAction=isValidElement(header)?(()=>{const children=Children.toArray(header.props.children);if(!children.length)return cloneElement(header,{},editAction);const [lead,...rest]=children;return cloneElement(header,{},<div className="today-hero-heading-row">{lead}{editAction}</div>,...rest)})():header;
 const placedDraft=placedRowsFrom(draft);
 const libraryDefinitions=draft?TodayWidgetRegistry.filter(definition=>isAvailableDefinition(definition)&&!draft.find(widget=>widget.id===definition.id)?.visible):[];
 const libraryGroups=categoryOrder.map(category=>({category,definitions:libraryDefinitions.filter(definition=>categoryFor(definition)===category)})).filter(group=>group.definitions.length);

 return <div className="today-page">
  {headerWithAction}
  {topNotice}
  {error&&<div className="today-layout-error" role="alert">{error}{(!loaded||conflict)&&<button type="button" className="secondary" onClick={load} disabled={busy}>{s.reload}</button>}</div>}
  {onboarding}
  {draft&&<section className="today-layout-editor" aria-label={s.edit}>
   <h2 ref={editorHeading} tabIndex={-1}>{s.heading}</h2>
   <p>{s.hint}</p>
   {editorExtras}
   <p id="today-layout-move-help" className="today-layout-sr-only">{s.moveHint}</p>
   <div className="today-layout-sr-only" role="status" aria-live="polite" aria-atomic="true" data-testid="today-layout-live">{announcement}</div>
   <section className="today-layout-placed" aria-labelledby="today-layout-placed-heading">
    <h3 id="today-layout-placed-heading">{s.placedHeading}</h3><p>{s.placedHint}</p>
    <ol>{placedDraft.map((widget,index)=>{const draftIndex=draft.findIndex(row=>row.id===widget.id);return <li key={widget.id} data-editor-widget-id={widget.id} data-editor-index={index} data-dragging={draggingId===widget.id?'true':'false'} className={settingsFor(widget.id)?'today-layout-settings-row':''}>
     <div className="today-layout-widget-main"><div className="today-layout-widget-identity">
      <button type="button" ref={element=>{if(element)dragHandles.current.set(widget.id,element);else dragHandles.current.delete(widget.id)}} className="ghost icon-button today-layout-drag-handle" data-testid={`today-drag-${widget.id}`} data-drag-handle="true" aria-label={`${labelFor(widget.id)} · ${s.move}`} aria-describedby="today-layout-move-help" aria-pressed={draggingId===widget.id} title={s.move} disabled={busy} onPointerDown={event=>pointerDragStart(widget,index,event)} onPointerMove={pointerDragMove} onPointerUp={pointerDragEnd} onPointerCancel={event=>{if(dragState.current?.pointerId===event.pointerId)cancelActiveDrag()}} onKeyDown={event=>dragKeyDown(widget,index,event)}><span aria-hidden="true">⋮⋮</span></button>
      <span className="today-layout-widget-copy"><strong>{labelFor(widget.id)}</strong>{descriptionFor(widget.id)&&<small>{descriptionFor(widget.id)}</small>}</span>
     </div><div className="today-layout-controls">
      <select aria-label={`${labelFor(widget.id)} · ${s.size}`} value={widget.size} onChange={event=>change(draftIndex,{size:event.target.value})} disabled={busy}>{sizeOptions(widget.id).map(size=><option key={size} value={size}>{s[size]}</option>)}</select>
      <button type="button" className="ghost icon-button" aria-label={`${labelFor(widget.id)} · ${s.up}`} onClick={()=>moveByDelta(widget.id,-1,true)} disabled={busy||index===0}>↑</button>
      <button type="button" className="ghost icon-button" aria-label={`${labelFor(widget.id)} · ${s.down}`} onClick={()=>moveByDelta(widget.id,1,true)} disabled={busy||index===placedDraft.length-1}>↓</button>
      <button type="button" className="ghost today-layout-hide" onClick={()=>hideWidget(widget.id)} disabled={busy}>{s.hide}</button>
     </div></div>
     {widget.id==='week'&&<fieldset className="today-week-settings"><legend>{s.week}</legend>{[['events','weekEvents'],['waste','weekWaste'],['holidays','weekHolidays'],['special','weekSpecial']].map(([key,label])=><label key={key}><input type="checkbox" checked={widget.settings?.[key]!==false} onChange={event=>changeSetting(draftIndex,key,event.target.checked)} disabled={busy}/><span>{s[label]}</span></label>)}</fieldset>}
     {widget.id==='trip'&&<fieldset className="today-week-settings"><legend>{s.trip}</legend><label><input type="checkbox" checked={widget.settings?.show_wishes===true} onChange={event=>changeSetting(draftIndex,'show_wishes',event.target.checked)} disabled={busy}/><span>{s.tripWishes}</span></label></fieldset>}
    </li>})}</ol>
   </section>
   <section className="today-widget-library" aria-labelledby="today-widget-library-heading">
    <h3 id="today-widget-library-heading">{s.libraryHeading}</h3><p>{s.libraryHint}</p>
    {libraryGroups.length?libraryGroups.map(group=><section key={group.category} className="today-widget-library-category" aria-labelledby={`today-library-${group.category}`}>
     <h4 id={`today-library-${group.category}`}>{categoryLabel(group.category)}</h4>
     <div className="today-widget-library-grid">{group.definitions.map(definition=><article key={definition.id} className="today-widget-library-card" data-library-widget={definition.id}>
      <div className="today-widget-library-preview" role="img" aria-label={s.safePreview}><span/><span/><span/></div>
      <div className="today-widget-library-copy"><h5>{labelFor(definition.id)}</h5><p>{descriptionFor(definition.id)}</p></div>
      <div className="today-widget-library-sizes" aria-label={s.supportedSizes}>{sizeOptions(definition.id).map(size=><span key={size}>{s[size]}</span>)}</div>
      <button type="button" ref={element=>{if(element)libraryButtons.current.set(definition.id,element);else libraryButtons.current.delete(definition.id)}} className="secondary" onClick={()=>addWidget(definition.id)} disabled={busy}>{s.add}</button>
     </article>)}</div>
    </section>):<p className="today-widget-library-empty">{s.allPlaced}</p>}
   </section>
   <div className="today-layout-actions">
    <button type="button" className="ghost" disabled={busy} onClick={()=>{clearDrag();setDraft(defaultTodayWidgets());setAnnouncement('')}}>{s.reset}</button>
    <button type="button" className="secondary" disabled={busy} onClick={cancelEditor}>{s.cancel}</button>
    <button type="button" className="primary" disabled={busy||conflict} onClick={save}>{s.save}</button>
   </div>
   <h3>{s.preview}</h3>
  </section>}
  {active.length>0?<div className={`app-widget-grid today-widget-grid${gridClassName?` ${gridClassName}`:''}`} data-testid={gridTestId||undefined}>{active.map(render)}</div>:<p className="today-calm">{s.empty}</p>}
 </div>;
}
