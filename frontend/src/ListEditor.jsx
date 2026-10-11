import {useState} from 'react';
import {useTranslation} from 'react-i18next';
import {api} from './api';
import {useFamilyPermissions} from './family-permissions';
import {Icon} from './icons';
import WorkflowSettings from './WorkflowSettings';
import ShoppingTemplateTools from './ShoppingTemplateTools';
import './workflow-i18n';
import {toast} from './feedback';
import {ErrorSummary,FormActions,FormField,FormShell,ProgressiveFieldGroup} from './form-primitives';

export default function ListEditor({type,list=null,family,onClose,onSaved}){
 const {t}=useTranslation();const {canManageSettings}=useFamilyPermissions(family);const isNew=!list?.id;const initial=list||{name:'',store:'',icon:type==='task'?'list-check':'cart-shopping',archived:false};
 const [form,setForm]=useState({...initial});const [busy,setBusy]=useState(false);const [error,setError]=useState('');
 const path=type==='task'?'task-lists':'shopping-lists';
 const set=(key,value)=>setForm(v=>({...v,[key]:value}));
 async function save(e){e.preventDefault();setBusy(true);setError('');try{const payload={name:form.name.trim(),store:type==='shopping'?form.store||'':undefined,archived:!!form.archived,icon:form.icon||(type==='task'?'list-check':'cart-shopping')};if(type==='task'&&canManageSettings&&!!form.workflow_enabled!==!!list?.workflow_enabled)payload.workflow_enabled=!!form.workflow_enabled;if(isNew)payload.family=family?.id;const saved=await api(isNew?`/${path}/`:`/${path}/${list.id}/`,{method:isNew?'POST':'PATCH',body:JSON.stringify(payload)});await onSaved(saved);toast(t(isNew?'listCreated':'listSaved'),{type:'success'})}catch(err){setError(err.message);toast(err.message||t('listSaveFailed'),{type:'error'})}finally{setBusy(false)}}
 async function archive(){setBusy(true);setError('');try{await api(`/${path}/${list.id}/`,{method:'PATCH',body:JSON.stringify({archived:true})});await onSaved();toast(t('listArchived',{name:list.name}),{type:'success',actionLabel:t('undo'),duration:8000,onAction:async()=>{try{await api(`/${path}/${list.id}/`,{method:'PATCH',body:JSON.stringify({archived:false})});await onSaved();toast(t('archiveUndone'),{type:'success'})}catch(err){toast(err.message||t('restoreListFailed'),{type:'error'})}}})}catch(err){setError(err.message);toast(err.message||t('archiveListFailed'),{type:'error'})}finally{setBusy(false)}}
 const errors=error?[{id:'list-name',label:t('name'),message:error}]:[];
 return <div className="sheet-backdrop" onMouseDown={e=>{if(e.target===e.currentTarget&&!busy)onClose()}}><section className="quick-sheet" role="dialog" aria-modal="true" aria-labelledby="list-editor-title"><div className="sheet-handle"/><div className="sheet-head"><div><small>{type==='task'?t('taskList'):t('shoppingList')}</small><h2 id="list-editor-title">{isNew?t('create'):t('editList')}</h2></div><button type="button" className="sheet-close" onClick={onClose} disabled={busy} aria-label={t('close')}><Icon name="close"/></button></div><FormShell className="quick-form" onSubmit={save}>
  <ErrorSummary errors={errors}/>
  <FormField id="list-name" label={t('name')} required><input value={form.name||''} onChange={e=>set('name',e.target.value)} autoFocus/></FormField>
  {type==='shopping'&&<FormField id="list-store" label={t('storeOrShop')}><input value={form.store||''} onChange={e=>set('store',e.target.value)} placeholder={t('storePlaceholder')}/></FormField>}
  <ProgressiveFieldGroup label={t('moreDetails')} defaultOpen={!isNew}>
    <FormField id="list-symbol" label={t('symbol')}><select value={form.icon||''} onChange={e=>set('icon',e.target.value)}><option value={type==='task'?'list-check':'cart-shopping'}>{t('default')}</option><option value="house">{t('homeLabel')}</option><option value="store">{t('store')}</option><option value="star">{t('favorites')}</option></select></FormField>
    {type==='task'&&canManageSettings&&<><label className="toggle-label"><input type="checkbox" checked={!!form.workflow_enabled} onChange={e=>set('workflow_enabled',e.target.checked)}/><span>{t('workflowUi.enabled')}</span></label><small>{t('workflowUi.hint')}</small>{list?.workflow_enabled&&form.workflow_enabled&&<WorkflowSettings list={list}/>}</>}
  </ProgressiveFieldGroup>
  <FormActions><button className="primary" disabled={busy||!form.name.trim()}><Icon name="check"/> {busy?t('saving'):t('save')}</button>{!isNew&&<button type="button" className="ghost-danger destructive-wide" onClick={archive} disabled={busy}><Icon name="archive"/> {t('archiveList')}</button>}</FormActions>
 </FormShell>{type==='shopping'&&!isNew&&<ShoppingTemplateTools familyId={family?.id||list?.family} list={list} onChanged={onSaved}/>}</section></div>
}
