import {useEffect,useMemo,useRef,useState} from 'react';
import {useTranslation} from 'react-i18next';
import {Icon} from './icons';
import {toast} from './feedback';
import './store-i18n';
import './shopping-store.css';

export default function ShoppingStoreMode({list,onLeave,onToggle,onDetails,onAdd,onRefresh,syncStatus}){
 const {t,i18n}=useTranslation();const [flashed,setFlashed]=useState({});const [cartOpen,setCartOpen]=useState(false);const timers=useRef(new Map());const buttons=useRef(new Map());
 useEffect(()=>()=>{for(const timer of timers.current.values())clearTimeout(timer)},[]);
 const items=list?.items||[];const open=items.filter(x=>!x.checked);const checked=items.filter(x=>x.checked);
 const groups=useMemo(()=>{
  const rows=[...open,...Object.values(flashed).filter(x=>!open.some(row=>row.id===x.id))];
  const byAisle=rows.length>0&&rows.filter(x=>x.aisle?.trim()).length>rows.length/2;
  const grouped=new Map();for(const item of rows){const key=(byAisle?item.aisle:item.category)?.trim()||t('other');if(!grouped.has(key))grouped.set(key,[]);grouped.get(key).push(item)}
  return [...grouped].sort(([a],[b])=>a.localeCompare(b,i18n.language,{numeric:true,sensitivity:'base'})).map(([name,rows])=>({name:byAisle&&name!==t('other')?t('storeUi.aisle',{name}):name,rows:rows.sort((a,b)=>String(a.id).localeCompare(String(b.id),undefined,{numeric:true}))}));
 },[items,flashed,t,i18n.language]);
 async function check(item){
  if(timers.current.has(item.id))return;
  const hadFocus=document.activeElement===buttons.current.get(item.id);const ids=groups.flatMap(group=>group.rows.map(x=>x.id));const index=ids.indexOf(item.id);
  setFlashed(current=>({...current,[item.id]:item}));
  const timer=setTimeout(()=>{timers.current.delete(item.id);setFlashed(current=>{const next={...current};delete next[item.id];return next});if(hadFocus)requestAnimationFrame(()=>buttons.current.get(ids[index+1]||ids[index-1])?.focus())},350);timers.current.set(item.id,timer);
  try{await onToggle(item,true);toast(t('storeUi.checked',{name:item.name}),{type:'success',actionLabel:t('storeUi.undo'),onAction:()=>onToggle(item,false).catch(e=>toast(e.message,{type:'error'}))})}catch(e){clearTimeout(timer);timers.current.delete(item.id);setFlashed(current=>{const next={...current};delete next[item.id];return next});toast(e.message,{type:'error'})}
 }
 return <section className="store-focus" aria-label={t('storeUi.title')}><header className="store-header"><button className="icon-button" onClick={onLeave} aria-label={t('storeUi.leave')}><Icon name="back"/></button><div className="grow"><strong>{list?.name||t('shopping')}</strong><small>{t('storeUi.open',{count:open.length})}</small></div><button className="icon-button" onClick={onAdd} aria-label={t('storeUi.add')}><Icon name="plus"/></button><button className="icon-button" onClick={onRefresh} aria-label={t('storeUi.refresh')}><Icon name="refresh"/></button></header><div className="store-progress" aria-hidden="true"><span style={{width:`${items.length?checked.length/items.length*100:0}%`}}/></div>{syncStatus&&<div className="store-sync" role="status">{syncStatus}</div>}
 <div className="store-checklist">{groups.map(group=><section className="store-group" key={group.name} aria-label={group.name}><h2>{group.name}</h2>{group.rows.map(item=><article className={`store-row ${flashed[item.id]?'store-checked':''}`} key={item.id}><button ref={node=>{if(node)buttons.current.set(item.id,node);else buttons.current.delete(item.id)}} className="store-check" aria-label={t('storeUi.check',{name:item.name,quantity:item.quantity||''})} aria-pressed={!!flashed[item.id]} aria-disabled={!!flashed[item.id]} onClick={()=>check(item)}><span className="store-checkmark" aria-hidden="true">{flashed[item.id]&&<Icon name="check"/>}</span><strong>{item.name}</strong><span className="store-quantity">{[item.quantity,item.aisle].filter(Boolean).join(' · ')}</span></button><button className="store-details" onClick={()=>onDetails(item)} aria-label={t('storeUi.details',{name:item.name})}><Icon name="info"/></button></article>)}</section>)}{!open.length&&!Object.keys(flashed).length&&<div className="smart-empty"><Icon name="doneAll"/><strong>{t(checked.length?'shoppingComplete':'listEmpty')}</strong></div>}</div>
 <footer className="store-footer"><button onClick={()=>setCartOpen(value=>!value)} aria-expanded={cartOpen}><Icon name="doneAll"/>{t('storeUi.cart',{count:checked.length})}</button><button onClick={onAdd}><Icon name="plus"/>{t('storeUi.add')}</button></footer>{cartOpen&&<div className="store-cart">{checked.map(item=><button key={item.id} onClick={()=>onToggle(item,false).catch(e=>toast(e.message,{type:'error'}))}><Icon name="check"/><span>{item.name}</span><small>{item.quantity}</small></button>)}</div>}</section>
}
