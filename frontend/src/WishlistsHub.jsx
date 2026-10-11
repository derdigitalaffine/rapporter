import {useEffect,useMemo,useState} from 'react';
import {useTranslation} from 'react-i18next';
import {api} from './api';
import {Icon} from './icons';
import {toast} from './feedback';
import {useFamilyPermissions} from './family-permissions';
import './wishlist-i18n';
import './wishlists.css';

const unwrap=value=>value?.results||value||[];

function ActionPanel({item,list,family,onDone}){
 const {t}=useTranslation();
 const [action,setAction]=useState('task');
 const [shoppingLists,setShoppingLists]=useState([]);
 const [shoppingList,setShoppingList]=useState('');
 const [amount,setAmount]=useState('');
 const [currency,setCurrency]=useState('EUR');
 const [expenseAck,setExpenseAck]=useState(false);
 const [busy,setBusy]=useState(false);
 const [error,setError]=useState('');

 useEffect(()=>{if(list.visibility!=='family')return;api(`/shopping-lists/?family=${encodeURIComponent(family.id)}`).then(rows=>{const active=unwrap(rows).filter(row=>!row.archived&&String(row.family)===String(family.id));setShoppingLists(active);setShoppingList(active[0]?.id||'')}).catch(()=>{})},[family.id,list.visibility]);

 async function create(){
  setBusy(true);setError('');
  try{
   const payload={confirmed:true,action};
   if(action==='shopping')payload.shopping_list=shoppingList;
   if(action==='expense'){payload.amount=amount;payload.currency=currency;payload.acknowledge_family_visibility=expenseAck}
   await api(`/wishlist-items/${item.id}/actions/`,{method:'POST',body:JSON.stringify(payload)});
   toast(t('wishlistUi.actionCreated'),{type:'success'});
   await onDone?.();
  }catch(err){setError(err.message)}finally{setBusy(false)}
 }

 if(list.visibility!=='family')return <div className="wishlist-privacy-note"><Icon name="lock"/><span>{t('wishlistUi.selectedActionBlocked')}</span></div>;
 return <details className="wishlist-action-panel"><summary>{t('wishlistUi.actionTitle')}</summary><p>{t('wishlistUi.actionHint')}</p>
  <label><span className="sr-only">{t('wishlistUi.actionTitle')}</span><select value={action} onChange={e=>setAction(e.target.value)}><option value="task">{t('wishlistUi.task')}</option><option value="shopping">{t('wishlistUi.shopping')}</option><option value="expense">{t('wishlistUi.expense')}</option></select></label>
  {action==='shopping'&&<label>{t('wishlistUi.shoppingList')}<select value={shoppingList} onChange={e=>setShoppingList(e.target.value)} disabled={!shoppingLists.length}>{shoppingLists.length?<>{shoppingLists.map(row=><option key={row.id} value={row.id}>{row.name}</option>)}</>:<option value="">{t('wishlistUi.noShoppingList')}</option>}</select></label>}
  {action==='expense'&&<><div className="wishlist-money"><label>{t('wishlistUi.amount')}<input type="number" min="0.01" step="0.01" inputMode="decimal" value={amount} onChange={e=>setAmount(e.target.value)}/></label><label>{t('wishlistUi.currency')}<input value={currency} maxLength="3" onChange={e=>setCurrency(e.target.value.toUpperCase())}/></label></div><label className="wishlist-check"><input type="checkbox" checked={expenseAck} onChange={e=>setExpenseAck(e.target.checked)}/><span>{t('wishlistUi.expenseAck')}</span></label></>}
  {error&&<p className="error" role="alert">{error}</p>}
  <button type="button" className="secondary compact" onClick={create} disabled={busy||(action==='shopping'&&!shoppingList)||(action==='expense'&&(!amount||!expenseAck))}>{t('wishlistUi.createAction')}</button>
 </details>
}

