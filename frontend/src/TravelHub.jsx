import {useEffect,useMemo,useState} from 'react';
import {useTranslation} from 'react-i18next';
import {api} from './api';
import {Icon} from './icons';
import {useFamilyPermissions} from './family-permissions';
import {confirmAction} from './feedback';
import FileDropZone from './FileDropZone';
import './travel.css';

const DAY=86400000;
const CONCRETE_PRECISIONS=new Set(['range','exact']);
const APPROXIMATE_PRECISIONS=new Set(['year','season','month']);
const CONCRETE_STAGES=new Set(['scheduled','active','completed']);

function dateKey(value){
 if(!value)return null;
 const [y,m,d]=String(value).slice(0,10).split('-').map(Number);
 return Date.UTC(y,m-1,d);
}
function todayKey(){const now=new Date();return Date.UTC(now.getFullYear(),now.getMonth(),now.getDate())}
function countdown(row,w){
 if(!CONCRETE_PRECISIONS.has(row.date_precision||'exact'))return '';
 const today=todayKey(),start=dateKey(row.starts_on),end=dateKey(row.ends_on);
 if(start==null||end==null)return '';
 const until=Math.round((start-today)/DAY);
 if(until>1)return w.inDays.replace('{{count}}',until);
 if(until===1)return w.tomorrow;
 if(until===0)return w.today;
 if(today<=end){const day=Math.round((today-start)/DAY)+1,total=Math.round((end-start)/DAY)+1;return w.tripDay.replace('{{day}}',day).replace('{{total}}',total)}
 return w.finished;
}
function displayDate(value,locale){
 if(!value)return '–';
 const [y,m,d]=String(value).split('-').map(Number);
 return new Date(y,m-1,d).toLocaleDateString(locale,{day:'2-digit',month:'short',year:'numeric'});
}
function periodLabel(row,locale,w){
 const precision=row.date_precision||((row.starts_on||row.ends_on)?'exact':'unknown');
 if(precision==='unknown')return w.whenUnknown;
 if(precision==='year')return row.date_year?String(row.date_year):w.whenUnknown;
 if(precision==='season')return row.date_year&&row.date_season?`${w.seasons[row.date_season]||row.date_season} ${row.date_year}`:w.whenUnknown;
 if(precision==='month'&&row.date_year&&row.date_month){
  return new Intl.DateTimeFormat(locale,{month:'long',year:'numeric'}).format(new Date(Number(row.date_year),Number(row.date_month)-1,1));
 }
 return `${displayDate(row.starts_on,locale)} – ${displayDate(row.ends_on,locale)}`;
}
function memberLabel(member){return member?.display_name||member?.username||String(member?.id||'')}
function formFromTrip(row){
 return {
  title:row?.title||'',destination:row?.destination||'',stage:row?.stage||'idea',
  date_precision:row?.date_precision||((row?.starts_on||row?.ends_on)?'exact':'unknown'),
  date_year:row?.date_year||'',date_month:row?.date_month||'',date_season:row?.date_season||'',
  starts_on:row?.starts_on||'',ends_on:row?.ends_on||'',notes:row?.notes||'',participants:(row?.participants||[]).map(String),updated_at:row?.updated_at||null,
 };
}
function payloadFromForm(form,familyId,isEdit){
 const payload={
  family:familyId,title:form.title.trim(),destination:form.destination.trim(),stage:form.stage,
  date_precision:form.date_precision,notes:form.notes,participants:form.participants,
 };
 if(APPROXIMATE_PRECISIONS.has(form.date_precision))payload.date_year=Number(form.date_year);
 if(form.date_precision==='month')payload.date_month=Number(form.date_month);
 if(form.date_precision==='season')payload.date_season=form.date_season;
 if(CONCRETE_PRECISIONS.has(form.date_precision)){
  payload.starts_on=form.starts_on;
  payload.ends_on=form.ends_on;
 }
 if(isEdit&&form.updated_at)payload.expected_updated_at=form.updated_at;
 return payload;
}

