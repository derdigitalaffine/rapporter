import {useEffect,useState} from 'react';
import {useTranslation} from 'react-i18next';
import {api} from './api';
import {Icon} from './icons';
import './workflow-i18n';
import {useDirtyForm} from './dirty-state';
import {ErrorSummary,FormActions,FormField,FormRow,FormShell,ProgressiveFieldGroup} from './form-primitives';

function localDateTime(value){if(!value)return'';const d=new Date(value);const pad=n=>String(n).padStart(2,'0');return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`}

export function TaskEditor({task=null,family,lists=[],members=[],defaultListId='',onClose,onSaved,onDelete}){
 const {t}=useTranslation();const isNew=!task?.id;const initial=task||{};
 const initialValues={title:initial.title||'',notes:initial.notes||'',task_list:initial.task_list||defaultListId||lists[0]?.id||'',due_at:localDateTime(initial.due_at),priority:initial.priority||'normal',estimate_minutes:initial.estimate_minutes||'',assignee:initial.assignee||'',workflow_column:initial.workflow_column||'',tags:(initial.tags||[]).join(', ')};
 const [historyRows,setHistoryRows]=useState([]);const [historyError,setHistoryError]=useState('');
 const [v,setV]=useState(initialValues);const [busy,setBusy]=useState(false);const [error,setError]=useState('');const set=(k,x)=>setV(s=>({...s,[k]:x}));
 useDirtyForm(JSON.stringify(v)!==JSON.stringify(initialValues));
 async function save(e){e.preventDefault();setBusy(true);setError('');try{const payload={title:v.title.trim(),notes:v.notes,task_list:v.task_list||null,due_at:v.due_at?new Date(v.due_at).toISOString():null,priority:v.priority,estimate_minutes:v.estimate_minutes?Number(v.estimate_minutes):null,assignee:v.assignee||null,tags:v.tags.split(',').map(x=>x.trim()).filter(Boolean)};if(lists.find(x=>x.id===v.task_list)?.workflow_enabled&&v.workflow_column)payload.workflow_column=v.workflow_column;if(isNew)payload.family=family?.id;const saved=await api(isNew?'/tasks/':`/tasks/${task.id}/`,{method:isNew?'POST':'PATCH',body:JSON.stringify(payload)});await onSaved(saved)}catch(e){setError(e.message);setBusy(false)}}
 async function remove(){if(!onDelete)return;setBusy(true);try{await onDelete()}finally{setBusy(false)}}
 const errors=error?[{id:'task-title',label:t('title'),message:error}]:[];
 const ambiguousList=isNew&&lists.length>1&&!defaultListId;
 return <div className="sheet-backdrop" onMouseDown={e=>{if(e.target===e.currentTarget&&!busy)onClose()}}><section className="quick-sheet" role="dialog" aria-modal="true" aria-labelledby="task-editor-title"><div className="sheet-handle"/><div className="sheet-head"><div><small>{t('taskTitle')}</small><h2 id="task-editor-title">{isNew?t('addTask'):task.title}</h2></div><button type="button" className="sheet-close" onClick={onClose} disabled={busy} aria-label={t('close')}><Icon name="close"/></button></div><FormShell className="quick-form" onSubmit={save}>
  <ErrorSummary errors={errors}/>
  <FormField id="task-title" label={t('title')} required><input value={v.title} onChange={e=>set('title',e.target.value)} autoFocus/></FormField>
  <FormRow>
    <FormField id="task-due" label={t('due')}><input type="datetime-local" value={v.due_at} onChange={e=>set('due_at',e.target.value)}/></FormField>
    {ambiguousList&&<FormField id="task-list" label={t('taskList')}><select value={v.task_list} onChange={e=>{set('task_list',e.target.value);set('workflow_column','')}}><option value="">{t('all')}</option>{lists.map(x=><option key={x.id} value={x.id}>{x.name}</option>)}</select></FormField>}
  </FormRow>
  <ProgressiveFieldGroup label={t('moreDetails')} defaultOpen={!isNew}>
    {!ambiguousList&&lists.length>0&&<FormField id="task-list-details" label={t('taskList')}><select value={v.task_list} onChange={e=>{set('task_list',e.target.value);set('workflow_column','')}}><option value="">{t('all')}</option>{lists.map(x=><option key={x.id} value={x.id}>{x.name}</option>)}</select></FormField>}
    <FormRow>
      <FormField id="task-priority" label={t('priority')}><select value={v.priority} onChange={e=>set('priority',e.target.value)}><option value="low">{t('low')}</option><option value="normal">{t('normal')}</option><option value="high">{t('high')}</option></select></FormField>
      <FormField id="task-duration" label={t('durationMinutes')}><input type="number" min="1" value={v.estimate_minutes} onChange={e=>set('estimate_minutes',e.target.value)}/></FormField>
    </FormRow>
    <FormField id="task-assignee" label={t('assignee')}><select value={v.assignee} onChange={e=>set('assignee',e.target.value)}><option value="">{t('nobody')}</option>{members.map(m=><option key={m.user} value={m.user}>{m.display_name||m.username}</option>)}</select></FormField>
    {lists.find(x=>x.id===v.task_list)?.workflow_enabled&&<FormField id="task-workflow" label={t('workflowUi.status')}><select value={v.workflow_column} onChange={e=>set('workflow_column',e.target.value)}><option value="">—</option>{(lists.find(x=>x.id===v.task_list)?.workflow_columns||[]).filter(x=>!x.archived).map(x=><option key={x.id} value={x.id}>{x.name}</option>)}</select></FormField>}
    <FormField id="task-tags" label={t('workflowUi.tag')}><input value={v.tags} onChange={e=>set('tags',e.target.value)}/></FormField>
    <FormField id="task-notes" label={t('notes')}><textarea rows="3" value={v.notes} onChange={e=>set('notes',e.target.value)}/></FormField>
  </ProgressiveFieldGroup>
  {!isNew&&lists.find(x=>x.id===v.task_list)?.workflow_enabled&&<details className="workflow-history" onToggle={async e=>{if(e.currentTarget.open)try{const rows=await api(`/tasks/${task.id}/status-history/`);setHistoryRows(rows.results||rows);setHistoryError('')}catch(err){setHistoryError(err.message)}}}><summary>{t('workflowUi.history')}</summary>{historyError&&<p role="alert">{historyError}</p>}{historyRows.map(row=><p key={row.id}>{row.changed_by}: {row.from||'—'} → {row.to||'—'} · {new Date(row.changed_at).toLocaleString()}</p>)}{!historyRows.length&&!historyError&&<p>{t('workflowUi.noHistory')}</p>}</details>}
  <FormActions><button className="primary" disabled={busy||!v.title.trim()}><Icon name="check"/>{busy?t('saving'):t('save')}</button>{!isNew&&onDelete&&<button type="button" className="ghost-danger destructive-wide" onClick={remove} disabled={busy}><Icon name="delete"/> {t('deleteTask')}</button>}</FormActions>
 </FormShell></section></div>
}

export function ShoppingEditor({item=null,shoppingList=null,lists=[],onClose,onSaved,onDelete,onSubmit}){
 const {t}=useTranslation();const isNew=!item?.id;const initial=item||{};const defaultList=shoppingList?.id||shoppingList||initial.shopping_list||lists[0]?.id||'';
 const initialValues={shopping_list:defaultList,name:initial.name||'',quantity:initial.quantity||'',category:initial.category||'',aisle:initial.aisle||'',note:initial.note||'',favorite:!!initial.favorite};
 const [v,setV]=useState(initialValues);const [busy,setBusy]=useState(false);const [error,setError]=useState('');const set=(k,x)=>setV(s=>({...s,[k]:x}));
 useDirtyForm(JSON.stringify(v)!==JSON.stringify(initialValues));
 async function save(e){e.preventDefault();if(isNew&&!v.shopping_list)return;setBusy(true);setError('');try{const payload={name:v.name.trim(),quantity:v.quantity,category:v.category,aisle:v.aisle,note:v.note,favorite:v.favorite};if(isNew)payload.shopping_list=v.shopping_list;const saved=onSubmit?await onSubmit(payload,{isNew,item}):await api(isNew?'/shopping-items/':`/shopping-items/${item.id}/`,{method:isNew?'POST':'PATCH',body:JSON.stringify(payload)});await onSaved(saved)}catch(e){setError(e.message);setBusy(false)}}
 async function remove(){if(!onDelete)return;setBusy(true);try{await onDelete()}finally{setBusy(false)}}
 const errors=error?[{id:'shopping-item-name',label:t('item'),message:error}]:[];
 return <div className="sheet-backdrop" onMouseDown={e=>{if(e.target===e.currentTarget&&!busy)onClose()}}><section className="quick-sheet" role="dialog" aria-modal="true" aria-labelledby="shopping-editor-title"><div className="sheet-handle"/><div className="sheet-head"><div><small>{t('shoppingItem')}</small><h2 id="shopping-editor-title">{isNew?t('addAction'):item.name}</h2></div><button type="button" className="sheet-close" onClick={onClose} disabled={busy} aria-label={t('close')}><Icon name="close"/></button></div><FormShell className="quick-form" onSubmit={save}>
  <ErrorSummary errors={errors}/>
  <FormField id="shopping-item-name" label={t('item')} required><input value={v.name} onChange={e=>set('name',e.target.value)} autoFocus/></FormField>
  <FormRow>
    <FormField id="shopping-quantity" label={t('quantity')}><input value={v.quantity} onChange={e=>set('quantity',e.target.value)} placeholder="2 × 500 g"/></FormField>
    {isNew&&lists.length>1&&<FormField id="shopping-list" label={t('shoppingList')} required><select value={v.shopping_list} onChange={e=>set('shopping_list',e.target.value)}><option value="">—</option>{lists.map(list=><option value={list.id} key={list.id}>{list.name}</option>)}</select></FormField>}
  </FormRow>
  <ProgressiveFieldGroup label={t('moreDetails')} defaultOpen={!isNew}>
    <FormField id="shopping-category" label={t('category')}><input value={v.category} onChange={e=>set('category',e.target.value)} placeholder={t('categoryPlaceholder')}/></FormField>
    <FormField id="shopping-aisle" label={t('aisle')}><input value={v.aisle} onChange={e=>set('aisle',e.target.value)} placeholder={t('aislePlaceholder')}/></FormField>
    <FormField id="shopping-note" label={t('note')}><textarea rows="2" value={v.note} onChange={e=>set('note',e.target.value)}/></FormField>
    <label className="toggle-label"><input type="checkbox" checked={v.favorite} onChange={e=>set('favorite',e.target.checked)}/><span><Icon name="favorite"/> {t('favoriteHint')}</span></label>
  </ProgressiveFieldGroup>
  <FormActions><button className="primary" disabled={busy||!v.name.trim()||(isNew&&!v.shopping_list)}><Icon name="check"/>{busy?t('saving'):t('save')}</button>{!isNew&&onDelete&&<button type="button" className="ghost-danger destructive-wide" onClick={remove} disabled={busy}><Icon name="delete"/> {t('deleteShoppingItem')}</button>}</FormActions>
 </FormShell></section></div>
}
