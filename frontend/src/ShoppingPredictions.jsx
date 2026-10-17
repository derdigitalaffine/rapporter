import {useEffect,useState} from 'react';
import {useTranslation} from 'react-i18next';
import './prediction-i18n';
import {api} from './api';
import {Icon} from './icons';
import {toast} from './feedback';
import {requestCreate} from './create-request';
import SmartShopping from './SmartShopping';
import ShoppingBudgetCommitment from './ShoppingBudgetCommitment';
import {SHOPPING_BUDGET_PURCHASE_EVENT} from './shopping-offline';
import './shopping-predictions.css';

const isStoreMode=()=>new URLSearchParams(location.search).get('mode')==='store';

function PredictionPanel({family,onAccepted}){
 const {t}=useTranslation();const [rows,setRows]=useState([]);const [busy,setBusy]=useState('');
 async function load(){if(!family){setRows([]);return}try{const result=await api(`/shopping-predictions/?family=${encodeURIComponent(family.id)}`);setRows(result?.suggestions||[])}catch{setRows([])}}
 useEffect(()=>{load()},[family?.id]);
 async function accept(row){if(busy)return;setBusy(row.key);try{await api('/shopping-predictions/accept/',{method:'POST',body:JSON.stringify({family:family.id,key:row.key})});toast(t('predictionUi.shoppingAdded',{name:row.name}),{type:'success'});await load();await onAccepted?.()}catch(e){toast(e.message||t('saveFailed'),{type:'error'})}finally{setBusy('')}}
 async function feedback(row,action){if(busy)return;setBusy(`${action}:${row.key}`);try{await api('/shopping-predictions/feedback/',{method:'POST',body:JSON.stringify({family:family.id,key:row.key,action})});setRows(current=>current.filter(item=>item.key!==row.key))}catch(e){toast(e.message||t('saveFailed'),{type:'error'})}finally{setBusy('')}}
 if(!rows.length)return null;
 return <section className="shopping-predictions" aria-labelledby="shopping-predictions-title"><div className="shopping-predictions-head"><div><small>{t('predictionUi.shoppingHint')}</small><h2 id="shopping-predictions-title">{t('predictionUi.shoppingTitle')}</h2></div></div><div className="shopping-prediction-list">{rows.map(row=><article className="shopping-prediction" key={row.key}><span className="round-icon"><Icon name="shopping"/></span><div className="grow"><strong>{row.name}</strong><small>{t('predictionUi.shoppingReason',{days:row.prediction?.expected_interval_days,since:row.prediction?.days_since_purchase})}</small></div><div className="shopping-prediction-actions"><button className="primary compact" onClick={()=>accept(row)} disabled={!!busy}><Icon name="plus"/>{t('predictionUi.shoppingAdd')}</button><button type="button" className="secondary compact" onClick={()=>feedback(row,'snoozed')} disabled={!!busy} aria-label={t('predictionUi.shoppingSnoozeLabel',{name:row.name})}>{t('predictionUi.shoppingSnooze')}</button></div><button className="icon-button" onClick={()=>feedback(row,'dismissed')} disabled={!!busy} aria-label={`${row.name}: ${t('predictionUi.shoppingDismiss')}`}><Icon name="close"/></button></article>)}</div></section>
}

export default function SmartShoppingPredicted({family,onChanged,...props}){
 const [revision,setRevision]=useState(0);
 const [storeMode,setStoreMode]=useState(isStoreMode);
 async function accepted(){setRevision(value=>value+1);await onChanged?.()}
 useEffect(()=>{
  const syncMode=()=>setStoreMode(isStoreMode());
  window.addEventListener('popstate',syncMode);
  return()=>window.removeEventListener('popstate',syncMode);
 },[]);
 useEffect(()=>{
  const openExpense=async event=>{
   const detail=event.detail||{};
   if(!family?.id||String(detail.familyId)!==String(family.id)||!detail.itemId||!detail.commitment)return;
   try{
    const item=await api(`/shopping-items/${encodeURIComponent(detail.itemId)}/`);
    const commitment=detail.commitment;
    requestCreate('expense',{
     origin:'shopping',
     mode:'details',
     ledger:commitment.ledger,
     commitment:commitment.id,
     commitmentBudget:commitment.budget,
     shoppingItem:item.id,
     prefill:{
      title:item.name||'',
      merchant:item.name||'',
      total_amount:commitment.amount,
      currency:commitment.currency||'EUR',
      ledger:commitment.ledger,
     },
    });
   }catch(error){toast(error.message,{type:'error'})}
  };
  window.addEventListener(SHOPPING_BUDGET_PURCHASE_EVENT,openExpense);
  return()=>window.removeEventListener(SHOPPING_BUDGET_PURCHASE_EVENT,openExpense);
 },[family?.id]);
 const syncModeAfterShoppingAction=()=>setStoreMode(isStoreMode());
 return <div className="shopping-prediction-shell" onClick={syncModeAfterShoppingAction}>{!storeMode&&<PredictionPanel family={family} onAccepted={accepted}/>}<SmartShopping key={`${family?.id||'none'}-${revision}`} family={family} onChanged={onChanged} {...props}/>{!storeMode&&<aside className="shopping-secondary-tools"><ShoppingBudgetCommitment key={`budget-${family?.id||'none'}-${revision}`} family={family} onChanged={accepted}/></aside>}</div>
}
