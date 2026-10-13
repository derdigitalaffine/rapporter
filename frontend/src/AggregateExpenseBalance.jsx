import {useEffect,useMemo,useRef,useState} from 'react';
import {useTranslation} from 'react-i18next';
import {api} from './api';
import './aggregate-expense-balance.css';

const money=(value,currency,locale)=>new Intl.NumberFormat(locale||'de',{style:'currency',currency}).format(Number(value||0));
const rounded=value=>Math.round(Number(value||0)*100)/100;

export function simplifyAggregateBalances(members=[]){
 const debtors=members.filter(member=>Number(member.balance)<0).map(member=>({...member,open:rounded(-Number(member.balance))})).sort((a,b)=>b.open-a.open||String(a.id).localeCompare(String(b.id)));
 const creditors=members.filter(member=>Number(member.balance)>0).map(member=>({...member,open:rounded(Number(member.balance))})).sort((a,b)=>b.open-a.open||String(a.id).localeCompare(String(b.id)));
 const transfers=[];
 let debtorIndex=0;let creditorIndex=0;
 while(debtorIndex<debtors.length&&creditorIndex<creditors.length){
  const debtor=debtors[debtorIndex];const creditor=creditors[creditorIndex];
  const amount=rounded(Math.min(debtor.open,creditor.open));
  if(amount>0)transfers.push({from_member:debtor.id,from_name:debtor.name,to_member:creditor.id,to_name:credititorName(creditor),amount});
  debtor.open=rounded(debtor.open-amount);creditor.open=rounded(creditor.open-amount);
  if(debtor.open===0)debtorIndex+=1;if(creditor.open===0)creditorIndex+=1;
 }
 return transfers;
}

function credititorName(creditor){return creditor.name}

export function aggregateExpenseBalances(summaries=[]){
 const members=new Map();
 summaries.forEach(summary=>{
  (summary?.members||[]).forEach(member=>{
   const current=members.get(String(member.id))||{id:member.id,name:member.name,balance:0};
   current.name=member.name||current.name;
   current.balance+=Number(member.balance||0);
   members.set(String(member.id),current);
  });
 });
 const rows=Array.from(members.values()).map(member=>({...member,balance:rounded(member.balance)}));
 return {
  members:rows,
  openAmount:rounded(rows.reduce((total,member)=>member.balance>0?total+member.balance:total,0)),
  transfers:simplifyAggregateBalances(rows),
 };
}

