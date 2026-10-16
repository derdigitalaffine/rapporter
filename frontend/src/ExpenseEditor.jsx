import {budgetTree} from './budget-tree';
import './budget-planning-i18n';
import {useEffect,useMemo,useRef,useState} from 'react';
import {useTranslation} from 'react-i18next';
import {api} from './api';
import {Icon} from './icons';
import {toast} from './feedback';
import {useFamilyPermissions} from './family-permissions';
import FileDropZone from './FileDropZone';
import ReceiptIntelligenceReview from './ReceiptIntelligenceReview';
import {ErrorSummary,FormActions,FormField,FormShell} from './form-primitives';
import './expenses-i18n';
import './expenses.css';

const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const unwrap=value=>value?.results||value||[];
const memberName=member=>member?.display_name||member?.username||'—';
const dateOnly=value=>{if(!value)return new Date().toISOString().slice(0,10);try{return new Date(value).toISOString().slice(0,10)}catch{return String(value).slice(0,10)}};
const localMidday=date=>new Date(`${date}T12:00:00`).toISOString();
const requestId=()=>globalThis.crypto?.randomUUID?.()||'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g,char=>{const value=Math.random()*16|0;return(char==='x'?value:(value&3|8)).toString(16)});
const normalizeAmount=value=>{
 const text=String(value??'').trim().replace(/\s/g,'');
 if(!text)return'';
 if(text.includes(',')&&text.includes('.'))return text.lastIndexOf(',')>text.lastIndexOf('.')?text.replace(/\./g,'').replace(',','.'):text.replace(/,/g,'');
 return text.replace(',','.');
};
const validAmount=value=>{const normalized=normalizeAmount(value);return /^\d+(?:\.\d{0,2})?$/.test(normalized)&&Number(normalized)>0};
const money=(value,currency,locale)=>new Intl.NumberFormat(locale||'de',{style:'currency',currency}).format(Number(value||0));
const namesList=(members,locale)=>{const names=members.map(memberName);try{return new Intl.ListFormat(locale||'de',{style:'short',type:'conjunction'}).format(names)}catch{return names.join(', ')}};

function initialValues(expense,splitType){
 const result={};
 for(const share of expense?.shares||[]){
  const original=share.split_value;
  if(splitType==='exact')result[share.member]=String(original??share.amount);
  else if(splitType==='percentage'&&Number(expense?.total_amount)>0)result[share.member]=original!==null&&original!==undefined?String(original):String((Number(share.amount)/Number(expense.total_amount)*100).toFixed(2));
  else if(splitType==='shares')result[share.member]=String(original??share.amount);
 }
 return result;
}
function formFrom(expense,members,initialPrefill={}){
 const splitType=expense?.shares?.[0]?.split_type||'equal';
 return {
  category:expense?.category||'',
  title:expense?.merchant||expense?.title||initialPrefill.title||'',
  amount:expense?.total_amount||'',
  date:expense?.extraction?.date||dateOnly(expense?.occurred_at||initialPrefill.occurred_at),
  currency:expense?.currency||'EUR',
  funding_source:expense?.funding_source||'member',
  paid_by:expense?.paid_by||'',
  participants:expense?.shares?.length?expense.shares.map(share=>String(share.member)):members.map(member=>String(member.id)),
  split_type:splitType,
  split_values:initialValues(expense,splitType),
  ledger:expense?.ledger?String(expense.ledger):'',
  budget:'',
 };
}
function accountDefaults(account,members){
 const configured=(account?.default_participants||[]).map(String);
 const participants=configured.length?configured:members.map(member=>String(member.id));
 const split_type=account?.default_split_type||'equal';
 const split_values=split_type==='equal'?{}:Object.fromEntries(Object.entries(account?.default_split_values||{}).map(([key,value])=>[String(key),String(value)]));
 return {participants,split_type,split_values};
}
function confidenceLabel(value,t){if(value>=.82)return['good',t('expensesUi.confidenceHigh')];if(value>=.55)return['warn',t('expensesUi.confidenceMedium')];return['low',t('expensesUi.confidenceLow')]}

