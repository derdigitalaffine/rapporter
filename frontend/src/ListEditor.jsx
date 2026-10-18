import {useState} from 'react';
import {useTranslation} from 'react-i18next';
import {api} from './api';
import {useFamilyPermissions} from './family-permissions';
import {Icon} from './icons';
import WorkflowSettings from './WorkflowSettings';
import ShoppingAudienceFields,{defaultShoppingAudience} from './ShoppingAudienceFields';
import './workflow-i18n';
import './shopping-list-delete-i18n';
import {confirmAction,toast} from './feedback';
import {ErrorSummary,FormActions,FormField,FormShell,ProgressiveFieldGroup} from './form-primitives';
import SymbolPicker from './SymbolPicker';
import FamilySheet from './ui/FamilySheet';

function initialAudience(list){
 const access=list?.access;if(!access)return defaultShoppingAudience();
 return {visibility:access.visibility||'family',visible_members:(access.visible_members||[]).map(row=>String(row.id)),responsible_members:(access.responsible_members||[]).map(row=>String(row.id))};
}

export default function ListEditor({type,list=null,family,onClose,onSaved}){
 const {t}=useTranslation();const {canManageSettings}=useFamilyPermissions(family);const isNew=!list?.id;const initial=list||{name:'',store:'',icon:type==='task'?'list-check':'cart-shopping',archived:false};
 const [form,setForm]=useState({...initial});const [audience,setAudience]=useState(()=>initialAudience(list));const [busy,setBusy]=useState(false);const [error,setError]=useState('');
 const path=type==='task'?'task-lists':'shopping-lists';const audienceFamily=family||{id:list?.family};const canManageAudience=isNew||list?.access?.can_manage!==false;const canDeleteShopping=type==='shopping'&&!isNew&&list?.access?.can_manage===true;
 const set=(key,value)=>setForm(v=>({...v,[key]:value}));
 async function save(e){e.preventDefault();setBusy(true);setError('');try{const payload={name:form.name.trim(),store:type==='shopping'?form.store||'':undefined,archived:!!form.archived,icon:form.icon||(type==='task'?'list-check':'cart-shopping')};if(type==='task'&&canManageSettings&&!!form.workflow_enabled!==!!list?.workflow_enabled)payload.workflow_enabled=!!form.workflow_enabled;if(isNew)payload.family=family?.id;if(type==='shopping'&&canManageAudience)Object.assign(payload,audience);const saved=await api(isNew?`/${path}/`:`/${path}/${list.id}/`,{method:isNew?'POST':'PATCH',body:JSON.stringify(payload)});await onSaved(saved);toast(t(isNew?'listCreated':'listSaved'),{type:'success'})}catch(err){setError(err.message);toast(err.message||t('listSaveFailed'),{type:'error'})}finally{setBusy(false)}}
 async function archive(){setBusy(true);setError('');try{await api(`/${path}/${list.id}/`,{method:'PATCH',body:JSON.stringify({archived:true})});await onSaved();toast(t('listArchived',{name:list.name}),{type:'success',actionLabel:t('undo'),duration:8000,onAction:async()=>{try{await api(`/${path}/${list.id}/`,{method:'PATCH',body:JSON.stringify({archived:false})});await onSaved();toast(t('archiveUndone'),{type:'success'})}catch(err){toast(err.message||t('restoreListFailed'),{type:'error'})}}})}catch(err){setError(err.message);toast(err.message||t('archiveListFailed'),{type:'error'})}finally{setBusy(false)}}
 async function removeShoppingList(){const ok=await confirmAction({title:t('shoppingListDelete.title'),message:t('shoppingListDelete.message',{name:list.name}),confirmLabel:t('shoppingListDelete.action'),danger:true});if(!ok)return;setBusy(true);setError('');try{await api(`/${path}/${list.id}/`,{method:'DELETE'});await onSaved();toast(t('shoppingListDelete.success',{name:list.name}),{type:'success'})}catch(err){setError(err.message);toast(err.message||t('shoppingListDelete.failed'),{type:'error'})}finally{setBusy(false)}}
 const errors=error?[{id:'list-name',label:t('name'),message:error}]:[];
 return <FamilySheet labelledBy="list-editor-title" onClose={onClose} busy={busy}><div className="sheet-handle"/><div className="sheet-head"><div><small>{type==='task'?t('taskList'):t('shoppingList')}</small><h2 id="list-editor-title">{isNew?t('create'):t('editList')}</h2></div><button type="button" className="sheet-close" onClick={onClose} disabled={busy} aria-label={t('close')}><Icon name="close"/></button></div><FormShell onSubmit={save} aria-busy={busy}>
  <ErrorSummary errors={errors}/>
  <FormField id="list-name" label={t('name')} required><input value={form.name||''} onChange={e=>set('name',e.target.value)}/></FormField>
  {type==='shopping'&&canManageAudience&&<ShoppingAudienceFields family={audienceFamily} value={audience} onChange={setAudience} compact/>}
  <ProgressiveFieldGroup label={t('moreDetails')} defaultOpen={!isNew}>
    <SymbolPicker label={t('symbol')} value={form.icon||initial.icon} onChange={icon=>set('icon',icon)} disabled={busy} options={['list-check','cart-shopping','house','store','star','calendar','utensils','car','broom','pet','school','heart']}/>
    {type==='task'&&canManageSettings&&<><label className="toggle-label"><input type="checkbox" checked={!!form.workflow_enabled} onChange={e=>set('workflow_enabled',e.target.checked)}/><span>{t('workflowUi.enabled')}</span></label><small>{t('workflowUi.hint')}</small>{list?.workflow_enabled&&form.workflow_enabled&&<WorkflowSettings list={list}/>}</>}
  </ProgressiveFieldGroup>
  <FormActions><button type="button" className="secondary" onClick={onClose} disabled={busy}>{t('cancel')}</button><button className="primary" disabled={busy||!form.name.trim()}><Icon name="check"/> {busy?t('saving'):t('save')}</button></FormActions>
  {!isNew&&<button type="button" className="ghost-danger destructive-wide" onClick={archive} disabled={busy}><Icon name="archive"/> {t('archiveList')}</button>}
  {canDeleteShopping&&<button type="button" className="ghost-danger destructive-wide" onClick={removeShoppingList} disabled={busy}><Icon name="trash"/> {t('shoppingListDelete.action')}</button>}
 </FormShell></FamilySheet>
}
