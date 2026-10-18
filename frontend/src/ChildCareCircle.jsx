import {useEffect,useState} from 'react';
import {useTranslation} from 'react-i18next';
import {api} from './api';
import {Icon} from './icons';
import {confirmAction,toast} from './feedback';
import FamilySheet from './ui/FamilySheet';
import {FormActions,FormField} from './form-primitives';
import './children-i18n';

export default function ChildCareCircle({baby,family}){
 const {t}=useTranslation(),c=key=>t(`childrenUi.${key}`);
 const [data,setData]=useState(null),[error,setError]=useState(''),[editing,setEditing]=useState(false);
 async function load(){setError('');try{setData(await api(`/baby/profiles/${baby.id}/care-circle/`))}catch(err){setError(err.message||c('accessError'))}}
 useEffect(()=>{let live=true;setData(null);setError('');api(`/baby/profiles/${baby.id}/care-circle/`).then(value=>{if(live)setData(value)}).catch(err=>{if(live)setError(err.message||c('accessError'))});return()=>{live=false}},[baby.id]);
 return <section className="child-circle" aria-labelledby="child-circle-title">
  <div className="child-section-head"><h2 id="child-circle-title">{c('careCircle')} · {baby.display_name}</h2><button type="button" className="secondary" disabled={!data} onClick={()=>setEditing(true)}><Icon name="edit"/>{c('editCircle')}</button></div>
  {error&&<div className="integration-notice" role="alert"><span>{error}</span><button type="button" className="secondary" onClick={load}>{c('reload')}</button></div>}
  {!data&&!error&&<p role="status">{c('loading')}</p>}
  {data&&<div className="child-circle-people">{data.authorities.map(row=><div key={row.membership} className="child-circle-person"><Icon name="lock"/><span><strong>{row.display_name}</strong><small>{c(row.has_custody?'custody':'legacy')} · {c('fullAccess')}</small></span></div>)}{data.care_circle.filter(row=>row.can_log_care||row.can_view_growth_development).map(row=><div key={row.membership} className="child-circle-person"><Icon name="members"/><span><strong>{row.display_name}</strong><small>{c('delegated')}</small></span></div>)}</div>}
  {editing&&data&&<CircleEditor key={baby.id} baby={baby} family={family} data={data} c={c} onClose={()=>setEditing(false)} onSaved={async()=>{setEditing(false);await load()}}/>}
 </section>;
}

function CircleEditor({baby,family,data,c,onClose,onSaved}){
 const authorityIds=new Set(data.authorities.map(row=>String(row.membership)));
 const candidates=(family.memberships||[]).filter(row=>!authorityIds.has(String(row.id))&&String(row.id)!==String(baby.membership));
 const [rows,setRows]=useState(()=>candidates.map(member=>data.care_circle.find(row=>String(row.membership)===String(member.id))||{membership:member.id,display_name:member.display_name||member.username,can_log_care:false,can_view_growth_development:false}));
 const [dirty,setDirty]=useState(false),[password,setPassword]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState('');
 async function close(){if(busy)return;if(dirty&&!await confirmAction({title:c('close'),message:c('unsaved'),confirmLabel:c('discard'),cancelLabel:c('keep')}))return;onClose()}
 function update(id,key,value){setDirty(true);setRows(current=>current.map(row=>String(row.membership)===String(id)?{...row,[key]:value}:row))}
 async function submit(event){event.preventDefault();setBusy(true);setError('');try{await api('/auth/reauth/password/',{method:'POST',body:JSON.stringify({password})});await api(`/baby/profiles/${baby.id}/care-circle/`,{method:'PUT',body:JSON.stringify({care_circle:rows.map(row=>({membership:row.membership,can_log_care:Boolean(row.can_log_care),can_view_growth_development:Boolean(row.can_view_growth_development)}))})});toast(c('saved'),{type:'success'});await onSaved()}catch(err){setError(err.message||c('error'))}finally{setBusy(false)}}
 return <FamilySheet labelledBy="child-circle-editor-title" busy={busy} onClose={close}>
  <div className="sheet-head"><h2 id="child-circle-editor-title">{c('careCircle')} · {baby.display_name}</h2><button className="sheet-close" type="button" disabled={busy} aria-label={c('close')} onClick={close}><Icon name="close"/></button></div>
  <form className="child-record-form" onSubmit={submit}>
   <fieldset className="child-form-fields" disabled={busy}><legend className="form-sr-only">{c('editCircle')}</legend>
    {data.authorities.map(row=><div className="child-circle-person" key={row.membership}><Icon name="lock"/><span><strong>{row.display_name}</strong><small>{c(row.has_custody?'custody':'legacy')} · {c('fullAccess')}</small></span></div>)}
    {rows.map(row=>{const inherited=data.inherited.find(item=>String(item.membership)===String(row.membership));return <fieldset className="child-delegation" key={row.membership}><legend>{row.display_name}</legend>{[['can_log_care','care'],['can_view_growth_development','growth']].map(([key,label])=><label key={key}><input type="checkbox" disabled={busy||Boolean(inherited?.[key])} checked={Boolean(inherited?.[key]||row[key])} onChange={event=>update(row.membership,key,event.target.checked)}/><span>{c(label)}{inherited?.[key]&&<small>{c('inherited')}</small>}</span></label>)}</fieldset>})}
    <FormField label={c('password')} required><input type="password" autoComplete="current-password" value={password} onChange={event=>setPassword(event.target.value)}/></FormField>
   </fieldset>
   {error&&<div className="integration-notice" role="alert">{error}</div>}
   <FormActions><button type="button" className="secondary" disabled={busy} onClick={close}>{c('cancel')}</button><button className="primary" disabled={busy||!dirty||!password}><Icon name="check"/>{c('save')}</button></FormActions>
  </form>
 </FamilySheet>;
}
