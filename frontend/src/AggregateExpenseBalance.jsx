import {useEffect,useMemo,useRef,useState} from 'react';
import {useTranslation} from 'react-i18next';
import {api} from './api';
import {Icon} from './icons';
import MemberAvatar from './MemberAvatar';
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

function normalizedSplitValues(type,participants,current={}){
 if(type==='equal')return {};
 if(type==='shares')return Object.fromEntries(participants.map(id=>[id,Number(current[id]||0)>0?String(current[id]):'1']));
 if(type==='percentage'){
  const existing=participants.map(id=>Number(current[id]||0));
  const total=existing.reduce((sum,value)=>sum+value,0);
  if(existing.every(value=>value>0)&&Math.abs(total-100)<.0001)return Object.fromEntries(participants.map(id=>[id,String(current[id])]));
  if(!participants.length)return {};
  const base=Math.floor(10000/participants.length);const remainder=10000-(base*participants.length);
  return Object.fromEntries(participants.map((id,index)=>[id,((base+(index<remainder?1:0))/100).toFixed(2)]));
 }
 return {};
}

export default function AggregateExpenseBalance({family,ledgers,currency,refreshKey}){
 const {t,i18n}=useTranslation();
 const members=family?.memberships||[];
 const memberIds=members.map(member=>String(member.id)).join('|');
 const [selectedIds,setSelectedIds]=useState(null);
 const [summary,setSummary]=useState({members:[],openAmount:0,transfers:[]});
 const [ledgerPlans,setLedgerPlans]=useState([]);
 const [loading,setLoading]=useState(false);
 const [error,setError]=useState('');
 const [settingsOpen,setSettingsOpen]=useState(false);
 const [settings,setSettings]=useState(()=>splitForm(ledgers[0],members));
 const [ledgerOverrides,setLedgerOverrides]=useState({});
 const [settingsBusy,setSettingsBusy]=useState(false);
 const [settingsError,setSettingsError]=useState('');
 const requestVersion=useRef(0);
 const activeIds=useMemo(()=>ledgers.map(item=>String(item.id)),[ledgers]);
 const selected=selectedIds===null?activeIds:selectedIds;
 const allSelected=activeIds.length>0&&selected.length===activeIds.length;
 const effectiveLedger=id=>ledgerOverrides[String(id)]||ledgers.find(item=>String(item.id)===String(id))||null;
 const settingsLedger=effectiveLedger(settings.ledgerId)||effectiveLedger(activeIds[0]);
 const previewSettings=splitForm(settingsLedger,members);
 const previewParticipants=members.filter(member=>previewSettings.participants.includes(String(member.id)));
 const settingsParticipants=members.filter(member=>settings.participants.includes(String(member.id)));
 const percentageTotal=settings.splitType==='percentage'?settingsParticipants.reduce((sum,member)=>sum+Number(settings.values[String(member.id)]||0),0):0;
 const participantLabel=previewParticipants.length===members.length?t('expensesUi.allFamilyMembers'):previewParticipants.map(memberName).join(', ');

 useEffect(()=>{
  setSelectedIds(current=>{
   if(current===null)return activeIds;
   const valid=current.filter(id=>activeIds.includes(id));
   const known=new Set(current);
   const added=activeIds.filter(id=>!known.has(id));
   return [...valid,...added];
  });
  setSettings(current=>{
   const ledger=effectiveLedger(current.ledgerId)||effectiveLedger(activeIds[0]);
   return ledger?splitForm(ledger,members):current;
  });
 },[activeIds.join('|'),memberIds]);

 useEffect(()=>{
  if(!settingsOpen)return undefined;
  const onKeyDown=event=>{if(event.key==='Escape'&&!settingsBusy)setSettingsOpen(false)};
  document.addEventListener('keydown',onKeyDown);
  return()=>document.removeEventListener('keydown',onKeyDown);
 },[settingsOpen,settingsBusy]);

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

 function personFor(id,name=''){return members.find(member=>String(member.id)===String(id))||{display_name:name}}
 function toggle(id){setSelectedIds(current=>{const values=current===null?activeIds:current;return values.includes(id)?values.filter(value=>value!==id):[...values,id]})}
 function selectSettingsLedger(id){const ledger=effectiveLedger(id);if(ledger){setSettings(splitForm(ledger,members));setSettingsError('')}}
 function openSettings(){const ledger=settingsLedger||effectiveLedger(activeIds[0]);if(!ledger)return;setSettings(splitForm(ledger,members));setSettingsError('');setSettingsOpen(true)}
 function toggleSettingsMember(id){
  const key=String(id);setSettings(current=>{
   const active=current.participants.includes(key);
   const participants=active?current.participants.filter(value=>value!==key):[...current.participants,key];
   return {...current,participants,values:normalizedSplitValues(current.splitType,participants,current.values)};
  });
 }
 function changeSplitType(type){setSettings(current=>({...current,splitType:type,values:normalizedSplitValues(type,current.participants,current.values)}));setSettingsError('')}
 async function saveSettings(event){
  event.preventDefault();setSettingsError('');
  if(!settings.participants.length){setSettingsError(t('expensesUi.selectAtLeastOne'));return}
  if(settings.splitType!=='equal'&&settings.participants.some(id=>Number(settings.values[id]||0)<=0)){setSettingsError(t('expensesUi.accountSplitValuesRequired'));return}
  if(settings.splitType==='percentage'&&Math.abs(percentageTotal-100)>.0001){setSettingsError(t('expensesUi.accountPercentageTotal',{total:percentageTotal.toFixed(2)}));return}
  setSettingsBusy(true);
  try{
   const values=settings.splitType==='equal'?{}:Object.fromEntries(settings.participants.map(id=>[id,settings.values[id]]));
   const payload={default_split_type:settings.splitType,default_participants:settings.participants,default_split_values:values};
   const saved=await api(`/expense-ledgers/${encodeURIComponent(settings.ledgerId)}/`,{method:'PATCH',body:JSON.stringify(payload)});
   setLedgerOverrides(current=>({...current,[String(saved.id)]:saved}));
   setSettings(splitForm(saved,members));setSettingsOpen(false);toast(t('expensesUi.accountSplitSaved'),{type:'success'});
  }catch(err){setSettingsError(err.message)}finally{setSettingsBusy(false)}
 }

 if(!ledgers.length)return null;
 return <>
  <section className="card ledger-split-settings" aria-labelledby="ledger-split-settings-title">
   <div className="balance-card-head"><div><small>{settingsLedger?.name}</small><h2 id="ledger-split-settings-title">{t('expensesUi.accountSettings')}</h2></div><button type="button" className="secondary ledger-settings-edit" onClick={openSettings}><Icon name="settings"/>{t('expensesUi.editAccountSettings')}</button></div>
   {ledgers.length>1&&<label className="ledger-settings-account-select"><span>{t('expensesUi.ledger')}</span><select value={settingsLedger?.id||''} onChange={event=>selectSettingsLedger(event.target.value)}>{ledgers.map(ledger=><option key={ledger.id} value={ledger.id}>{ledger.name}</option>)}</select></label>}
   <div className="ledger-settings-summary">
    <div className="ledger-setting-summary-row"><div className="ledger-setting-summary-label"><Icon name="members"/><span><strong>{t('expensesUi.participantsSummary')}</strong><small>{participantLabel}</small></span></div><div className="ledger-settings-avatars" aria-hidden="true">{previewParticipants.slice(0,4).map(member=><MemberAvatar key={member.id} person={member} size={32} decorative/>)}{previewParticipants.length>4&&<span className="ledger-avatar-more">+{previewParticipants.length-4}</span>}</div></div>
    <div className="ledger-setting-summary-row"><div className="ledger-setting-summary-label"><Icon name="sliders"/><span><strong>{t('expensesUi.distributionSummary')}</strong><small>{t(`expensesUi.${previewSettings.splitType}`)}</small></span></div></div>
   </div>
   <p className="aggregate-balance-hint">{t('expensesUi.accountSplitHint')}</p>
  </section>
  {settingsOpen&&<div className="sheet-backdrop ledger-settings-backdrop" onMouseDown={event=>event.target===event.currentTarget&&!settingsBusy&&setSettingsOpen(false)}><section className="quick-sheet ledger-settings-sheet" role="dialog" aria-modal="true" aria-labelledby="ledger-settings-dialog-title">
   <div className="sheet-handle" aria-hidden="true"/>
   <div className="sheet-head"><div><small>{settingsLedger?.name}</small><h2 id="ledger-settings-dialog-title">{t('expensesUi.accountSplitSettings')}</h2></div><button type="button" className="sheet-close" disabled={settingsBusy} onClick={()=>setSettingsOpen(false)} aria-label={t('expensesUi.close')}><Icon name="close"/></button></div>
   <form className="quick-form ledger-settings-form" onSubmit={saveSettings}>
    {ledgers.length>1&&<label>{t('expensesUi.ledger')}<select value={settings.ledgerId} onChange={event=>selectSettingsLedger(event.target.value)}>{ledgers.map(ledger=><option key={ledger.id} value={ledger.id}>{ledger.name}</option>)}</select></label>}
    <section className="ledger-settings-section" aria-labelledby="ledger-participants-title"><div className="ledger-settings-section-head"><div><strong id="ledger-participants-title">{t('expensesUi.participants')}</strong><small>{t('expensesUi.accountParticipantsHint')}</small></div><span>{settings.participants.length}/{members.length}</span></div><div className="ledger-participant-list">{members.map(member=>{const active=settings.participants.includes(String(member.id));return <button type="button" className={`secondary ledger-participant-row ${active?'is-selected':''}`} aria-pressed={active} key={member.id} onClick={()=>toggleSettingsMember(member.id)}><MemberAvatar person={member} size={40} decorative/><span>{memberName(member)}</span><Icon name={active?'check':'plus'} /></button>})}</div></section>
    <section className="ledger-settings-section" aria-labelledby="ledger-split-title"><div className="ledger-settings-section-head"><div><strong id="ledger-split-title">{t('expensesUi.defaultSplit')}</strong><small>{t('expensesUi.accountDistributionHint')}</small></div></div><div className="ledger-split-options" role="radiogroup" aria-labelledby="ledger-split-title">{['equal','percentage','shares'].map(type=><button type="button" role="radio" aria-checked={settings.splitType===type} key={type} className={`secondary ledger-split-option ${settings.splitType===type?'is-selected':''}`} onClick={()=>changeSplitType(type)}><span><strong>{t(`expensesUi.${type}`)}</strong><small>{t(`expensesUi.${type}DefaultHint`)}</small></span>{settings.splitType===type&&<Icon name="check"/>}</button>)}</div></section>
    {settings.splitType!=='equal'&&<section className="ledger-settings-section ledger-split-values" aria-labelledby="ledger-values-title"><div className="ledger-settings-section-head"><div><strong id="ledger-values-title">{t(settings.splitType==='percentage'?'expensesUi.percentageValues':'expensesUi.shareValues')}</strong><small>{t(settings.splitType==='percentage'?'expensesUi.percentageValuesHint':'expensesUi.shareValuesHint')}</small></div></div>{settingsParticipants.map(member=><label className="ledger-split-value-row" key={member.id}><MemberAvatar person={member} size={36} decorative/><span>{memberName(member)}</span><span className="ledger-split-input"><input type="number" min="0.01" step="0.01" inputMode="decimal" value={settings.values[String(member.id)]||''} onChange={event=>setSettings(current=>({...current,values:{...current.values,[String(member.id)]:event.target.value}}))} required/>{settings.splitType==='percentage'&&<span aria-hidden="true">%</span>}</span></label>)}{settings.splitType==='percentage'&&<small className={`ledger-percentage-total ${Math.abs(percentageTotal-100)>.0001?'is-invalid':'is-valid'}`}>{t('expensesUi.accountPercentageTotal',{total:percentageTotal.toFixed(2)})}</small>}</section>}
    {settingsError&&<p className="error" role="alert">{settingsError}</p>}
    <div className="ledger-settings-actions"><button className="primary" disabled={settingsBusy}>{settingsBusy?t('expensesUi.saving'):t('expensesUi.saveAccountSplit')}</button><button type="button" className="secondary" disabled={settingsBusy} onClick={()=>setSettingsOpen(false)}>{t('expensesUi.close')}</button></div>
   </form>
  </section></div>}
  {ledgers.length>1&&<section className="card aggregate-balance-card" aria-labelledby="aggregate-balance-title">
   <div className="balance-card-head aggregate-balance-head"><div><small>{t('expensesUi.aggregateScope',{count:selected.length})}</small><h2 id="aggregate-balance-title">{t('expensesUi.aggregateBalance')}</h2></div><strong className="balance-total">{summary.openAmount>0?t('expensesUi.openAmount',{amount:money(summary.openAmount,currency,i18n.language)}):t('expensesUi.allSettled')}</strong></div>
   <div className="aggregate-account-controls" role="group" aria-label={t('expensesUi.aggregateAccounts')}><button type="button" className="secondary aggregate-select-all" disabled={allSelected} onClick={()=>setSelectedIds(activeIds)}>{t('expensesUi.allAccounts')}</button><div className="aggregate-account-list">{ledgers.map(ledger=><label className="aggregate-account-chip" key={ledger.id}><input type="checkbox" checked={selected.includes(String(ledger.id))} onChange={()=>toggle(String(ledger.id))}/><span>{ledger.name}</span></label>)}</div></div>
   {error&&<p className="error" role="alert">{error}</p>}
   {loading?<p role="status">{t('pleaseWait')}</p>:selected.length===0?<p className="expense-empty">{t('expensesUi.noAccountsSelected')}</p>:<><div className="balance-members">{summary.members.map(member=>{const person=personFor(member.id,member.name);return <div className="balance-member" key={member.id}><div className="aggregate-balance-person"><MemberAvatar person={person} size={38} decorative/><span><strong>{member.name}</strong><small>{member.balance<0?t('expensesUi.owes'):member.balance>0?t('expensesUi.gets'):t('expensesUi.allSettled')}</small></span></div><strong className={member.balance>0?'positive':member.balance<0?'negative':''}>{money(Math.abs(member.balance),currency,i18n.language)}</strong></div>})}</div>{summary.transfers.length>0&&<div className="aggregate-transfer-section"><h3>{t('expensesUi.netSettlement')}</h3>{summary.transfers.map((item,index)=><div className="aggregate-transfer" key={`${item.from_member}-${item.to_member}-${index}`}><div className="aggregate-transfer-party"><div className="aggregate-transfer-avatars"><MemberAvatar person={personFor(item.from_member,item.from_name)} size={30} decorative/><MemberAvatar person={personFor(item.to_member,item.to_name)} size={30} decorative/></div><span>{t('expensesUi.owesPerson',{from:item.from_name,to:item.to_name})}</span></div><strong>{money(item.amount,currency,i18n.language)}</strong></div>)}<small>{t('expensesUi.netSettlementHint')}</small></div>}{ledgerPlans.length>0&&<div className="aggregate-ledger-plans"><h3>{t('expensesUi.settlementByAccount')}</h3>{ledgerPlans.map(ledger=><div className="aggregate-ledger-plan" key={ledger.id}><strong>{ledger.name}</strong>{ledger.transfers.map((item,index)=><div className="aggregate-transfer" key={`${ledger.id}-${item.from_member}-${item.to_member}-${index}`}><div className="aggregate-transfer-party"><div className="aggregate-transfer-avatars"><MemberAvatar person={personFor(item.from_member,item.from_name)} size={30} decorative/><MemberAvatar person={personFor(item.to_member,item.to_name)} size={30} decorative/></div><span>{t('expensesUi.owesPerson',{from:item.from_name,to:item.to_name})}</span></div><strong>{money(item.amount,currency,i18n.language)}</strong></div>)}</div>)}</div>}</>}
   <p className="aggregate-balance-hint">{t('expensesUi.aggregateBalanceHint')}</p>
  </section>}
 </>;
}