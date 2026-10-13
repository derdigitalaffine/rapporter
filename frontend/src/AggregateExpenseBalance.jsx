import {useEffect,useMemo,useRef,useState} from 'react';
import {useTranslation} from 'react-i18next';
import {api} from './api';
import {toast} from './feedback';
import './aggregate-expense-balance.css';

const money=(value,currency,locale)=>new Intl.NumberFormat(locale||'de',{style:'currency',currency}).format(Number(value||0));
const rounded=value=>Math.round(Number(value||0)*100)/100;
const memberName=member=>member?.display_name||member?.username||'—';

export function simplifyAggregateBalances(members=[]){
 const debtors=members.filter(member=>Number(member.balance)<0).map(member=>({...member,open:rounded(-Number(member.balance))})).sort((a,b)=>b.open-a.open||String(a.id).localeCompare(String(b.id)));
 const creditors=members.filter(member=>Number(member.balance)>0).map(member=>({...member,open:rounded(Number(member.balance))})).sort((a,b)=>b.open-a.open||String(a.id).localeCompare(String(b.id)));
 const transfers=[];
 let debtorIndex=0;let creditorIndex=0;
 while(debtorIndex<debtors.length&&creditorIndex<creditors.length){
  const debtor=debtors[debtorIndex];const creditor=creditors[creditorIndex];
  const amount=rounded(Math.min(debtor.open,creditor.open));
  if(amount>0)transfers.push({from_member:debtor.id,from_name:debtor.name,to_member:creditor.id,to_name:creditor.name,amount});
  debtor.open=rounded(debtor.open-amount);creditor.open=rounded(creditor.open-amount);
  if(debtor.open===0)debtorIndex+=1;if(creditor.open===0)creditorIndex+=1;
 }
 return transfers;
}

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
 return {members:rows,openAmount:rounded(rows.reduce((total,member)=>member.balance>0?total+member.balance:total,0)),transfers:simplifyAggregateBalances(rows)};
}

function splitForm(ledger,members){
 const configured=(ledger?.default_participants||[]).map(String);
 const participants=configured.length?configured:members.map(member=>String(member.id));
 const splitType=ledger?.default_split_type||'equal';
 const values=Object.fromEntries(Object.entries(ledger?.default_split_values||{}).map(([key,value])=>[String(key),String(value)]));
 return {ledgerId:String(ledger?.id||''),splitType,participants,values};
}

