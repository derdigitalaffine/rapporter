import {useEffect,useState} from 'react';
import {useTranslation} from 'react-i18next';
import {api} from './api';
import {Icon} from './icons';
import {toast} from './feedback';
import ExpenseEditor from './ExpenseEditor';
import ShoppingCompletionSummary from './ShoppingCompletionSummary';
import {flushShoppingMutations} from './shopping-offline';
import './shopping-checkout-i18n';
import './shopping-checkout.css';

const unwrap=x=>x?.results||x||[];

export default function ShoppingCheckoutFlow({list,sessionId,openCount,onClose,onCompleted}){
 const {t}=useTranslation();
 const [stage,setStage]=useState('review');
 const [completion,setCompletion]=useState(null);
 const [linkedExpense,setLinkedExpense]=useState(null);
 const [busy,setBusy]=useState(false);
 const [expenseMode,setExpenseMode]=useState('');
 const [family,setFamily]=useState(null);
 const [error,setError]=useState('');
 const [stores,setStores]=useState([]);
 const [storeId,setStoreId]=useState('');
 const [storesLoading,setStoresLoading]=useState(false);
 const [storeLoadFailed,setStoreLoadFailed]=useState(false);

 useEffect(()=>{
  if(!list?.family){setStores([]);setStoreId('');return}
  let alive=true;
  setStoresLoading(true);setStoreLoadFailed(false);
  api(`/shopping-stores/?family=${encodeURIComponent(list.family)}`)
   .then(payload=>{
    if(!alive)return;
    const rows=unwrap(payload).filter(row=>row.active);
    setStores(rows);
    setStoreId(current=>{
     if(current&&rows.some(row=>String(row.id)===String(current)))return current;
     const assigned=rows.find(row=>(row.shopping_list_ids||[]).some(id=>String(id)===String(list.id)));
     return assigned?.id||'';
    });
   })
   .catch(()=>{if(alive){setStores([]);setStoreLoadFailed(true)}})
   .finally(()=>{if(alive)setStoresLoading(false)});
  return()=>{alive=false};
 },[list?.family,list?.id]);

 async function complete(openItems='keep'){
  if(busy||!list?.id||!sessionId)return;
  setBusy(true);setError('');setStage('finishing');
  try{
   if(typeof navigator!=='undefined'&&!navigator.onLine)throw new Error(t('shoppingOffline.offlineReady'));
   const flushed=await flushShoppingMutations(list.family);
   if(flushed.blocked||flushed.failed||flushed.pending||flushed.error)throw new Error(t('shoppingOffline.failed'));
   const payload=await api('/shopping-sessions/complete/',{method:'POST',body:JSON.stringify({shopping_list:list.id,session:sessionId,open_items:openItems,store:storeId||null})});
   setCompletion(payload);setStage('done');
   if(payload?.session?.id&&typeof window!=='undefined'){
    const url=new URL(window.location.href);url.searchParams.set('session',payload.session.id);history.replaceState(history.state,'',url.pathname+url.search);
   }
   onCompleted?.(payload);
  }catch(err){setError(err.message||t('shoppingCheckout.completeFailed'));setStage('review')}
  finally{setBusy(false)}
 }
 async function openExpense(mode){
  setBusy(true);setError('');
  try{
   const loaded=await api(`/families/${encodeURIComponent(list.family)}/`);
   setFamily(loaded);setExpenseMode(mode);
  }catch(err){setError(err.message||t('shoppingCheckout.loadFamilyFailed'))}
  finally{setBusy(false)}
 }
 async function linkExpense(expense){
  if(!expense?.id||!completion?.session?.id)return;
  try{
   await api('/context-links/',{method:'POST',body:JSON.stringify({family:list.family,source:{type:'expense',id:expense.id},context:{type:'shopping_session',id:completion.session.id},relation:'context'})});
  }catch(err){
   toast(t('shoppingCheckout.linkFailed'),{type:'error'});
   throw err;
  }
  setExpenseMode('');setLinkedExpense(expense);setStage('summary');
 }
 const expensePrefill={title:completion?.completion?.shopping_list?.store||list?.store||'',occurred_at:completion?.session?.completed_at||completion?.completion?.completed_at||''};
 if(expenseMode&&family)return <ExpenseEditor family={family} initialMode={expenseMode} initialPrefill={expensePrefill} onClose={()=>setExpenseMode('')} onSaved={linkExpense}/>;
 if(stage==='summary'&&completion)return <ShoppingCompletionSummary payload={completion} expense={linkedExpense} onClose={onClose}/>;
 const purchased=completion?.completion?.purchased_count||0;
 const stillOpen=completion?.completion?.open_count??openCount;
 return <div className="sheet-backdrop shopping-checkout-backdrop" onMouseDown={event=>{if(event.target===event.currentTarget&&!busy&&stage==='review')onClose?.()}}><section className="quick-sheet shopping-checkout-sheet" role="dialog" aria-modal="true" aria-labelledby="shopping-checkout-title"><div className="sheet-handle"/>
  {stage==='review'&&<><div className="sheet-head"><div><small>{list?.name}</small><h2 id="shopping-checkout-title">{t('shoppingCheckout.reviewTitle')}</h2></div><button className="sheet-close" onClick={onClose} aria-label={t('shoppingCheckout.cancel')}><Icon name="close"/></button></div><div className="shopping-checkout-section"><strong>{t('shoppingCheckout.storeTitle')}</strong><label htmlFor="shopping-checkout-store">{t('shoppingCheckout.storeLabel')}</label><select id="shopping-checkout-store" value={storeId} onChange={event=>setStoreId(event.target.value)} disabled={busy||storesLoading}><option value="">{storesLoading?t('shoppingCheckout.storeLoading'):t('shoppingCheckout.noStore')}</option>{stores.map(store=><option key={store.id} value={store.id}>{store.display_label}{store.address?` · ${store.address}`:''}</option>)}</select>{list?.store&&!storeId&&<small>{t('shoppingCheckout.currentStore',{store:list.store})}</small>}{storeLoadFailed&&<small role="status">{t('shoppingCheckout.storeLoadFailed')}</small>}</div>{openCount>0?<div className="shopping-checkout-section"><strong>{t('shoppingCheckout.openTitle',{count:openCount})}</strong><p>{t('shoppingCheckout.openHint')}</p>{error&&<p className="error" role="alert">{error}</p>}<div className="shopping-checkout-actions"><button className="primary" disabled={busy} onClick={()=>complete('keep')}><Icon name="check"/>{t('shoppingCheckout.keepOpen')}</button><button className="secondary" disabled={busy} onClick={()=>complete('remove')}><Icon name="delete"/>{t('shoppingCheckout.removeOpen')}</button><button className="text-button" disabled={busy} onClick={onClose}>{t('shoppingCheckout.cancel')}</button></div></div>:<div className="shopping-checkout-section">{error&&<p className="error" role="alert">{error}</p>}<div className="shopping-checkout-actions"><button className="primary" disabled={busy} onClick={()=>complete('keep')}><Icon name="check"/>{t('shoppingCheckout.finish')}</button><button className="text-button" disabled={busy} onClick={onClose}>{t('shoppingCheckout.cancel')}</button></div></div>}</>}
  {stage==='finishing'&&<div className="shopping-checkout-status" role="status"><Icon name="refresh" size={30}/><strong id="shopping-checkout-title">{t('shoppingCheckout.finishing')}</strong></div>}
  {stage==='done'&&<><div className="sheet-head"><div><small>{list?.name}</small><h2 id="shopping-checkout-title">{t('shoppingCheckout.doneTitle')}</h2></div></div><div className="shopping-checkout-summary" role="status"><Icon name="doneAll" size={34}/><strong>{t('shoppingCheckout.doneSummaryDetailed',{purchased,open:stillOpen})}</strong></div><p>{t('shoppingCheckout.expenseHint')}</p>{error&&<p className="error" role="alert">{error}</p>}<div className="shopping-checkout-actions"><button className="primary" disabled={busy} onClick={()=>openExpense('receipt')}><Icon name="receipt"/>{t('shoppingCheckout.receipt')}</button><button className="secondary" disabled={busy} onClick={()=>openExpense('quick')}><Icon name="edit"/>{t('shoppingCheckout.amount')}</button><button className="text-button" disabled={busy} onClick={onClose}>{t('shoppingCheckout.withoutExpense')}</button></div></>}
 </section></div>;
}
