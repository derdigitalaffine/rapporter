import {useLayoutEffect,useRef} from 'react';
import {Icon} from './icons';
import PinInteractionBar from './PinInteractions';
import {formatPinEventMeta,pinAuthorHue,pinAuthorInitial,pinIconName} from './pinboard-ui';
import {appLocale} from './locale';
import './todo-action-row.css';
import './pin-board-card.css';

const COPY={
 de:{more:'Mehr',options:'Optionen für',up:'Weiter nach vorne',down:'Weiter nach hinten',edit:'Bearbeiten',remove:'Entfernen',share:'Quelle zusätzlich freigeben',unavailable:'Nicht mehr verfügbar',private:'Nur mich',selected:'Ausgewählte Personen',family:'Ganze Familie',author:'Angepinnt von',photos:'Fotos hinzufügen',types:['Notizzettel','Foto','Termin','Aufgabe','Routine','Notiz','Einkaufsartikel','Einkaufsliste','Reise','Dokument'],holiday:'Ferien'},
 en:{more:'More',options:'Options for',up:'Move earlier',down:'Move later',edit:'Edit',remove:'Remove',share:'Also share source',unavailable:'No longer available',private:'Only me',selected:'Selected people',family:'Whole family',author:'Pinned by',photos:'Add photos',types:['Note','Photo','Event','Task','Routine','Note','Shopping item','Shopping list','Trip','Document'],holiday:'School holidays'},
 fr:{more:'Plus',options:'Options pour',up:'Déplacer avant',down:'Déplacer après',edit:'Modifier',remove:'Retirer',share:'Partager aussi la source',unavailable:'Indisponible',private:'Moi uniquement',selected:'Personnes choisies',family:'Toute la famille',author:'Épinglé par',photos:'Photos',types:['Note','Photo','Événement','Tâche','Routine','Note','Article','Liste de courses','Voyage','Document'],holiday:'Vacances scolaires'},
 nl:{more:'Meer',options:'Opties voor',up:'Eerder plaatsen',down:'Later plaatsen',edit:'Bewerken',remove:'Verwijderen',share:'Bron ook delen',unavailable:'Niet meer beschikbaar',private:'Alleen ik',selected:'Gekozen personen',family:'Hele familie',author:'Vastgepind door',photos:'Foto’s',types:['Notitie','Foto','Afspraak','Taak','Routine','Notitie','Boodschap','Boodschappenlijst','Reis','Document'],holiday:'Schoolvakantie'},
 th:{more:'เพิ่มเติม',options:'ตัวเลือกสำหรับ',up:'ย้ายขึ้น',down:'ย้ายลง',edit:'แก้ไข',remove:'นำออก',share:'แชร์ต้นฉบับด้วย',unavailable:'ไม่พร้อมใช้งานแล้ว',private:'ฉันเท่านั้น',selected:'บุคคลที่เลือก',family:'ทั้งครอบครัว',author:'ปักหมุดโดย',photos:'รูปภาพ',types:['บันทึก','รูปภาพ','กิจกรรม','งาน','กิจวัตร','บันทึก','สินค้า','รายการซื้อของ','การเดินทาง','เอกสาร'],holiday:'ปิดเทอม'},
};
const KINDS=['note','photo','event','task','routine','note_ref','shopping','shopping_list','trip','document'];