export default function AggregateExpenseBalance({family,ledgers,currency,refreshKey}){
 const {t,i18n}=useTranslation();
 const members=family?.memberships||[];
 const [selectedIds,setSelectedIds]=useState(null);
 const [summary,setSummary]=useState({members:[],openAmount:0,transfers:[]});
 const [ledgerPlans,setLedgerPlans]=useState([]);
 const [loading,setLoading]=useState(false);
 const [error,setError]=useState('');
 const [settingsOpen,setSettingsOpen]=useState(false);
 const [settings,setSettings]=useState(()=>splitForm(ledgers[0],members));
 const [settingsBusy,setSettingsBusy]=useState(false);
 const [settingsError,setSettingsError]=useState('');
 const requestVersion=useRef(0);
 const activeIds=useMemo(()=>ledgers.map(item=>String(item.id)),[ledgers]);
 const selected=selectedIds===null?activeIds:selectedIds;
 const allSelected=activeIds.length>0&&selected.length===activeIds.length;
 const settingsLedger=ledgers.find(item=>String(item.id)===settings.ledgerId)||ledgers[0]||null;
 const settingsParticipants=members.filter(member=>settings.participants.includes(String(member.id)));
 const percentageTotal=settings.splitType==='percentage'?settingsParticipants.reduce((sum,member)=>sum+Number(settings.values[String(member.id)]||0),0):0;

 useEffect(()=>{
  setSelectedIds(current=>{
   if(current===null)return activeIds;
   const valid=current.filter(id=>activeIds.includes(id));
   const known=new Set(current);
   const added=activeIds.filter(id=>!known.has(id));
   return [...valid,...added];
  });
  setSettings(current=>{
   const ledger=ledgers.find(item=>String(item.id)===current.ledgerId)||ledgers[0];
   return ledger?splitForm(ledger,members):current;
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
  setSelectedIds(current=>{const values=current===null?activeIds:current;return values.includes(id)?values.filter(value=>value!==id):[...values,id]});
 }
 function selectSettingsLedger(id){const ledger=ledgers.find(item=>String(item.id)===String(id));if(ledger){setSettings(splitForm(ledger,members));setSettingsError('')}}
 function toggleSettingsMember(id){
  const key=String(id);setSettings(current=>{
   const active=current.participants.includes(key);const participants=active?current.participants.filter(value=>value!==key):[...current.participants,key];const values={...current.values};if(active)delete values[key];return {...current,participants,values};
  });
 }
 async function saveSettings(event){
  event.preventDefault();setSettingsError('');
  if(!settings.participants.length){setSettingsError(t('expensesUi.selectAtLeastOne'));return}
  if(settings.splitType!=='equal'&&settings.participants.some(id=>Number(settings.values[id]||0)<=0)){setSettingsError(t('expensesUi.accountSplitValuesRequired'));return}
  if(settings.splitType==='percentage'&&Math.abs(percentageTotal-100)>.0001){setSettingsError(t('expensesUi.accountPercentageTotal',{total:percentageTotal.toFixed(2)}));return}
  setSettingsBusy(true);
  try{
   const payload={default_split_type:settings.splitType,default_participants:settings.participants,default_split_values:settings.splitType==='equal'?{}:settings.values};
   const saved=await api(`/expense-ledgers/${encodeURIComponent(settings.ledgerId)}/`,{method:'PATCH',body:JSON.stringify(payload)});
   setSettings(splitForm(saved,members));toast(t('expensesUi.accountSplitSaved'),{type:'success'});
  }catch(err){setSettingsError(err.message)}finally{setSettingsBusy(false)}
 }

 if(!ledgers.length)return null;
 return <>
  <section className="card ledger-split-settings" aria-labelledby="ledger-split-settings-title">
   <div className="balance-card-head"><div><small>{settingsLedger?.name}</small><h2 id="ledger-split-settings-title">{t('expensesUi.accountSplitSettings')}</h2></div><button type="button" className="secondary compact" aria-expanded={settingsOpen} onClick={()=>setSettingsOpen(value=>!value)}>{settingsOpen?t('expensesUi.close'):t('expensesUi.configure')}</button></div>
   <p className="aggregate-balance-hint">{t('expensesUi.accountSplitHint')}</p>
   {settingsOpen&&<form className="ledger-split-form" onSubmit={saveSettings}>
    {ledgers.length>1&&<label>{t('expensesUi.ledger')}<select value={settings.ledgerId} onChange={event=>selectSettingsLedger(event.target.value)}>{ledgers.map(ledger=><option key={ledger.id} value={ledger.id}>{ledger.name}</option>)}</select></label>}
    <fieldset><legend>{t('expensesUi.participants')}</legend><div className="aggregate-account-list">{members.map(member=>{const active=settings.participants.includes(String(member.id));return <button type="button" className={`aggregate-member-chip ${active?'active':''}`} aria-pressed={active} key={member.id} onClick={()=>toggleSettingsMember(member.id)}>{memberName(member)}</button>})}</div></fieldset>
    <fieldset><legend>{t('expensesUi.defaultSplit')}</legend><div className="ledger-split-tabs">{['equal','percentage','shares'].map(type=><button type="button" key={type} className={settings.splitType===type?'active':''} aria-pressed={settings.splitType===type} onClick={()=>setSettings(current=>({...current,splitType:type,values:type==='equal'?{}:current.values}))}>{t(`expensesUi.${type}`)}</button>)}</div></fieldset>
    {settings.splitType!=='equal'&&<div className="ledger-split-values">{settingsParticipants.map(member=><label key={member.id}><span>{memberName(member)}</span><input type="number" min="0.01" step="0.01" inputMode="decimal" value={settings.values[String(member.id)]||''} onChange={event=>setSettings(current=>({...current,values:{...current.values,[String(member.id)]:event.target.value}}))} required/></label>)}{settings.splitType==='percentage'&&<small className={Math.abs(percentageTotal-100)>.0001?'error':''}>{t('expensesUi.accountPercentageTotal',{total:percentageTotal.toFixed(2)})}</small>}</div>}
    {settingsError&&<p className="error" role="alert">{settingsError}</p>}
    <button className="primary compact" disabled={settingsBusy}>{settingsBusy?t('expensesUi.saving'):t('expensesUi.saveAccountSplit')}</button>
   </form>}
  </section>
  {ledgers.length>1&&<section className="card aggregate-balance-card" aria-labelledby="aggregate-balance-title">
   <div className="balance-card-head aggregate-balance-head"><div><small>{t('expensesUi.aggregateScope',{count:selected.length})}</small><h2 id="aggregate-balance-title">{t('expensesUi.aggregateBalance')}</h2></div><strong className="balance-total">{summary.openAmount>0?t('expensesUi.openAmount',{amount:money(summary.openAmount,currency,i18n.language)}):t('expensesUi.allSettled')}</strong></div>
   <div className="aggregate-account-controls" role="group" aria-label={t('expensesUi.aggregateAccounts')}><button type="button" className="text-button" disabled={allSelected} onClick={()=>setSelectedIds(activeIds)}>{t('expensesUi.allAccounts')}</button><div className="aggregate-account-list">{ledgers.map(ledger=><label className="aggregate-account-chip" key={ledger.id}><input type="checkbox" checked={selected.includes(String(ledger.id))} onChange={()=>toggle(String(ledger.id))}/><span>{ledger.name}</span></label>)}</div></div>
   {error&&<p className="error" role="alert">{error}</p>}
   {loading?<p role="status">{t('pleaseWait')}</p>:selected.length===0?<p className="expense-empty">{t('expensesUi.noAccountsSelected')}</p>:<><div className="balance-members">{summary.members.map(member=><div className="balance-member" key={member.id}><div><strong>{member.name}</strong><span>{member.balance<0?t('expensesUi.owes'):member.balance>0?t('expensesUi.gets'):t('expensesUi.allSettled')}</span></div><strong className={member.balance>0?'positive':member.balance<0?'negative':''}>{money(Math.abs(member.balance),currency,i18n.language)}</strong></div>)}</div>{summary.transfers.length>0&&<div className="aggregate-transfer-section"><h3>{t('expensesUi.netSettlement')}</h3>{summary.transfers.map((item,index)=><div className="aggregate-transfer" key={`${item.from_member}-${item.to_member}-${index}`}><span>{t('expensesUi.owesPerson',{from:item.from_name,to:item.to_name})}</span><strong>{money(item.amount,currency,i18n.language)}</strong></div>)}<small>{t('expensesUi.netSettlementHint')}</small></div>}{ledgerPlans.length>0&&<div className="aggregate-ledger-plans"><h3>{t('expensesUi.settlementByAccount')}</h3>{ledgerPlans.map(ledger=><div className="aggregate-ledger-plan" key={ledger.id}><strong>{ledger.name}</strong>{ledger.transfers.map((item,index)=><div className="aggregate-transfer" key={`${ledger.id}-${item.from_member}-${item.to_member}-${index}`}><span>{t('expensesUi.owesPerson',{from:item.from_name,to:item.to_name})}</span><strong>{money(item.amount,currency,i18n.language)}</strong></div>)}</div>)}</div>}</>}
   <p className="aggregate-balance-hint">{t('expensesUi.aggregateBalanceHint')}</p>
  </section>}
 </>;
}