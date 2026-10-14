import {useEffect,useMemo,useRef,useState} from 'react';
import {useTranslation} from 'react-i18next';
import {api} from './api';
import {Icon} from './icons';
import MemberAvatar from './MemberAvatar';
import {confirmAction,toast} from './feedback';
import {requestCreate} from './create-request';
import {FormShell,FormField,FormActions} from './form-primitives';
import ExpenseEditor from './ExpenseEditor';
import AggregateExpenseBalance from './AggregateExpenseBalance';
import './expenses-i18n';
import './expenses.css';

const unwrap=value=>value?.results||value||[];
const amount=(value,currency,locale)=>new Intl.NumberFormat(locale||'de',{style:'currency',currency}).format(Number(value||0));
const shortDate=(value,locale)=>value?new Intl.DateTimeFormat(locale||'de',{day:'2-digit',month:'short',year:'numeric'}).format(new Date(value)):'';
const budgetMax=value=>Math.max(Number(value||0),.01);
const budgetValue=(spent,total)=>Math.min(Math.max(Number(spent||0),0),budgetMax(total));
const localDate=value=>{const date=value?new Date(value):new Date();const offset=date.getTimezoneOffset()*60000;return new Date(date.getTime()-offset).toISOString().slice(0,10)};
const defaultRepaymentDate=()=>{const date=new Date();date.setDate(date.getDate()+7);return localDate(date)};
const memberName=member=>member?.display_name||member?.username||'—';

function addScheduleDate(value,index,cadence){
 const base=new Date(`${value}T12:00:00`);
 if(cadence==='weekly'){base.setDate(base.getDate()+(index*7));return base}
 const day=base.getDate();base.setDate(1);base.setMonth(base.getMonth()+index);const month=base.getMonth();base.setDate(day);if(base.getMonth()!==month){base.setDate(0)}return base;
}

function repaymentSchedule(total,count,firstDue,cadence){
 const installments=Math.max(1,Math.min(24,Number(count)||1));
 const cents=Math.max(0,Math.round(Number(total||0)*100));
 const base=Math.floor(cents/installments);const remainder=cents-(base*installments);
 return Array.from({length:installments},(_,index)=>({index:index+1,amount:(base+(index<remainder?1:0))/100,due:addScheduleDate(firstDue,index,cadence)}));
}

function BudgetProgress({summary,ledger,t,locale}){
 if(!summary)return null;
 const budgets=summary.budgets||[];
 const hasOverall=summary.budget_amount!==null&&summary.budget_amount!==undefined;
 const unconverted=Number(summary.unconverted_expense_count||0);
 if(!hasOverall&&!budgets.length&&!unconverted)return null;
 const currency=summary.currency||ledger?.base_currency||'EUR';
 const remaining=Number(summary.remaining_amount||0);
 return <section className="card budget-progress-card" aria-labelledby="expense-budget-title">
  <div className="budget-progress-head"><div><small>{ledger?.name}</small><h2 id="expense-budget-title">{t('expensesUi.budgetProgress')}</h2></div>{hasOverall&&<strong>{t('expensesUi.budgetUsed',{spent:amount(summary.spent_amount,currency,locale),budget:amount(summary.budget_amount,currency,locale)})}</strong>}</div>
  {hasOverall&&<><progress max={budgetMax(summary.budget_amount)} value={budgetValue(summary.spent_amount,summary.budget_amount)} aria-label={t('expensesUi.budgetProgress')}/><p className="budget-status">{summary.over_budget?t('expensesUi.budgetExceeded',{amount:amount(Math.abs(remaining),currency,locale)}):t('expensesUi.budgetRemaining',{amount:amount(remaining,currency,locale)})}</p></>}
  {budgets.length>0&&<details className="finance-collapsible"><summary><span>{t('expensesUi.subBudgets')}</span><small>{budgets.length}</small></summary><div className="subbudget-list">{budgets.map(item=><div className="subbudget-row" key={item.id}><div><span>{item.name}</span><small>{t('expensesUi.budgetUsed',{spent:amount(item.spent_amount,item.currency||currency,locale),budget:amount(item.amount,item.currency||currency,locale)})}</small></div><progress max={budgetMax(item.amount)} value={budgetValue(item.spent_amount,item.amount)} aria-label={item.name}/><small className="subbudget-status">{item.over_budget?t('expensesUi.budgetExceeded',{amount:amount(Math.abs(Number(item.remaining_amount||0)),item.currency||currency,locale)}):t('expensesUi.budgetRemaining',{amount:amount(item.remaining_amount,item.currency||currency,locale)})}</small></div>)}</div></details>}
  {unconverted>0&&<p className="budget-unconverted"><Icon name="info"/>{t('expensesUi.budgetUnconverted',{count:unconverted})}</p>}
  <p className="budget-soft-hint"><Icon name="info"/>{t('expensesUi.budgetSoftHint')}</p>
 </section>
}

