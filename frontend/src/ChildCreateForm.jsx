import {useRef,useState} from 'react';
import {useTranslation} from 'react-i18next';
import {api} from './api';
import {Icon} from './icons';
import {FormActions,FormField} from './form-primitives';
import './children-i18n';
import './children-hub.css';

export default function ChildCreateForm({family,canRecordCustody,onBusyChange,onDirtyChange,onSaved,onCancel}){
 const {t}=useTranslation(),c=key=>t(`childrenUi.${key}`),key=useRef(crypto.randomUUID());
 const [form,setForm]=useState({name:'',birth:'',membership:'',custody:false,password:''}),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const existingChildren=(family.memberships||[]).filter(member=>member.role==='child');
 function update(field,value){setForm(current=>({...current,[field]:value}));onDirtyChange?.(true)}
 async function submit(event){event.preventDefault();setBusy(true);onBusyChange?.(true);setError('');try{
  if(form.custody)await api('/auth/reauth/password/',{method:'POST',body:JSON.stringify({password:form.password})});
  const child=await api('/baby/managed-children/',{method:'POST',body:JSON.stringify({family:family.id,display_name:form.name.trim(),birth_date:form.birth,client_identity_key:key.current,custody_for_self:form.custody,...(form.membership?{membership:form.membership}:{})})});
  onDirtyChange?.(false);await onSaved(child,{hasCustody:form.custody});
 }catch(err){setError(err.message||c('error'))}finally{setBusy(false);onBusyChange?.(false)}}
 return <form className="child-record-form" onSubmit={submit}><fieldset className="child-form-fields" disabled={busy}><legend>{c('addChild')}</legend>
  {existingChildren.length>0&&<FormField label={c('child')}><select value={form.membership} onChange={event=>{const child=existingChildren.find(row=>String(row.id)===event.target.value);setForm(current=>({...current,membership:event.target.value,birth:'',name:child?.display_name||child?.username||'',custody:false,password:''}));onDirtyChange?.(true)}}><option value="">{c('newChild')}</option>{existingChildren.map(child=><option key={child.id} value={child.id}>{child.display_name||child.username}</option>)}</select></FormField>}
  <FormField label={t('babyUi.name')} required><input maxLength={80} autoComplete="off" readOnly={Boolean(form.membership)} value={form.name} onChange={event=>update('name',event.target.value)}/></FormField>
  <FormField label={t('babyUi.birthDate')} required><input type="date" value={form.birth} onChange={event=>update('birth',event.target.value)}/></FormField>
  {canRecordCustody&&<label className="baby-toggle"><input type="checkbox" checked={form.custody} onChange={event=>update('custody',event.target.checked)}/><span>{c('confirmCustody')}</span></label>}
  {form.custody&&<FormField label={c('password')} required><input type="password" autoComplete="current-password" value={form.password} onChange={event=>update('password',event.target.value)}/></FormField>}
 </fieldset>{error&&<div className="integration-notice" role="alert">{error}</div>}<FormActions><button type="button" className="secondary" disabled={busy} onClick={onCancel}>{c('cancel')}</button><button className="primary" disabled={busy||!form.name.trim()||!form.birth||form.custody&&!form.password}><Icon name="check"/>{c('save')}</button></FormActions></form>;
}