function OwnerSettings({list,family,onSaved}){
 const {t}=useTranslation();
 const [open,setOpen]=useState(false);
 const [visibility,setVisibility]=useState(list.visibility);
 const [access,setAccess]=useState(()=>new Set((list.access||[]).map(row=>String(row.id))));
 const [busy,setBusy]=useState(false);
 const [error,setError]=useState('');
 useEffect(()=>{setVisibility(list.visibility);setAccess(new Set((list.access||[]).map(row=>String(row.id))))},[list.id,list.visibility,list.access]);
 const candidates=(family?.memberships||[]).filter(row=>String(row.id)!==String(list.owner.id));
 function toggle(id){setAccess(current=>{const next=new Set(current);next.has(id)?next.delete(id):next.add(id);return next})}
 async function save(){
  setBusy(true);setError('');
  try{
   await api(`/wishlists/${list.id}/`,{method:'PATCH',body:JSON.stringify({visibility,access:visibility==='selected'?[...access].map(membership=>({membership})):[]})});
   toast(t('wishlistUi.settingsSaved'),{type:'success'});setOpen(false);await onSaved();
  }catch(err){setError(err.message)}finally{setBusy(false)}
 }
 return <div className="wishlist-settings"><button type="button" className="text-button" aria-expanded={open} onClick={()=>setOpen(value=>!value)}><Icon name="settings"/>{t('wishlistUi.settings')}</button>{open&&<div className="wishlist-settings-panel">
  <label>{t('wishlistUi.visibility')}<select value={visibility} onChange={e=>setVisibility(e.target.value)}><option value="selected">{t('wishlistUi.selected')}</option><option value="family">{t('wishlistUi.family')}</option></select></label>
  <small>{visibility==='selected'?t('wishlistUi.selectedHint'):t('wishlistUi.familyHint')}</small>
  {visibility==='selected'&&candidates.map(member=><label className="wishlist-check" key={member.id}><input type="checkbox" checked={access.has(String(member.id))} onChange={()=>toggle(String(member.id))}/><span>{member.display_name||member.username||member.name||member.user}</span></label>)}
  {error&&<p className="error" role="alert">{error}</p>}<button type="button" className="secondary compact" onClick={save} disabled={busy}>{t('wishlistUi.save')}</button>
 </div>}</div>
}

