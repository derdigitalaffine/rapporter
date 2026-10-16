import {budgetTree} from './budget-tree';
import './budget-planning-i18n';
import {useEffect,useMemo,useState} from 'react';
import {useTranslation} from 'react-i18next';
import {api} from './api';
import {toast} from './feedback';
import {Icon} from './icons';
import {FormActions,FormField,FormRow,FormShell} from './form-primitives';
import './budget-commitments-i18n';
import './shopping-budget-commitment.css';

const unwrap=value=>value?.results||value||[];
const normalizedAmount=value=>String(value??'').trim().replace(/\s/g,'').replace(',','.');

export default function ShoppingBudgetCommitment({family,onChanged}){
 const {t}=useTranslation();
 const [expanded,setExpanded]=useState(false);
 const [items,setItems]=useState([]);const [ledgers,setLedgers]=useState([]);const [budgets,setBudgets]=useState([]);
 const [itemId,setItemId]=useState('');const [ledgerId,setLedgerId]=useState('');const [budgetId,setBudgetId]=useState('');const [amount,setAmount]=useState('');
 const [commitment,setCommitment]=useState(null);const [loading,setLoading]=useState(false);const [saving,setSaving]=useState(false);const [error,setError]=useState('');
 const selectedLedger=useMemo(()=>ledgers.find(row=>String(row.id)===String(ledgerId))||null,[ledgers,ledgerId]);

 useEffect(()=>{
  setItems([]);setLedgers([]);setBudgets([]);setItemId('');setLedgerId('');setBudgetId('');setAmount('');setCommitment(null);setError('');
 },[family?.id]);

 useEffect(()=>{
  if(!family?.id||!expanded)return;
  let live=true;setLoading(true);setError('');
  api('/shopping-lists/')
   .then(listRows=>{
    if(!live)return;
    const nextItems=unwrap(listRows).filter(list=>String(list.family)===String(family.id)&&!list.archived).flatMap(list=>(list.items||[]).filter(item=>!item.checked).map(item=>({...item,list_name:list.name})));
    setItems(nextItems);
    setItemId(current=>nextItems.some(row=>String(row.id)===String(current))?current:'');
   })
   .catch(err=>{if(live)setError(err.message)})
   .finally(()=>{if(live)setLoading(false)});
  return()=>{live=false};
 },[family?.id,expanded]);

 useEffect(()=>{
  if(!family?.id||!expanded||!itemId){setLedgers([]);setLedgerId('');return}
  let live=true;setError('');
  api(`/expense-ledgers/?family=${encodeURIComponent(family.id)}`)
   .then(ledgerRows=>{
    if(!live)return;
    const nextLedgers=unwrap(ledgerRows).filter(row=>!row.archived);
    setLedgers(nextLedgers);
    setLedgerId(current=>nextLedgers.some(row=>String(row.id)===String(current))?current:String(nextLedgers.find(row=>row.is_default)?.id||nextLedgers[0]?.id||''));
   })
   .catch(err=>{if(live)setError(err.message)});
  return()=>{live=false};
 },[family?.id,expanded,itemId]);

 useEffect(()=>{
  if(!family?.id||!expanded||!ledgerId){setBudgets([]);return}
  let live=true;
  api(`/expense-budgets/?family=${encodeURIComponent(family.id)}&ledger=${encodeURIComponent(ledgerId)}`)
   .then(rows=>{if(live)setBudgets(unwrap(rows).filter(row=>!row.archived))})
   .catch(()=>{if(live)setBudgets([])});
  return()=>{live=false};
 },[family?.id,expanded,ledgerId]);

 useEffect(()=>{
  if(!family?.id||!expanded||!itemId){setCommitment(null);setAmount('');setBudgetId('');return}
  let live=true;setCommitment(null);setAmount('');setBudgetId('');setError('');
  api(`/budget-commitments/source/shopping_item/${encodeURIComponent(itemId)}/?family=${encodeURIComponent(family.id)}`)
   .then(result=>{
    if(!live)return;
    const row=result?.commitment||null;setCommitment(row);
    if(row){setAmount(String(row.amount||''));setLedgerId(String(row.ledger||''));setBudgetId(String(row.budget||''))}
   })
   .catch(err=>{if(live)setError(err.message)});
  return()=>{live=false};
 },[family?.id,expanded,itemId]);

 async function save(event){
  event.preventDefault();if(!itemId||!ledgerId||!amount||saving)return;
  setSaving(true);setError('');
  try{
   const result=await api(`/budget-commitments/source/shopping_item/${encodeURIComponent(itemId)}/`,{method:'PUT',body:JSON.stringify({family:family.id,ledger:ledgerId,budget:budgetId||null,amount:normalizedAmount(amount)})});
   setCommitment(result.commitment);toast(t('budgetCommitments.saved'),{type:'success'});await onChanged?.();
  }catch(err){setError(err.message)}finally{setSaving(false)}
 }
 async function release(){
  if(!itemId||saving)return;setSaving(true);setError('');
  try{await api(`/budget-commitments/source/shopping_item/${encodeURIComponent(itemId)}/?family=${encodeURIComponent(family.id)}`,{method:'DELETE'});setCommitment(null);setAmount('');setBudgetId('');toast(t('budgetCommitments.released'),{type:'success'});await onChanged?.()}
  catch(err){setError(err.message)}finally{setSaving(false)}
 }

 return <details className="card finance-collapsible shopping-budget-commitment" onToggle={event=>setExpanded(event.currentTarget.open)}><summary><span><Icon name="euro"/>{t('budgetCommitments.title')}</span>{commitment&&<small>{t('budgetCommitments.active',{amount:commitment.amount,currency:commitment.currency})}</small>}</summary><div className="shopping-budget-commitment-body"><p>{t('budgetCommitments.hint')}</p>{loading?<p role="status">{t('pleaseWait')}</p>:items.length===0?<p className="expense-empty">{t('budgetCommitments.empty')}</p>:<FormShell onSubmit={save}><FormField label={t('budgetCommitments.item')}><select value={itemId} onChange={event=>setItemId(event.target.value)}><option value="">{t('budgetCommitments.item')}</option>{items.map(item=><option key={item.id} value={item.id}>{item.name}{item.list_name?` · ${item.list_name}`:''}</option>)}</select></FormField>{itemId&&<><FormRow><FormField label={t('budgetCommitments.ledger')}><select value={ledgerId} onChange={event=>{setLedgerId(event.target.value);setBudgetId('')}}>{ledgers.map(row=><option key={row.id} value={row.id}>{row.name}</option>)}</select></FormField><FormField label={t('budgetCommitments.budget')}><select value={budgetId} onChange={event=>setBudgetId(event.target.value)}><option value="">{t('budgetCommitments.overall')}</option>{budgets.map(row=><option key={row.id} value={row.id}>{budgetTree(budgets).path(row)} · {t('budgetPlanning.miscellaneous')}</option>)}</select></FormField></FormRow><FormField label={`${t('budgetCommitments.amount')} (${selectedLedger?.base_currency||'EUR'})`} required><input type="text" inputMode="decimal" value={amount} onChange={event=>setAmount(event.target.value)} required/></FormField><p className="shopping-budget-purchase-hint"><Icon name="info"/>{t('budgetCommitments.purchaseHint')}</p>{error&&<p className="error" role="alert">{error}</p>}<FormActions><button className="primary" disabled={saving||!amount||!ledgerId}>{saving?t('expensesUi.saving'):t(commitment?'budgetCommitments.update':'budgetCommitments.save')}</button>{commitment&&<button type="button" className="secondary" disabled={saving} onClick={release}>{t('budgetCommitments.release')}</button>}</FormActions></>}</FormShell>}</div></details>;
}