export default function ExpenseEditor({family,expense=null,onClose,onSaved,onUndo,initialMode='quick',initialLedger='',initialPrefill={},initialBudget='',createExpense=null}){
 const {t,i18n}=useTranslation();
 const members=family?.memberships||[];
 const {membership}=useFamilyPermissions(family);
 const isExisting=Boolean(expense?.id);
 const [stage,setStage]=useState(isExisting?'form':initialMode==='receipt'?'capture':initialMode==='details'?'form':'quick');
 const [draft,setDraft]=useState(expense);
 const [form,setForm]=useState(()=>({...formFrom(expense,members,initialPrefill),ledger:expense?.ledger?String(expense.ledger):initialLedger,budget:isExisting?'':String(initialBudget||'')}));
 const [ledgers,setLedgers]=useState([]);
 const [budgets,setBudgets]=useState([]);
 const [contextError,setContextError]=useState('');
 const [allocationState,setAllocationState]=useState({expenseId:'',ledger:'',budget:'',advanced:false,loaded:false,baseAmount:'',currency:''});
 const [busy,setBusy]=useState(false);
 const [error,setError]=useState('');
 const [quality,setQuality]=useState(expense?.extraction?.quality_warnings||[]);
 const cancelled=useRef(false);
 const quickRequestId=useRef(requestId());

 useEffect(()=>()=>{cancelled.current=true},[]);
 useEffect(()=>{if(form.funding_source==='member'&&!form.paid_by&&membership?.id)setForm(value=>({...value,paid_by:String(membership.id)}))},[membership?.id,form.funding_source,form.paid_by]);
 useEffect(()=>{
  if(!family?.id)return;
  let live=true;
  api(`/expense-ledgers/?family=${encodeURIComponent(family.id)}`).then(rows=>{
   if(!live)return;
   const active=unwrap(rows).filter(row=>!row.archived);
   setLedgers(active);
   setForm(current=>{
    const chosen=active.find(row=>String(row.id)===String(current.ledger));
    const preferred=chosen||active.find(row=>row.is_default)||active[0];
    if(!preferred)return current;
    if(expense)return current;
    return {...current,ledger:String(preferred.id),currency:preferred.base_currency||current.currency,...accountDefaults(preferred,members)};
   });
  }).catch(()=>{if(live)setContextError(t('expensesUi.contextLoadFailed'))});
  return()=>{live=false};
 },[family?.id,t]);
 useEffect(()=>{
  if(!family?.id||!form.ledger){setBudgets([]);return}
  let live=true;
  api(`/expense-budgets/?family=${encodeURIComponent(family.id)}&ledger=${encodeURIComponent(form.ledger)}`).then(rows=>{
   if(!live)return;
   const active=unwrap(rows).filter(row=>!row.archived);
   setBudgets(active);
   setForm(current=>{
    if(!current.budget||current.budget==='__advanced__'||active.some(row=>String(row.id)===String(current.budget)))return current;
    return {...current,budget:''};
   });
  }).catch(()=>{if(live){setBudgets([]);setContextError(t('expensesUi.contextLoadFailed'))}});
  return()=>{live=false};
 },[family?.id,form.ledger,t]);
 useEffect(()=>{
  const id=draft?.id;
  if(!id||allocationState.expenseId===String(id))return;
  let live=true;
  api(`/expenses/${id}/budget-allocations/`).then(data=>{
   if(!live)return;
   const allocations=data?.allocations||[];
   const advanced=allocations.length>1;
   const budget=advanced?'__advanced__':allocations[0]?.budget||'';
   const ledger=String(data?.ledger||draft?.ledger||form.ledger||'');
   setAllocationState({expenseId:String(id),ledger,budget,advanced,loaded:true,baseAmount:String(draft?.total_amount||''),currency:draft?.currency||''});
   setForm(current=>({...current,ledger:ledger||current.ledger,budget}));
  }).catch(()=>{if(live)setAllocationState({expenseId:String(id),ledger:String(draft?.ledger||form.ledger||''),budget:'',advanced:false,loaded:true,baseAmount:String(draft?.total_amount||''),currency:draft?.currency||''})});
  return()=>{live=false};
 },[draft?.id]);

 const extraction=draft?.extraction;
 const status=draft?.receipt_status;
 const confidences=extraction?.field_confidences||{};
 const receiptUrl=draft?.receipt_available?`${import.meta.env.VITE_API_BASE||'/api'}/expenses/${draft.id}/receipt-file/`:'';
 const selectedMembers=useMemo(()=>members.filter(member=>form.participants.includes(String(member.id))),[members,form.participants]);
 const selectedLedger=useMemo(()=>ledgers.find(row=>String(row.id)===String(form.ledger))||null,[ledgers,form.ledger]);
 const budgetCurrencyCompatible=!selectedLedger||String(selectedLedger.base_currency||'EUR').toUpperCase()===String(form.currency||'EUR').toUpperCase();
 const splitLabel=t(`expensesUi.${form.split_type||'equal'}`);
 const defaultsSummary=t('expensesUi.quickAccountDefaults',{split:splitLabel,names:namesList(selectedMembers,i18n.language)});
 const editorTitle=isExisting?t('expensesUi.edit'):stage==='quick'?t('expensesUi.quickTitle'):t('expensesUi.addExpense');
 const isShared=form.funding_source==='shared';
 const allocationReady=!draft?.id||(allocationState.expenseId===String(draft.id)&&allocationState.loaded);
 const canSubmit=validAmount(form.amount)&&(isShared||form.participants.length>0)&&allocationReady;
 const quickErrorId=error===t('expensesUi.invalidAmount')?'expense-quick-amount':'expense-quick-details';
 const quickErrors=error?[{id:quickErrorId,message:error}]:[];

 function mergeDetected(next){
  setDraft(next);
  setQuality(next?.extraction?.quality_warnings||quality);
  const detectedDate=next?.extraction?.date||(next?.source==='receipt'&&initialPrefill.occurred_at?dateOnly(initialPrefill.occurred_at):dateOnly(next?.occurred_at));
  setForm(current=>({...current,title:next?.merchant||next?.title||current.title,amount:next?.total_amount||current.amount,date:detectedDate||current.date,currency:next?.currency||current.currency,funding_source:next?.funding_source||current.funding_source,paid_by:String(next?.paid_by||current.paid_by||''),ledger:String(next?.ledger||current.ledger||'')}));
 }
 async function pollReceipt(id){for(let attempt=0;attempt<36&&!cancelled.current;attempt++){await sleep(attempt<8?500:900);if(cancelled.current)return;try{const next=await api(`/expenses/${id}/`);mergeDetected(next);if(['review','failed','ready'].includes(next.receipt_status)){setStage('form');return}}catch(err){setError(err.message);setStage('form');return}}setStage('form')}
 async function upload(file){if(!file)return;setBusy(true);setError('');setStage('processing');try{const body=new FormData();body.append('family',family.id);body.append('receipt',file);if(form.ledger)body.append('ledger',form.ledger);const created=await api('/expenses/receipt/',{method:'POST',body});mergeDetected(created);setQuality(created.quality_warnings||[]);setBusy(false);await pollReceipt(created.id)}catch(err){setError(err.message);setBusy(false);setStage('capture')}}
 function toggleMember(id){setForm(value=>{const key=String(id);const selected=value.participants.includes(key);const participants=selected?value.participants.filter(item=>item!==key):[...value.participants,key];const split_values={...value.split_values};if(selected)delete split_values[key];return{...value,participants,split_values}})}
 function changeSplit(type){setForm(value=>({...value,split_type:type,split_values:type==='equal'?{}:{...value.split_values}}))}
 function changeLedger(ledger){const account=ledgers.find(row=>String(row.id)===String(ledger));setForm(value=>({...value,ledger,budget:'',currency:!draft?.id?account?.base_currency||value.currency:value.currency,...(!draft?.id&&account?accountDefaults(account,members):{})}))}
 async function retry(){if(!draft?.id)return;setBusy(true);setError('');try{await api(`/expenses/${draft.id}/retry-receipt/`,{method:'POST',body:'{}'});setDraft(value=>({...value,receipt_status:'queued'}));setStage('processing');setBusy(false);await pollReceipt(draft.id)}catch(err){setError(err.message);setBusy(false);setStage('form')}}
 async function removeReceipt(){if(!draft?.id)return;try{await api(`/expenses/${draft.id}/receipt-file/`,{method:'DELETE'});setDraft(value=>({...value,receipt_available:false}));toast(t('expensesUi.removeReceipt'),{type:'success'})}catch(err){setError(err.message)}}
 async function close(){if(!isExisting&&draft?.id&&draft?.status==='draft'){try{await api(`/expenses/${draft.id}/`,{method:'DELETE'})}catch{}}onClose()}
 async function undoQuick(saved){try{await api(`/expenses/${saved.id}/`,{method:'DELETE'});toast(t('expensesUi.undone'),{type:'success'});await onUndo?.(saved)}catch(err){toast(err.message,{type:'error'})}}
 async function saveQuick(event){
  event.preventDefault();
  if(!validAmount(form.amount)){setError(t('expensesUi.invalidAmount'));return}
  if(!form.participants.length){setError(t('expensesUi.selectAtLeastOne'));return}
  if(typeof navigator!=='undefined'&&navigator.onLine===false){setError(t('expensesUi.offlineUnavailable'));return}
  setBusy(true);setError('');
  const normalized=normalizeAmount(form.amount);
  const payload={family:family.id,ledger:form.ledger||undefined,category:form.category,title:form.title.trim(),total_amount:normalized,currency:form.currency,occurred_at:initialPrefill.occurred_at||new Date().toISOString(),paid_by:form.paid_by||undefined,participants:form.participants,split_type:form.split_type,split_values:form.split_type==='equal'?undefined:form.split_values,client_request_id:quickRequestId.current};
  try{const saved=await api('/expenses/',{method:'POST',body:JSON.stringify(payload)});toast(t('expensesUi.savedAmount',{amount:money(normalized,form.currency,i18n.language)}),{type:'success',actionLabel:t('expensesUi.undo'),onAction:()=>undoQuick(saved),duration:8000});await onSaved?.(saved,{budget:form.budget})}catch(err){setError(err.message);setBusy(false)}
 }
 async function syncBudgetAllocation(saved){
  if(!saved?.id||form.budget==='__advanced__')return;
  const known=allocationState.loaded&&allocationState.expenseId===String(saved.id);
  const relevantChanged=known&&(String(saved.total_amount||'')!==String(allocationState.baseAmount||'')||String(saved.currency||'')!==String(allocationState.currency||'')||String(saved.ledger||'')!==String(allocationState.ledger||''));
  const selectionChanged=known&&String(form.budget||'')!==String(allocationState.budget||'');
  if(!known&&!form.budget)return;
  if(known&&!relevantChanged&&!selectionChanged)return;
  const allocations=form.budget?[{budget:form.budget,amount_in_budget_currency:saved.total_amount}]:[];
  await api(`/expenses/${saved.id}/budget-allocations/`,{method:'PUT',body:JSON.stringify({allocations})});
  setAllocationState({expenseId:String(saved.id),ledger:String(saved.ledger||form.ledger||''),budget:form.budget||'',advanced:false,loaded:true,baseAmount:String(saved.total_amount||''),currency:saved.currency||''});
 }
 async function save(event){
  event.preventDefault();
  if(!allocationReady)return;
  if(!isShared&&!form.participants.length){setError(t('expensesUi.selectAtLeastOne'));return}
  if(!validAmount(form.amount)){setError(t('expensesUi.invalidAmount'));return}
  if(form.budget&&form.budget!=='__advanced__'&&!budgetCurrencyCompatible){setError(t('expensesUi.budgetCurrencyHint',{currency:selectedLedger?.base_currency||'EUR'}));return}
  const advancedRelevantEdit=allocationState.advanced&&allocationState.expenseId===String(draft?.id||'')&&(normalizeAmount(form.amount)!==String(allocationState.baseAmount||'')||String(form.currency)!==String(allocationState.currency||'')||String(form.ledger)!==String(allocationState.ledger||''));
  if(advancedRelevantEdit){setError(t('expensesUi.advancedBudgetLocked'));return}
  setBusy(true);setError('');
  const payload={family:family.id,category:form.category,title:form.title.trim(),merchant:form.title.trim(),total_amount:normalizeAmount(form.amount),currency:form.currency,occurred_at:localMidday(form.date),funding_source:form.funding_source,ledger:form.ledger||undefined};
  if(!isShared){payload.paid_by=form.paid_by||undefined;payload.participants=form.participants;payload.split_type=form.split_type;payload.split_values=form.split_type==='equal'?undefined:form.split_values}
  try{
   let saved;let customCreated=false;
   if(draft?.id&&draft?.status==='draft')saved=await api(`/expenses/${draft.id}/`,{method:'PATCH',body:JSON.stringify({...payload,finalize:true})});
   else if(isExisting)saved=await api(`/expenses/${expense.id}/`,{method:'PATCH',body:JSON.stringify(payload)});
   else if(createExpense){saved=await createExpense({...payload,client_request_id:quickRequestId.current},{budget:form.budget});customCreated=true}
   else saved=await api('/expenses/',{method:'POST',body:JSON.stringify({...payload,client_request_id:quickRequestId.current})});
   setDraft(saved);
   if(!customCreated)await syncBudgetAllocation(saved);
   toast(t('expensesUi.save'),{type:'success'});
   await onSaved?.(saved,{budget:form.budget});
  }catch(err){setError(err.message);setBusy(false)}
 }

 return <div className="sheet-backdrop expense-sheet-backdrop" onMouseDown={event=>{if(event.target===event.currentTarget&&!busy)close()}}><section className={`quick-sheet expense-sheet ${stage==='quick'?'expense-sheet-quick':''}`} role="dialog" aria-modal="true" aria-labelledby="expense-editor-title"><div className="sheet-handle"/><div className="sheet-head"><div><small>{family?.name}</small><h2 id="expense-editor-title">{editorTitle}</h2></div><button className="sheet-close" onClick={close} disabled={busy} aria-label={t('expensesUi.close')}><Icon name="close"/></button></div>
 {stage==='quick'&&<FormShell className="expense-quick-add" onSubmit={saveQuick}><ErrorSummary errors={quickErrors}/><FormField id="expense-quick-amount" label={t('expensesUi.amount')} required>{controlProps=><div className="quick-amount-field"><input {...controlProps} type="text" inputMode="decimal" autoComplete="off" autoFocus value={form.amount} onChange={event=>setForm(value=>({...value,amount:event.target.value}))} placeholder="0,00"/><span>{form.currency}</span></div>}</FormField><FormField id="expense-quick-title" label={t('expensesUi.optionalTitle')}><input className="quick-title-input" value={form.title} onChange={event=>setForm(value=>({...value,title:event.target.value}))} placeholder={t('expensesUi.optionalTitle')} maxLength={180}/></FormField><FormField label={t('expensesUi.ledger')}><select value={form.ledger} onChange={event=>changeLedger(event.target.value)}>{ledgers.map(row=><option value={row.id} key={row.id}>{row.name}</option>)}</select></FormField><button id="expense-quick-details" type="button" className="quick-defaults" onClick={()=>setStage('form')} aria-label={`${defaultsSummary}. ${t('expensesUi.changeDetails')}`}><Icon name="users"/><span>{defaultsSummary}</span><Icon name="chevronRight"/></button><FormActions><button className="primary quick-save" type="submit" disabled={busy||!validAmount(form.amount)||!form.participants.length}><Icon name="check"/>{busy?t('expensesUi.saving'):t('expensesUi.saveQuick')}</button><button type="button" className="text-button quick-scan" onClick={()=>{setError('');setStage('capture')}}><Icon name="camera"/>{t('expensesUi.scanReceipt')}</button></FormActions></FormShell>}
 {stage==='capture'&&<div className="expense-capture"><div className="receipt-hero"><Icon name="receipt" size={34}/><strong>{t('expensesUi.photo')}</strong><span>{t('expensesUi.captureHint')}</span></div><div className="file-drop-zone-grid"><FileDropZone className="compact" accept="image/*" capture="environment" disabled={busy} icon="camera" title={t('expensesUi.photo')} hint={t('expensesUi.captureHint')} onFiles={files=>upload(files[0])}/><FileDropZone className="compact" accept="image/jpeg,image/png,image/webp,image/heic,image/heif,.heic,.heif,application/pdf,.pdf" disabled={busy} icon="upload" title={t('expensesUi.chooseFile')} hint={t('expensesUi.captureHint')} onFiles={files=>upload(files[0])}/></div><button className="text-button manual-expense" onClick={()=>{setError('');setStage('quick')}}><Icon name="edit"/>{t('expensesUi.manual')}</button>{error&&<p className="error" role="alert">{error}</p>}</div>}
 {stage==='processing'&&<div className="expense-processing" role="status"><span className="receipt-spinner"><Icon name="refresh" size={30}/></span><strong>{status==='queued'?t('expensesUi.queued'):t('expensesUi.processing')}</strong><span>{t('expensesUi.captureHint')}</span>{quality.map(item=><small key={item}>{item==='dark'?t('expensesUi.qualityDark'):t('expensesUi.qualityLowResolution')}</small>)}</div>}
 {stage==='form'&&<form className="quick-form expense-form" onSubmit={save}>{draft?.source==='receipt'&&<div className={`receipt-review-status ${status==='failed'?'failed':''}`}><Icon name={status==='failed'?'warning':'receipt'}/><div><strong>{status==='failed'?t('expensesUi.ocrFailed'):t('expensesUi.review')}</strong><span>{t('expensesUi.reviewHint')}</span></div>{status==='failed'&&<button type="button" className="secondary compact" onClick={retry} disabled={busy}><Icon name="refresh"/>{t('expensesUi.retryOcr')}</button>}</div>}{quality.map(item=><p className="receipt-quality" key={item}><Icon name="warning"/>{item==='dark'?t('expensesUi.qualityDark'):t('expensesUi.qualityLowResolution')}</p>)}{receiptUrl&&<div className="receipt-preview">{draft?.receipt_mime==='application/pdf'?<span>{t('expensesUi.pdfReceipt')}</span>:<img src={receiptUrl} alt={t('expensesUi.imageReceipt')}/>}<a className="text-button" href={receiptUrl} target="_blank" rel="noopener noreferrer">{t('expensesUi.openReceipt')}</a><span><Icon name="lock"/>{t('expensesUi.receiptStored')}</span><button type="button" className="text-button" onClick={removeReceipt}>{t('expensesUi.removeReceipt')}</button></div>}{draft?.source==='receipt'&&<ReceiptIntelligenceReview extraction={extraction} currency={form.currency}/>} 
 <label>{t('expensesUi.merchant')}<span className="field-with-confidence"><input value={form.title} onChange={event=>setForm(value=>({...value,title:event.target.value}))} placeholder={t('expensesUi.optionalTitle')}/>{draft?.source==='receipt'&&<Confidence value={confidences.merchant} t={t}/>}</span></label><div className="form-grid"><label>{t('expensesUi.amount')}<span className="field-with-confidence"><input type="text" inputMode="decimal" value={form.amount} onChange={event=>setForm(value=>({...value,amount:event.target.value}))} required/>{draft?.source==='receipt'&&<Confidence value={confidences.total} t={t}/>}</span></label><label>{t('expensesUi.currency')}<select value={form.currency} onChange={event=>setForm(value=>({...value,currency:event.target.value,budget:event.target.value===(selectedLedger?.base_currency||event.target.value)?value.budget:''}))}><option>EUR</option><option>USD</option><option>GBP</option><option>CHF</option></select></label></div><label>{t('expensesUi.date')}<span className="field-with-confidence"><input type="date" value={form.date} onChange={event=>setForm(value=>({...value,date:event.target.value}))} required/>{draft?.source==='receipt'&&<Confidence value={confidences.date} t={t}/>}</span></label>
 <label>{t('expensesUi.category')}<input value={form.category} maxLength={80} onChange={event=>setForm(value=>({...value,category:event.target.value}))}/></label>
 <fieldset className="expense-funding"><legend>{t('expensesUi.fundingSource')}</legend><div className="funding-tabs"><button type="button" className={!isShared?'active':''} aria-pressed={!isShared} onClick={()=>setForm(value=>({...value,funding_source:'member'}))}>{t('expensesUi.personalFunding')}</button><button type="button" className={isShared?'active':''} aria-pressed={isShared} onClick={()=>setForm(value=>({...value,funding_source:'shared'}))}>{t('expensesUi.sharedFunding')}</button></div><small>{isShared?t('expensesUi.sharedFundingHint'):t('expensesUi.personalFundingHint')}</small></fieldset>
 {ledgers.length>0&&<label>{t('expensesUi.ledger')}<select value={form.ledger} onChange={event=>changeLedger(event.target.value)}>{ledgers.map(row=><option value={row.id} key={row.id}>{row.name}{row.is_default?` · ${t('expensesUi.defaultLedger')}`:''}</option>)}</select></label>}
 {(budgets.length>0||form.budget==='__advanced__')&&<label>{t('expensesUi.budget')}<select value={form.budget} disabled={!budgetCurrencyCompatible} onChange={event=>setForm(value=>({...value,budget:event.target.value}))}><option value="">{t('expensesUi.noBudget')}</option>{form.budget==='__advanced__'&&<option value="__advanced__">{t('expensesUi.advancedBudget')}</option>}{budgets.map(row=><option value={row.id} key={row.id}>{budgetTree(budgets).path(row)} · {t('budgetPlanning.miscellaneous')}</option>)}</select>{!budgetCurrencyCompatible&&<small className="expense-context-note">{t('expensesUi.budgetCurrencyHint',{currency:selectedLedger?.base_currency||'EUR'})}</small>}</label>}
 {contextError&&<p className="expense-context-note"><Icon name="warning"/>{contextError}</p>}
 {isShared?<p className="shared-funding-note"><Icon name="info"/>{t('expensesUi.sharedNoBalance')}</p>:<><label>{t('expensesUi.paidBy')}<select value={form.paid_by} onChange={event=>setForm(value=>({...value,paid_by:event.target.value}))} required><option value="" disabled>—</option>{members.map(member=><option key={member.id} value={member.id}>{memberName(member)}</option>)}</select></label><fieldset className="expense-participants"><legend>{t('expensesUi.participants')}</legend><div className="participant-chips">{members.map(member=>{const active=form.participants.includes(String(member.id));return <button type="button" key={member.id} className={active?'active':''} aria-pressed={active} onClick={()=>toggleMember(member.id)}><span>{memberName(member).slice(0,1).toUpperCase()}</span>{memberName(member)}{active&&<Icon name="check" size={12}/>}</button>})}</div></fieldset><fieldset className="expense-split"><legend>{t('expensesUi.split')}</legend><div className="split-tabs">{[['equal','equal'],['exact','exact'],['percentage','percentage'],['shares','shares']].map(([id,key])=><button key={id} type="button" className={form.split_type===id?'active':''} onClick={()=>changeSplit(id)}>{t(`expensesUi.${key}`)}</button>)}</div>{form.split_type!=='equal'&&<div className="split-values">{selectedMembers.map(member=><label key={member.id}><span>{memberName(member)}</span><input type="number" min="0" step={form.split_type==='shares'?'0.1':'0.01'} value={form.split_values[member.id]||''} onChange={event=>setForm(value=>({...value,split_values:{...value.split_values,[member.id]:event.target.value}}))} required/></label>)}</div>}</fieldset></>}
 {error&&<p className="error" role="alert">{error}</p>}<button className="primary" disabled={busy||!canSubmit}><Icon name="check"/>{busy?t('expensesUi.saving'):t('expensesUi.save')}</button></form>}</section></div>
}

function Confidence({value=0,t}){if(!value)return null;const [tone,label]=confidenceLabel(Number(value),t);return <small className={`confidence ${tone}`} title={`${t('expensesUi.confidence')}: ${Math.round(Number(value)*100)}%`}>{Math.round(Number(value)*100)}% · {label}</small>}
