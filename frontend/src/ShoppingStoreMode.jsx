import {useEffect,useMemo,useRef,useState} from 'react';
import {useTranslation} from 'react-i18next';
import {api} from './api';
import {Icon} from './icons';
import {toast} from './feedback';
import ShoppingCheckoutFlow from './ShoppingCheckoutFlow';
import ShoppingCompletionSummary from './ShoppingCompletionSummary';
import './store-i18n';
import './shopping-template-i18n';
import './shopping-session-i18n';
import './shopping-checkout-i18n';
import './shopping-store.css';
import './shopping-session.css';

const unwrap=value=>value?.results||value||[];
const byPosition=(a,b)=>(Number(a.position??2147483647)-Number(b.position??2147483647))||String(a.id).localeCompare(String(b.id),undefined,{numeric:true});
const participantGlyph=person=>{const avatar=String(person?.avatar||'').trim();if(avatar&&avatar.length<=4&&!avatar.includes('/'))return avatar;return String(person?.name||'?').trim().slice(0,1).toLocaleUpperCase()||'?'};

export default function ShoppingStoreMode({list,onLeave,onToggle,onDetails,onAdd,syncStatus,initialStatusFilter='open'}){
 const {t}=useTranslation();
 const [cartOpen,setCartOpen]=useState(false);const [offersUrl,setOffersUrl]=useState('');const [statusFilter,setStatusFilter]=useState(initialStatusFilter);const [completingIds,setCompletingIds]=useState([]);const [session,setSession]=useState(null);const [sessionError,setSessionError]=useState('');const [remotePatches,setRemotePatches]=useState({});const [remotePulse,setRemotePulse]=useState(null);const [online,setOnline]=useState(()=>typeof navigator==='undefined'||navigator.onLine);const [checkoutOpen,setCheckoutOpen]=useState(false);const [checkoutHiddenIds,setCheckoutHiddenIds]=useState([]);const [historySessionId,setHistorySessionId]=useState(()=>typeof location==='undefined'?'':new URLSearchParams(location.search).get('session')||'');const [historyPayload,setHistoryPayload]=useState(null);const [historyError,setHistoryError]=useState('');
 const cursorRef=useRef(0);const startedRef=useRef(false);const pulseTimerRef=useRef(null);
 const baseItems=(list?.items||[]).filter(item=>!checkoutHiddenIds.includes(String(item.id)));
 const items=useMemo(()=>{
  const known=new Set(baseItems.map(item=>String(item.id)));
  const rows=baseItems.map(item=>{const patch=remotePatches[String(item.id)];return patch?{...item,checked:patch.checked,checked_at:patch.checked_at}:item});
  for(const [id,patch] of Object.entries(remotePatches)){if(!known.has(id)&&patch.item&&!checkoutHiddenIds.includes(id))rows.push({...patch.item,checked:patch.checked,checked_at:patch.checked_at})}
  return rows;
 },[baseItems,remotePatches,checkoutHiddenIds]);
 const open=items.filter(x=>!x.checked);const checked=items.filter(x=>x.checked);
 useEffect(()=>{let active=true;setOffersUrl('');if(!list?.family||!list?.id)return()=>{active=false};api(`/shopping-stores/?family=${encodeURIComponent(list.family)}`).then(value=>{if(!active)return;const store=unwrap(value).find(row=>(row.shopping_list_ids||[]).some(id=>String(id)===String(list.id)));setOffersUrl(store?.offers_url||'')}).catch(()=>{});return()=>{active=false}},[list?.family,list?.id]);
 useEffect(()=>{setStatusFilter(initialStatusFilter);setCompletingIds([]);setSession(null);setSessionError('');setRemotePatches({});setRemotePulse(null);setCheckoutOpen(false);setCheckoutHiddenIds([]);cursorRef.current=0;startedRef.current=false;if(pulseTimerRef.current){clearTimeout(pulseTimerRef.current);pulseTimerRef.current=null}},[list?.id,initialStatusFilter]);
 useEffect(()=>{const update=()=>setOnline(navigator.onLine);window.addEventListener('online',update);window.addEventListener('offline',update);return()=>{window.removeEventListener('online',update);window.removeEventListener('offline',update)}},[]);
 useEffect(()=>{const update=()=>{const id=new URLSearchParams(location.search).get('session')||'';setHistorySessionId(id)};window.addEventListener('popstate',update);return()=>window.removeEventListener('popstate',update)},[]);
 useEffect(()=>{
  if(!historySessionId){setHistoryPayload(null);setHistoryError('');return}
  let live=true;setHistoryPayload(null);setHistoryError('');
  api(`/shopping-sessions/${encodeURIComponent(historySessionId)}/`).then(payload=>{
   if(!live)return;
   if(list?.id&&String(payload?.session?.shopping_list)!==String(list.id)){setHistoryError(t('shoppingCheckout.historyLoadFailed'));return}
   setHistoryPayload(payload);
  }).catch(()=>{if(live)setHistoryError(t('shoppingCheckout.historyLoadFailed'))});
  return()=>{live=false};
 },[historySessionId,list?.id,t]);
 useEffect(()=>{
  const listId=list?.id;if(!listId||historySessionId)return;
  let stopped=false;let timer=null;
  const showPulse=activity=>{
   if(!activity?.actor||activity.actor.is_self)return;
   const key=activity.kind==='item_checked'?'remoteChecked':activity.kind==='item_reopened'?'remoteReopened':'remoteAdded';
   const next={actor:activity.actor,text:t(`shoppingSession.${key}`,{name:activity.actor.name,item:activity.item_name||activity.item?.name||''})};
   setRemotePulse(next);if(pulseTimerRef.current)clearTimeout(pulseTimerRef.current);pulseTimerRef.current=setTimeout(()=>setRemotePulse(null),2200);
  };
  const applyActivities=activities=>{
   let latest=null;
   setRemotePatches(current=>{
    const next={...current};
    for(const activity of activities||[]){
     if(activity.actor?.is_self)continue;
     latest=activity;
     if(!activity.item_id||!activity.item)continue;
     const id=String(activity.item_id);const previous=next[id]||{};
     next[id]={...previous,checked:!!activity.item.checked,checked_at:activity.item.checked_at||null,item:activity.kind==='item_added'?activity.item:previous.item};
    }
    return next;
   });
   if(latest)showPulse(latest);
  };
  const tick=async()=>{
   if(stopped)return;
   if(online&&document.visibilityState==='visible'){
    try{
     if(!startedRef.current){
      const started=await api('/shopping-sessions/start/',{method:'POST',body:JSON.stringify({shopping_list:listId})});
      if(stopped)return;startedRef.current=true;cursorRef.current=Number(started.cursor)||0;setSession(started.session||null);
     }else{
      const payload=await api(`/shopping-sessions/current/?shopping_list=${encodeURIComponent(listId)}&after=${cursorRef.current}`);
      if(stopped)return;setSession(payload.session||null);applyActivities(payload.activities||[]);cursorRef.current=Math.max(cursorRef.current,Number(payload.cursor)||0);
     }
     setSessionError('');
    }catch(error){if(!stopped&&error?.message!=='unauthorized')setSessionError(t('shoppingSession.syncIssue'))}
   }
   if(!stopped)timer=setTimeout(tick,2500);
  };
  void tick();
  return()=>{stopped=true;if(timer)clearTimeout(timer)};
 },[list?.id,online,t,historySessionId]);
 useEffect(()=>()=>{if(pulseTimerRef.current)clearTimeout(pulseTimerRef.current)},[]);
 const visibleItems=useMemo(()=>statusFilter==='open'?[...open].sort(byPosition):statusFilter==='done'?[...checked].sort(byPosition):[...open].sort(byPosition).concat([...checked].sort(byPosition)),[statusFilter,open,checked]);
 const groups=useMemo(()=>{
  const rows=[...visibleItems];
  const byAisle=rows.length>0&&rows.filter(x=>x.aisle?.trim()).length>rows.length/2;
  const grouped=new Map();for(const item of rows){const key=(byAisle?item.aisle:item.category)?.trim()||t('other');if(!grouped.has(key))grouped.set(key,[]);grouped.get(key).push(item)}
  return [...grouped].map(([name,groupRows])=>({name:byAisle&&name!==t('other')?t('storeUi.aisle',{name}):name,rows:groupRows}));
 },[visibleItems,t]);
 async function toggle(item){
  const target=!item.checked;const id=String(item.id);const confirmInline=target&&statusFilter==='open';const previousPatch=remotePatches[id];
  setRemotePatches(current=>({...current,[id]:{...(current[id]||{}),checked:target,checked_at:target?new Date().toISOString():null}}));
  if(confirmInline){
   setCompletingIds(ids=>ids.includes(id)?ids:[...ids,id]);
   if(!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches)await new Promise(resolve=>setTimeout(resolve,180));
  }
  try{await onToggle(item,target)}catch(e){setRemotePatches(current=>{const next={...current};if(previousPatch)next[id]=previousPatch;else delete next[id];return next});toast(e.message,{type:'error'})}finally{if(confirmInline)setCompletingIds(ids=>ids.filter(row=>row!==id))}
 }
 function checkoutCompleted(payload){
  const completion=payload?.completion||{};const hidden=[...(completion.purchased_items||[])];
  if(completion.open_items_policy==='remove')hidden.push(...(completion.open_items||[]));
  setCheckoutHiddenIds(rows=>[...new Set([...rows,...hidden.map(item=>String(item.id))])]);
  setCartOpen(false);setStatusFilter('open');setSession(payload?.session||null);
 }
 function closeCheckout(){setCheckoutOpen(false);cursorRef.current=0;startedRef.current=false;setSession(null)}
 function closeHistory(){
  const url=new URL(location.href);url.searchParams.delete('session');history.replaceState(history.state,'',url.pathname+url.search);setHistorySessionId('');setHistoryPayload(null);setHistoryError('');
 }
 const peers=(session?.participants||[]).filter(person=>!person.is_self);const peerNames=peers.map(person=>person.name).join(', ');
 const emptyLabel=statusFilter==='open'?t('storeUi.noOpen'):statusFilter==='done'?t('storeUi.noDone'):t('listEmpty');
 return <section className="store-focus" aria-label={t('storeUi.title')}><header className="store-header"><button className="icon-button" onClick={onLeave} aria-label={t('storeUi.leave')}><Icon name="back"/></button><div className="grow"><strong>{list?.name||t('shopping')}</strong><small>{t('storeUi.open',{count:open.length})}</small></div>{offersUrl&&<a className="icon-button" href={offersUrl} target="_blank" rel="noopener noreferrer" aria-label={t('shoppingTemplateUi.offersOpen')}><Icon name="store"/></a>}</header><div className="store-progress" aria-hidden="true"><span style={{width:`${items.length?checked.length/items.length*100:0}%`}}/></div>{session&&session.status==='active'&&<div className="store-session" role="status"><div className="store-session-main"><Icon name="users"/><strong>{t('shoppingSession.running')}</strong></div>{peers.length>0&&<div className="store-session-peers"><div className="store-session-avatars" aria-hidden="true">{peers.slice(0,3).map(person=><span className="store-session-avatar" key={person.id}>{participantGlyph(person)}</span>)}</div><span className="store-session-names">{t('shoppingSession.together',{names:peerNames})}</span></div>}{remotePulse&&<div className="store-session-pulse" aria-live="polite"><span className="store-session-avatar" aria-hidden="true">{participantGlyph(remotePulse.actor)}</span><span>{remotePulse.text}</span></div>}</div>}{sessionError&&online&&<div className="store-session-error" role="status">{sessionError}</div>}{historyError&&<div className="store-session-error" role="alert">{historyError}<button className="secondary compact" onClick={closeHistory}>{t('shoppingCheckout.closeSummary')}</button></div>}{syncStatus&&<div className="store-sync" role={syncStatus===t('shoppingOffline.failed')?'alert':'status'}>{syncStatus}</div>}
 <div className="store-status-filter" role="group" aria-label={t('storeUi.statusLabel')}>{[['open','statusOpen'],['done','statusDone'],['all','statusAll']].map(([value,label])=><button key={value} type="button" className={statusFilter===value?'active':''} aria-pressed={statusFilter===value} onClick={()=>setStatusFilter(value)}>{t(`storeUi.${label}`)}{value==='open'?` ${open.length}`:value==='done'?` ${checked.length}`:''}</button>)}</div>
 <div className="store-checklist">{groups.map(group=><section className="store-group" key={group.name} aria-label={group.name}><h2>{group.name}</h2>{group.rows.map(item=>{const completing=completingIds.includes(String(item.id));const selected=item.checked||completing;return <article className={`store-row ${item.checked?'store-checked':''} ${completing?'store-completing':''}`} key={item.id}><button className="store-check" aria-label={selected?`${item.name} · ${t('reopen')}`:t('storeUi.check',{name:item.name,quantity:item.quantity||''})} aria-pressed={selected} disabled={completing} onClick={()=>toggle(item)}><span className="store-checkmark" aria-hidden="true">{selected&&<Icon name="check"/>}</span><strong>{item.name}</strong><span className="store-quantity">{[item.quantity,item.aisle].filter(Boolean).join(' · ')}</span></button><button className="store-details" onClick={()=>onDetails(item)} aria-label={t('storeUi.details',{name:item.name})}><Icon name="info"/></button></article>})}</section>)}{!visibleItems.length&&<div className="smart-empty"><Icon name="doneAll"/><strong>{emptyLabel}</strong></div>}</div>
 <footer className="store-footer"><button onClick={()=>setCartOpen(value=>!value)} aria-expanded={cartOpen}><Icon name="doneAll"/>{t('storeUi.cart',{count:checked.length})}</button><button onClick={onAdd}><Icon name="plus"/>{t('storeUi.add')}</button>{checked.length>0&&<button className="store-finish" disabled={!online||!session?.id} onClick={()=>setCheckoutOpen(true)}><Icon name="check"/>{t('shoppingCheckout.finish')}</button>}</footer>{cartOpen&&<div className="store-cart">{[...checked].sort(byPosition).map(item=><button key={item.id} onClick={()=>onToggle(item,false).catch(e=>toast(e.message,{type:'error'}))}><Icon name="check"/><span>{item.name}</span><small>{item.quantity}</small></button>)}</div>}{checkoutOpen&&<ShoppingCheckoutFlow list={list} sessionId={session?.id} openCount={open.length} onClose={closeCheckout} onCompleted={checkoutCompleted}/>} {historyPayload&&<ShoppingCompletionSummary payload={historyPayload} history onClose={closeHistory}/>}</section>
}
