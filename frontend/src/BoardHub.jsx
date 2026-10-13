import {useEffect,useRef,useState} from 'react';
import {useTranslation} from 'react-i18next';
import {api,AUTH_CHANGED_EVENT} from './api';
import {Icon} from './icons';
import {useFamilyPermissions} from './family-permissions';
import {confirmAction} from './feedback';
import PinComposer from './PinComposer';
import PinCard from './PinBoardCard';
import './board.css';

const unwrap=value=>value?.results||value||[];
const SHARING_COPY={"fr": {"shared": "Le contenu lié conserve les autorisations de sa source. Épingler ne partage jamais la source automatiquement.", "inheritVisibility": "Cette épingle reprend la visibilité actuelle de sa source. Vous pouvez ensuite la restreindre sans modifier les droits de la source.", "shareSource": "Partager aussi la source", "visibleFor": "Visible par", "onlyMe": "Moi uniquement", "selectedPeople": "Personnes choisies", "wholeFamily": "Toute la famille", "choosePeople": "Choisir des personnes", "visibilityPrivate": "Vous seul pouvez voir cette épingle.", "visibilitySelected": "Seules les personnes choisies peuvent voir cette épingle.", "visibilityFamily": "Les membres actuels de la famille peuvent voir cette épingle dans les limites des droits de la source."}, "nl": {"shared": "Gekoppelde inhoud behoudt de rechten van de bron. Vastpinnen deelt de bron nooit automatisch.", "inheritVisibility": "Deze pin neemt de huidige zichtbaarheid van de bron over. Je kunt de pin daarna beperken zonder de bronrechten te wijzigen.", "shareSource": "Bron ook delen", "visibleFor": "Zichtbaar voor", "onlyMe": "Alleen ik", "selectedPeople": "Gekozen personen", "wholeFamily": "Hele familie", "choosePeople": "Personen kiezen", "visibilityPrivate": "Alleen jij kunt deze pin zien.", "visibilitySelected": "Alleen de gekozen personen kunnen deze pin zien.", "visibilityFamily": "Huidige familieleden kunnen deze pin zien binnen de rechten van de bron."}, "th": {"shared": "เนื้อหาที่เชื่อมโยงยังใช้สิทธิ์ของต้นฉบับ การปักหมุดไม่แชร์ต้นฉบับโดยอัตโนมัติ", "inheritVisibility": "หมุดนี้ใช้การมองเห็นปัจจุบันของต้นฉบับ คุณจำกัดการมองเห็นหมุดได้โดยไม่เปลี่ยนสิทธิ์ของต้นฉบับ", "shareSource": "แชร์ต้นฉบับด้วย", "visibleFor": "ผู้ที่มองเห็นได้", "onlyMe": "ฉันเท่านั้น", "selectedPeople": "บุคคลที่เลือก", "wholeFamily": "ทั้งครอบครัว", "choosePeople": "เลือกบุคคล", "visibilityPrivate": "มีเพียงคุณที่มองเห็นหมุดนี้ได้", "visibilitySelected": "มีเพียงบุคคลที่เลือกที่มองเห็นหมุดนี้ได้", "visibilityFamily": "สมาชิกปัจจุบันของครอบครัวมองเห็นหมุดนี้ได้ตามสิทธิ์ของต้นฉบับ"}};