export default function TravelHub({family,onBack,onOpen}){
 const {i18n}=useTranslation();const en=i18n.language.startsWith('en');
 const w=en?{
  title:'Trips',hint:'Start with an idea and make the trip more concrete together over time.',newTrip:'Plan trip',editTrip:'Edit trip',tripTitle:'Trip name',destination:'Destination',when:'When?',precision:'How precise?',year:'Year',month:'Month',season:'Season',start:'From',end:'To',notes:'Notes',stage:'Planning status',participants:'Travellers',participantsHint:'Choose the family members joining this trip.',noParticipants:'No family members available.',morePlanning:'More planning details',save:'Save',cancel:'Cancel',delete:'Delete trip',deleteConfirm:'Delete this trip and its private album?',empty:'No trips planned yet.',open:'Open',inDays:'{{count}} days to go',tomorrow:'Leaving tomorrow',today:'Leaving today',tripDay:'Day {{day}} of {{total}}',finished:'Trip finished',photos:'Private album',addPhotos:'Add photos',photoHint:'JPEG, PNG or WebP. Photos are resized and metadata including GPS is removed on the server.',caption:'Caption for this upload (optional)',removePhoto:'Delete photo',loading:'Loading …',failed:'Could not load trips.',retry:'Try again',calendar:'Calendar',tasks:'Tasks / packing',shopping:'Shopping',expenses:'Trip expenses',expensesOpening:'Opening trip expenses …',expensesUnavailable:'No trip expense area has been created yet.',expensesArchived:'The linked trip expense area is archived. Open Expenses to manage it.',planning:'Continue planning in FamilyOS',dateError:'End date must not be before start date.',datesRequired:'Please enter both start and end date.',yearRequired:'Please enter a year.',seasonRequired:'Please choose a season.',monthRequired:'Please choose a month.',conflict:'Someone changed this trip while you were editing. The current version has been reloaded.',whenUnknown:'Timing open',back:'Back',precisions:{unknown:'Not decided yet',year:'Year',season:'Season',month:'Month',range:'Date range',exact:'Exact dates'},stages:{idea:'Idea',planning:'Planning',scheduled:'Scheduled',active:'Active',completed:'Completed',archived:'Archived'},seasons:{spring:'Spring',summer:'Summer',autumn:'Autumn',winter:'Winter'}
 }:{
  title:'Reisen',hint:'Mit einer Idee starten und die Reise gemeinsam Schritt für Schritt konkretisieren.',newTrip:'Reise planen',editTrip:'Reise bearbeiten',tripTitle:'Reisename',destination:'Ziel',when:'Wann?',precision:'Wie genau?',year:'Jahr',month:'Monat',season:'Jahreszeit',start:'Von',end:'Bis',notes:'Notizen',stage:'Planungsstatus',participants:'Reisende',participantsHint:'Wähle die Familienmitglieder aus, die mitreisen.',noParticipants:'Keine Familienmitglieder verfügbar.',morePlanning:'Weitere Planungsdetails',save:'Speichern',cancel:'Abbrechen',delete:'Reise löschen',deleteConfirm:'Diese Reise und ihr privates Album löschen?',empty:'Noch keine Reise geplant.',open:'Öffnen',inDays:'Noch {{count}} Tage',tomorrow:'Morgen geht es los',today:'Heute geht es los',tripDay:'Tag {{day}} von {{total}}',finished:'Reise beendet',photos:'Privates Fotoalbum',addPhotos:'Fotos hinzufügen',photoHint:'JPEG, PNG oder WebP. Fotos werden verkleinert und Metadaten inklusive GPS serverseitig entfernt.',caption:'Bildunterschrift für diesen Upload (optional)',removePhoto:'Foto löschen',loading:'Wird geladen …',failed:'Reisen konnten nicht geladen werden.',retry:'Erneut versuchen',calendar:'Kalender',tasks:'Aufgaben / Packen',shopping:'Einkauf',expenses:'Reisekosten',expensesOpening:'Reisekosten werden geöffnet …',expensesUnavailable:'Für diese Reise wurde noch kein Reisekosten-Bereich angelegt.',expensesArchived:'Der verknüpfte Reisekosten-Bereich ist archiviert. Verwalte ihn unter Ausgaben.',planning:'In FamilyOS weiterplanen',dateError:'Das Enddatum darf nicht vor dem Startdatum liegen.',datesRequired:'Bitte Start- und Enddatum angeben.',yearRequired:'Bitte ein Jahr angeben.',seasonRequired:'Bitte eine Jahreszeit wählen.',monthRequired:'Bitte einen Monat wählen.',conflict:'Jemand hat diese Reise während deiner Bearbeitung geändert. Der aktuelle Stand wurde neu geladen.',whenUnknown:'Zeitraum offen',back:'Zurück',precisions:{unknown:'Noch offen',year:'Jahr',season:'Jahreszeit',month:'Monat',range:'Zeitraum',exact:'Exakte Daten'},stages:{idea:'Idee',planning:'Planung',scheduled:'Geplant',active:'Aktiv',completed:'Abgeschlossen',archived:'Archiviert'},seasons:{spring:'Frühling',summer:'Sommer',autumn:'Herbst',winter:'Winter'}
 };
 const familyId=family?.id;const {role}=useFamilyPermissions(family);const canManage=role==='owner'||role==='adult';
 const participantOptions=(family?.memberships||[]).filter(member=>member?.id);
 const emptyForm=formFromTrip(null);
 const [rows,setRows]=useState([]),[loading,setLoading]=useState(true),[error,setError]=useState(''),[editing,setEditing]=useState(null),[selectedId,setSelectedId]=useState(null),[busy,setBusy]=useState(false),[caption,setCaption]=useState('');
 const [form,setForm]=useState(emptyForm);
 const selected=useMemo(()=>rows.find(row=>String(row.id)===String(selectedId))||null,[rows,selectedId]);
 const selectedParticipants=(selected?.participants||[]).map(id=>participantOptions.find(member=>String(member.id)===String(id))).filter(Boolean);
 async function load(){if(!familyId)return;setLoading(true);try{const data=await api(`/trips/?family=${encodeURIComponent(familyId)}`);const next=data.results||data||[];setRows(next);if(selectedId&&!next.some(row=>String(row.id)===String(selectedId)))setSelectedId(null)}catch(e){setError(e.message||w.failed)}finally{setLoading(false)}}
 useEffect(()=>{setError('');load()},[familyId]);
 function beginCreate(){setEditing('new');setForm(formFromTrip(null));setError('')}
 function beginEdit(row){setEditing(row.id);setForm(formFromTrip(row));setError('')}
 function closeEditor(){setEditing(null);setForm(formFromTrip(null))}
 async function save(e){
  e.preventDefault();
  if(CONCRETE_PRECISIONS.has(form.date_precision)&&(!form.starts_on||!form.ends_on)){setError(w.datesRequired);return}
  if(CONCRETE_PRECISIONS.has(form.date_precision)&&form.ends_on<form.starts_on){setError(w.dateError);return}
  if(APPROXIMATE_PRECISIONS.has(form.date_precision)&&!form.date_year){setError(w.yearRequired);return}
  if(form.date_precision==='season'&&!form.date_season){setError(w.seasonRequired);return}
  if(form.date_precision==='month'&&!form.date_month){setError(w.monthRequired);return}
  setBusy(true);setError('');
  try{
   const isEdit=editing!=='new';const payload=payloadFromForm(form,familyId,isEdit);
   if(isEdit)await api(`/trips/${editing}/`,{method:'PATCH',body:JSON.stringify(payload)});else await api('/trips/',{method:'POST',body:JSON.stringify(payload)});
   closeEditor();await load();
  }catch(e){
   if(e.status===409||e.code==='trip_conflict'){closeEditor();await load();setError(w.conflict)}else setError(e.message);
  }finally{setBusy(false)}
 }
 async function removeTrip(row){if(!await confirmAction({title:w.deleteConfirm,confirmLabel:w.delete,cancelLabel:w.cancel,danger:true}))return;setBusy(true);try{await api(`/trips/${row.id}/`,{method:'DELETE'});if(String(selectedId)===String(row.id))setSelectedId(null);await load()}catch(e){setError(e.message)}finally{setBusy(false)}}
 async function uploadPhotos(files){if(!selected||!files?.length)return;setBusy(true);setError('');try{const body=new FormData();files.forEach(file=>body.append('images',file));if(caption.trim())body.append('caption',caption.trim());const updated=await api(`/trips/${selected.id}/photos/`,{method:'POST',body});setRows(old=>old.map(row=>row.id===updated.id?updated:row));setCaption('')}catch(e){setError(e.message)}finally{setBusy(false)}}
 async function removePhoto(photo){if(!await confirmAction({title:w.removePhoto,confirmLabel:w.removePhoto,cancelLabel:w.cancel,danger:true}))return;setBusy(true);try{await api(`/trip-photos/${photo.id}/`,{method:'DELETE'});await load()}catch(e){setError(e.message)}finally{setBusy(false)}}
 async function openExpenses(){
  if(!selected||busy)return;
  setBusy(true);setError('');let ledger=null;
  try{
   try{
    ledger=await api(`/expense-ledgers/for-trip/?family=${encodeURIComponent(familyId)}&trip=${encodeURIComponent(selected.id)}`);
   }catch(e){
    if(e.status===404&&canManage){
     ledger=await api('/expense-ledgers/for-trip/',{method:'POST',body:JSON.stringify({family:familyId,trip:selected.id})});
    }else if(e.status===404){setError(w.expensesUnavailable);return}
    else if(e.status===409){setError(w.expensesArchived);return}
    else throw e;
   }
  }catch(e){
   if(e.status===409)setError(w.expensesArchived);else setError(e.message||w.failed);
   return;
  }finally{setBusy(false)}
  if(!ledger?.id)return;
  const opened=onOpen('expenses');
  if(opened===false)return;
  const url=new URL(location.href);
  url.searchParams.set('ledger',ledger.id);
  history.replaceState(history.state,'',`${url.pathname}${url.search}${url.hash}`);
 }
 const locale=en?'en-GB':'de-DE';
 if(selected)return <section className="travel-hub"><header className="page-head"><button className="icon-btn" aria-label={w.back} onClick={()=>setSelectedId(null)}><Icon name="back"/></button><div><h1>{selected.title}</h1><p>{selected.destination||w.title}</p></div></header>{error&&<div className="card travel-error" role="alert">{error}</div>}<section className="card travel-hero"><div><strong>{countdown(selected,w)||w.stages[selected.stage]||w.planning}</strong><span>{periodLabel(selected,locale,w)}</span></div><span className="travel-badge">{w.stages[selected.stage]||selected.stage}</span></section>{selectedParticipants.length>0&&<section className="card travel-participants"><h2>{w.participants}</h2><div className="travel-participant-chips">{selectedParticipants.map(member=><span className="travel-participant-chip" key={member.id}>{memberLabel(member)}</span>)}</div></section>}{selected.notes&&<section className="card travel-notes"><p>{selected.notes}</p></section>}<section className="card"><h2>{w.planning}</h2><div className="travel-links"><button className="secondary" onClick={()=>onOpen('calendar')}><Icon name="calendar"/>{w.calendar}</button><button className="secondary" onClick={()=>onOpen('tasks')}><Icon name="tasks"/>{w.tasks}</button><button className="secondary" onClick={()=>onOpen('shopping')}><Icon name="shopping"/>{w.shopping}</button><button className="secondary" disabled={busy} onClick={openExpenses}><Icon name="receipt"/>{busy?w.expensesOpening:w.expenses}</button></div></section><section className="card travel-album"><h2>{w.photos}</h2>{selected.can_add_photos&&<><label>{w.caption}<input maxLength={240} value={caption} onChange={e=>setCaption(e.target.value)}/></label><FileDropZone multiple accept="image/jpeg,image/png,image/webp" disabled={busy} icon="camera" title={w.addPhotos} hint={w.photoHint} onFiles={uploadPhotos}/></>}{selected.photos?.length?<div className="travel-photos">{selected.photos.map((photo,index)=><figure key={photo.id}><a href={photo.url} target="_blank" rel="noreferrer"><img src={photo.url} width={photo.width} height={photo.height} loading="lazy" alt={`${selected.title} · ${index+1}`}/></a>{photo.caption&&<figcaption>{photo.caption}</figcaption>}{photo.can_delete&&<button className="ghost-danger compact" disabled={busy} onClick={()=>removePhoto(photo)}>{w.removePhoto}</button>}</figure>)}</div>:<p className="travel-muted">{w.addPhotos}</p>}</section>{selected.can_manage&&<div className="travel-detail-actions"><button className="secondary" onClick={()=>beginEdit(selected)}>{w.editTrip}</button><button className="ghost-danger" disabled={busy} onClick={()=>removeTrip(selected)}>{w.delete}</button></div>}{editing&&<TripEditor w={w} locale={locale} form={form} setForm={setForm} save={save} close={closeEditor} busy={busy} members={participantOptions}/>}</section>;
 return <section className="travel-hub"><header className="page-head"><button className="icon-btn" aria-label={w.back} onClick={onBack}><Icon name="back"/></button><div><h1>{w.title}</h1><p>{w.hint}</p></div></header>{canManage&&!editing&&<button className="primary travel-new" onClick={beginCreate}><Icon name="plus"/>{w.newTrip}</button>}{error&&<div className="card travel-error" role="alert">{error} {!editing&&<button onClick={load}>{w.retry}</button>}</div>}{editing&&<TripEditor w={w} locale={locale} form={form} setForm={setForm} save={save} close={closeEditor} busy={busy} members={participantOptions}/>}<div className="travel-list">{rows.map(row=><article className={`card travel-card ${row.stage==='archived'||row.archived?'is-archived':''}`} key={row.id}><div className="travel-card-main"><span className="travel-countdown">{countdown(row,w)||w.stages[row.stage]||w.planning}</span><h2>{row.title}</h2>{row.destination&&<p><Icon name="location" size={14}/>{row.destination}</p>}<small>{periodLabel(row,locale,w)}</small><span className="travel-badge">{w.stages[row.stage]||row.stage}</span></div><div className="travel-card-actions"><button className="primary compact" onClick={()=>setSelectedId(row.id)}>{w.open}</button>{row.can_manage&&<button className="secondary compact" onClick={()=>beginEdit(row)}>{w.editTrip}</button>}</div></article>)}</div>{loading&&<p role="status">{w.loading}</p>}{!loading&&!rows.length&&!error&&!editing&&<div className="card travel-empty"><Icon name="route" size={34}/><strong>{w.empty}</strong>{canManage&&<button className="primary" onClick={beginCreate}>{w.newTrip}</button>}</div>}</section>
}

