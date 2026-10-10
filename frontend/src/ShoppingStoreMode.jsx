import {useMemo,useState} from 'react';
import {useTranslation} from 'react-i18next';
import {Icon} from './icons';
import {toast} from './feedback';
import './store-i18n';
import './shopping-store.css';

export default function ShoppingStoreMode({list,onLeave,onToggle,onDetails,onAdd,onRefresh,syncStatus}){
 const {t,i18n}=useTranslation();const [cartOpen,setCartOpen]=useState(false);
 const items=list?.items||[];const open=items.filter(x=>!x.checked);const checked=items.filter(x=>x.checked);
 const groups=useMemo(()=>{
  const rows=[...items];
  const byAisle=rows.length>0&&rows.filter(x=>x.aisle?.trim()).length>rows.length/2;
  const grouped=new Map();for(const item of rows){const key=(byAisle?item.aisle:item.category)?.trim()||t('other');if(!grouped.has(key))grouped.set(key,[]);grouped.get(key).push(item)}
  return [...grouped].sort(([a],[b])=>a.localeCompare(b,i18n.language,{numeric:true,sensitivity:'base'})).map(([name,groupRows])=>({name:byAisle&&name!==t('other')?t('storeUi.aisle',{name}):name,rows:groupRows.sort((a,b)=>Number(a.checked)-Number(b.checked)||String(a.id).localeCompare(String(b.id),undefined,{numeric:true}))}));
 },[items,t,i18n.language]);
 async function toggle(item){
  const target=!item.checked;
  try{
   await onToggle(item,target);
   if(target)toast(t('storeUi.checked',{name:item.name}),{type:'success',actionLabel:t('storeUi.undo'),onAction:()=>onToggle(item,false).catch(e=>toast(e.message,{type:'error'}))});
  }catch(e){toast(e.message,{type:'error'})}
 }
 return <section className="store-focus" aria-label={t('storeUi.title')}><header className="store-header"><button className="icon-button" onClick={onLeave} aria-label={t('storeUi.leave')}><Icon name="back"/></button><div className="grow"><strong>{list?.name||t('shopping')}</strong><small>{t('storeUi.open',{count:open.length})}</small></div><button className="icon-button" onClick={onAdd} aria-label={t('storeUi.add')}><Icon name="plus"/></button><button className="icon-button" onClick={onRefresh} aria-label={t('storeUi.refresh')}><Icon name="refresh"/></button></header><div className="store-progress" aria-hidden="true"><span style={{width:`${items.length?checked.length/items.length*100:0}%`}}/></div>{syncStatus&&<div className="store-sync" role="status">{syncStatus}</div>}
 <div className="store-checklist">{groups.map(group=><section className="store-group" key={group.name} aria-label={group.name}><h2>{group.name}</h2>{group.rows.map(item=><article className={`store-row ${item.checked?'store-checked':''}`} key={item.id}><button className="store-check" aria-label={item.checked?`${item.name} · ${t('reopen')}`:t('storeUi.check',{name:item.name,quantity:item.quantity||''})} aria-pressed={!!item.checked} onClick={()=>toggle(item)}><span className="store-checkmark" aria-hidden="true">{item.checked&&<Icon name="check"/>}</span><strong>{item.name}</strong><span className="store-quantity">{[item.quantity,item.aisle].filter(Boolean).join(' · ')}</span></button><button className="store-details" onClick={()=>onDetails(item)} aria-label={t('storeUi.details',{name:item.name})}><Icon name="info"/></button></article>)}</section>)}{!items.length&&<div className="smart-empty"><Icon name="doneAll"/><strong>{t('listEmpty')}</strong></div>}</div>
 <footer className="store-footer"><button onClick={()=>setCartOpen(value=>!value)} aria-expanded={cartOpen}><Icon name="doneAll"/>{t('storeUi.cart',{count:checked.length})}</button><button onClick={onAdd}><Icon name="plus"/>{t('storeUi.add')}</button></footer>{cartOpen&&<div className="store-cart">{checked.map(item=><button key={item.id} onClick={()=>onToggle(item,false).catch(e=>toast(e.message,{type:'error'}))}><Icon name="check"/><span>{item.name}</span><small>{item.quantity}</small></button>)}</div>}</section>
}
