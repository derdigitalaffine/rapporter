import {useEffect,useMemo,useState} from 'react';
import {useTranslation} from 'react-i18next';
import {api} from './api';
import {Icon} from './icons';
import {toast} from './feedback';
import './notification-inbox.css';

const copy={
 de:{title:'Mitteilungen',hint:'Familienaktivitäten, die für dich bestimmt sind.',unread:'ungelesen',markAll:'Alle als gelesen markieren',empty:'Keine Mitteilungen',emptyHint:'Neue relevante Familienaktivitäten erscheinen hier.',loadMore:'Mehr laden',open:'Öffnen',loading:'Mitteilungen werden geladen …',failed:'Mitteilungen konnten nicht geladen werden.'},
 en:{title:'Notifications',hint:'Family activity addressed to you.',unread:'unread',markAll:'Mark all as read',empty:'No notifications',emptyHint:'New relevant family activity will appear here.',loadMore:'Load more',open:'Open',loading:'Loading notifications …',failed:'Could not load notifications.'},
};

function normalizePage(payload){
 const results=Array.isArray(payload?.results)?payload.results:Array.isArray(payload)?payload:[];
 const unreadCount=Number.isFinite(payload?.unread_count)?Math.max(0,payload.unread_count):0;
 return {results,unreadCount,nextCursor:payload?.next_cursor||null};
}

export default function NotificationInbox({family}){
 const {i18n}=useTranslation();const text=copy[i18n.language?.startsWith('en')?'en':'de'];
 const [rows,setRows]=useState([]);const [unread,setUnread]=useState(0);const [cursor,setCursor]=useState(null);const [loading,setLoading]=useState(true);const [busy,setBusy]=useState('');
 const formatter=useMemo(()=>new Intl.DateTimeFormat(i18n.language?.startsWith('en')?'en-GB':'de-DE',{dateStyle:'medium',timeStyle:'short'}),[i18n.language]);
 async function load(nextCursor='',append=false){
  if(!family?.id)return;setLoading(true);
  try{const query=new URLSearchParams({family:String(family.id),limit:'20'});if(nextCursor)query.set('cursor',nextCursor);const page=normalizePage(await api(`/notifications/?${query}`));setRows(current=>append?[...current,...page.results]:page.results);setUnread(page.unreadCount);setCursor(page.nextCursor)}
  catch(error){toast(error.message||text.failed,{type:'error'})}
  finally{setLoading(false)}
 }
 useEffect(()=>{setRows([]);setUnread(0);setCursor(null);if(family?.id)load()},[family?.id]);
 async function setRead(row){
  if(row.read)return row;
  const saved=await api(`/notifications/${row.id}/`,{method:'PATCH',body:JSON.stringify({read:true})});
  setRows(current=>current.map(item=>item.id===saved.id?saved:item));setUnread(value=>Math.max(0,value-1));return saved;
 }
 async function open(row){
  setBusy(row.id);
  try{const saved=await setRead(row);if(saved.resource_url)window.location.assign(saved.resource_url)}
  catch(error){toast(error.message||text.failed,{type:'error'})}
  finally{setBusy('')}
 }
 async function markAll(){
  if(!unread||busy)return;setBusy('all');
  try{await api('/notifications/read-all/',{method:'POST',body:JSON.stringify({family:String(family.id)})});setRows(current=>current.map(item=>({...item,read:true,read_at:item.read_at||new Date().toISOString()})));setUnread(0)}
  catch(error){toast(error.message||text.failed,{type:'error'})}
  finally{setBusy('')}
 }
 return <section className="card notification-inbox" aria-labelledby="notification-inbox-title">
  <div className="notification-inbox-head"><div><h2 id="notification-inbox-title">{text.title}</h2><p>{text.hint}</p></div><div className="notification-inbox-actions">{unread>0&&<span className="notification-unread-count" aria-live="polite">{unread} {text.unread}</span>}<button className="secondary compact" onClick={markAll} disabled={!unread||!!busy}><Icon name="check"/> {text.markAll}</button></div></div>
  {loading&&!rows.length?<div className="notification-inbox-empty" role="status"><Icon name="refresh"/><span>{text.loading}</span></div>:!rows.length?<div className="notification-inbox-empty"><Icon name="warning" size={30}/><strong>{text.empty}</strong><span>{text.emptyHint}</span></div>:<div className="notification-inbox-list">{rows.map(row=><article className={`notification-inbox-row ${row.read?'read':'unread'}`} key={row.id}><button onClick={()=>open(row)} disabled={busy===row.id}><span className="notification-state-dot" aria-hidden="true"/><span className="notification-inbox-copy"><strong>{row.title}</strong>{row.body&&<span>{row.body}</span>}<small>{formatter.format(new Date(row.created_at))}</small></span>{row.resource_url&&<span className="notification-open"><Icon name="next"/><span className="sr-only">{text.open}</span></span>}</button></article>)}</div>}
  {cursor&&<button className="secondary notification-load-more" onClick={()=>load(cursor,true)} disabled={loading}>{loading?<Icon name="refresh"/>:null}{text.loadMore}</button>}
 </section>
}