export default function ExpensesHub({family,onBack,entitlements}){
 const {t}=useTranslation();
 if(!entitlements)return <p role="status">{t('pleaseWait')}</p>;
 if(!entitlements.capabilities?.includes('expenses'))return <section className="card"><h1>{t('expensesUi.title')}</h1><p role="status">{t('entitlementsUi.lockedMessage',{feature:t('expensesUi.title'),tier:entitlements.display_name||'Light'})}</p><button className="secondary" onClick={onBack}>{t('expensesUi.back')}</button></section>;
 return <FinanceContent family={family} onBack={onBack}/>;
}

function FinanceContent({family,onBack}){
 const {t,i18n}=useTranslation();
 const requestedLedgerId=new URLSearchParams(location.search).get('ledger')||'';
 const loadVersion=useRef(0);
 const focusedExpense=useRef(false);
 const [search,setSearch]=useState('');
 const [category,setCategory]=useState('');
 const [filtersOpen,setFiltersOpen]=useState(false);
 const [accountForm,setAccountForm]=useState(null);
 const [accountBusy,setAccountBusy]=useState(false);
 const [accountError,setAccountError]=useState('');
 const [expenses,setExpenses]=useState([]);
 const [balance,setBalance]=useState(null);
 const [plan,setPlan]=useState(null);
 const [settlements,setSettlements]=useState([]);
 const [ledgers,setLedgers]=useState([]);
 const [budgetSummary,setBudgetSummary]=useState(null);
 const [ledgerId,setLedgerId]=useState(requestedLedgerId);
 const [currency,setCurrency]=useState('EUR');
 const [editing,setEditing]=useState(null);
 const [loading,setLoading]=useState(true);
 const [error,setError]=useState('');
 const [busyId,setBusyId]=useState('');
 const [repayment,setRepayment]=useState(null);
 const [repaymentBusy,setRepaymentBusy]=useState(false);
 const [repaymentError,setRepaymentError]=useState('');
 const selectedLedger=useMemo(()=>ledgers.find(item=>String(item.id)===String(ledgerId))||ledgers.find(item=>item.is_default)||ledgers[0]||null,[ledgers,ledgerId]);
 const currencies=useMemo(()=>Array.from(new Set([selectedLedger?.base_currency||'EUR',...expenses.map(item=>item.currency).filter(Boolean)])).sort(),[expenses,selectedLedger?.base_currency]);
 const familyMembers=family?.memberships||[];
 const memberById=id=>familyMembers.find(member=>String(member.id)===String(id));
 const balanceRows=useMemo(()=>[...(balance?.members||[])].sort((a,b)=>{const az=Math.abs(Number(a.balance||0));const bz=Math.abs(Number(b.balance||0));if(!az&&bz)return 1;if(az&&!bz)return -1;return bz-az||String(a.name||'').localeCompare(String(b.name||''),i18n.language)}),[balance?.members,i18n.language]);
 const openBalanceRows=balanceRows.filter(member=>Math.abs(Number(member.balance||0))>=.005);
 const settledBalanceRows=balanceRows.filter(member=>Math.abs(Number(member.balance||0))<.005);
 const repaymentItems=useMemo(()=>repayment?repaymentSchedule(repayment.amount,repayment.mode==='installments'?repayment.count:1,repayment.firstDue,repayment.cadence):[],[repayment]);

 useEffect(()=>{
  if(!family?.id)return;
  let live=true;
  api(`/expense-ledgers/?family=${encodeURIComponent(family.id)}`).then(rows=>{
   if(!live)return;
   const active=unwrap(rows).filter(item=>!item.archived);
   setLedgers(active);
   const preferred=active.find(item=>String(item.id)===String(requestedLedgerId))||active.find(item=>item.is_default)||active[0];
   setLedgerId(String(preferred?.id||''));
   if(preferred?.base_currency)setCurrency(preferred.base_currency);
  }).catch(err=>{if(live)setError(err.message)});
  return()=>{live=false};
 },[family?.id]);

 async function load(){
  if(!family?.id)return;
  const version=++loadVersion.current;
  setLoading(true);setError('');
  const ledgerQuery=ledgerId?`&ledger=${encodeURIComponent(ledgerId)}`:'';
  try{
   const [expenseRows,balanceData,planData,settlementRows,budgetData]=await Promise.all([
    api(`/expenses/?family=${encodeURIComponent(family.id)}${ledgerQuery}`),
    api(`/expenses/balance/?family=${encodeURIComponent(family.id)}&currency=${encodeURIComponent(currency)}${ledgerQuery}`),
    api(`/expenses/settlement-plan/?family=${encodeURIComponent(family.id)}&currency=${encodeURIComponent(currency)}${ledgerQuery}`),
    api(`/expenses/settlements/?family=${encodeURIComponent(family.id)}${ledgerQuery}`),
    ledgerId?api(`/expense-ledgers/${encodeURIComponent(ledgerId)}/budget-summary/`).catch(()=>null):Promise.resolve(null),
   ]);
   if(version!==loadVersion.current)return;
   const rows=unwrap(expenseRows);
   setExpenses(rows);
   const expenseId=new URLSearchParams(location.search).get('expense');
   if(expenseId&&!focusedExpense.current){focusedExpense.current=true;const row=rows.find(item=>String(item.id)===expenseId);if(row)setEditing(row);else api(`/expenses/${encodeURIComponent(expenseId)}/`).then(item=>{if(version===loadVersion.current)setEditing(item)}).catch(()=>{})}
   setBalance(balanceData);
   setPlan(planData);
   setSettlements(unwrap(settlementRows).filter(item=>item.currency===currency));
   setBudgetSummary(budgetData);
  }catch(err){if(version===loadVersion.current)setError(err.message)}finally{if(version===loadVersion.current)setLoading(false)}
 }
 useEffect(()=>{load();return()=>{loadVersion.current+=1}},[family?.id,currency,ledgerId]);

 function selectLedger(id){
  setLedgerId(id);
  setBudgetSummary(null);
  const next=ledgers.find(item=>String(item.id)===String(id));
  if(next?.base_currency)setCurrency(next.base_currency);
  const url=new URL(location.href);
  url.searchParams.set('ledger',id);
  history.replaceState(history.state,'',`${url.pathname}${url.search}${url.hash}`);
 }
 async function settle(item){
  setBusyId(`${item.from_member}-${item.to_member}`);
  try{
   await api('/expenses/settlements/',{method:'POST',body:JSON.stringify({family:family.id,ledger:ledgerId||undefined,from_member:item.from_member,to_member:item.to_member,amount:item.amount,currency})});
   toast(t('expensesUi.settlementRecorded'),{type:'success'});await load();
  }catch(err){toast(err.message,{type:'error'})}finally{setBusyId('')}
 }
 async function voidSettlement(item){setBusyId(item.id);try{await api(`/expenses/settlements/${item.id}/void/`,{method:'POST',body:'{}'});toast(t('expensesUi.settlementVoided'),{type:'success'});await load()}catch(err){toast(err.message,{type:'error'})}finally{setBusyId('')}}
 async function removeExpense(item){const ok=await confirmAction({title:t('expensesUi.deleteQuestion'),message:`${item.title||item.merchant||t('expensesUi.add')} · ${amount(item.total_amount,item.currency,i18n.language)}`,confirmLabel:t('expensesUi.delete'),danger:true});if(!ok)return;setBusyId(item.id);try{await api(`/expenses/${item.id}/`,{method:'DELETE'});toast(t('expensesUi.deleted'),{type:'success'});await load()}catch(err){toast(err.message,{type:'error'})}finally{setBusyId('')}}
 async function createAccount(event){
  event.preventDefault();setAccountBusy(true);setAccountError('');
  try{const row=await api('/expense-ledgers/',{method:'POST',body:JSON.stringify({family:family.id,name:accountForm.name.trim(),base_currency:accountForm.currency})});setLedgers(rows=>[...rows,row]);selectLedger(String(row.id));setCurrency(row.base_currency);setAccountForm(null)}catch(err){setAccountError(err.message)}finally{setAccountBusy(false)}
 }
 function openRepayment(item){
  setRepaymentError('');
  setRepayment({...item,mode:'single',count:3,cadence:'monthly',firstDue:defaultRepaymentDate()});
 }
 async function createRepaymentTasks(event){
  event.preventDefault();if(!repayment||repaymentBusy)return;
  const debtor=memberById(repayment.from_member);
  if(!debtor?.user){setRepaymentError(t('expensesUi.repaymentAssigneeMissing'));return}
  setRepaymentBusy(true);setRepaymentError('');let created=0;
  try{
   for(const installment of repaymentItems){
    const title=repaymentItems.length>1?t('expensesUi.repaymentInstallmentTaskTitle',{index:installment.index,count:repaymentItems.length,amount:amount(installment.amount,currency,i18n.language),to:repayment.to_name,ledger:selectedLedger?.name||''}):t('expensesUi.repaymentTaskTitle',{amount:amount(installment.amount,currency,i18n.language),to:repayment.to_name,ledger:selectedLedger?.name||''});
    const notes=t('expensesUi.repaymentTaskNotes',{from:repayment.from_name,to:repayment.to_name,ledger:selectedLedger?.name||'',amount:amount(installment.amount,currency,i18n.language)});
    await api('/tasks/',{method:'POST',body:JSON.stringify({family:family.id,title,notes,due_at:new Date(`${localDate(installment.due)}T09:00:00`).toISOString(),priority:'normal',assignee:debtor.user})});
    created+=1;
   }
   toast(t('expensesUi.repaymentTasksCreated',{count:created}),{type:'success'});setRepayment(null);
  }catch(err){setRepaymentError(created?t('expensesUi.repaymentTasksPartial',{created,total:repaymentItems.length,error:err.message}):err.message)}finally{setRepaymentBusy(false)}
 }
 const categories=[...new Set(expenses.map(item=>item.category).filter(Boolean))].sort();
 const visibleExpenses=expenses.filter(item=>item.currency===currency&&(!category||item.category===category)&&(!search||`${item.title} ${item.merchant} ${item.category||''}`.toLocaleLowerCase(i18n.language).includes(search.toLocaleLowerCase(i18n.language))));
 const visibleTotal=visibleExpenses.reduce((sum,item)=>sum+Number(item.total_amount||0),0);
 const activeFilterCount=Number(Boolean(search))+Number(Boolean(category));
 const receiptLink=item=>item.receipt_available?<a className="text-button transaction-receipt" href={`${import.meta.env.VITE_API_BASE||'/api'}/expenses/${item.id}/receipt-file/`} target="_blank" rel="noopener noreferrer" aria-label={`${t('expensesUi.openReceipt')}: ${item.title||item.merchant}`}>{t(item.receipt_mime==='application/pdf'?'expensesUi.pdfReceipt':'expensesUi.imageReceipt')}</a>:<span>{t('expensesUi.noReceipt')}</span>;

 return <><div className="expenses-page"><div className="expenses-head"><div><button type="button" className="ghost icon-button expenses-back" onClick={onBack} aria-label={t('expensesUi.back')}><Icon name="back"/></button><h1>{t('expensesUi.title')}</h1><p>{t('expensesUi.subtitle')}</p></div><div className="expenses-toolbar">{ledgers.length>0&&<select value={ledgerId} onChange={event=>selectLedger(event.target.value)} aria-label={t('expensesUi.ledger')}>{ledgers.map(item=><option key={item.id} value={item.id}>{item.name}</option>)}</select>}<select value={currency} onChange={event=>setCurrency(event.target.value)} aria-label={t('expensesUi.currency')}>{currencies.map(code=><option key={code}>{code}</option>)}</select><button type="button" className="secondary compact" onClick={()=>setAccountForm({name:'',currency})}>{t('expensesUi.newAccount')}</button><button className="primary compact" onClick={()=>requestCreate('expense',{ledger:ledgerId})}><Icon name="plus"/>{t('expensesUi.add')}</button></div></div>
 {accountForm&&<section className="card finance-account-form"><h2>{t('expensesUi.newAccount')}</h2><FormShell onSubmit={createAccount}><FormField label={t('expensesUi.accountName')} required><input value={accountForm.name} maxLength={120} required onChange={event=>setAccountForm(value=>({...value,name:event.target.value}))}/></FormField><FormField label={t('expensesUi.currency')}><select value={accountForm.currency} onChange={event=>setAccountForm(value=>({...value,currency:event.target.value}))}>{['EUR','USD','GBP','CHF'].map(code=><option key={code}>{code}</option>)}</select></FormField>{accountError&&<p role="alert" className="error">{accountError}</p>}<FormActions><button className="primary" disabled={accountBusy||!accountForm.name.trim()}>{t('expensesUi.createAccount')}</button><button className="secondary" type="button" disabled={accountBusy} onClick={()=>setAccountForm(null)}>{t('expensesUi.close')}</button></FormActions></FormShell></section>}
 <div className="expenses-primary"><AggregateExpenseBalance family={family} ledgers={ledgers} currency={currency} refreshKey={loadVersion.current}/><section className="card balance-card smart-balance-card"><div className="balance-card-head"><div><small>{selectedLedger?.name||t('expensesUi.forCurrency',{currency})}</small><h2>{t('expensesUi.balance')}</h2><p>{t('expensesUi.balanceHint')}</p></div><strong className={`balance-total ${Number(balance?.open_amount||0)>0?'has-open':''}`}>{balance?.open_amount&&Number(balance.open_amount)>0?t('expensesUi.openAmount',{amount:amount(balance.open_amount,currency,i18n.language)}):t('expensesUi.allSettled')}</strong></div>{loading&&!balance?<p>{t('pleaseWait')}</p>:<>{openBalanceRows.length>0?<div className="balance-members smart-balance-members">{openBalanceRows.map(member=>{const person=memberById(member.id)||{display_name:member.name};const value=Number(member.balance);return <div className={`balance-member smart-balance-member ${value<0?'is-debtor':'is-creditor'}`} key={member.id}><MemberAvatar person={person} size={42} decorative/><div className="smart-balance-copy"><strong>{member.name}</strong><span>{value<0?t('expensesUi.owes'):t('expensesUi.gets')}</span></div><strong className={value>0?'positive':'negative'}>{amount(Math.abs(value),currency,i18n.language)}</strong></div>})}</div>:<p className="expense-empty balance-empty"><Icon name="check"/>{t('expensesUi.allSettled')}</p>}{settledBalanceRows.length>0&&<details className="finance-collapsible settled-members"><summary><span>{t('expensesUi.settledMembers')}</span><small>{settledBalanceRows.length}</small></summary><div className="settled-member-list">{settledBalanceRows.map(member=><div key={member.id}><MemberAvatar person={memberById(member.id)||{display_name:member.name}} size={32} decorative/><span>{member.name}</span><Icon name="check"/></div>)}</div></details>}</>}</section>
 <BudgetProgress summary={budgetSummary} ledger={selectedLedger} t={t} locale={i18n.language}/>
 <section className="expense-section smart-transactions"><div className="transaction-section-head"><div><h2>{t('expensesUi.recent')}</h2><p>{t('expensesUi.transactionSummary',{count:visibleExpenses.length,amount:amount(visibleTotal,currency,i18n.language)})}</p></div><button type="button" className="secondary compact" aria-expanded={filtersOpen} onClick={()=>setFiltersOpen(value=>!value)}><Icon name="filter"/>{t('expensesUi.filters')}{activeFilterCount>0&&<span className="filter-count">{activeFilterCount}</span>}</button></div>{filtersOpen&&<div className="transaction-filters"><FormField label={t('expensesUi.search')}><input type="search" value={search} onChange={event=>setSearch(event.target.value)}/></FormField><FormField label={t('expensesUi.category')}><select value={category} onChange={event=>setCategory(event.target.value)}><option value="">{t('expensesUi.allCategories')}</option>{categories.map(value=><option key={value}>{value}</option>)}</select></FormField>{activeFilterCount>0&&<button type="button" className="ghost transaction-filter-reset" onClick={()=>{setSearch('');setCategory('')}}>{t('expensesUi.resetFilters')}</button>}</div>}{error&&<p className="error" role="alert">{error}<button className="text-button" onClick={load}>{t('expensesUi.retryLoad')}</button></p>}{loading&&<p role="status">{t('pleaseWait')}</p>}<table className="transaction-table" role="table"><caption className="sr-only">{t('expensesUi.recent')} · {selectedLedger?.name}</caption><thead role="rowgroup"><tr role="row">{['date','description','category','ledger','amount','receipt','actions'].map(key=><th scope="col" role="columnheader" key={key}>{t(`expensesUi.${key}`)}</th>)}</tr></thead><tbody role="rowgroup">{visibleExpenses.map(item=><tr className="expense-row" role="row" key={item.id}><td role="cell" className="transaction-date">{shortDate(item.occurred_at,i18n.language)}</td><th scope="row" role="rowheader" className="transaction-description"><button type="button" className="text-button" onClick={()=>setEditing(item)}>{item.title||item.merchant||t('expensesUi.add')}</button><small>{item.funding_source==='shared'?t('expensesUi.sharedPaid'):t('expensesUi.paid',{name:item.paid_by_name})}</small></th><td role="cell" className="transaction-category">{item.category||t('expensesUi.uncategorized')}</td><td role="cell" className="transaction-account">{ledgers.find(row=>String(row.id)===String(item.ledger))?.name||selectedLedger?.name}</td><td role="cell" className="transaction-amount">{amount(item.total_amount,item.currency,i18n.language)}</td><td role="cell" className="transaction-receipt-cell">{receiptLink(item)}</td><td role="cell" className="expense-actions"><button className="ghost icon-button" type="button" onClick={()=>setEditing(item)} aria-label={`${t('expensesUi.edit')}: ${item.title||item.merchant}`}><Icon name="edit"/></button><button className="ghost icon-button ghost-danger" type="button" disabled={busyId===item.id} onClick={()=>removeExpense(item)} aria-label={`${t('expensesUi.delete')}: ${item.title||item.merchant}`}><Icon name="delete"/></button></td></tr>)}</tbody></table>{!loading&&!visibleExpenses.length&&<div className="expense-empty"><Icon name="receipt" size={28}/>{activeFilterCount?t('expensesUi.noMatchingExpenses'):t('expensesUi.noExpenses')}</div>}</section></div>
 <aside className="expenses-side"><section className="card settlement-card"><div className="balance-card-head"><div><small>{selectedLedger?.name}</small><h2>{t('expensesUi.settle')}</h2></div><Icon name="settle"/></div><div className="settlement-plan">{(plan?.transfers||[]).map(item=>{const id=`${item.from_member}-${item.to_member}`;return <div className="settlement-row smart-settlement-row" key={id}><div className="settlement-party"><div className="settlement-avatars"><MemberAvatar person={memberById(item.from_member)||{display_name:item.from_name}} size={36} decorative/><MemberAvatar person={memberById(item.to_member)||{display_name:item.to_name}} size={36} decorative/></div><p><strong>{t('expensesUi.owesPerson',{from:item.from_name,to:item.to_name})}</strong><span>{amount(item.amount,currency,i18n.language)}</span></p></div><div className="settlement-actions"><button className="secondary compact" type="button" onClick={()=>openRepayment(item)}><Icon name="tasks"/>{t('expensesUi.planRepayment')}</button><button className="primary compact" disabled={busyId===id} onClick={()=>settle(item)}>{t('expensesUi.markSettled')}</button></div></div>})}{!loading&&!(plan?.transfers||[]).length&&<p className="expense-empty">{t('expensesUi.allSettled')}</p>}</div><p className="settlement-disclaimer"><Icon name="info"/>{t('expensesUi.settleHint')}</p></section>{settlements.length>0&&<details className="card finance-history-card finance-collapsible"><summary><span>{t('expensesUi.settlements')}</span><small>{settlements.length}</small></summary><div className="settlement-history">{settlements.slice(0,8).map(item=><div className="settlement-history-row" key={item.id}><p><strong>{item.from_name} → {item.to_name}</strong><small>{amount(item.amount,item.currency,i18n.language)} · {shortDate(item.settled_at,i18n.language)}{item.voided_at?` · ${t('expensesUi.voided')}`:''}</small></p>{!item.voided_at&&<button className="text-button" disabled={busyId===item.id} onClick={()=>voidSettlement(item)}>{t('expensesUi.undoSettlement')}</button>}</div>)}</div></details>}</aside></div>{editing&&<ExpenseEditor family={family} expense={editing} onClose={()=>setEditing(null)} onSaved={async()=>{setEditing(null);await load()}}/>}
 {repayment&&<div className="sheet-backdrop repayment-backdrop" onMouseDown={event=>event.target===event.currentTarget&&!repaymentBusy&&setRepayment(null)}><section className="quick-sheet repayment-sheet" role="dialog" aria-modal="true" aria-labelledby="repayment-title"><div className="sheet-handle"/><div className="sheet-head"><div><small>{selectedLedger?.name}</small><h2 id="repayment-title">{t('expensesUi.planRepayment')}</h2></div><button type="button" className="sheet-close" disabled={repaymentBusy} onClick={()=>setRepayment(null)} aria-label={t('expensesUi.close')}><Icon name="close"/></button></div><form className="quick-form repayment-form" onSubmit={createRepaymentTasks}><div className="repayment-debt"><div className="settlement-avatars"><MemberAvatar person={memberById(repayment.from_member)||{display_name:repayment.from_name}} size={44} decorative/><MemberAvatar person={memberById(repayment.to_member)||{display_name:repayment.to_name}} size={44} decorative/></div><div><strong>{t('expensesUi.owesPerson',{from:repayment.from_name,to:repayment.to_name})}</strong><span>{amount(repayment.amount,currency,i18n.language)}</span></div></div><fieldset className="repayment-mode"><legend>{t('expensesUi.repaymentMode')}</legend><div><button type="button" className={`secondary ${repayment.mode==='single'?'is-selected':''}`} aria-pressed={repayment.mode==='single'} onClick={()=>setRepayment(value=>({...value,mode:'single'}))}>{t('expensesUi.singleRepayment')}</button><button type="button" className={`secondary ${repayment.mode==='installments'?'is-selected':''}`} aria-pressed={repayment.mode==='installments'} onClick={()=>setRepayment(value=>({...value,mode:'installments'}))}>{t('expensesUi.installments')}</button></div></fieldset><div className="repayment-fields"><label>{t('expensesUi.firstDue')}<input type="date" required value={repayment.firstDue} onChange={event=>setRepayment(value=>({...value,firstDue:event.target.value}))}/></label>{repayment.mode==='installments'&&<><label>{t('expensesUi.installmentCount')}<input type="number" min="2" max="24" inputMode="numeric" value={repayment.count} onChange={event=>setRepayment(value=>({...value,count:Math.max(2,Math.min(24,Number(event.target.value)||2))}))}/></label><label>{t('expensesUi.cadence')}<select value={repayment.cadence} onChange={event=>setRepayment(value=>({...value,cadence:event.target.value}))}><option value="monthly">{t('expensesUi.monthly')}</option><option value="weekly">{t('expensesUi.weekly')}</option></select></label></>}</div><div className="repayment-preview"><strong>{t('expensesUi.repaymentPreview')}</strong>{repaymentItems.map(item=><div key={item.index}><span>{repaymentItems.length>1?t('expensesUi.installmentLabel',{index:item.index,count:repaymentItems.length}):t('expensesUi.singleRepayment')} · {shortDate(item.due,i18n.language)}</span><strong>{amount(item.amount,currency,i18n.language)}</strong></div>)}</div><p className="repayment-note"><Icon name="info"/>{t('expensesUi.repaymentTaskDisclaimer')}</p>{repaymentError&&<p className="error" role="alert">{repaymentError}</p>}<div className="repayment-actions"><button className="primary" disabled={repaymentBusy||!repayment.firstDue}>{repaymentBusy?t('expensesUi.saving'):t('expensesUi.createRepaymentTasks',{count:repaymentItems.length})}</button><button type="button" className="secondary" disabled={repaymentBusy} onClick={()=>setRepayment(null)}>{t('expensesUi.close')}</button></div></form></section></div>}
 </>
}