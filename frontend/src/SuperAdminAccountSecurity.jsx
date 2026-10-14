import {useEffect,useState} from 'react';
import {adminApi} from './superadmin-api';
import {Icon} from './icons';
import {toast} from './feedback';
import './superadmin-account-security.css';

const webAuthnAvailable=()=>typeof window!=='undefined'&&Boolean(window.PublicKeyCredential)&&Boolean(navigator.credentials?.create)&&Boolean(navigator.credentials?.get);

function decodeBase64Url(value){
 const normalized=String(value||'').replace(/-/g,'+').replace(/_/g,'/');
 const padded=normalized+'='.repeat((4-normalized.length%4)%4);
 const binary=atob(padded);
 return Uint8Array.from(binary,char=>char.charCodeAt(0));
}

function encodeBase64Url(value){
 if(value===null||value===undefined)return null;
 const bytes=value instanceof ArrayBuffer?new Uint8Array(value):new Uint8Array(value.buffer,value.byteOffset,value.byteLength);
 let binary='';
 for(const byte of bytes)binary+=String.fromCharCode(byte);
 return btoa(binary).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'');
}

function registrationOptions(options={}){
 return {
  ...options,
  challenge:decodeBase64Url(options.challenge),
  user:{...options.user,id:decodeBase64Url(options.user?.id)},
  excludeCredentials:(options.excludeCredentials||[]).map(item=>({...item,id:decodeBase64Url(item.id)})),
 };
}

function authenticationOptions(options={}){
 return {
  ...options,
  challenge:decodeBase64Url(options.challenge),
  allowCredentials:(options.allowCredentials||[]).map(item=>({...item,id:decodeBase64Url(item.id)})),
 };
}

function registrationCredential(credential){
 const response=credential.response;
 return {
  id:credential.id,
  rawId:encodeBase64Url(credential.rawId),
  type:credential.type,
  authenticatorAttachment:credential.authenticatorAttachment||undefined,
  clientExtensionResults:credential.getClientExtensionResults?.()||{},
  response:{
   clientDataJSON:encodeBase64Url(response.clientDataJSON),
   attestationObject:encodeBase64Url(response.attestationObject),
   transports:response.getTransports?.()||[],
  },
 };
}

function authenticationCredential(credential){
 const response=credential.response;
 return {
  id:credential.id,
  rawId:encodeBase64Url(credential.rawId),
  type:credential.type,
  authenticatorAttachment:credential.authenticatorAttachment||undefined,
  clientExtensionResults:credential.getClientExtensionResults?.()||{},
  response:{
   clientDataJSON:encodeBase64Url(response.clientDataJSON),
   authenticatorData:encodeBase64Url(response.authenticatorData),
   signature:encodeBase64Url(response.signature),
   userHandle:encodeBase64Url(response.userHandle),
  },
 };
}

function ceremonyError(error){
 if(error?.name==='NotAllowedError')return 'Der Passkey-Vorgang wurde abgebrochen oder ist abgelaufen.';
 if(error?.name==='InvalidStateError')return 'Dieser Passkey ist bereits für die Superadmin-App registriert.';
 if(error?.name==='SecurityError')return 'Passkeys sind für diese Origin nicht verfügbar.';
 return error?.message||'Passkey-Vorgang fehlgeschlagen.';
}

async function createPasskey(name){
 if(!webAuthnAvailable())throw new Error('Dieser Browser unterstützt die benötigte Passkey-Funktion nicht.');
 const start=await adminApi('/auth/passkeys/register/options/',{method:'POST',body:'{}'});
 const credential=await navigator.credentials.create({publicKey:registrationOptions(start.options)});
 if(!credential)throw new Error('Es wurde kein Passkey erstellt.');
 return adminApi('/auth/passkeys/register/verify/',{
  method:'POST',
  body:JSON.stringify({challenge_id:start.challenge_id,credential:registrationCredential(credential),name}),
 });
}

