import {useEffect,useMemo,useState} from 'react';
import {useTranslation} from 'react-i18next';
import {api} from './api';
import {Icon} from './icons';
import {toast} from './feedback';
import './store-i18n';
import './shopping-template-i18n';
import './shopping-store.css';

const unwrap=value=>value?.results||value||[];
const byPosition=(a,b)=>(Number(a.position??2147483647)-Number(b.position??2147483647))||String(a.id).localeCompare(String(b.id),undefined,{numeric:true});
export default function ShoppingStoreMode({list,onLeave,onToggle,onDetails,onAdd,syncStatus}){
 const {t}=useTranslation();const [cartOpen,setCartOpen]=useState(false);const [offersUrl,setOffersUrl]=useState('');const [statusFilter,setStatusFilter]=useState('open');const [completingIds,setCompletingIds]=useState([]);
 const items=list?.items||[];const open=items.filter(x=>!x.checked);const checked=items.filter(x=>x.checked);
 useEffect(()=>{let active=true;setOffersUrl('');if(!list?.family||!list?.id)return()=>{active=false};api(`/shopping-stores/?family=${encodeURIComponent(list.family)}`).then(value=>{if(!active)return;const store=unwrap(value).find(row=>(row.shopping_list_ids||[]).some(id=>String(id)===String(list.id)));setOffersUrl(store?.offers_url||'')}).catch(()=>{});return()=>{active=false}},[list?.family,list?.id]);
 useEffect(()=>{setStatusFilter('open');setCompletingIds([])},[list?.id]);
 const visibleItems=useMemo(()=>statusFilter==='open'?[...open].sort(byPosition):statusFilter==='done'?[...checked].sort(byPosition):[...open].sort(byPosition).concat([...checked].sort(byPosition)),[statusFilter,open,checked]);
 const groups=useMemo(()=>{
  const rows=[...visibleItems];
  const byAisle=rows.length>0&&rows.filter(x=>x.aisle?.trim()).length>rows.length/2;
  const grouped=new Map();for(const item of rows){const key=(byAisle?item.aisle:item.category)?.trim()||t('other');if(!grouped.has(key))grouped.set(key,[]);grouped.get(key).push(item)}
  return [...grouped].map(([name,groupRows])=>({name:byAisle&&name!==t('other')?t('storeUi.aisle',{name}):name,rows:groupRows}));
 },[visibleItems,t]);
 async function toggle(item){
  const target=!item.checked;const id=String(item.id);const confirmInline=target&&statusFilter==='open';
  if(confirmInline){
   setCompletingIds(ids=>ids.includes(id)?ids:[...ids,id]);
   if(!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches)await new Promise(resolve=>setTimeout(resolve,180));
  }
  try{await onToggle(item,target)}catch(e){toast(e.message,{type:'error'})}finally{if(confirmInline)setCompletingIds(ids=>ids.filter(row=>row!==id))}
 }
 const emptyLabel=statusFilter==='open'?t('storeUi.noOpen'):statusFilter==='done'?t('storeUi.noDone'):t('listEmpty');
 return <section className="store-focus" aria-label={t('storeUi.title')}><header className="store-header"><button className="icon-button" onClick={onLeave} aria-label={t('storeUi.leave')}><Icon name="back"/></button><div className="grow"><strong>{list?.name||t('shopping')}</strong><small>{t('storeUi.open',{count:open.length})}</small></div>{offersUrl&&<a className="icon-button" href={offersUrl} target="_blank" rel="noopener noreferrer" aria-label={t('shoppingTemplateUi.offersOpen')}><Icon name="store"/></a>}</header><div className="store-progress" aria-hidden="true"><span style={{width:`${items.length?checked.length/items.length*100:0}%`}}/></div>{syncStatus&&<div className="store-sync" role={syncStatus===t('shoppingOffline.failed')?'alert':'status'}>{syncStatus}</div>}
 <div className="store-status-filter" role="group" aria-label={t('storeUi.statusLabel')}>{[['open','statusOpen'],['done','statusDone'],['all','statusAll']].map(([value,label])=><button key={value} type="button" className={statusFilter===value?'active':''} aria-pressed={statusFilter===value} onClick={()=>setStatusFilter(value)}>{t(`storeUi.${label}`)}{value==='open'?` ${open.length}`:value==='done'?` ${checked.length}`:''}</button>)}</div>
 <div className="store-checklist">{groups.map(group=><section className="store-group" key={group.name} aria-label={group.name}><h2>{group.name}</h2>{group.rows.map(item=>{const completing=completingIds.includes(String(item.id));const selected=item.checked||completing;return <article className={`store-row ${item.checked?'store-checked':''} ${completing?'store-completing':''}`} key={item.id}><button className="store-check" aria-label={selected?`${item.name} · ${t('reopen')}`:t('storeUi.check',{name:item.name,quantity:item.quantity||''})} aria-pressed={selected} disabled={completing} onClick={()=>toggle(item)}><span className="store-checkmark" aria-hidden="true">{selected&&<Icon name="check"/>}</span><strong>{item.name}</strong><span className="store-quantity">{[item.quantity,item.aisle].filter(Boolean).join(' · ')}</span></button><button className="store-details" onClick={()=>onDetails(item)} aria-label={t('storeUi.details',{name:item.name})}><Icon name="info"/></button></article>})}</section>)}{!visibleItems.length&&<div className="smart-empty"><Icon name="doneAll"/><strong>{emptyLabel}</strong></div>}</div>
 <footer className="store-footer"><button onClick={()=>setCartOpen(value=>!value)} aria-expanded={cartOpen}><Icon name="doneAll"/>{t('storeUi.cart',{count:checked.length})}</button><button onClick={onAdd}><Icon name="plus"/>{t('storeUi.add')}</button></footer>{cartOpen&&<div className="store-cart">{[...checked].sort(byPosition).map(item=><button key={item.id} onClick={()=>onToggle(item,false).catch(e=>toast(e.message,{type:'error'}))}><Icon name="check"/><span>{item.name}</span><small>{item.quantity}</small></button>)}</div>}</section>
}