export default function AggregateExpenseBalance({family,ledgers,currency,refreshKey}){
 const {t,i18n}=useTranslation();
 const [selectedIds,setSelectedIds]=useState(null);
 const [summary,setSummary]=useState({members:[],openAmount:0,transfers:[]});
 const [ledgerPlans,setLedgerPlans]=useState([]);
 const [loading,setLoading]=useState(false);
 const [error,setError]=useState('');
 const requestVersion=useRef(0);
 const activeIds=useMemo(()=>ledgers.map(item=>String(item.id)),[ledgers]);
 const selected=selectedIds===null?activeIds:selectedIds;
 const allSelected=activeIds.length>0&&selected.length===activeIds.length;

 useEffect(()=>{
  setSelectedIds(current=>{
   if(current===null)return activeIds;
   const valid=current.filter(id=>activeIds.includes(id));
   const known=new Set(current);
   const added=activeIds.filter(id=>!known.has(id));
   return [...valid,...added];
  });
 },[activeIds.join('|')]);

 useEffect(()=>{
  const version=++requestVersion.current;
  if(!family?.id||selected.length===0){setSummary({members:[],openAmount:0,transfers:[]});setLedgerPlans([]);setLoading(false);setError('');return}
  setLoading(true);setError('');
  Promise.all(selected.map(async id=>{
   const ledger=ledgers.find(item=>String(item.id)===String(id));
   const [balance,plan]=await Promise.all([
    api(`/expenses/balance/?family=${encodeURIComponent(family.id)}&currency=${encodeURIComponent(currency)}&ledger=${encodeURIComponent(id)}`),
    api(`/expenses/settlement-plan/?family=${encodeURIComponent(family.id)}&currency=${encodeURIComponent(currency)}&ledger=${encodeURIComponent(id)}`),
   ]);
   return {ledger,balance,plan};
  }))
   .then(rows=>{
    if(version!==requestVersion.current)return;
    setSummary(aggregateExpenseBalances(rows.map(row=>row.balance)));
    setLedgerPlans(rows.map(row=>({id:String(row.ledger?.id||row.plan?.ledger||''),name:row.ledger?.name||'',transfers:row.plan?.transfers||[]})).filter(row=>row.transfers.length));
   })
   .catch(err=>{if(version===requestVersion.current)setError(err.message)})
   .finally(()=>{if(version===requestVersion.current)setLoading(false)});
  return()=>{requestVersion.current+=1};
 },[family?.id,currency,selected.join('|'),refreshKey,ledgers]);

 function toggle(id){
  setSelectedIds(current=>{
   const values=current===null?activeIds:current;
   return values.includes(id)?values.filter(value=>value!==id):[...values,id];
  });
 }

 if(ledgers.length<2)return null;
 return <section className="card aggregate-balance-card" aria-labelledby="aggregate-balance-title">
  <div className="balance-card-head aggregate-balance-head"><div><small>{t('expensesUi.aggregateScope',{count:selected.length})}</small><h2 id="aggregate-balance-title">{t('expensesUi.aggregateBalance')}</h2></div><strong className="balance-total">{summary.openAmount>0?t('expensesUi.openAmount',{amount:money(summary.openAmount,currency,i18n.language)}):t('expensesUi.allSettled')}</strong></div>
  <div className="aggregate-account-controls" role="group" aria-label={t('expensesUi.aggregateAccounts')}>
   <button type="button" className="text-button" disabled={allSelected} onClick={()=>setSelectedIds(activeIds)}>{t('expensesUi.allAccounts')}</button>
   <div className="aggregate-account-list">{ledgers.map(ledger=><label className="aggregate-account-chip" key={ledger.id}><input type="checkbox" checked={selected.includes(String(ledger.id))} onChange={()=>toggle(String(ledger.id))}/><span>{ledger.name}</span></label>)}</div>
  </div>
  {error&&<p className="error" role="alert">{error}</p>}
  {loading?<p role="status">{t('pleaseWait')}</p>:selected.length===0?<p className="expense-empty">{t('expensesUi.noAccountsSelected')}</p>:<>
   <div className="balance-members">{summary.members.map(member=><div className="balance-member" key={member.id}><div><strong>{member.name}</strong><span>{member.balance<0?t('expensesUi.owes'):member.balance>0?t('expensesUi.gets'):t('expensesUi.allSettled')}</span></div><strong className={member.balance>0?'positive':member.balance<0?'negative':''}>{money(Math.abs(member.balance),currency,i18n.language)}</strong></div>)}</div>
   {summary.transfers.length>0&&<div className="aggregate-transfer-section"><h3>{t('expensesUi.netSettlement')}</h3>{summary.transfers.map((item,index)=><div className="aggregate-transfer" key={`${item.from_member}-${item.to_member}-${index}`}><span>{t('expensesUi.owesPerson',{from:item.from_name,to:item.to_name})}</span><strong>{money(item.amount,currency,i18n.language)}</strong></div>)}<small>{t('expensesUi.netSettlementHint')}</small></div>}
   {ledgerPlans.length>0&&<div className="aggregate-ledger-plans"><h3>{t('expensesUi.settlementByAccount')}</h3>{ledgerPlans.map(ledger=><div className="aggregate-ledger-plan" key={ledger.id}><strong>{ledger.name}</strong>{ledger.transfers.map((item,index)=><div className="aggregate-transfer" key={`${ledger.id}-${item.from_member}-${item.to_member}-${index}`}><span>{t('expensesUi.owesPerson',{from:item.from_name,to:item.to_name})}</span><strong>{money(item.amount,currency,i18n.language)}</strong></div>)}</div>)}</div>}
  </>}
  <p className="aggregate-balance-hint">{t('expensesUi.aggregateBalanceHint')}</p>
 </section>;
}