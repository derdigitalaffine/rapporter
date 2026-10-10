import {useEffect,useMemo,useState} from 'react';
import {useTranslation} from 'react-i18next';
import {api} from './api';
import {Icon} from './icons';
import './context-links.css';

function tripLabel(trip,fallback){
 if(!trip)return fallback;
 const place=trip.destination?` · ${trip.destination}`:'';
 return `${trip.title||fallback}${place}`;
}

export default function NoteContextLinks({family,note,readonly}){
 const {i18n}=useTranslation();
 const en=i18n.language.startsWith('en');
 const w=en?{
  title:'Context',open:'Link context',hint:'Keep this note connected to the trip it belongs to. The note stays the original object.',linked:'Linked trips',none:'No trip linked yet.',choose:'Choose a trip',link:'Link trip',remove:'Remove link',loading:'Loading context …',error:'Context links could not be loaded.',retry:'Try again',tripFallback:'Trip',readonly:'Read-only notes can view links but cannot change them.'
 }:{
  title:'Kontext',open:'Kontext verknüpfen',hint:'Verknüpfe diese Notiz mit der passenden Reise. Die Notiz bleibt dabei das Originalobjekt.',linked:'Verknüpfte Reisen',none:'Noch keine Reise verknüpft.',choose:'Reise auswählen',link:'Reise verknüpfen',remove:'Verknüpfung lösen',loading:'Kontext wird geladen …',error:'Kontext-Verknüpfungen konnten nicht geladen werden.',retry:'Erneut versuchen',tripFallback:'Reise',readonly:'Schreibgeschützte Notizen können Verknüpfungen sehen, aber nicht ändern.'
 };
 const familyId=family?.id;
 const noteId=note?.id;
 const [expanded,setExpanded]=useState(false),[links,setLinks]=useState([]),[trips,setTrips]=useState([]),[choice,setChoice]=useState(''),[loading,setLoading]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState('');
 useEffect(()=>{setExpanded(false);setLinks([]);setTrips([]);setChoice('');setError('')},[familyId,noteId]);
 const tripById=useMemo(()=>new Map(trips.map(row=>[String(row.id),row])),[trips]);
 const tripLinks=useMemo(()=>links.filter(row=>row?.context?.type==='trip'),[links]);
 const linkedIds=useMemo(()=>new Set(tripLinks.map(row=>String(row.context.id))),[tripLinks]);
 const availableTrips=useMemo(()=>trips.filter(row=>!linkedIds.has(String(row.id))),[trips,linkedIds]);
 async function load(){
  if(!familyId||!noteId)return;
  setLoading(true);setError('');
  try{
   const [linkData,tripData]=await Promise.all([
    api(`/context-links/?family=${encodeURIComponent(familyId)}&anchor_type=note&anchor_id=${encodeURIComponent(noteId)}`),
    api(`/trips/?family=${encodeURIComponent(familyId)}`)
   ]);
   setLinks(linkData.results||[]);setTrips(tripData.results||tripData||[]);
  }catch(e){setError(e.message||w.error)}finally{setLoading(false)}
 }
 async function toggle(){const next=!expanded;setExpanded(next);if(next&&!links.length&&!trips.length&&!loading)await load()}
 async function linkTrip(){
  if(readonly||busy||!choice)return;
  setBusy(true);setError('');
  try{
   const data=await api('/context-links/',{method:'POST',body:JSON.stringify({family:familyId,source:{type:'note',id:noteId},context:{type:'trip',id:choice},relation:'context'})});
   const linked=data.link;
   setLinks(old=>old.some(row=>String(row.id)===String(linked.id))?old:[...old,linked]);setChoice('');
  }catch(e){setError(e.message||w.error)}finally{setBusy(false)}
 }
 async function unlink(link){
  if(readonly||busy)return;
  setBusy(true);setError('');
  try{await api(`/context-links/${link.id}/?family=${encodeURIComponent(familyId)}`,{method:'DELETE'});setLinks(old=>old.filter(row=>String(row.id)!==String(link.id)))}catch(e){setError(e.message||w.error)}finally{setBusy(false)}
 }
 return <section className="note-context-links" aria-label={w.title}>
  <button type="button" className="ghost note-context-toggle" aria-expanded={expanded} onClick={toggle}><Icon name="link"/><span>{w.open}</span>{tripLinks.length>0&&<span className="note-context-count">{tripLinks.length}</span>}</button>
  {expanded&&<div className="note-context-panel">
   <div className="note-context-head"><div><h2>{w.title}</h2><p>{w.hint}</p></div>{loading&&<span role="status" className="note-context-muted">{w.loading}</span>}</div>
   {error&&<div className="note-context-error" role="alert">{w.error} <button type="button" onClick={load} disabled={loading||busy}>{w.retry}</button></div>}
   {!loading&&<><div className="note-context-linked"><strong>{w.linked}</strong>{tripLinks.length?<ul>{tripLinks.map(link=>{const trip=tripById.get(String(link.context.id));return <li key={link.id}><div><a href={link.context.deep_link||'#'}>{tripLabel(trip,w.tripFallback)}</a>{trip?.starts_on&&trip?.ends_on&&<small>{trip.starts_on} – {trip.ends_on}</small>}</div>{!readonly&&<button type="button" className="ghost-danger compact" disabled={busy} onClick={()=>unlink(link)}>{w.remove}</button>}</li>})}</ul>:<p className="note-context-muted">{w.none}</p>}</div>
   {!readonly&&<div className="note-context-add"><label><span>{w.choose}</span><select value={choice} onChange={e=>setChoice(e.target.value)} disabled={busy||!availableTrips.length}><option value="">{w.choose}</option>{availableTrips.map(trip=><option value={trip.id} key={trip.id}>{tripLabel(trip,w.tripFallback)}</option>)}</select></label><button type="button" className="secondary compact" disabled={busy||!choice} onClick={linkTrip}><Icon name="link"/>{w.link}</button></div>}
   {readonly&&<p className="note-context-muted">{w.readonly}</p>}</>}
  </div>}
 </section>
}
