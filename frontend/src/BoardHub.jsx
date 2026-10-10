import {useEffect,useMemo,useState} from 'react';
import {useTranslation} from 'react-i18next';
import {api} from './api';
import {Icon} from './icons';
import {useFamilyPermissions} from './family-permissions';
import {confirmAction} from './feedback';
import FileDropZone from './FileDropZone';
import './board.css';

const unwrap=value=>value?.results||value||[];
const PIN_TYPES=['note','photo','event','task','note_ref','shopping'];

export default function BoardHub({family,onBack}){
 const {i18n}=useTranslation();const en=i18n.language.startsWith('en');const familyId=family?.id;
 const w=en?{
  title:'Pinboard',eyebrow:'Shared family space',hint:'Keep the things your family needs in view — notes, photos, events, tasks and shopping.',pin:'Pin something',type:'What do you want to pin?',note:'Note',photo:'Photo',event:'Event',task:'Task',note_ref:'Family note',shopping:'Shopping',message:'Note text',photos:'Add photos',publish:'Pin it',cancel:'Cancel',edit:'Edit',remove:'Remove',save:'Save',more:'Load more',empty:'Your pinboard is ready for the first important thing.',loading:'Loading …',confirm:'Remove this pin?',limit:'Up to four JPEG, PNG or WebP images, 10 MB each. Photos are resized and metadata removed on the server.',back:'Back',failed:'Could not load the pinboard.',retry:'Try again',removePhoto:'Remove photo',shared:'Visible to family members who are allowed to see the linked content.',choose:'Choose an existing item',noChoices:'Nothing suitable is available yet.',unavailable:'No longer available',open:'Open',moveUp:'Move earlier',moveDown:'Move later',arrange:'Arrange pinboard',caption:'Optional caption',pinnedBy:'Pinned by'
 }:{
  title:'Pinnwand',eyebrow:'Gemeinsam im Blick',hint:'Haltet fest, was eure Familie gerade braucht – Notizen, Fotos, Termine, Aufgaben und Einkauf.',pin:'Anpinnen',type:'Was möchtest du anpinnen?',note:'Notizzettel',photo:'Foto',event:'Termin',task:'Aufgabe',note_ref:'Notiz',shopping:'Einkauf',message:'Notizzettel',photos:'Fotos hinzufügen',publish:'Anpinnen',cancel:'Abbrechen',edit:'Bearbeiten',remove:'Entfernen',save:'Speichern',more:'Weitere laden',empty:'Eure Pinnwand wartet auf den ersten wichtigen Punkt.',loading:'Wird geladen …',confirm:'Diesen Pin entfernen?',limit:'Bis zu vier Bilder als JPEG, PNG oder WebP, je 10 MB. Fotos werden auf dem Server verkleinert und Metadaten entfernt.',back:'Zurück',failed:'Pinnwand konnte nicht geladen werden.',retry:'Erneut versuchen',removePhoto:'Foto entfernen',shared:'Sichtbar für Familienmitglieder, die auch den verknüpften Inhalt sehen dürfen.',choose:'Vorhandenen Inhalt auswählen',noChoices:'Noch kein passender Inhalt vorhanden.',unavailable:'Nicht mehr verfügbar',open:'Öffnen',moveUp:'Weiter nach vorne',moveDown:'Weiter nach hinten',arrange:'Pinnwand anordnen',caption:'Optionale Beschriftung',pinnedBy:'Angepinnt von'
 };
 const [rows,setRows]=useState([]),[next,setNext]=useState(null),[loading,setLoading]=useState(true),[error,setError]=useState(''),[compose,setCompose]=useState(false),[editing,setEditing]=useState(null),[kind,setKind]=useState('note'),[text,setText]=useState(''),[files,setFiles]=useState([]),[targetId,setTargetId]=useState(''),[choices,setChoices]=useState([]),[choicesBusy,setChoicesBusy]=useState(false),[busy,setBusy]=useState(false);
 const {role}=useFamilyPermissions(family);const canPost=!!role&&role!=='guest';

 async function load(path=`/board/?family=${encodeURIComponent(familyId)}`,append=false){
  setLoading(true);setError('');
  try{const data=await api(path);let incoming=unwrap(data);const target=new URLSearchParams(location.search).get('post');if(!append&&target&&!incoming.some(row=>String(row.id)===target)){try{const focused=await api(`/board/${encodeURIComponent(target)}/?family=${encodeURIComponent(familyId)}`);incoming=[focused,...incoming]}catch{}}
   setRows(previous=>append?[...previous,...incoming]:incoming);
   if(target)setTimeout(()=>document.getElementById(`pin-${target}`)?.scrollIntoView({block:'nearest'}),100);
   setNext(data?.next?new URL(data.next,location.origin).pathname.replace(/^\/api/,'')+new URL(data.next,location.origin).search:null);
  }catch(e){setError(e.message||w.failed)}finally{setLoading(false)}
 }
 useEffect(()=>{if(!familyId)return;load();if(new URLSearchParams(location.search).get('compose')==='1'&&canPost)setCompose(true)},[familyId,canPost]);
 useEffect(()=>{if(compose&&!editing&&!['note','photo'].includes(kind))loadChoices(kind)},[compose,kind,editing,familyId]);

 function close(){setCompose(false);setEditing(null);setKind('note');setText('');setFiles([]);setTargetId('');setChoices([]);setError('')}
 function startCompose(nextKind='note'){close();setKind(nextKind);setCompose(true)}
 function addFiles(picked){if(picked.length+files.length>4||picked.some(file=>file.size>10*1024*1024)){setError(w.limit);return}setError('');setFiles(old=>[...old,...picked])}
 async function loadChoices(nextKind){setChoicesBusy(true);setChoices([]);setTargetId('');try{
  if(nextKind==='event'){const result=unwrap(await api('/events/')).filter(row=>String(row.family)===String(familyId));setChoices(result.map(row=>({id:row.id,title:row.title,meta:formatDate(row.starts_at,en)})))}
  else if(nextKind==='task'){const result=unwrap(await api('/tasks/')).filter(row=>String(row.family)===String(familyId)&&!row.completed_at);setChoices(result.map(row=>({id:row.id,title:row.title,meta:row.due_at?formatDate(row.due_at,en):''}))}
  else if(nextKind==='note_ref'){const result=unwrap(await api(`/notes/?family=${encodeURIComponent(familyId)}`));setChoices(result.map(row=>({id:row.id,title:row.title||w.note_ref,meta:(row.body||'').replace(/\s+/g,' ').slice(0,90)})))}
  else if(nextKind==='shopping'){const lists=unwrap(await api('/shopping-lists/')).filter(row=>String(row.family)===String(familyId));setChoices(lists.flatMap(list=>(list.items||[]).filter(item=>!item.checked).map(item=>({id:item.id,title:item.name,meta:list.name}))));}
 }catch(e){setError(e.message||w.failed)}finally{setChoicesBusy(false)}}
 async function submit(e){e.preventDefault();setBusy(true);setError('');try{
  if(editing){await api(`/board/${editing.id}/`,{method:'PATCH',body:JSON.stringify({text})})}
  else if(['note','photo'].includes(kind)){const body=new FormData();body.append('family',familyId);body.append('kind',kind);body.append('text',text);files.forEach(file=>body.append('images',file));await api('/board/',{method:'POST',body})}
  else await api('/board/',{method:'POST',body:JSON.stringify({family:familyId,kind,target_id:targetId,text:text.trim()})});
  close();await load();
 }catch(e){setError(e.message||w.failed)}finally{setBusy(false)}}
 async function removePhoto(image){setBusy(true);try{await api(`/board-images/${image.id}/`,{method:'DELETE'});setEditing(old=>({...old,images:old.images.filter(row=>row.id!==image.id)}));await load()}catch(e){setError(e.message)}finally{setBusy(false)}}
 async function remove(row){if(!await confirmAction({title:w.confirm,confirmLabel:w.remove,cancelLabel:w.cancel,danger:true}))return;setBusy(true);try{await api(`/board/${row.id}/`,{method:'DELETE'});setRows(old=>old.filter(pin=>pin.id!==row.id))}catch(e){setError(e.message)}finally{setBusy(false)}}
 async function move(row,delta){const index=rows.findIndex(item=>item.id===row.id),other=index+delta;if(index<0||other<0||other>=rows.length)return;const reordered=[...rows];[reordered[index],reordered[other]]=[reordered[other],reordered[index]];setRows(reordered);try{await api('/board/reorder/',{method:'POST',body:JSON.stringify({family:familyId,ids:reordered.map(item=>item.id)})})}catch(e){setRows(rows);setError(e.message||w.failed)}}
 const selected=useMemo(()=>choices.find(item=>String(item.id)===String(targetId)),[choices,targetId]);

 return <section className="board-hub"><header className="page-head board-head"><button className="icon-btn" aria-label={w.back} onClick={onBack}><Icon name="back"/></button><div className="grow"><small>{w.eyebrow}</small><h1>{w.title}</h1><p>{w.hint}</p></div>{canPost&&!compose&&<button className="primary board-pin-button" onClick={()=>startCompose()}><Icon name="plus"/> {w.pin}</button>}</header>
 {error&&<div role="alert" className="card board-error">{error} {!compose&&<button onClick={()=>load()}>{w.retry}</button>}</div>}
 {compose&&<PinComposer w={w} kind={kind} setKind={value=>{setKind(value);setText('');setFiles([]);setTargetId('')}} text={text} setText={setText} files={files} addFiles={addFiles} setFiles={setFiles} choices={choices} choicesBusy={choicesBusy} targetId={targetId} setTargetId={setTargetId} selected={selected} editing={editing} busy={busy} onSubmit={submit} onClose={close} removePhoto={removePhoto}/>} 
 {!compose&&rows.length>0&&<div className="pinboard-guide"><Icon name="drag"/><span>{w.arrange}</span><small>{en?'Use the arrow controls on a card to change the shared order.':'Mit den Pfeilen an einer Karte änderst du die gemeinsame Reihenfolge.'}</small></div>}
 <div className="pinboard-grid" aria-live="polite">{rows.map((row,index)=><PinCard key={row.id} row={row} index={index} total={rows.length} w={w} en={en} busy={busy} onMove={move} onRemove={remove} onEdit={()=>{setEditing(row);setKind(row.kind);setText(row.text||'');setFiles([]);setCompose(true);window.scrollTo({top:0,behavior:'smooth'})}}/>)}</div>
 {loading&&<p role="status" className="board-loading">{w.loading}</p>}{!loading&&!error&&!rows.length&&!compose&&<button className="card board-empty" onClick={()=>canPost&&startCompose()} disabled={!canPost}><span><Icon name="plus"/></span><strong>{w.empty}</strong>{canPost&&<small>{w.pin}</small>}</button>}{next&&<button className="secondary board-more" disabled={loading} onClick={()=>load(next,true)}>{w.more}</button>}</section>
}

function PinComposer({w,kind,setKind,text,setText,files,addFiles,setFiles,choices,choicesBusy,targetId,setTargetId,selected,editing,busy,onSubmit,onClose,removePhoto}){
 const ref=!['note','photo'].includes(kind);const valid=editing?Boolean(text.trim()||editing.images?.length):kind==='photo'?files.length>0:kind==='note'?Boolean(text.trim()):Boolean(targetId);
 return <form className="card pin-composer" onSubmit={onSubmit}><div className="pin-composer-head"><div><small>{editing?w.edit:w.pin}</small><h2>{editing?typeLabel(kind,w):w.type}</h2></div><button type="button" className="icon-btn" onClick={onClose} aria-label={w.cancel}><Icon name="close"/></button></div>
 {!editing&&<div className="pin-type-grid" role="group" aria-label={w.type}>{PIN_TYPES.map(type=><button type="button" key={type} className={kind===type?'active':''} onClick={()=>setKind(type)}><span><Icon name={pinIcon(type)}/></span>{w[type]}</button>)}</div>}
 {kind==='note'&&<label>{w.message}<textarea autoFocus rows={5} maxLength={10000} value={text} onChange={e=>setText(e.target.value)}/></label>}
 {kind==='photo'&&!editing&&<><label>{w.caption}<textarea rows={3} maxLength={10000} value={text} onChange={e=>setText(e.target.value)}/></label><FileDropZone multiple accept="image/jpeg,image/png,image/webp" disabled={busy||files.length>=4} icon="upload" title={w.photos} hint={w.limit} onFiles={addFiles}/><ul className="board-files">{files.map((file,index)=><li key={`${file.name}-${index}`}><FilePreview file={file}/><span>{file.name}</span><button type="button" aria-label={`${w.removePhoto}: ${file.name}`} onClick={()=>setFiles(old=>old.filter((_,i)=>i!==index))}>×</button></li>)}</ul></>}
 {editing?.images?.length>0&&<div className="board-edit-photos">{editing.images.map(image=><div key={image.id}><img src={image.url} alt=""/><button type="button" className="secondary compact" disabled={busy} onClick={()=>removePhoto(image)}>{w.removePhoto}</button></div>)}</div>}
 {ref&&!editing&&<><label>{w.choose}<select value={targetId} onChange={e=>setTargetId(e.target.value)} disabled={choicesBusy}><option value="">{choicesBusy?w.loading:w.choose}</option>{choices.map(item=><option key={item.id} value={item.id}>{item.title}{item.meta?` · ${item.meta}`:''}</option>)}</select></label>{!choicesBusy&&!choices.length&&<div className="pin-choice-empty"><Icon name={pinIcon(kind)}/><span>{w.noChoices}</span></div>}{selected&&<div className="pin-choice-preview"><span><Icon name={pinIcon(kind)}/></span><div><strong>{selected.title}</strong>{selected.meta&&<small>{selected.meta}</small>}</div></div>}</>}
 <p className="pin-privacy"><Icon name="lock"/>{w.shared}</p><div className="board-actions"><button type="button" className="secondary" onClick={onClose} disabled={busy}>{w.cancel}</button><button className="primary" disabled={busy||!valid}>{busy?w.loading:editing?w.save:w.publish}</button></div></form>
}

function PinCard({row,index,total,w,en,busy,onMove,onRemove,onEdit}){
 const unavailable=row.target?.available===false;const target=row.target&&!unavailable?row.target:null;const title=unavailable?w.unavailable:(target?.title||row.text||typeLabel(row.kind,w));const meta=target?.subtitle;const open=()=>{if(target?.url)location.assign(target.url)};
 return <article id={`pin-${row.id}`} className={`pin-card pin-${row.kind} ${unavailable?'pin-unavailable':''}`}><div className="pin-card-top"><span className="pin-kind"><Icon name={pinIcon(row.kind)}/>{typeLabel(row.kind,w)}</span><div className="pin-order" aria-label={w.arrange}>{row.can_reorder&&<><button className="icon-btn" disabled={busy||index===0} onClick={()=>onMove(row,-1)} aria-label={`${w.moveUp}: ${title}`}><span aria-hidden="true">↑</span></button><button className="icon-btn" disabled={busy||index===total-1} onClick={()=>onMove(row,1)} aria-label={`${w.moveDown}: ${title}`}><span aria-hidden="true">↓</span></button></>}</div></div>
 {row.images?.length>0&&<div className={`pin-photos pin-photos-${Math.min(row.images.length,4)}`}>{row.images.map((image,i)=><a key={image.id} href={image.url} target="_blank" rel="noreferrer" aria-label={`${w.photos} ${i+1}`}><img src={image.url} width={image.width} height={image.height} loading="lazy" alt=""/></a>)}</div>}
 {target?<button className="pin-target" onClick={open}><span className="pin-target-icon"><Icon name={pinIcon(row.kind)}/></span><span className="grow"><strong>{title}</strong>{meta&&<small>{formatTargetMeta(meta,en)}</small>}</span><Icon name="next"/></button>:<>{row.text&&<p className="pin-text">{row.text}</p>}{unavailable&&<div className="pin-target unavailable"><span className="pin-target-icon"><Icon name="lock"/></span><strong>{w.unavailable}</strong></div>}</>}
 <footer><span>{w.pinnedBy} <strong>{row.author_name}</strong> · <time dateTime={row.created_at}>{new Date(row.created_at).toLocaleDateString(en?'en-GB':'de-DE',{day:'2-digit',month:'short'})}</time></span><div>{row.can_edit&&['note','photo'].includes(row.kind)&&<button className="secondary compact" disabled={busy} onClick={onEdit}>{w.edit}</button>}{row.can_delete&&<button className="ghost-danger compact" disabled={busy} onClick={()=>onRemove(row)}>{w.remove}</button>}</div></footer></article>
}

function pinIcon(kind){return kind==='event'?'calendar':kind==='task'?'tasks':kind==='shopping'?'shopping':kind==='photo'?'camera':kind==='note_ref'?'lists':'light'}
function typeLabel(kind,w){return w[kind]||w.note}
function formatDate(value,en){if(!value)return'';const date=new Date(value);return Number.isNaN(date.getTime())?'':date.toLocaleString(en?'en-GB':'de-DE',{dateStyle:'short',timeStyle:'short'})}
function formatTargetMeta(value,en){if(typeof value==='string'&&/^\d{4}-\d{2}-\d{2}T/.test(value))return formatDate(value,en);return String(value||'').slice(0,140)}
function FilePreview({file}){const [url,setUrl]=useState('');useEffect(()=>{const value=URL.createObjectURL(file);setUrl(value);return()=>URL.revokeObjectURL(value)},[file]);return url?<img className="board-file-preview" src={url} alt=""/>:null}
