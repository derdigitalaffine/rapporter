import {useEffect,useRef,useState} from 'react';
import {api} from './api';
import {GamePicker,MatchCard,gameStrings} from './GamesHub';
import {FormShell,FormActions} from './form-primitives';
import {useTranslation} from 'react-i18next';

export default function FriendDuels({friendshipId}){
 const {t,i18n}=useTranslation();const s=gameStrings(i18n.language);const [rows,setRows]=useState([]),[type,setType]=useState('rps'),[selected,setSelected]=useState(null),[error,setError]=useState(false),[busy,setBusy]=useState(false),[loaded,setLoaded]=useState(false);const alive=useRef(false),version=useRef(0),mutating=useRef(false),reading=useRef(false);
 async function load(){if(reading.current||mutating.current)return;reading.current=true;const readVersion=version.current;try{const data=await api(`/games/?friendship=${encodeURIComponent(friendshipId)}`);if(alive.current&&readVersion===version.current){setRows(data);setLoaded(true);setError(false)}}catch{if(alive.current)setError(true)}finally{reading.current=false}}
 useEffect(()=>{alive.current=true;load();const timer=setInterval(()=>{if(document.visibilityState==='visible'&&navigator.onLine&&!busy)load()},8000);return()=>{alive.current=false;clearInterval(timer)}},[friendshipId]);
 async function action(path,data){if(mutating.current)return;mutating.current=true;version.current+=1;setBusy(true);setError(false);try{const row=await api(path,{method:'POST',body:JSON.stringify(data)});if(alive.current){setRows(old=>[row,...old.filter(x=>x.id!==row.id)]);setSelected(row.id)}}catch{if(alive.current)setError(true)}finally{mutating.current=false;if(alive.current)setBusy(false)}}
 return <section className="messenger-duels"><h3>{t('messengerUi.duels')}</h3><p>{t('messengerUi.justFun')}</p>{error&&<p role="alert">{s.saveError} <button className="text-button" onClick={load}>{s.retry}</button></p>}<FormShell onSubmit={e=>{e.preventDefault();action('/games/',{friendship:friendshipId,game_type:type})}}><GamePicker value={type} onChange={setType} s={s} disabled={busy}/><FormActions><button className="primary" disabled={busy||!navigator.onLine}>{t('messengerUi.startDuel')}</button></FormActions></FormShell>{!loaded?<p role="status">{s.loading}</p>:rows.map(row=><MatchCard key={row.id} match={row} s={s} onAction={action} busy={busy} selected={selected===row.id} onSelect={()=>setSelected(selected===row.id?null:row.id)} memberships={[]}/>)}</section>
}