export default function BoardHub({family,onBack}){
 const {i18n}=useTranslation();const en=i18n.language.startsWith('en');const familyId=family?.id;
 const w=en?{
  title:'Pinboard',eyebrow:'Shared family space',hint:'Keep the things your family needs in view — notes, photos, events, tasks and shopping.',pin:'Pin something',type:'What do you want to pin?',note:'Note',photo:'Photo',event:'Event',task:'Task',note_ref:'Family note',shopping:'Shopping item',shopping_list:'Shopping list',message:'Note text',photos:'Add photos',publish:'Pin it',cancel:'Cancel',edit:'Edit',remove:'Remove',save:'Save',more:'Load more',empty:'Your pinboard is ready for the first important thing.',loading:'Loading …',confirm:'Remove this pin?',limit:'Up to four JPEG, PNG or WebP images, 10 MB each. Photos are resized and metadata removed on the server.',back:'Back',failed:'Could not load the pinboard.',retry:'Try again',removePhoto:'Remove photo',shared:'Linked content stays limited by its original permissions. Pinning never shares the source automatically.',inheritVisibility:'This pin starts with the source’s current visibility. You can narrow the pin later without changing source permissions.',shareSource:'Also share source',choose:'Choose an existing item',noChoices:'Nothing suitable is available yet.',unavailable:'No longer available',open:'Open',moveUp:'Move earlier',moveDown:'Move later',arrange:'Arrange pinboard',caption:'Optional caption',pinnedBy:'Pinned by',searchEvent:'Search events',eventHint:'Search by title or date, then tap the event you want to pin.',openItems:'open items',visibleFor:'Visible to',onlyMe:'Only me',selectedPeople:'Selected people',wholeFamily:'Whole family',choosePeople:'Choose people',visibilityPrivate:'Only you can see this pin.',visibilitySelected:'Only the people you select can see this pin.',visibilityFamily:'Every current family member can see this pin, subject to source permissions.'
 }:{
  title:'Pinnwand',eyebrow:'Gemeinsam im Blick',hint:'Haltet fest, was eure Familie gerade braucht – Notizen, Fotos, Termine, Aufgaben und Einkauf.',pin:'Anpinnen',type:'Was möchtest du anpinnen?',note:'Notizzettel',photo:'Foto',event:'Termin',task:'Aufgabe',note_ref:'Notiz',shopping:'Einkaufsartikel',shopping_list:'Einkaufsliste',message:'Notizzettel',photos:'Fotos hinzufügen',publish:'Anpinnen',cancel:'Abbrechen',edit:'Bearbeiten',remove:'Entfernen',save:'Speichern',more:'Weitere laden',empty:'Eure Pinnwand wartet auf den ersten wichtigen Punkt.',loading:'Wird geladen …',confirm:'Diesen Pin entfernen?',limit:'Bis zu vier Bilder als JPEG, PNG oder WebP, je 10 MB. Fotos werden auf dem Server verkleinert und Metadaten entfernt.',back:'Zurück',failed:'Pinnwand konnte nicht geladen werden.',retry:'Erneut versuchen',removePhoto:'Foto entfernen',shared:'Verknüpfte Inhalte bleiben durch ihre ursprünglichen Rechte geschützt. Anpinnen teilt die Quelle niemals automatisch.',inheritVisibility:'Dieser Pin übernimmt beim Anpinnen die aktuelle Sichtbarkeit der Quelle. Danach kannst du den Pin enger stellen, ohne die Quellrechte zu ändern.',shareSource:'Quelle zusätzlich freigeben',choose:'Vorhandenen Inhalt auswählen',noChoices:'Noch kein passender Inhalt vorhanden.',unavailable:'Nicht mehr verfügbar',open:'Öffnen',moveUp:'Weiter nach vorne',moveDown:'Weiter nach hinten',arrange:'Pinnwand anordnen',caption:'Optionale Beschriftung',pinnedBy:'Angepinnt von',searchEvent:'Termine durchsuchen',eventHint:'Nach Titel oder Datum suchen und den gewünschten Termin antippen.',openItems:'offen',visibleFor:'Sichtbar für',onlyMe:'Nur mich',selectedPeople:'Ausgewählte Personen',wholeFamily:'Ganze Familie',choosePeople:'Personen auswählen',visibilityPrivate:'Nur du kannst diesen Pin sehen.',visibilitySelected:'Nur die ausgewählten Personen können diesen Pin sehen.',visibilityFamily:'Alle aktuellen Familienmitglieder können diesen Pin sehen – soweit die Quelle es erlaubt.'
 };
 Object.assign(w,SHARING_COPY[i18n.language.split('-')[0]]||{});
 const [rows,setRows]=useState([]),[next,setNext]=useState(null),[loading,setLoading]=useState(true),[error,setError]=useState(''),[compose,setCompose]=useState(false),[editing,setEditing]=useState(null),[kind,setKind]=useState('note'),[adapterKey,setAdapterKey]=useState(''),[text,setText]=useState(''),[files,setFiles]=useState([]),[targetId,setTargetId]=useState(''),[busy,setBusy]=useState(false),[visibility,setVisibility]=useState('family'),[selectedMembershipIds,setSelectedMembershipIds]=useState([]);
 const {role}=useFamilyPermissions(family);const canPost=!!role&&role!=='guest';const members=family?.memberships||[];
 const [rowScope,setRowScope]=useState(null);
 const visibleRows=rowScope===familyId?rows:[],visibleNext=rowScope===familyId?next:null;
 const boardLease=useRef({familyId,active:true,request:0});
 if(boardLease.current.familyId!==familyId){boardLease.current.active=false;boardLease.current={familyId,active:true,request:0}}
 const renderLease=boardLease.current;
 useEffect(()=>{const lease=boardLease.current;lease.active=true;const auth=event=>{if(event.detail?.authenticated===false){lease.active=false;setRows([]);setNext(null)}};window.addEventListener(AUTH_CHANGED_EVENT,auth);return()=>{lease.active=false;window.removeEventListener(AUTH_CHANGED_EVENT,auth)}},[familyId]);

 async function load(path=`/board/?family=${encodeURIComponent(familyId)}`,append=false){
  const lease=boardLease.current,request=++lease.request;if(!lease.active||lease.pending)return;const current=()=>lease.active&&lease===boardLease.current&&lease.request===request;
  setLoading(true);setError('');
  try{
   const data=await api(path);let incoming=unwrap(data);const target=new URLSearchParams(location.search).get('post');
   if(!append&&target&&!incoming.some(row=>String(row.id)===target)){try{const focused=await api(`/board/${encodeURIComponent(target)}/?family=${encodeURIComponent(familyId)}`);incoming=[focused,...incoming]}catch{}}
   if(!current())return;
   setRowScope(familyId);setRows(previous=>append?[...previous,...incoming]:incoming);
   if(target)setTimeout(()=>document.getElementById(`pin-${target}`)?.scrollIntoView({block:'nearest'}),100);
   setNext(data?.next?new URL(data.next,location.origin).pathname.replace(/^\/api/,'')+new URL(data.next,location.origin).search:null);
  }catch(e){if(current()){setRows([]);setNext(null);setError(e.message||w.failed)}}finally{if(current())setLoading(false)}
 }
 useEffect(()=>{setRows([]);setNext(null);setBusy(false);if(!familyId)return;load();if(new URLSearchParams(location.search).get('compose')==='1'&&canPost)setCompose(true)},[familyId,canPost]);

 function close(){setCompose(false);setEditing(null);setKind('note');setAdapterKey('');setText('');setFiles([]);setTargetId('');setVisibility('family');setSelectedMembershipIds([]);setError('')}
 function startCompose(nextKind='note'){close();setKind(nextKind);setCompose(true)}
 function addFiles(picked){if(picked.length+files.length>4||picked.some(file=>file.size>10*1024*1024)){setError(w.limit);return}setError('');setFiles(old=>[...old,...picked])}
 async function submit(e){
  e.preventDefault();setBusy(true);setError('');
  try{
   const sharing={visibility};if(visibility==='selected')sharing.selected_membership_ids=selectedMembershipIds;
   if(editing){const body={...sharing};if(['note','photo'].includes(editing.kind))body.text=text;await api(`/board/${editing.id}/`,{method:'PATCH',body:JSON.stringify(body)})}
   else if(['note','photo'].includes(kind)){const body=new FormData();body.append('family',familyId);body.append('kind',kind);body.append('text',text);body.append('visibility',visibility);if(visibility==='selected')selectedMembershipIds.forEach((id,index)=>body.append(`selected_membership_ids[${index}]`,id));files.forEach(file=>body.append('images',file));await api('/board/',{method:'POST',body})}
   else {const body={family:familyId,kind,target_id:targetId,text:text.trim()};if(adapterKey)body.adapter_key=adapterKey;await api('/board/',{method:'POST',body:JSON.stringify(body)})}
   close();await load();
  }catch(e){setError(e.message||w.failed)}finally{setBusy(false)}
 }
 async function removePhoto(image){setBusy(true);try{await api(`/board-images/${image.id}/`,{method:'DELETE'});setEditing(old=>({...old,images:old.images.filter(row=>row.id!==image.id)}));await load()}catch(e){setError(e.message)}finally{setBusy(false)}}
 function mutationCurrent(lease){return lease.active&&lease===boardLease.current&&lease.familyId===familyId}
 async function remove(row){
  const lease=renderLease;if(!mutationCurrent(lease)||lease.pending||!row.can_delete)return;
  lease.pending=true;setBusy(true);
  try{
   if(!await confirmAction({title:w.confirm,confirmLabel:w.remove,cancelLabel:w.cancel,danger:true})||!mutationCurrent(lease))return;
   ++lease.request;await api(`/board/${row.id}/`,{method:'DELETE'});
   if(mutationCurrent(lease))setRows(old=>old.filter(pin=>pin.id!==row.id));
  }catch(e){if(mutationCurrent(lease))setError(e.message||w.failed)}finally{lease.pending=false;if(mutationCurrent(lease))setBusy(false)}
 }
 async function move(row,delta){
  const lease=renderLease;if(!mutationCurrent(lease)||lease.pending||!row.can_reorder)return;
  const index=rows.findIndex(item=>item.id===row.id),other=index+delta;if(index<0||other<0||other>=rows.length)return;
  const before=rows,reordered=[...rows];[reordered[index],reordered[other]]=[reordered[other],reordered[index]];
  lease.pending=true;++lease.request;setLoading(false);setBusy(true);setRows(reordered);setError('');
  try{await api('/board/reorder/',{method:'POST',body:JSON.stringify({family:familyId,ids:reordered.map(item=>item.id)})})}
  catch(e){if(mutationCurrent(lease)){setRows(before);setError(e.message||w.failed)}}
  finally{lease.pending=false;if(mutationCurrent(lease))setBusy(false)}
 }
 const startEdit=row=>{setEditing(row);setKind(row.kind);setAdapterKey(row.adapter_key||'');setText(row.text||'');setFiles([]);setVisibility(row.visibility||'family');setSelectedMembershipIds(row.selected_membership_ids||[]);setCompose(true);window.scrollTo({top:0,behavior:'smooth'})};
 const interactionLease=boardLease.current;
 const updateInteraction=(id,interaction)=>{if(!interactionLease.active||interactionLease!==boardLease.current)return;if(interaction?.can_interact===false){setRows(current=>current.filter(row=>String(row.id)!==String(id)));load();return}setRows(current=>current.map(row=>String(row.id)===String(id)?{...row,interaction}:row))};

 return <section className="board-hub"><header className="page-head board-head"><button className="icon-btn" aria-label={w.back} onClick={onBack}><Icon name="back"/></button><div className="grow"><small>{w.eyebrow}</small><h1>{w.title}</h1><p>{w.hint}</p></div>{canPost&&!compose&&<button className="primary board-pin-button" onClick={()=>startCompose()}><Icon name="plus"/> {w.pin}</button>}</header>
 {error&&<div role="alert" className="card board-error">{error} {!compose&&<button onClick={()=>load()}>{w.retry}</button>}</div>}
 {compose&&<PinComposer key={`${familyId}-${editing?.id||'new'}`} familyId={familyId} language={i18n.language} kind={kind} setKind={setKind} adapterKey={adapterKey} setAdapterKey={setAdapterKey} text={text} setText={setText} files={files} addFiles={addFiles} setFiles={setFiles} targetId={targetId} setTargetId={setTargetId} editing={editing} busy={busy} onSubmit={submit} onClose={close} removePhoto={removePhoto} members={members} visibility={visibility} setVisibility={setVisibility} selectedMembershipIds={selectedMembershipIds} setSelectedMembershipIds={setSelectedMembershipIds}/>} 
 {!compose&&visibleRows.length>0&&<div className="pinboard-guide"><Icon name="drag"/><span>{w.arrange}</span><small>{({de:'Unter Mehr kannst du Karten mit den Pfeilen anordnen.',en:'Open More on a card to arrange it with the arrow controls.',fr:'Ouvrez Plus pour réorganiser les cartes avec les flèches.',nl:'Open Meer om kaarten met de pijlen te ordenen.',th:'เปิดเพิ่มเติมเพื่อจัดเรียงการ์ดด้วยปุ่มลูกศร'})[i18n.language.split('-')[0]]||'Unter Mehr kannst du Karten mit den Pfeilen anordnen.'}</small></div>}
 <div className="pinboard-grid" aria-live="polite">{visibleRows.map((row,index)=><PinCard key={row.id} row={row} index={index} total={visibleRows.length} language={i18n.language} busy={busy} onMove={move} onRemove={remove} onEdit={()=>startEdit(row)} onInteractionChange={interaction=>updateInteraction(row.id,interaction)}/>)}</div>
 {loading&&<p role="status" className="board-loading">{w.loading}</p>}{!loading&&!error&&!visibleRows.length&&!compose&&<button className="card board-empty" onClick={()=>canPost&&startCompose()} disabled={!canPost}><span><Icon name="plus"/></span><strong>{w.empty}</strong>{canPost&&<small>{w.pin}</small>}</button>}{visibleNext&&<button className="secondary board-more" disabled={loading} onClick={()=>load(visibleNext,true)}>{w.more}</button>}</section>
}
