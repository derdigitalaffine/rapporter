import {useEffect,useId,useRef,useState} from 'react';
import {useTranslation} from 'react-i18next';
import {createPortal} from 'react-dom';
import {api} from './api';
import {Icon} from './icons';
import {confirmAction,toast} from './feedback';
import {ErrorSummary,FormActions,FormField,FormRow,FormShell} from './form-primitives';
import './budget-planning-i18n';
import './budget-planning.css';

const hasAmount=value=>value!==null&&value!==undefined;
const format=(value,currency,locale)=>new Intl.NumberFormat(locale,{style:'currency',currency}).format(Number(value||0));
const maximum=value=>Math.max(Number(value||0),.01);
const progress=(spent,total)=>Math.min(Math.max(Number(spent||0),0),maximum(total));

export default function BudgetPlanner({familyId,ledger,summary,loading,onReload,onSaved}){
 const {t,i18n}=useTranslation();
 const titleId=useId();
 const triggerRef=useRef(null);
 const sectionRef=useRef(null);
 const restoreFocus=useRef(false);
 const editorRef=useRef(null);
 const live=useRef(true);
 const [draft,setDraft]=useState(null);
 const [busy,setBusy]=useState(false);
 const [errors,setErrors]=useState({});
 const [failure,setFailure]=useState('');
 const [conflict,setConflict]=useState(false);
 useEffect(()=>{live.current=true;return()=>{live.current=false}},[]);
 useEffect(()=>{if(draft)editorRef.current?.querySelector('input')?.focus()},[Boolean(draft)]);
 useEffect(()=>{
  if(draft||loading||busy||!restoreFocus.current)return;
  const trigger=Array.from(sectionRef.current?.querySelectorAll('[data-budget-action]')||[]).find(item=>item.dataset.budgetAction===triggerRef.current);
  (trigger||sectionRef.current?.querySelector('[data-budget-action="overall"]'))?.focus();
  restoreFocus.current=false;
 },[Boolean(draft),loading,busy]);
 const currency=summary?.currency||ledger?.base_currency||'EUR';
 const f=value=>format(value,currency,i18n.language);
 const budgets=summary?.budgets||[];
 const hasOverall=hasAmount(summary?.budget_amount);
 const label=key=>t(`budgetPlanning.${key}`);

 function open(event,record,type){
  triggerRef.current=event.currentTarget.dataset.budgetAction;
  setErrors({});setFailure('');setConflict(false);
  setDraft({type,id:record?.id||null,name:record?.name||'',amount:String((type==='overall'?summary?.budget_amount:record?.amount)??''),estimate:String((type==='overall'?summary?.estimated_amount:record?.estimated_amount)??''),revision:type==='overall'?summary?.updated_at:record?.updated_at,requestId:crypto.randomUUID()});
 }
 function close(){restoreFocus.current=true;setDraft(null);setErrors({});setFailure('');setConflict(false)}
 function set(key,value){setDraft(current=>({...current,[key]:value}));setErrors(current=>({...current,[key]:''}));if(!conflict)setFailure('')}
 async function save(event){
  event.preventDefault();if(busy||conflict)return;
  const next={};
  for(const key of ['amount','estimate'])if(draft[key].trim()&&!/^\d{1,10}([,.]\d{1,2})?$/.test(draft[key].trim()))next[key]=label('invalidMoney');
  if(draft.type!=='overall'&&!draft.amount.trim())next.amount=label('requiredPlan');
  if(draft.type!=='overall'&&!draft.name.trim())next.name=label('requiredName');
  setErrors(next);if(Object.keys(next).length)return;
  if(!navigator.onLine){setFailure(label('offline'));return}
  setBusy(true);setFailure('');
  const overall=draft.type==='overall';
  const payload={family:familyId,estimated_amount:draft.estimate.trim()||null,expected_updated_at:draft.revision||undefined};
  if(overall)payload.budget_amount=draft.amount.trim()||null;
  else Object.assign(payload,{ledger:ledger.id,name:draft.name.trim(),amount:draft.amount.trim(),...(!draft.id?{client_request_id:draft.requestId}:{})});
  try{
   await api(overall?`/expense-ledgers/${ledger.id}/`:draft.id?`/expense-budgets/${draft.id}/`:'/expense-budgets/',{method:overall||draft.id?'PATCH':'POST',body:JSON.stringify(payload)});
   if(!live.current)return;
   close();toast(label('saved'),{type:'success'});await onSaved();
  }catch(error){
   if(!live.current)return;
   if(error.status===409){setConflict(true);setFailure(label('conflict'))}
   else{
    const fieldErrors={};
    for(const [server,local] of [[overall?'budget_amount':'amount','amount'],['estimated_amount','estimate'],['name','name']]){
     const messages=error.payload?.[server];if(messages)fieldErrors[local]=Array.isArray(messages)?messages.join(' '):String(messages);
    }
    setErrors(fieldErrors);setFailure(Object.keys(fieldErrors).length?'':error.status?error.message||label('saveFailed'):label('saveFailed'));
   }
  }finally{if(live.current)setBusy(false)}
 }
 async function archive(event,item){
  if(!await confirmAction({title:label('archiveQuestion'),message:item.name,confirmLabel:label('archive'),danger:false}))return;
  if(!navigator.onLine){setFailure(label('offline'));return}
  setBusy(true);
  try{await api(`/expense-budgets/${item.id}/`,{method:'PATCH',body:JSON.stringify({family:familyId,archived:true,expected_updated_at:item.updated_at})});if(live.current){restoreFocus.current=true;triggerRef.current='new-category';await onSaved()}}
  catch(error){if(live.current)setFailure(error.status===409?label('conflict'):error.message)}
  finally{if(live.current)setBusy(false)}
 }
 async function reload(){close();await onReload()}

 return <><section ref={sectionRef} className="expense-section budget-progress-card budget-planner" aria-labelledby={titleId}>
  <div className="budget-progress-head"><div><small>{ledger?.name}</small><h2 id={titleId}>{t('expensesUi.budgetProgress')}</h2></div><button type="button" data-budget-action="overall" className="secondary compact" disabled={!summary||loading||busy} onClick={event=>open(event,ledger,'overall')}><Icon name="edit"/>{label('plan')}</button></div>
  {!draft&&failure&&<div role="alert"><p className="error">{failure}</p><button type="button" className="secondary" disabled={busy||loading} onClick={onReload}><Icon name="refresh"/>{label('reload')}</button></div>}
  {!summary&&(loading?<p role="status">{t('pleaseWait')}</p>:<div role="alert"><p>{label('loadFailed')}</p><button type="button" className="secondary" onClick={onReload}><Icon name="refresh"/>{t('expensesUi.retryLoad')}</button></div>)}
  {summary&&<>
   {(hasOverall||hasAmount(summary.estimated_amount))?<dl className="budget-planning-facts">{hasAmount(summary.estimated_amount)&&<div><dt>{label('estimated')}</dt><dd>{f(summary.estimated_amount)}</dd></div>}<div><dt>{label('planned')}</dt><dd>{hasOverall?f(summary.budget_amount):label('notPlanned')}</dd></div><div><dt>{label('actual')}</dt><dd>{f(summary.spent_amount)}</dd></div></dl>:<p className="budget-planning-empty">{label('empty')}</p>}
   {hasOverall&&<><strong className="budget-planning-used">{t('expensesUi.budgetUsed',{spent:f(summary.spent_amount),budget:f(summary.budget_amount)})}</strong><progress max={maximum(summary.budget_amount)} value={progress(summary.spent_amount,summary.budget_amount)} aria-label={t('expensesUi.budgetProgress')}/><p className="budget-status">{summary.over_budget?t('expensesUi.budgetExceeded',{amount:f(Math.abs(Number(summary.remaining_amount||0)))}):t('expensesUi.budgetRemaining',{amount:f(summary.remaining_amount)})}</p></>}
   <details className="finance-collapsible"><summary><span>{t('expensesUi.subBudgets')}</span><small>{budgets.length}</small></summary><div className="subbudget-list">{budgets.map(item=><div className="budget-planning-row" key={item.id}><div><strong>{item.name}</strong><small>{t('expensesUi.budgetUsed',{spent:f(item.spent_amount),budget:f(item.amount)})}</small>{hasAmount(item.estimated_amount)&&<small>{label('estimated')}: {f(item.estimated_amount)}</small>}<progress max={maximum(item.amount)} value={progress(item.spent_amount,item.amount)} aria-label={item.name}/><small>{item.over_budget?t('expensesUi.budgetExceeded',{amount:f(Math.abs(Number(item.remaining_amount||0)))}):t('expensesUi.budgetRemaining',{amount:f(item.remaining_amount)})}</small></div><div className="budget-planning-row-actions"><button type="button" data-budget-action={item.id} className="ghost icon-button" disabled={busy} aria-label={`${label('editCategory')}: ${item.name}`} title={label('editCategory')} onClick={event=>open(event,item,'category')}><Icon name="edit"/></button><button type="button" className="ghost icon-button" disabled={busy} aria-label={`${label('archive')}: ${item.name}`} title={label('archive')} onClick={event=>archive(event,item)}><Icon name="archive"/></button></div></div>)}</div><button type="button" data-budget-action="new-category" className="text-button budget-planning-add" disabled={busy||loading} onClick={event=>open(event,null,'category')}><Icon name="plus"/>{label('newCategory')}</button></details>
   {Number(summary.unconverted_expense_count)>0&&<p className="budget-unconverted"><Icon name="info"/>{t('expensesUi.budgetUnconverted',{count:Number(summary.unconverted_expense_count)})}</p>}
   <p className="budget-soft-hint"><Icon name="info"/>{t('expensesUi.budgetSoftHint')}</p>
  </>}
 </section>
 {draft&&createPortal(<div className="sheet-backdrop budget-planning-backdrop" onMouseDown={event=>{if(event.target===event.currentTarget&&!busy)close()}}><section ref={editorRef} className="quick-sheet budget-planning-sheet" role="dialog" aria-modal="true" aria-labelledby={`${titleId}-editor`}>
  <div className="sheet-head"><div><small>{ledger?.name}</small><h2 id={`${titleId}-editor`}>{label(draft.type==='overall'?'editOverall':draft.id?'editCategory':'newCategory')}</h2></div><button type="button" className="sheet-close" disabled={busy} onClick={close} aria-label={t('dismiss')}><Icon name="close"/></button></div>
  {failure&&<p role="alert" className="error">{failure}</p>}
  <FormShell onSubmit={save} noValidate className="budget-planner-editor">
   <ErrorSummary title={label('checkFields')} errors={Object.entries(errors).filter(([,message])=>message).map(([key,message])=>({id:`${titleId}-${key}`,message,label:label(key==='name'?'name':key==='amount'?'planned':'estimated')}))}/>
   <fieldset disabled={busy} className="budget-planner-fields">
    {draft.type!=='overall'&&<FormField id={`${titleId}-name`} label={label('name')} error={errors.name} required><input maxLength={120} value={draft.name} onChange={event=>set('name',event.target.value)}/></FormField>}
    <FormRow>
     <FormField id={`${titleId}-amount`} label={`${label(draft.type==='overall'?'overallPlanned':'planned')} (${currency})`} error={errors.amount} required={draft.type!=='overall'}><input type="text" inputMode="decimal" autoComplete="off" value={draft.amount} onChange={event=>set('amount',event.target.value)}/></FormField>
     <FormField id={`${titleId}-estimate`} label={`${label('estimated')} (${currency})`} error={errors.estimate}><input type="text" inputMode="decimal" autoComplete="off" value={draft.estimate} onChange={event=>set('estimate',event.target.value)}/></FormField>
    </FormRow>
   </fieldset>
   <FormActions><button type="button" className="secondary" disabled={busy} onClick={close}>{t('expensesUi.close')}</button>{conflict?<button type="button" className="primary" disabled={busy} onClick={reload}><Icon name="refresh"/>{label('reload')}</button>:<button type="submit" className="primary" disabled={busy}><Icon name="check"/>{busy?t('expensesUi.saving'):label('save')}</button>}</FormActions>
  </FormShell></section></div>,document.body)}
 </>;
}
