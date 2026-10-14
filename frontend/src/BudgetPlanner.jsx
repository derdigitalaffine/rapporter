import {useEffect,useId,useMemo,useRef,useState} from 'react';
import {useTranslation} from 'react-i18next';
import {createPortal} from 'react-dom';
import {api} from './api';
import {Icon} from './icons';
import {confirmAction,toast} from './feedback';
import {ErrorSummary,FormActions,FormField,FormRow,FormShell} from './form-primitives';
import './budget-planning-i18n';
import './budget-planning.css';

const hasAmount=value=>value!==null&&value!==undefined;
const unwrap=value=>value?.results||value||[];
const format=(value,currency,locale)=>new Intl.NumberFormat(locale,{style:'currency',currency}).format(Number(value||0));
const maximum=value=>Math.max(Number(value||0),.01);
const progress=(spent,total)=>Math.min(Math.max(Number(spent||0),0),maximum(total));
const periodKeys={open:'periodOpen',month:'periodMonth',year:'periodYear',date_range:'periodDateRange',context:'periodContext'};
const displayDate=(value,locale)=>value?new Intl.DateTimeFormat(locale,{dateStyle:'medium'}).format(new Date(`${value}T12:00:00`)):'';
const moneyPattern=/^\d{1,10}([,.]\d{1,2})?$/;
const moneyNumber=value=>Number(String(value??'').trim().replace(',','.'))||0;
const memberName=member=>member?.display_name||member?.username||'—';
const blankParticipantPlans=members=>(members||[]).map(member=>({member:String(member.id),name:memberName(member),spending_limit:'',planned_share:''}));
const populatedParticipantCount=rows=>(rows||[]).filter(row=>String(row.spending_limit||'').trim()||String(row.planned_share||'').trim()).length;
const flattenMessage=value=>{
 if(!value)return'';
 if(typeof value==='string')return value;
 if(Array.isArray(value))return value.map(flattenMessage).filter(Boolean).join(' ');
 if(typeof value==='object')return Object.values(value).map(flattenMessage).filter(Boolean).join(' ');
 return String(value);
};

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
 const [familyContext,setFamilyContext]=useState({members:[],role:null,loaded:false});
 useEffect(()=>{live.current=true;return()=>{live.current=false}},[]);
 useEffect(()=>{if(draft)editorRef.current?.querySelector('input')?.focus()},[Boolean(draft)]);
 useEffect(()=>{
  if(draft||loading||busy||!restoreFocus.current)return;
  const trigger=Array.from(sectionRef.current?.querySelectorAll('[data-budget-action]')||[]).find(item=>item.dataset.budgetAction===triggerRef.current);
  (trigger||sectionRef.current?.querySelector('[data-budget-action="overall"]'))?.focus();
  restoreFocus.current=false;
 },[Boolean(draft),loading,busy]);
 useEffect(()=>{
  if(!familyId)return;
  let active=true;
  Promise.all([api('/families/'),api('/auth/session/')]).then(([families,session])=>{
   if(!active)return;
   const family=unwrap(families).find(row=>String(row.id)===String(familyId));
   const members=family?.memberships||[];
   const own=members.find(row=>String(row.user)===String(session?.user?.id));
   setFamilyContext({members,role:own?.role||null,loaded:true});
  }).catch(()=>{if(active)setFamilyContext({members:[],role:null,loaded:true})});
  return()=>{active=false};
 },[familyId]);
 const canManageParticipants=familyContext.role==='owner'||familyContext.role==='adult';
 const memberKey=familyContext.members.map(member=>member.id).join('|');
 useEffect(()=>{
  if(!draft||draft.type==='overall'||draft.id||!canManageParticipants)return;
  setDraft(current=>{
   if(!current||current.type==='overall'||current.id)return current;
   const existing=new Map((current.participantPlans||[]).map(row=>[String(row.member),row]));
   return {...current,participantPlans:blankParticipantPlans(familyContext.members).map(row=>existing.get(row.member)||row),participantLoaded:true};
  });
 },[draft?.id,draft?.type,canManageParticipants,memberKey]);
 useEffect(()=>{
  if(!draft?.id||!canManageParticipants)return;
  let active=true;
  const scopeId=String(draft.id);
  const endpoint=draft.type==='overall'?`/expense-ledgers/${encodeURIComponent(scopeId)}/participant-plans/`:`/expense-budgets/${encodeURIComponent(scopeId)}/participant-plans/`;
  setDraft(current=>current?.id===scopeId?{...current,participantLoading:true,participantError:''}:current);
  api(endpoint).then(data=>{
   if(!active)return;
   const configured=new Map((data?.plans||[]).map(row=>[String(row.member),row]));
   const participantPlans=blankParticipantPlans(familyContext.members).map(row=>{
    const saved=configured.get(row.member);
    return saved?{...row,spending_limit:saved.spending_limit??'',planned_share:saved.planned_share??''}:row;
   });
   setDraft(current=>current?.id===scopeId?{...current,participantPlans,participantLoaded:true,participantLoading:false,participantError:'',participantDirty:false}:current);
  }).catch(()=>{
   if(active)setDraft(current=>current?.id===scopeId?{...current,participantLoading:false,participantLoaded:false,participantError:t('budgetPlanning.participantLoadFailed')}:current);
  });
  return()=>{active=false};
 },[draft?.id,draft?.type,canManageParticipants,memberKey,familyId,t]);
 const currency=summary?.currency||ledger?.base_currency||'EUR';
 const f=value=>format(value,currency,i18n.language);
 const budgets=summary?.budgets||[];
 const hasOverall=hasAmount(summary?.budget_amount);
 const label=key=>t(`budgetPlanning.${key}`);
 const participantCount=populatedParticipantCount(draft?.participantPlans);
 const participantShareTotal=useMemo(()=>draft?.participantPlans?.reduce((sum,row)=>sum+moneyNumber(row.planned_share),0)||0,[draft?.participantPlans]);
 const participantDifference=draft?.amount&&moneyPattern.test(String(draft.amount).trim())?moneyNumber(draft.amount)-participantShareTotal:null;

 function open(event,record,type){
  triggerRef.current=event.currentTarget.dataset.budgetAction;
  setErrors({});setFailure('');setConflict(false);
  setDraft({
   type,id:record?.id?String(record.id):null,name:record?.name||'',amount:String((type==='overall'?summary?.budget_amount:record?.amount)??''),estimate:String((type==='overall'?summary?.estimated_amount:record?.estimated_amount)??''),
   periodType:record?.period_type||'open',rolloverPolicy:record?.rollover_policy||'reset',startsOn:record?.starts_on||'',endsOn:record?.ends_on||'',
   participantPlans:blankParticipantPlans(familyContext.members),participantLoaded:!record?.id,participantLoading:false,participantError:'',participantDirty:false,
   revision:type==='overall'?summary?.updated_at:record?.updated_at,requestId:crypto.randomUUID(),
  });
 }
 function close(){restoreFocus.current=true;setDraft(null);setErrors({});setFailure('');setConflict(false)}
 function set(key,value){setDraft(current=>({...current,[key]:value}));setErrors(current=>({...current,[key]:''}));if(!conflict)setFailure('')}
 function setParticipant(member,key,value){
  setDraft(current=>({...current,participantDirty:true,participantPlans:(current.participantPlans||[]).map(row=>row.member===member?{...row,[key]:value}:row)}));
  setErrors(current=>({...current,[`participant-${member}-${key}`]:''}));
  if(!conflict)setFailure('');
 }
 function errorLabel(key){
  if(key.endsWith('-spending_limit'))return label('personalLimit');
  if(key.endsWith('-planned_share'))return label('plannedShare');
  return label(key==='name'?'name':key==='amount'?'planned':key==='estimate'?'estimated':key==='periodType'?'periodType':key==='rolloverPolicy'?'rolloverPolicy':key==='startsOn'?'startsOn':'endsOn');
 }
 async function save(event){
  event.preventDefault();if(busy||conflict)return;
  const next={};
  for(const key of ['amount','estimate'])if(draft[key].trim()&&!moneyPattern.test(draft[key].trim()))next[key]=label('invalidMoney');
  if(draft.type!=='overall'&&!draft.amount.trim())next.amount=label('requiredPlan');
  if(draft.type!=='overall'&&!draft.name.trim())next.name=label('requiredName');
  if(draft.type!=='overall'&&draft.periodType==='date_range'){
   if(!draft.startsOn||!draft.endsOn){next.startsOn=label('requiredDates');next.endsOn=label('requiredDates')}
   else if(draft.endsOn<draft.startsOn)next.endsOn=label('invalidDateRange');
  }
  if(canManageParticipants&&draft.participantLoaded){
   for(const row of draft.participantPlans||[]){
    for(const key of ['spending_limit','planned_share']){
     const value=String(row[key]??'').trim();
     if(value&&!moneyPattern.test(value))next[`participant-${row.member}-${key}`]=label('invalidMoney');
    }
   }
  }
  setErrors(next);if(Object.keys(next).length)return;
  if(!navigator.onLine){setFailure(label('offline'));return}
  setBusy(true);setFailure('');
  const overall=draft.type==='overall';
  const payload={family:familyId,estimated_amount:draft.estimate.trim()||null,expected_updated_at:draft.revision||undefined};
  if(overall)payload.budget_amount=draft.amount.trim()||null;
  else{
   Object.assign(payload,{ledger:ledger.id,name:draft.name.trim(),amount:draft.amount.trim(),period_type:draft.periodType,...(!draft.id?{client_request_id:draft.requestId}:{})});
   if(draft.periodType==='month'||draft.periodType==='year')payload.rollover_policy=draft.rolloverPolicy;
   if(draft.periodType==='date_range'){
    payload.starts_on=draft.startsOn||null;payload.ends_on=draft.endsOn||null;
   }else if(draft.periodType!=='context'){
    payload.starts_on=null;payload.ends_on=null;
   }
  }
  const participantWrite=canManageParticipants&&draft.participantLoaded&&draft.participantDirty;
  if(participantWrite){
   payload.participant_plans=(draft.participantPlans||[]).filter(row=>String(row.spending_limit||'').trim()||String(row.planned_share||'').trim()).map(row=>({
    member:row.member,
    spending_limit:String(row.spending_limit||'').trim()||null,
    planned_share:String(row.planned_share||'').trim()||null,
   }));
  }
  try{
   const url=overall?(participantWrite?`/expense-ledgers/${ledger.id}/participant-plans/`:`/expense-ledgers/${ledger.id}/`):draft.id?`/expense-budgets/${draft.id}/`:'/expense-budgets/';
   await api(url,{method:overall||draft.id?'PATCH':'POST',body:JSON.stringify(payload)});
   if(!live.current)return;
   close();toast(label('saved'),{type:'success'});await onSaved();
  }catch(error){
   if(!live.current)return;
   if(error.status===409){setConflict(true);setFailure(label('conflict'))}
   else{
    const fieldErrors={};
    for(const [server,local] of [[overall?'budget_amount':'amount','amount'],['estimated_amount','estimate'],['name','name'],['period_type','periodType'],['rollover_policy','rolloverPolicy'],['starts_on','startsOn'],['ends_on','endsOn']]){
     const messages=error.payload?.[server];if(messages)fieldErrors[local]=flattenMessage(messages);
    }
    const participantMessage=flattenMessage(error.payload?.participant_plans);
    setErrors(fieldErrors);setFailure(participantMessage||(Object.keys(fieldErrors).length?'':error.status?error.message||label('saveFailed'):label('saveFailed')));
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
   {(hasOverall||hasAmount(summary.estimated_amount))?<dl className="budget-planning-facts">{hasAmount(summary.estimated_amount)&&<div><dt>{label('estimated')}</dt><dd>{f(summary.estimated_amount)}</dd></div>}<div><dt>{label('planned')}</dt><dd>{hasOverall?f(summary.budget_amount):label('notPlanned')}</dd></div><div><dt>{label('reserved')}</dt><dd>{f(summary.reserved_amount||0)}</dd></div><div><dt>{label('actual')}</dt><dd>{f(summary.spent_amount)}</dd></div>{hasOverall&&<div><dt>{label('available')}</dt><dd>{f(summary.available_amount)}</dd></div>}</dl>:<p className="budget-planning-empty">{label('empty')}</p>}
   {hasOverall&&<><strong className="budget-planning-used">{t('expensesUi.budgetUsed',{spent:f(summary.spent_amount),budget:f(summary.budget_amount)})}</strong><progress max={maximum(summary.budget_amount)} value={progress(summary.spent_amount,summary.budget_amount)} aria-label={t('expensesUi.budgetProgress')}/><p className="budget-status">{summary.over_available?t('expensesUi.budgetExceeded',{amount:f(Math.abs(Number(summary.available_amount||0)))}):t('expensesUi.budgetRemaining',{amount:f(summary.available_amount)})}</p></>}
   <details className="finance-collapsible"><summary><span>{t('expensesUi.subBudgets')}</span><small>{budgets.length}</small></summary><div className="subbudget-list">{budgets.map(item=>{const period=item.period_starts_on&&item.period_ends_on?`${displayDate(item.period_starts_on,i18n.language)} – ${displayDate(item.period_ends_on,i18n.language)}`:'';const periodLabel=label(periodKeys[item.period_type]||'periodOpen');return <div className="budget-planning-row" key={item.id}><div><strong>{item.name}</strong><small>{label('actual')}: {f(item.spent_amount)} · {label('reserved')}: {f(item.reserved_amount||0)}</small>{Number(item.carryover_amount||0)>0&&<small>{label('carryover')}: {f(item.carryover_amount)}</small>}{item.period_type!=='open'&&<small>{period?`${label('periodCurrent')}: ${period} · ${periodLabel}`:periodLabel}</small>}{hasAmount(item.estimated_amount)&&<small>{label('estimated')}: {f(item.estimated_amount)}</small>}<progress max={maximum(Number(item.amount||0)+Number(item.carryover_amount||0))} value={progress(item.spent_amount,Number(item.amount||0)+Number(item.carryover_amount||0))} aria-label={item.name}/><small>{label('available')}: {f(item.available_amount??item.remaining_amount)}</small></div><div className="budget-planning-row-actions"><button type="button" data-budget-action={item.id} className="ghost icon-button" disabled={busy} aria-label={`${label('editCategory')}: ${item.name}`} title={label('editCategory')} onClick={event=>open(event,item,'category')}><Icon name="edit"/></button><button type="button" className="ghost icon-button" disabled={busy} aria-label={`${label('archive')}: ${item.name}`} title={label('archive')} onClick={event=>archive(event,item)}><Icon name="archive"/></button></div></div>})}</div><button type="button" data-budget-action="new-category" className="text-button budget-planning-add" disabled={busy||loading} onClick={event=>open(event,null,'category')}><Icon name="plus"/>{label('newCategory')}</button></details>
   {Number(summary.unconverted_expense_count)>0&&<p className="budget-unconverted"><Icon name="info"/>{t('expensesUi.budgetUnconverted',{count:Number(summary.unconverted_expense_count)})}</p>}
   <p className="budget-soft-hint"><Icon name="info"/>{t('expensesUi.budgetSoftHint')}</p>
  </>}
 </section>
 {draft&&createPortal(<div className="sheet-backdrop budget-planning-backdrop" onMouseDown={event=>{if(event.target===event.currentTarget&&!busy)close()}}><section ref={editorRef} className="quick-sheet budget-planning-sheet" role="dialog" aria-modal="true" aria-labelledby={`${titleId}-editor`}>
  <div className="sheet-head"><div><small>{ledger?.name}</small><h2 id={`${titleId}-editor`}>{label(draft.type==='overall'?'editOverall':draft.id?'editCategory':'newCategory')}</h2></div><button type="button" className="sheet-close" disabled={busy} onClick={close} aria-label={t('dismiss')}><Icon name="close"/></button></div>
  {failure&&<p role="alert" className="error">{failure}</p>}
  <FormShell onSubmit={save} noValidate className="budget-planner-editor">
   <ErrorSummary title={label('checkFields')} errors={Object.entries(errors).filter(([,message])=>message).map(([key,message])=>({id:`${titleId}-${key}`,message,label:errorLabel(key)}))}/>
   <fieldset disabled={busy} className="budget-planner-fields">
    {draft.type!=='overall'&&<FormField id={`${titleId}-name`} label={label('name')} error={errors.name} required><input maxLength={120} value={draft.name} onChange={event=>set('name',event.target.value)}/></FormField>}
    <FormRow>
     <FormField id={`${titleId}-amount`} label={`${label(draft.type==='overall'?'overallPlanned':'planned')} (${currency})`} error={errors.amount} required={draft.type!=='overall'}><input type="text" inputMode="decimal" autoComplete="off" value={draft.amount} onChange={event=>set('amount',event.target.value)}/></FormField>
     <FormField id={`${titleId}-estimate`} label={`${label('estimated')} (${currency})`} error={errors.estimate}><input type="text" inputMode="decimal" autoComplete="off" value={draft.estimate} onChange={event=>set('estimate',event.target.value)}/></FormField>
    </FormRow>
    {draft.type!=='overall'&&<details className="finance-collapsible budget-period-settings"><summary><span>{label('periodSettings')}</span><small>{label(periodKeys[draft.periodType]||'periodOpen')}</small></summary><div className="budget-period-fields">
     <FormField id={`${titleId}-periodType`} label={label('periodType')} error={errors.periodType}><select value={draft.periodType} disabled={draft.periodType==='context'} onChange={event=>set('periodType',event.target.value)}><option value="open">{label('periodOpen')}</option><option value="month">{label('periodMonth')}</option><option value="year">{label('periodYear')}</option><option value="date_range">{label('periodDateRange')}</option>{draft.periodType==='context'&&<option value="context">{label('periodContext')}</option>}</select></FormField>
     {(draft.periodType==='month'||draft.periodType==='year')&&<><FormField id={`${titleId}-rolloverPolicy`} label={label('rolloverPolicy')} error={errors.rolloverPolicy}><select value={draft.rolloverPolicy} onChange={event=>set('rolloverPolicy',event.target.value)}><option value="reset">{label('rolloverReset')}</option><option value="carry_positive">{label('rolloverCarry')}</option></select></FormField><small className="budget-soft-hint"><Icon name="info"/>{label('rolloverHint')}</small></>}
     {draft.periodType==='date_range'&&<FormRow><FormField id={`${titleId}-startsOn`} label={label('startsOn')} error={errors.startsOn} required><input type="date" value={draft.startsOn} onChange={event=>set('startsOn',event.target.value)}/></FormField><FormField id={`${titleId}-endsOn`} label={label('endsOn')} error={errors.endsOn} required><input type="date" value={draft.endsOn} onChange={event=>set('endsOn',event.target.value)}/></FormField></FormRow>}
     {draft.periodType==='context'&&<p className="budget-soft-hint"><Icon name="info"/>{label('contextManaged')}</p>}
    </div></details>}
    {canManageParticipants&&<details className="finance-collapsible budget-participant-settings"><summary><span>{label('participantPlanning')}</span><small>{participantCount?t('budgetPlanning.participantCount',{count:participantCount}):label('participantOptional')}</small></summary><div className="budget-participant-fields">
     <p className="budget-soft-hint"><Icon name="info"/>{label('participantHint')}</p>
     {draft.participantLoading?<p role="status">{label('participantLoading')}</p>:draft.participantError?<p role="alert" className="budget-participant-error">{draft.participantError}</p>:draft.participantLoaded?<>{draft.participantPlans?.length?<div className="budget-participant-list">{draft.participantPlans.map(row=>{const limitKey=`participant-${row.member}-spending_limit`;const shareKey=`participant-${row.member}-planned_share`;return <div className="budget-participant-row" key={row.member}><strong>{row.name}</strong><div className="budget-participant-money"><FormField id={`${titleId}-${limitKey}`} label={`${label('personalLimit')} · ${row.name} (${currency})`} error={errors[limitKey]}><input type="text" inputMode="decimal" autoComplete="off" value={row.spending_limit} onChange={event=>setParticipant(row.member,'spending_limit',event.target.value)}/></FormField><FormField id={`${titleId}-${shareKey}`} label={`${label('plannedShare')} · ${row.name} (${currency})`} error={errors[shareKey]}><input type="text" inputMode="decimal" autoComplete="off" value={row.planned_share} onChange={event=>setParticipant(row.member,'planned_share',event.target.value)}/></FormField></div></div>})}</div>:<p>{label('noParticipants')}</p>}<div className="budget-participant-summary"><span><span>{label('plannedShareTotal')}</span><strong>{f(participantShareTotal)}</strong></span>{participantDifference!==null&&<span><span>{label('plannedShareDifference')}</span><strong>{f(participantDifference)}</strong></span>}<small className="budget-soft-hint">{label('plannedShareHint')}</small></div></>:null}
    </div></details>}
   </fieldset>
   <FormActions><button type="button" className="secondary" disabled={busy} onClick={close}>{t('expensesUi.close')}</button>{conflict?<button type="button" className="primary" disabled={busy} onClick={reload}><Icon name="refresh"/>{label('reload')}</button>:<button type="submit" className="primary" disabled={busy}><Icon name="check"/>{busy?t('expensesUi.saving'):label('save')}</button>}</FormActions>
  </FormShell></section></div>,document.body)}
 </>;
}