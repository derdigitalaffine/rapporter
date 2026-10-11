import {useEffect,useMemo,useState} from 'react';
import {useTranslation} from 'react-i18next';
import {api} from './api';
import {Icon} from './icons';
import {toast} from './feedback';
import './wishlist-i18n';
import './wishlists.css';

const NEW='__new__';

export default function WishlistEditor({family,context={},onClose,onSaved}){
 const {t}=useTranslation();
 const [lists,setLists]=useState([]);
 const [target,setTarget]=useState(context.wishlistId||NEW);
 const [title,setTitle]=useState('');
 const [url,setUrl]=useState('');
 const [note,setNote]=useState('');
 const [priority,setPriority]=useState('');
 const [listTitle,setListTitle]=useState(t('wishlistUi.title'));
 const [visibility,setVisibility]=useState('selected');
 const [access,setAccess]=useState([]);
 const [sessionUser,setSessionUser]=useState(null);
 const [busy,setBusy]=useState(false);
 const [error,setError]=useState('');

 useEffect(()=>{let live=true;Promise.all([
  api(`/wishlists/?family=${encodeURIComponent(family.id)}`),
  api('/auth/session/')
 ]).then(([rows,session])=>{if(!live)return;const owned=(rows||[]).filter(row=>row.is_owner);setLists(owned);setSessionUser(session?.user||null);const requested=owned.find(row=>String(row.id)===String(context.wishlistId));setTarget(requested?.id||owned[0]?.id||NEW)}).catch(err=>live&&setError(err.message));return()=>{live=false}},[family.id,context.wishlistId]);

 const members=useMemo(()=>(family?.memberships||[]).filter(member=>String(member.user)!==String(sessionUser?.id)),[family?.memberships,sessionUser?.id]);
 const creatingList=target===NEW;

 function toggleAccess(id){setAccess(current=>current.includes(id)?current.filter(value=>value!==id):[...current,id])}

 async function submit(event){
  event.preventDefault();
  if(!title.trim())return;
  setBusy(true);setError('');
  try{
   let wishlistId=target;
   if(creatingList){
    const created=await api('/wishlists/',{method:'POST',body:JSON.stringify({
     family:family.id,
     title:(listTitle.trim()||t('wishlistUi.title')),
     visibility,
     access:visibility==='selected'?access.map(membership=>({membership})):[]
    })});
    wishlistId=created.id;
   }
   const saved=await api(`/wishlists/${wishlistId}/items/`,{method:'POST',body:JSON.stringify({
    title:title.trim(),url:url.trim(),note:note.trim(),priority
   })});
   toast(t('wishlistUi.saved'),{type:'success'});
   await onSaved?.(saved);
   onClose();
  }catch(err){setError(err.message)}finally{setBusy(false)}
 }

 return <div className="sheet-backdrop" onMouseDown={event=>event.target===event.currentTarget&&!busy&&onClose()}>
  <section className="quick-sheet wishlist-sheet" role="dialog" aria-modal="true" aria-labelledby="wishlist-editor-title">
   <div className="sheet-handle"/>
   <div className="sheet-head"><div><small>{family?.name}</small><h2 id="wishlist-editor-title">{t('wishlistUi.newWish')}</h2></div><button className="sheet-close" type="button" onClick={onClose} disabled={busy} aria-label={t('wishlistUi.close')}><Icon name="close"/></button></div>
   <form className="quick-form wishlist-editor-form" onSubmit={submit}>
    <label>{t('wishlistUi.list')}<select value={target} onChange={e=>setTarget(e.target.value)}>{lists.map(list=><option value={list.id} key={list.id}>{list.title}</option>)}<option value={NEW}>{t('wishlistUi.newList')}</option></select></label>
    {creatingList&&<fieldset className="wishlist-fieldset"><legend>{t('wishlistUi.newList')}</legend>
     <label>{t('wishlistUi.listTitle')}<input value={listTitle} onChange={e=>setListTitle(e.target.value)} required/></label>
     <label>{t('wishlistUi.visibility')}<select value={visibility} onChange={e=>setVisibility(e.target.value)}><option value="selected">{t('wishlistUi.selected')}</option><option value="family">{t('wishlistUi.family')}</option></select></label>
     <small>{visibility==='selected'?t('wishlistUi.selectedHint'):t('wishlistUi.familyHint')}</small>
     {visibility==='selected'&&members.length>0&&<div className="wishlist-access"><strong>{t('wishlistUi.access')}</strong>{members.map(member=><label className="wishlist-check" key={member.id}><input type="checkbox" checked={access.includes(String(member.id))} onChange={()=>toggleAccess(String(member.id))}/><span>{member.display_name||member.username||member.name||member.user}</span></label>)}</div>}
    </fieldset>}
    <label>{t('wishlistUi.wishTitle')}<input value={title} onChange={e=>setTitle(e.target.value)} required autoFocus={!creatingList} maxLength="180"/></label>
    <label>{t('wishlistUi.url')}<input type="url" inputMode="url" placeholder="https://…" value={url} onChange={e=>setUrl(e.target.value)}/></label>
    <label>{t('wishlistUi.note')}<textarea rows="3" value={note} onChange={e=>setNote(e.target.value)}/></label>
    <label>{t('wishlistUi.priority')}<select value={priority} onChange={e=>setPriority(e.target.value)}><option value="">{t('wishlistUi.priorityNone')}</option><option value="low">{t('wishlistUi.low')}</option><option value="normal">{t('wishlistUi.normal')}</option><option value="high">{t('wishlistUi.high')}</option></select></label>
    {error&&<p className="error" role="alert">{error}</p>}
    <button className="primary" type="submit" disabled={busy||!title.trim()}>{busy?t('wishlistUi.saving'):t('wishlistUi.save')}</button>
   </form>
  </section>
 </div>
}
