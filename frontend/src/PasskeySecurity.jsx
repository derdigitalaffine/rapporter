import {useEffect,useState} from 'react';
import {useTranslation} from 'react-i18next';
import {api} from './api';
import {Icon} from './icons';
import {toast} from './feedback';
import {isPasskeyCancellation,isPasskeySupported,listPasskeys,reauthenticateWithPasskey,registerPasskey,removePasskey,renamePasskey} from './passkey-api';
import './passkey-i18n';
import './passkey-security.css';

function formatDate(value,language){if(!value)return null;const date=new Date(value);if(Number.isNaN(date.getTime()))return null;return new Intl.DateTimeFormat(language||'de',{dateStyle:'medium',timeStyle:'short'}).format(date)}

export default function PasskeySecurity(){
 const {t,i18n}=useTranslation();
 const [rows,setRows]=useState([]);const [loading,setLoading]=useState(true);const [loadError,setLoadError]=useState(false);const [busy,setBusy]=useState(false);
 const [name,setName]=useState('');const [editId,setEditId]=useState('');const [editName,setEditName]=useState('');
 const [reauthOpen,setReauthOpen]=useState(false);const [reauthBusy,setReauthBusy]=useState(false);const [password,setPassword]=useState('');const [pending,setPending]=useState(null);
 const supported=isPasskeySupported();
 async function load(){setLoading(true);setLoadError(false);try{const data=await listPasskeys();setRows(data.results||[])}catch{setLoadError(true)}finally{setLoading(false)}}
 useEffect(()=>{load()},[]);
 function messageFor(error){if(error?.status===429)return t('passkeys.rateLimited');if(error?.status===503)return t('passkeys.unavailable');return error?.message||t('passkeys.actionFailed')}
 async function execute(action,{afterReauth=false}={}){
  setBusy(true);
  try{
   if(action.type==='add'){await registerPasskey(action.name);setName('');toast(t('passkeys.created'),{type:'success'})}
   if(action.type==='rename'){await renamePasskey(action.id,action.name);setEditId('');setEditName('');toast(t('passkeys.renamed'),{type:'success'})}
   if(action.type==='remove'){await removePasskey(action.id);toast(t('passkeys.removed'),{type:'success'})}
   setPending(null);setReauthOpen(false);await load();
  }catch(error){
   if(isPasskeyCancellation(error)){return}
   if(error?.status===403&&error?.code==='reauth_required'&&!afterReauth){setPending(action);setReauthOpen(true);return}
   toast(messageFor(error),{type:'error'});
  }finally{setBusy(false)}
 }
 async function add(event){event.preventDefault();const value=name.trim();if(value)await execute({type:'add',name:value})}
 async function saveRename(event,row){event.preventDefault();const value=editName.trim();if(value&&value!==row.name)await execute({type:'rename',id:row.id,name:value});else setEditId('')}
 async function remove(row){if(!window.confirm(t('passkeys.removeConfirm')))return;await execute({type:'remove',id:row.id})}
 async function finishReauth(){const action=pending;setPassword('');setReauthOpen(false);if(action)await execute(action,{afterReauth:true})}
 async function confirmPassword(event){event.preventDefault();if(!password)return;setReauthBusy(true);try{await api('/auth/reauth/password/',{method:'POST',body:JSON.stringify({password})});toast(t('passkeys.confirmed'),{type:'success'});await finishReauth()}catch(error){toast(error?.message||t('securitySessions.reauthFailed'),{type:'error'})}finally{setReauthBusy(false)}}
 async function confirmPasskey(){setReauthBusy(true);try{await reauthenticateWithPasskey();toast(t('passkeys.confirmed'),{type:'success'});await finishReauth()}catch(error){if(!isPasskeyCancellation(error))toast(messageFor(error),{type:'error'})}finally{setReauthBusy(false)}}
 if(loading)return <section className="card passkey-card" aria-busy="true"><div className="smart-empty"><Icon name="refresh" size={26}/><strong>{t('passkeys.loading')}</strong></div></section>;
 if(loadError)return <section className="card passkey-card"><div className="smart-empty"><Icon name="warning" size={26}/><strong>{t('passkeys.loadFailed')}</strong><button className="secondary" type="button" onClick={load}>{t('securitySessions.retry')}</button></div></section>;
 return <section className="card passkey-card" data-testid="passkey-security">
  <div className="passkey-head"><div><small>{t('passkeys.eyebrow')}</small><h2>{t('passkeys.title')}</h2><p>{t('passkeys.intro')}</p></div><Icon name="key" size={22}/></div>
  {!supported&&<div className="integration-notice" role="status"><Icon name="info"/><span>{t('passkeys.unsupported')}</span></div>}
  <div className="passkey-list">{rows.map(row=><article className="passkey-row" key={row.id}>
   <div className="passkey-main"><div className="passkey-title"><Icon name="key"/><strong>{row.name}</strong>{row.backed_up&&<span className="security-session-badge">{t('passkeys.backup')}</span>}</div><div className="passkey-meta"><span>{t('passkeys.createdAt')}: {formatDate(row.created_at,i18n.language)||'–'}</span><span>{t('passkeys.lastUsed')}: {formatDate(row.last_used_at,i18n.language)||t('passkeys.neverUsed')}</span></div></div>
   {editId===row.id?<form className="passkey-rename" onSubmit={event=>saveRename(event,row)}><label>{t('passkeys.nameLabel')}<input value={editName} maxLength={120} onChange={event=>setEditName(event.target.value)} autoFocus required/></label><div><button className="primary compact" disabled={busy}>{t('passkeys.saveName')}</button><button className="secondary compact" type="button" onClick={()=>setEditId('')} disabled={busy}>{t('passkeys.cancel')}</button></div></form>:<div className="passkey-actions"><button className="secondary compact" type="button" onClick={()=>{setEditId(row.id);setEditName(row.name)}} disabled={busy}><Icon name="edit"/> {t('passkeys.rename')}</button><button className="ghost-danger compact" type="button" onClick={()=>remove(row)} disabled={busy}><Icon name="delete"/> {t('passkeys.remove')}</button></div>}
  </article>)}{!rows.length&&<div className="security-session-empty">{t('passkeys.empty')}</div>}</div>
  <form className="passkey-add" onSubmit={add}><div><label>{t('passkeys.nameLabel')}<input value={name} maxLength={120} placeholder={t('passkeys.namePlaceholder')} onChange={event=>setName(event.target.value)} required disabled={!supported||busy}/></label><small>{t('passkeys.addHint')}</small></div><button className="primary" disabled={!supported||busy||!name.trim()}><Icon name="plus"/> {t('passkeys.add')}</button></form>
  {reauthOpen&&<section className="security-reauth" aria-live="polite"><div><h3>{t('passkeys.reauthTitle')}</h3><p>{t('passkeys.reauthText')}</p></div>{supported&&rows.length>0&&<button className="primary" type="button" onClick={confirmPasskey} disabled={reauthBusy}><Icon name="key"/> {t('passkeys.reauthPasskey')}</button>}<form onSubmit={confirmPassword}><label>{t('passkeys.passwordLabel')}<input type="password" autoComplete="current-password" value={password} onChange={event=>setPassword(event.target.value)} required/></label><div className="security-reauth-actions"><button className="secondary" disabled={reauthBusy}>{t('passkeys.confirmPassword')}</button><button className="text-button" type="button" onClick={()=>{setReauthOpen(false);setPending(null);setPassword('')}} disabled={reauthBusy}>{t('passkeys.cancel')}</button></div></form></section>}
  <div className="security-privacy-note"><Icon name="info"/><span>{t('passkeys.privacy')}</span></div>
 </section>;
}