export default function WishlistsHub({family,onBack,onCreate}){
 const {t}=useTranslation();
 const {canManageSettings}=useFamilyPermissions(family);
 const [lists,setLists]=useState([]);
 const [selectedId,setSelectedId]=useState(()=>new URLSearchParams(location.search).get('wishlist')||'');
 const [loading,setLoading]=useState(true);
 const [error,setError]=useState('');

 async function load(){
  setLoading(true);setError('');
  try{
   const rows=await api(`/wishlists/?family=${encodeURIComponent(family.id)}`);
   setLists(rows||[]);
   const requested=new URLSearchParams(location.search).get('wishlist');
   setSelectedId(current=>rows?.some(row=>String(row.id)===String(requested||current))?(requested||current):(rows?.[0]?.id||''));
  }catch(err){setError(err.message)}finally{setLoading(false)}
 }
 useEffect(()=>{load()},[family.id]);
 const selected=useMemo(()=>lists.find(row=>String(row.id)===String(selectedId))||lists[0]||null,[lists,selectedId]);

 async function reservation(item,status){
  try{await api(`/wishlist-items/${item.id}/reservation/`,{method:'POST',body:JSON.stringify({status})});toast(t('wishlistUi.reservationSaved'),{type:'success'});await load()}catch(err){toast(err.message,{type:'error'})}
 }
 async function release(item){
  try{await api(`/wishlist-items/${item.id}/reservation/`,{method:'DELETE'});toast(t('wishlistUi.reservationReleased'),{type:'success'});await load()}catch(err){toast(err.message,{type:'error'})}
 }
 async function archive(item){
  try{await api(`/wishlist-items/${item.id}/`,{method:'DELETE'});await load()}catch(err){toast(err.message,{type:'error'})}
 }

 return <div className="wishlist-page">
  <div className="page-head wishlist-head"><div><button type="button" className="text-button back-link" onClick={onBack}><Icon name="back"/>{t('wishlistUi.back')}</button><h1>{t('wishlistUi.title')}</h1></div>{canManageSettings&&<button type="button" className="primary compact" onClick={()=>onCreate?.('wish',{wishlistId:selected?.is_owner?selected.id:null})}><Icon name="plus"/>{t('wishlistUi.newWish')}</button>}</div>
  {error&&<div className="smart-empty" role="alert"><Icon name="warning"/><strong>{t('wishlistUi.loadFailed')}</strong><span>{error}</span><button className="secondary compact" onClick={load}><Icon name="refresh"/></button></div>}
  {!error&&loading&&<div className="smart-empty" role="status"><Icon name="refresh" className="spin"/><strong>{t('sessionUi.loading')}</strong></div>}
  {!loading&&!error&&!lists.length&&<div className="smart-empty"><Icon name="heart" size={34}/><strong>{t('wishlistUi.empty')}</strong>{canManageSettings&&<button className="primary compact" onClick={()=>onCreate?.('wish')}>{t('wishlistUi.newWish')}</button>}<small>{t('wishlistUi.adultCoreHint')}</small></div>}
  {!loading&&!error&&lists.length>0&&<div className="wishlist-layout">
   <nav className="wishlist-list-tabs" aria-label={t('wishlistUi.title')}>{lists.map(list=><button key={list.id} className={String(selected?.id)===String(list.id)?'active':''} aria-current={String(selected?.id)===String(list.id)?'page':undefined} onClick={()=>setSelectedId(list.id)}><span>{list.title}</span><small>{list.is_owner?t('wishlistUi.yourList'):t('wishlistUi.owner',{name:list.owner.name})}</small></button>)}</nav>
   {selected&&<section className="card wishlist-card" aria-labelledby={`wishlist-${selected.id}`}><header className="wishlist-card-head"><div><h2 id={`wishlist-${selected.id}`}>{selected.title}</h2><span className="wishlist-badge"><Icon name={selected.visibility==='family'?'members':'lock'}/>{selected.visibility==='family'?t('wishlistUi.family'):t('wishlistUi.selected')}</span></div>{selected.is_owner&&<button className="secondary compact" onClick={()=>onCreate?.('wish',{wishlistId:selected.id})}><Icon name="plus"/>{t('wishlistUi.newWish')}</button>}</header>
    {selected.is_owner&&<><p className="wishlist-surprise"><Icon name="lock"/>{t('wishlistUi.surpriseOwner')}</p><OwnerSettings list={selected} family={family} onSaved={load}/></>}
    {!selected.items?.length?<div className="empty">{t('wishlistUi.emptyItems')}</div>:<div className="wishlist-items">{selected.items.map(item=><article className="wishlist-item" key={item.id}><div className="wishlist-item-main"><div><h3>{item.title}</h3>{item.note&&<p>{item.note}</p>}<div className="wishlist-meta">{item.priority&&<span><Icon name="priority"/>{t(`wishlistUi.${item.priority}`)}</span>}{item.url&&<a href={item.url} target="_blank" rel="noopener noreferrer"><Icon name="link"/>{t('wishlistUi.openLink')}</a>}</div></div>{selected.is_owner&&<button type="button" className="icon-button" onClick={()=>archive(item)} aria-label={t('wishlistUi.archiveItem')}><Icon name="delete"/></button>}</div>
      {'reservation'in item&&<div className="wishlist-reservation">{!item.reservation&&item.can_reserve&&<button type="button" className="secondary compact" onClick={()=>reservation(item,'reserved')}>{t('wishlistUi.reserve')}</button>}{item.reservation&&<><strong>{item.reservation.status==='purchased'?t('wishlistUi.purchasedBy',{name:item.reservation.reserved_by.name}):t('wishlistUi.reservedBy',{name:item.reservation.reserved_by.name})}</strong>{item.reservation.note&&<span>{item.reservation.note}</span>}{item.reservation.mine&&<div className="wishlist-inline-actions">{item.reservation.status!=='purchased'&&<button type="button" className="secondary compact" onClick={()=>reservation(item,'purchased')}>{t('wishlistUi.markPurchased')}</button>}<button type="button" className="text-button" onClick={()=>release(item)}>{t('wishlistUi.release')}</button></div>}</>}</div>}
      {!selected.is_owner&&item.can_reserve&&<ActionPanel item={item} list={selected} family={family} onDone={load}/>} 
     </article>)}</div>}
   </section>}
  </div>}
 </div>
}