async function reauthenticateWithPasskey(){
 if(!webAuthnAvailable())throw new Error('Dieser Browser unterstützt die benötigte Passkey-Funktion nicht.');
 const start=await adminApi('/auth/reauth/passkey/options/',{method:'POST',body:'{}'});
 const credential=await navigator.credentials.get({publicKey:authenticationOptions(start.options)});
 if(!credential)throw new Error('Es wurde kein Passkey verwendet.');
 return adminApi('/auth/reauth/passkey/verify/',{
  method:'POST',
  body:JSON.stringify({challenge_id:start.challenge_id,credential:authenticationCredential(credential)}),
 });
}

function formatDate(value){
 if(!value)return 'Noch nie';
 const date=new Date(value);
 return Number.isNaN(date.getTime())?'—':new Intl.DateTimeFormat(undefined,{dateStyle:'medium',timeStyle:'short'}).format(date);
}

export default function SuperAdminAccountSecurity({fresh,onChanged}){
 const [passkeys,setPasskeys]=useState([]);
 const [names,setNames]=useState({});
 const [loading,setLoading]=useState(true);
 const [busy,setBusy]=useState('');
 const [registerName,setRegisterName]=useState('');
 const [removeCandidate,setRemoveCandidate]=useState('');
 const [newPassword,setNewPassword]=useState('');
 const [confirmPassword,setConfirmPassword]=useState('');
 const [reauthOpen,setReauthOpen]=useState(false);
 const [reauthPassword,setReauthPassword]=useState('');
 const [pendingAction,setPendingAction]=useState(null);
 const supportsPasskeys=webAuthnAvailable();

 async function loadPasskeys(){
  setLoading(true);
  try{
   const data=await adminApi('/auth/passkeys/');
   const items=data?.results||[];
   setPasskeys(items);
   setNames(Object.fromEntries(items.map(item=>[item.id,item.name||'Passkey'])));
  }catch(error){toast(error.message||'Superadmin-Passkeys konnten nicht geladen werden.',{type:'error'})}
  finally{setLoading(false)}
 }
 useEffect(()=>{loadPasskeys()},[]);

 async function refreshSecurity(){
  await loadPasskeys();
  await onChanged?.();
 }

 async function runSensitive(action){
  try{return await action()}catch(error){
   if(error.status===403&&error.code==='reauth_required'){
    setPendingAction(()=>action);
    setReauthOpen(true);
    return null;
   }
   throw error;
  }
 }

 async function resumeAfterReauth(){
  const action=pendingAction;
  setPendingAction(null);
  setReauthOpen(false);
  setReauthPassword('');
  await onChanged?.();
  if(action)await action();
 }

 async function confirmPasswordReauth(event){
  event.preventDefault();
  if(!reauthPassword)return;
  setBusy('reauth-password');
  try{
   await adminApi('/auth/reauth/password/',{method:'POST',body:JSON.stringify({password:reauthPassword})});
   toast('Superadmin-Identität bestätigt.',{type:'success'});
   await resumeAfterReauth();
  }catch(error){toast(error.message||'Bestätigung fehlgeschlagen.',{type:'error'})}
  finally{setBusy('')}
 }

 async function confirmPasskeyReauth(){
  setBusy('reauth-passkey');
  try{
   await reauthenticateWithPasskey();
   toast('Superadmin-Identität mit Passkey bestätigt.',{type:'success'});
   await resumeAfterReauth();
  }catch(error){toast(ceremonyError(error),{type:'error'})}
  finally{setBusy('')}
 }

 function cancelReauth(){
  setPendingAction(null);
  setReauthOpen(false);
  setReauthPassword('');
 }

 async function register(event){
  event.preventDefault();
  const name=registerName.trim()||'Superadmin Passkey';
  const action=async()=>{
   setBusy('register');
   try{
    await createPasskey(name);
    setRegisterName('');
    await refreshSecurity();
    toast('Superadmin-Passkey registriert.',{type:'success'});
   }finally{setBusy('')}
  };
  try{await runSensitive(action)}catch(error){toast(ceremonyError(error),{type:'error'})}
 }

 async function rename(item){
  const name=String(names[item.id]||'').trim();
  if(!name||name===item.name)return;
  const action=async()=>{
   setBusy(`rename:${item.id}`);
   try{
    await adminApi(`/auth/passkeys/${item.id}/`,{method:'PATCH',body:JSON.stringify({name})});
    await refreshSecurity();
    toast('Passkey umbenannt.',{type:'success'});
   }finally{setBusy('')}
  };
  try{await runSensitive(action)}catch(error){toast(error.message||'Passkey konnte nicht umbenannt werden.',{type:'error'})}
 }

 async function remove(item){
  const action=async()=>{
   setBusy(`remove:${item.id}`);
   try{
    await adminApi(`/auth/passkeys/${item.id}/`,{method:'DELETE'});
    setRemoveCandidate('');
    await refreshSecurity();
    toast('Superadmin-Passkey entfernt.',{type:'success'});
   }finally{setBusy('')}
  };
  try{await runSensitive(action)}catch(error){toast(error.message||'Passkey konnte nicht entfernt werden.',{type:'error'})}
 }

 async function changePassword(event){
  event.preventDefault();
  if(!newPassword||newPassword!==confirmPassword)return;
  const password=newPassword;
  const confirmation=confirmPassword;
  const action=async()=>{
   setBusy('password');
   try{
    await adminApi('/auth/password/',{method:'PUT',body:JSON.stringify({new_password:password,confirm_password:confirmation})});
    setNewPassword('');
    setConfirmPassword('');
    await onChanged?.();
    toast('Superadmin-Passwort geändert. Andere Admin-Sitzungen wurden beendet.',{type:'success'});
   }finally{setBusy('')}
  };
  try{await runSensitive(action)}catch(error){toast(error.message||'Passwort konnte nicht geändert werden.',{type:'error'})}
 }

 return <section className="card admin-account-security" aria-labelledby="admin-account-security-title">
  <div className="superadmin-list-head admin-account-security-head"><div><small>Credential Management</small><h2 id="admin-account-security-title">Superadmin-Zugang</h2><p>Passkeys und Passwort gelten hier für die getrennte Superadmin-Sicherheitsoberfläche.</p></div><span className={`tenant-status ${fresh?'active':'suspended'}`}>{fresh?'Fresh':'Bestätigung nötig'}</span></div>
  {reauthOpen&&<div className="admin-account-reauth" role="region" aria-labelledby="admin-account-reauth-title"><div><strong id="admin-account-reauth-title">Identität erneut bestätigen</strong><span>Nur die getrennte Superadmin-Sitzung wird erneuert.</span></div><form onSubmit={confirmPasswordReauth}><label>Aktuelles Superadmin-Passwort<input type="password" autoComplete="current-password" value={reauthPassword} onChange={event=>setReauthPassword(event.target.value)} required autoFocus/></label><div className="superadmin-actions"><button className="primary" disabled={Boolean(busy)}><Icon name="lock"/>{busy==='reauth-password'?'Wird bestätigt …':'Mit Passwort bestätigen'}</button>{supportsPasskeys&&passkeys.length>0&&<button className="secondary" type="button" onClick={confirmPasskeyReauth} disabled={Boolean(busy)}><Icon name="lock"/>{busy==='reauth-passkey'?'Passkey wird geprüft …':'Mit Passkey bestätigen'}</button>}<button className="ghost" type="button" onClick={cancelReauth} disabled={Boolean(busy)}>Abbrechen</button></div></form></div>}
  <div className="admin-account-security-grid">
   <section className="admin-account-panel" aria-labelledby="admin-passkeys-title"><div className="admin-account-panel-head"><div><small>Phishing-resistent</small><h3 id="admin-passkeys-title">Superadmin-Passkeys</h3></div><span className="superadmin-count">{passkeys.length}</span></div><p>Diese Passkeys sind ausschließlich der Superadmin-Surface zugeordnet und werden nicht als FamilyOS-App-Passkeys verwendet.</p>{supportsPasskeys?<form className="admin-passkey-register" onSubmit={register}><label>Bezeichnung<input value={registerName} onChange={event=>setRegisterName(event.target.value)} placeholder="z. B. MacBook Touch ID" maxLength="120"/></label><button className="primary" disabled={Boolean(busy)}><Icon name="lock"/>{busy==='register'?'Wird registriert …':'Passkey hinzufügen'}</button></form>:<div className="admin-notice warning" role="status"><Icon name="info"/><div><strong>Passkeys nicht verfügbar</strong><span>Dieser Browser stellt die benötigte WebAuthn-Funktion nicht bereit.</span></div></div>}
    <div className="admin-passkey-list" aria-busy={loading}>{passkeys.map(item=><article className="admin-passkey-row" key={item.id}><div className="admin-passkey-meta"><strong>{item.name||'Passkey'}</strong><span>{item.backed_up?'Synchronisiert':'Gerätegebunden'} · erstellt {formatDate(item.created_at)} · zuletzt {formatDate(item.last_used_at)}</span></div><label className="admin-passkey-name"><span className="sr-only">Bezeichnung für {item.name||'Passkey'}</span><input value={names[item.id]??item.name??''} onChange={event=>setNames(current=>({...current,[item.id]:event.target.value}))} maxLength="120"/></label><div className="admin-passkey-actions"><button className="secondary" type="button" onClick={()=>rename(item)} disabled={Boolean(busy)||!String(names[item.id]||'').trim()||names[item.id]===item.name}>Speichern</button>{removeCandidate===item.id?<><button className="ghost-danger" type="button" onClick={()=>remove(item)} disabled={Boolean(busy)}>{busy===`remove:${item.id}`?'Wird entfernt …':'Entfernen bestätigen'}</button><button className="ghost" type="button" onClick={()=>setRemoveCandidate('')} disabled={Boolean(busy)}>Abbrechen</button></>:<button className="ghost-danger" type="button" onClick={()=>setRemoveCandidate(item.id)} disabled={Boolean(busy)}>Entfernen</button>}</div></article>)}{!loading&&!passkeys.length&&<div className="smart-empty"><strong>Noch kein Superadmin-Passkey</strong><span>Das Passwort bleibt verfügbar. Für sensible Admin-Aktionen kann anschließend ein Passkey zur Bestätigung verwendet werden.</span></div>}</div>
   </section>
   <section className="admin-account-panel" aria-labelledby="admin-password-title"><div className="admin-account-panel-head"><div><small>Fallback & Recovery</small><h3 id="admin-password-title">Superadmin-Passwort</h3></div></div><p>Eine Änderung beendet nur andere Superadmin-Sitzungen. Sitzungen der normalen FamilyOS-App bleiben unangetastet.</p><form className="admin-password-form" onSubmit={changePassword}><label>Neues Passwort<input type="password" autoComplete="new-password" value={newPassword} onChange={event=>setNewPassword(event.target.value)} required/></label><label>Neues Passwort wiederholen<input type="password" autoComplete="new-password" value={confirmPassword} onChange={event=>setConfirmPassword(event.target.value)} required aria-invalid={Boolean(confirmPassword&&newPassword!==confirmPassword)}/>{confirmPassword&&newPassword!==confirmPassword&&<small className="admin-field-error">Die Passwörter stimmen nicht überein.</small>}</label><button className="primary" disabled={Boolean(busy)||!newPassword||newPassword!==confirmPassword}><Icon name="lock"/>{busy==='password'?'Wird geändert …':'Passwort ändern'}</button></form><div className="admin-account-boundary" role="note"><Icon name="info"/><div><strong>Getrennte Sicherheitsdomäne</strong><span>Diese Verwaltung verwendet ausschließlich <code>/api/superadmin/auth/…</code>. Normale App-Sessions, App-Passkeys und App-Challenges werden nicht verändert.</span></div></div></section>
  </div>
 </section>;
}
