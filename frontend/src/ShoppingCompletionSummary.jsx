import {useEffect,useState} from 'react';
import {useTranslation} from 'react-i18next';
import {api} from './api';
import {Icon} from './icons';
import './shopping-checkout-i18n';
import './shopping-checkout.css';

const money=(value,currency='EUR',locale='de')=>{
 try{return new Intl.NumberFormat(locale,{style:'currency',currency}).format(Number(value||0))}catch{return `${value||0} ${currency}`}
};

export default function ShoppingCompletionSummary({payload,onClose,expense=null,history=false}){
 const {t,i18n}=useTranslation();
 const completion=payload?.completion||{};
 const session=payload?.session||{};
 const [historyExpense,setHistoryExpense]=useState(null);
 useEffect(()=>{
  if(!history||expense||!session?.id||!completion?.shopping_list?.id){setHistoryExpense(null);return}
  let live=true;
  (async()=>{
   try{
    const shoppingList=await api(`/shopping-lists/${encodeURIComponent(completion.shopping_list.id)}/`);
    if(!shoppingList?.family)return;
    const links=await api(`/context-links/?family=${encodeURIComponent(shoppingList.family)}&anchor_type=shopping_session&anchor_id=${encodeURIComponent(session.id)}&limit=10`);
    const link=(links?.results||[]).find(row=>row?.source?.type==='expense'||row?.context?.type==='expense');
    const ref=link?.source?.type==='expense'?link.source:link?.context?.type==='expense'?link.context:null;
    if(!ref?.id)return;
    const loaded=await api(`/expenses/${encodeURIComponent(ref.id)}/`);
    if(live)setHistoryExpense(loaded);
   }catch{
    // Context Links already intersect Shopping + Finance ACLs. Missing or
    // newly restricted finance context must not make Shopping history fail.
    if(live)setHistoryExpense(null);
   }
  })();
  return()=>{live=false};
 },[history,expense,session?.id,completion?.shopping_list?.id]);
 const shownExpense=expense||historyExpense;
 const purchased=completion.purchased_count||0;
 const open=completion.open_count||0;
 const completedAt=session.completed_at||completion.completed_at;
 const date=completedAt?new Intl.DateTimeFormat(i18n.language||'de',{dateStyle:'medium',timeStyle:'short'}).format(new Date(completedAt)):'';
 const amount=shownExpense?.total_amount?money(shownExpense.total_amount,shownExpense.currency||'EUR',i18n.language):'';
 return <div className="sheet-backdrop shopping-checkout-backdrop" onMouseDown={event=>{if(event.target===event.currentTarget)onClose?.()}}><section className="quick-sheet shopping-checkout-sheet" role="dialog" aria-modal="true" aria-labelledby="shopping-completion-title"><div className="sheet-handle"/><div className="sheet-head"><div><small>{history?t('shoppingCheckout.historyLabel'):completion?.shopping_list?.name}</small><h2 id="shopping-completion-title">{t('shoppingCheckout.doneTitle')}</h2></div><button className="sheet-close" onClick={onClose} aria-label={t('shoppingCheckout.closeSummary')}><Icon name="close"/></button></div><div className="shopping-checkout-summary shopping-completion-summary" role="status"><Icon name="doneAll" size={34}/><strong>{t('shoppingCheckout.doneSummaryDetailed',{purchased,open})}</strong>{date&&<small>{t('shoppingCheckout.completedAt',{date})}</small>}{shownExpense&&<span className="shopping-completion-expense"><Icon name={shownExpense.source==='receipt'?'receipt':'edit'}/>{shownExpense.source==='receipt'?t('shoppingCheckout.receiptSaved'):t('shoppingCheckout.expenseSaved',{amount})}</span>}</div>{(completion.purchased_items||[]).length>0&&<details className="shopping-completion-items"><summary>{t('shoppingCheckout.doneSummary',{count:purchased})}</summary><ul>{completion.purchased_items.map(item=><li key={item.id}><span>{item.name}</span>{item.quantity&&<small>{item.quantity}</small>}</li>)}</ul></details>}<div className="shopping-checkout-actions"><button className="primary" onClick={onClose}><Icon name="check"/>{t('shoppingCheckout.closeSummary')}</button></div></section></div>;
}
