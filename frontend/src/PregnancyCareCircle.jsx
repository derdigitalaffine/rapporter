import {useEffect,useState} from 'react';
import {useTranslation} from 'react-i18next';
import {api} from './api';
import {Icon} from './icons';
import {confirmAction} from './feedback';
import FamilySheet from './ui/FamilySheet';
import {FormActions,FormField} from './form-primitives';

export default function PregnancyCareCircle({family}){
 const {t}=useTranslation(),c=key=>t(`childrenUi.${key}`);
 const [open,setOpen]=useState(false),[rows,setRows]=useState(null),[password,setPassword]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState(''),[dirty,setDirty]=useState(false);
 useEffect(()=>{setOpen(false);setRows(null);setPassword('');setDirty(false)},[family.id]);
 async function edit(){setError('');try{const value=await api(`/baby/care-circle/?family=${encodeURIComponent(family.id)}`);setRows((family.memberships||[]).map(member=>value.care_circle.find(row=>String(row.membership)===String(member.id))||{membership:member.id,display_name:member.display_name||member.username,can_view_pregnancy:false,can_log_care:false,can_view_growth_development:false,is_guardian:false}));setOpen(true)}catch(err){setError(err.message||c('accessError'))}}
 async function close(){if(busy)return;if(dirty&&!await confirmAction({title:c('close'),message:c('unsaved'),confirmLabel:c('discard'),cancelLabel:c('keep')}))return;setOpen(false);setPassword('');setDirty(false)}
 async function save(event){event.preventDefault();setBusy(true);setError('');try{await api('/auth/reauth/password/',{method:'POST',body:JSON.stringify({password})});await api('/baby/care-circle/',{method:'PUT',body:JSON.stringify({family:family.id,care_circle:rows.map(row=>({membership:row.membership,can_view_pregnancy:Boolean(row.can_view_pregnancy),can_log_care:Boolean(row.can_log_care),can_view_growth_development:Boolean(row.can_view_growth_development),is_guardian:Boolean(row.is_guardian)}))})});setOpen(false);setPassword('');setDirty(false)}catch(err){setError(err.message||c('error'))}finally{setBusy(false)}}
 return <section className="child-circle"><div className="child-section-head"><h2>{t('babyUi.pregnancy')} · {c('careCircle')}</h2><button className="secondary" type="button" onClick={edit}><Icon name="edit"/>{c('editCircle')}</button></div>{error&&!open&&<div className="integration-notice" role="alert">{error}</div>}{open&&rows&&<FamilySheet labelledBy="pregnancy-circle-title" onClose={close} busy={busy}>
  <div className="sheet-head"><h2 id="pregnancy-circle-title">{t('babyUi.pregnancy')} · {c('careCircle')}</h2><button className="sheet-close" type="button" disabled={busy} onClick={close} aria-label={c('close')}><Icon name="close"/></button></div>
  <form className="child-record-form" onSubmit={save}><fieldset className="child-form-fields" disabled={busy}><legend className="form-sr-only">{t('babyUi.pregnancyPermission')}</legend>{rows.map(row=><label className="baby-toggle" key={row.membership}><input type="checkbox" checked={Boolean(row.can_view_pregnancy)} onChange={event=>{setDirty(true);setRows(current=>current.map(item=>item.membership===row.membership?{...item,can_view_pregnancy:event.target.checked}:item))}}/><span><strong>{row.display_name}</strong><small>{t('babyUi.pregnancyPermission')}</small></span></label>)}<FormField label={c('password')} required><input type="password" autoComplete="current-password" value={password} onChange={event=>setPassword(event.target.value)}/></FormField></fieldset>{error&&<div className="integration-notice" role="alert">{error}</div>}<FormActions><button type="button" className="secondary" disabled={busy} onClick={close}>{c('cancel')}</button><button className="primary" disabled={busy||!password||!dirty}>{c('save')}</button></FormActions></form>
 </FamilySheet>}</section>;
}