export default function PinBoardCard({row,index,total,language='de',busy,onMove,onRemove,onEdit,onInteractionChange}){
 const text=COPY[language.split('-')[0]]||COPY.de,summary=useRef(null),focusAfterMove=useRef(false);
 useLayoutEffect(()=>{if(focusAfterMove.current){summary.current?.focus();if(!busy)focusAfterMove.current=false}},[index,busy]);
 const unavailable=row.target?.available===false||row.effective_scope==='none';
 const target=unavailable?null:row.target;
 const event=target?.kind==='event'?{type:target.event_type,starts_at:target.subtitle,ends_at:target.ends_at,payload:{date_start:target.date_start,date_end_exclusive:target.date_end_exclusive}}:null;
 const icon=pinIconName(row.kind,event),type=icon==='school'?text.holiday:text.types[KINDS.indexOf(row.kind)]||text.types[0];
 const title=unavailable?text.unavailable:target?.title||row.text||type;
 const scope=row.effective_scope||row.visibility;
 const visibility=unavailable?text.unavailable:scope==='private'?text.private:scope==='selected'?text.selected:text.family;
 let meta=event?formatPinEventMeta(event,language):target?.subtitle;
 if(!event&&typeof meta==='string'&&/^\d{4}-\d{2}-\d{2}T/.test(meta)){const date=new Date(meta);meta=Number.isNaN(date.getTime())?'':date.toLocaleString(appLocale(language),{dateStyle:'short',timeStyle:'short'})}
 const hasActions=row.can_reorder||row.can_change_pin_visibility||row.can_delete||target?.can_share_source&&target?.source_share_url;
 function close(){summary.current?.closest('details')?.removeAttribute('open');summary.current?.focus()}
 function action(run){close();run()}
 function move(delta){focusAfterMove.current=true;action(()=>onMove(row,delta))}
 return <article id={`pin-${row.id}`} aria-label={unavailable?text.unavailable:`${type}: ${title}; ${visibility}`} className={`pin-card pin-${row.kind} pin-board-card ${unavailable?'pin-unavailable':''}`} onKeyDown={event=>{if(event.key==='Escape'&&summary.current?.closest('details')?.open){event.preventDefault();event.stopPropagation();close()}}}>
  <div className="pin-card-top"><span className="pin-kind"><span className="pin-kind-icon"><Icon name={unavailable?'lock':icon}/></span>{unavailable?text.unavailable:type}</span><span className="pin-visibility"><Icon name={unavailable||scope==='private'?'lock':scope==='selected'?'users':'home'}/>{visibility}</span></div>
  {!unavailable&&row.images?.length>0&&<div className={`pin-photos pin-photos-${Math.min(row.images.length,4)}`}>{row.images.map((image,i)=><a key={image.id} href={image.url} target="_blank" rel="noreferrer" aria-label={`${text.photos} ${i+1}`}><img src={image.url} width={image.width} height={image.height} loading="lazy" alt=""/></a>)}</div>}
  {target?.url?<a className="pin-target" href={target.url}><span className="pin-target-icon"><Icon name={icon}/></span><span className="grow"><strong>{title}</strong>{meta&&<small>{String(meta).slice(0,140)}</small>}</span><Icon name="next"/></a>:unavailable?<div className="pin-target unavailable"><Icon name="lock"/><strong>{text.unavailable}</strong></div>:<>{target&&<strong>{title}</strong>}{row.text&&<p className="pin-text">{row.text}</p>}</>}
  {!unavailable&&target&&row.text&&<p className="pin-text">{row.text}</p>}
  {!unavailable&&row.can_interact&&<PinInteractionBar pin={row} onChange={onInteractionChange}/>}
  <footer>{!unavailable&&(row.author_name||row.created_at)&&<span className="pin-author-line">{row.author_name&&<span className="pin-author" style={{'--pin-author-hue':pinAuthorHue(row.author)}} title={`${text.author} ${row.author_name}`}><span className="pin-author-avatar" aria-hidden="true">{pinAuthorInitial(row.author_name)}</span><span>{text.author} <strong>{row.author_name}</strong></span></span>}{row.created_at&&<time dateTime={row.created_at}>{new Date(row.created_at).toLocaleDateString(appLocale(language),{day:'2-digit',month:'short'})}</time>}</span>}
   {hasActions&&<details className="todo-actions-menu pin-card-actions"><summary ref={summary} aria-label={`${text.more}: ${title}`}><Icon name="more"/><span>{text.more}</span></summary><div className="todo-actions-popover" role="group" aria-label={`${text.options} ${title}`}>
    {row.can_reorder&&<><button type="button" disabled={busy||index===0} onClick={()=>move(-1)} aria-label={`${text.up}: ${title}`}><span aria-hidden="true">↑</span>{text.up}</button><button type="button" disabled={busy||index===total-1} onClick={()=>move(1)} aria-label={`${text.down}: ${title}`}><span aria-hidden="true">↓</span>{text.down}</button></>}
    {row.can_change_pin_visibility&&<button type="button" disabled={busy} onClick={()=>action(onEdit)}><Icon name="edit"/>{text.edit}</button>}
    {target?.can_share_source&&target?.source_share_url&&<a href={target.source_share_url}><Icon name="members"/>{text.share}</a>}
    {row.can_delete&&<button className="todo-action-danger" type="button" disabled={busy} onClick={()=>action(()=>onRemove(row))}><Icon name="delete"/>{text.remove}</button>}
   </div></details>}
  </footer>
 </article>;
}