function TripEditor({w,locale,form,setForm,save,close,busy,members}){
 const concrete=CONCRETE_PRECISIONS.has(form.date_precision);
 const monthNames=Array.from({length:12},(_,index)=>new Intl.DateTimeFormat(locale,{month:'long'}).format(new Date(2028,index,1)));
 const availableStages=Object.entries(w.stages).filter(([key])=>concrete||!CONCRETE_STAGES.has(key));
 function changePrecision(value){setForm(old=>({...old,date_precision:value,stage:!CONCRETE_PRECISIONS.has(value)&&CONCRETE_STAGES.has(old.stage)?'planning':old.stage,starts_on:CONCRETE_PRECISIONS.has(value)?old.starts_on:'',ends_on:CONCRETE_PRECISIONS.has(value)?old.ends_on:'',date_year:APPROXIMATE_PRECISIONS.has(value)?old.date_year:'',date_month:value==='month'?old.date_month:'',date_season:value==='season'?old.date_season:''}))}
 function toggleParticipant(id,checked){setForm(old=>({...old,participants:checked?[...old.participants.filter(value=>value!==id),id]:old.participants.filter(value=>value!==id)}))}
 return <form className="card travel-editor" onSubmit={save}><h2>{form.updated_at?w.editTrip:w.newTrip}</h2><label>{w.tripTitle}<input required maxLength={160} value={form.title} onChange={e=>setForm(old=>({...old,title:e.target.value}))}/></label><label>{w.destination}<input maxLength={160} value={form.destination} onChange={e=>setForm(old=>({...old,destination:e.target.value}))}/></label><fieldset className="travel-period"><legend>{w.when}</legend><label>{w.precision}<select value={form.date_precision} onChange={e=>changePrecision(e.target.value)}>{Object.entries(w.precisions).map(([key,label])=><option value={key} key={key}>{label}</option>)}</select></label>{form.date_precision==='year'&&<label>{w.year}<input type="number" min="1" max="9999" required value={form.date_year} onChange={e=>setForm(old=>({...old,date_year:e.target.value}))}/></label>}{form.date_precision==='season'&&<div className="travel-date-grid"><label>{w.year}<input type="number" min="1" max="9999" required value={form.date_year} onChange={e=>setForm(old=>({...old,date_year:e.target.value}))}/></label><label>{w.season}<select required value={form.date_season} onChange={e=>setForm(old=>({...old,date_season:e.target.value}))}><option value="">–</option>{Object.entries(w.seasons).map(([key,label])=><option value={key} key={key}>{label}</option>)}</select></label></div>}{form.date_precision==='month'&&<div className="travel-date-grid"><label>{w.year}<input type="number" min="1" max="9999" required value={form.date_year} onChange={e=>setForm(old=>({...old,date_year:e.target.value}))}/></label><label>{w.month}<select required value={form.date_month} onChange={e=>setForm(old=>({...old,date_month:e.target.value}))}><option value="">–</option>{monthNames.map((label,index)=><option value={index+1} key={label}>{label}</option>)}</select></label></div>}{concrete&&<div className="travel-date-grid"><label>{w.start}<input required type="date" value={form.starts_on} onChange={e=>setForm(old=>({...old,starts_on:e.target.value}))}/></label><label>{w.end}<input required type="date" min={form.starts_on||undefined} value={form.ends_on} onChange={e=>setForm(old=>({...old,ends_on:e.target.value}))}/></label></div>}</fieldset><details className="travel-advanced"><summary>{w.morePlanning}</summary><div className="travel-advanced-fields"><fieldset className="travel-participant-picker"><legend>{w.participants}</legend><p>{w.participantsHint}</p>{members.length?<div className="travel-participant-grid">{members.map(member=>{const id=String(member.id);return <label className="travel-participant-option" key={id}><input type="checkbox" checked={form.participants.includes(id)} onChange={e=>toggleParticipant(id,e.target.checked)}/><span>{memberLabel(member)}</span></label>})}</div>:<span className="travel-muted">{w.noParticipants}</span>}</fieldset><label>{w.stage}<select value={form.stage} onChange={e=>setForm(old=>({...old,stage:e.target.value}))}>{availableStages.map(([key,label])=><option value={key} key={key}>{label}</option>)}</select></label><label>{w.notes}<textarea rows={4} maxLength={10000} value={form.notes} onChange={e=>setForm(old=>({...old,notes:e.target.value}))}/></label></div></details><div className="travel-editor-actions"><button type="button" className="secondary" onClick={close} disabled={busy}>{w.cancel}</button><button className="primary" disabled={busy}>{w.save}</button></div></form>
}
