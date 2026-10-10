import {useEffect,useState} from 'react';
import {useTranslation} from 'react-i18next';
import './session-i18n';
import {api} from './api';
import {Icon} from './icons';
import {toast} from './feedback';

const empty={email:'',email_verified:false,email_action_required:false,pending_email:'',pending_verification_sent_at:null};

export default function EmailIdentityCard(){
 const {t}=useTranslation();
 const [identity,setIdentity]=useState(empty);const [loading,setLoading]=useState(true);const [busy,setBusy]=useState(false);const [editing,setEditing]=useState(false);const [email,setEmail]=useState('');const [password,setPassword]=useState('');
 async function load(){setLoading(true);try{setIdentity(await api('/auth/email/identity/'))}catch(e){toast(e.message||t('profileUi.loadFailed'),{type:'error'})}finally{setLoading(false)}}
 useEffect(()=>{load()},[]);
 async function resend(target){setBusy(true);try{await api('/auth/email/verification/resend/',{method:'POST',body:JSON.stringify({target})});toast(t('identityUi.verificationSent'),{type:'success'});await load()}catch(e){toast(e.message||t('saveFailed'),{type:'error'})}finally{setBusy(false)}}
 async function change(event){event.preventDefault();setBusy(true);try{await api('/auth/email/change/',{method:'POST',body:JSON.stringify({email,password})});setEmail('');setPassword('');setEditing(false);toast(t('identityUi.changeStarted'),{type:'success'});await load()}catch(e){toast(e.message||t('saveFailed'),{type:'error'})}finally{setBusy(false)}}
 if(loading)return <section className="card"><div className="profile-privacy-note"><Icon name="refresh"/><span>{t('pleaseWait')}</span></div></section>;
 const status=identity.email_action_required?t('identityUi.actionRequired'):identity.email_verified?t('identityUi.verified'):t('identityUi.unverified');
 return <section className="card" data-testid="email-identity-card"><div className="family-master-head"><div><small>{t('identityUi.securityTitle')}</small><h2>{identity.email||t('identityUi.actionRequired')}</h2><p>{t('identityUi.securityHint')}</p></div><span className={`status-pill ${identity.email_verified?'':'warning'}`}><Icon name={identity.email_verified?'check':'info'}/>{status}</span></div>
  {!identity.email_action_required&&!identity.email_verified&&<button className="secondary compact" disabled={busy} onClick={()=>resend('primary')}><Icon name="refresh"/>{t('identityUi.resend')}</button>}
  {identity.pending_email&&<div className="profile-privacy-note"><Icon name="info"/><span>{t('identityUi.pending')}: <strong>{identity.pending_email}</strong></span><button className="text-button" disabled={busy} onClick={()=>resend('pending')}>{t('identityUi.resend')}</button></div>}
  {!editing?<button className="secondary compact" onClick={()=>setEditing(true)}><Icon name="edit"/>{t('identityUi.change')}</button>:<form className="profile-form" onSubmit={change}><label>{t('identityUi.newEmail')}<input type="email" autoComplete="email" required value={email} onChange={event=>setEmail(event.target.value)}/></label><label>{t('identityUi.currentPassword')}<input type="password" autoComplete="current-password" required value={password} onChange={event=>setPassword(event.target.value)}/></label><div className="dialog-actions"><button type="button" className="secondary" onClick={()=>{setEditing(false);setEmail('');setPassword('')}}>{t('back')}</button><button className="primary" disabled={busy}>{busy?t('saving'):t('identityUi.change')}</button></div></form>}
 </section>
}
