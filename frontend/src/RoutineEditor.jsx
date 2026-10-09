import {useState} from 'react';
import {useTranslation} from 'react-i18next';
import './prediction-i18n';
import {api} from './api';
import {Icon} from './icons';
import {confirmAction,toast} from './feedback';
import {formatDateTime} from './locale';

function predictionText(prediction,t,language){
 if(!prediction||prediction.status==='not_enough_data')return t('predictionUi.routineLearningShort');
 if(prediction.status==='learning')return t('predictionUi.routineLearningShort');
 if(prediction.status==='overdue')return t('predictionUi.routineOverdue');
 if(prediction.status==='due')return t('predictionUi.routineDue');
 if(prediction.days_until_expected!==null&&prediction.days_until_expected!==undefined)return t('predictionUi.routineUpcoming',{count:Math.max(0,prediction.days_until_expected)});
 if(prediction.expected_at)return t('predictionUi.routineNext',{date:formatDateTime(language,prediction.expected_at,{dateStyle:'medium'})});
 return t('predictionUi.routineLearningShort');
}

export default function RoutineEditor({family,routine=null,onClose,onSaved}){
 const {t,i18n}=useTranslation();const isNew=!routine?.id;
 const [edit,setEdit]=useState(routine?{...routine}:{name:'',icon:'history',active:true});const [busy,setBusy]=useState(false);const [error,setError]=useState('');
 async function save(e){e.preventDefault();setBusy(true);setError('');try{const payload={family:family.id,name:edit.name.trim(),icon:edit.icon||'history',active:edit.active};const saved=await api(isNew?'/routines/':`/routines/${routine.id}/`,{method:isNew?'POST':'PATCH',body:JSON.stringify(payload)});toast(isNew?t('addRoutine'):t('save'),{type:'success'});await onSaved(saved)}catch(err){setError(err.message);toast(err.message||t('saveFailed'),{type:'error'});setBusy(false)}}
 async function remove(){if(isNew)return;const ok=await confirmAction({title:t('deleteRoutineConfirm'),message:edit.name||'',confirmLabel:t('delete'),danger:true});if(!ok)return;setBusy(true);try{await api(`/routines/${routine.id}/`,{method:'DELETE'});toast(t('delete'),{type:'success'});await onSaved(null,{deleted:true})}catch(err){setError(err.message);toast(err.message||t('saveFailed'),{type:'error'});setBusy(false)}}
 const prediction=routine?.prediction;
 return <div className="sheet-backdrop" onMouseDown={e=>{if(e.target===e.currentTarget&&!busy)onClose()}}><section className="quick-sheet" role="dialog" aria-modal="true"><div className="sheet-handle"/><div className="sheet-head"><h2>{isNew?t('addRoutine'):t('editRoutine')}</h2><button className="sheet-close" onClick={onClose} disabled={busy} aria-label={t('close')}><Icon name="close"/></button></div><form className="quick-form" onSubmit={save}><label>{t('name')}<input value={edit.name} onChange={e=>setEdit(v=>({...v,name:e.target.value}))} required autoFocus/></label><div className="integration-notice" role="status"><Icon name="history"/><div><strong>{isNew?t('predictionUi.routineLearningShort'):predictionText(prediction,t,i18n.language)}</strong><span>{prediction?.expected_interval_days?t('predictionUi.routineUsually',{days:prediction.expected_interval_days}):t('predictionUi.routineLearning')}</span></div></div><label className="toggle-label"><input type="checkbox" checked={edit.active} onChange={e=>setEdit(v=>({...v,active:e.target.checked}))}/>{t('enabled')}</label>{error&&<p className="error" role="alert">{error}</p>}<button className="primary" disabled={busy||!edit.name.trim()}><Icon name="check"/>{busy?t('pleaseWait'):t('save')}</button>{!isNew&&<button type="button" className="ghost-danger destructive-wide" onClick={remove} disabled={busy}><Icon name="delete"/>{t('delete')}</button>}</form></section></div>
}
