import {useTranslation} from 'react-i18next';
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
 const purchased=completion.purchased_count||0;
 const open=completion.open_count||0;
 const completedAt=session.completed_at||completion.completed_at;
 const date=completedAt?new Intl.DateTimeFormat(i18n.language||'de',{dateStyle:'medium',timeStyle:'short'}).format(new Date(completedAt)):'';
 const amount=expense?.total_amount?money(expense.total_amount,expense.currency||'EUR',i18n.language):'';
 return <div className="sheet-backdrop shopping-checkout-backdrop" onMouseDown={event=>{if(event.target===event.currentTarget)onClose?.()}}><section className="quick-sheet shopping-checkout-sheet" role="dialog" aria-modal="true" aria-labelledby="shopping-completion-title"><div className="sheet-handle"/><div className="sheet-head"><div><small>{history?t('shoppingCheckout.historyLabel'):completion?.shopping_list?.name}</small><h2 id="shopping-completion-title">{t('shoppingCheckout.doneTitle')}</h2></div><button className="sheet-close" onClick={onClose} aria-label={t('shoppingCheckout.closeSummary')}><Icon name="close"/></button></div><div className="shopping-checkout-summary shopping-completion-summary" role="status"><Icon name="doneAll" size={34}/><strong>{t('shoppingCheckout.doneSummaryDetailed',{purchased,open})}</strong>{date&&<small>{t('shoppingCheckout.completedAt',{date})}</small>}{expense&&<span className="shopping-completion-expense"><Icon name={expense.source==='receipt'?'receipt':'edit'}/>{expense.source==='receipt'?t('shoppingCheckout.receiptSaved'):t('shoppingCheckout.expenseSaved',{amount})}</span>}</div>{(completion.purchased_items||[]).length>0&&<details className="shopping-completion-items"><summary>{t('shoppingCheckout.doneSummary',{count:purchased})}</summary><ul>{completion.purchased_items.map(item=><li key={item.id}><span>{item.name}</span>{item.quantity&&<small>{item.quantity}</small>}</li>)}</ul></details>}<div className="shopping-checkout-actions"><button className="primary" onClick={onClose}><Icon name="check"/>{t('shoppingCheckout.closeSummary')}</button></div></section></div>;
}
