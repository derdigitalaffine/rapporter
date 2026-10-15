import {useEffect,useId,useRef,useState} from 'react';
import {useTranslation} from 'react-i18next';
import {api} from './api';
import OverlayPortal from './OverlayPortal';
import {confirmAction} from './feedback';
import {isPasskeySupported,reauthenticateWithPasskey,isPasskeyCancellation} from './passkey-api';
import {calendarSubscriptionLabels} from './calendar-subscriptions-i18n';
import './calendar-subscriptions.css';

export default function CalendarSubscriptions({familyId,settings=false}){
 const {i18n}=useTranslation(),labels=calendarSubscriptionLabels[i18n.language.split('-')[0]]||calendarSubscriptionLabels.en;
 const [open,setOpen]=useState(false);
 if(!familyId)return null;
 const button=<button type="button" className="secondary calendar-subscription-launch" onClick={()=>setOpen(true)}>{labels.open}</button>;
 return <>{settings?<section className="card settings-section" id="calendar-subscriptions"><div><h2>{labels.title}</h2><p>{labels.intro}</p></div>{button}</section>:button}{open&&<SubscriptionDialog key={familyId} familyId={familyId} labels={labels} language={i18n.language} close={()=>setOpen(false)}/>}</>;
}

function SubscriptionDialog({familyId,labels:t,language,close}){
 const linkId=useId();
 const dialog=useRef(null),alive=useRef(true),pending=useRef(null);
 const [rows,setRows]=useState([]),[loading,setLoading]=useState(true),[configured,setConfigured]=useState(true),[restricted,setRestricted]=useState(false);
 const [name,setName]=useState(''),[secret,setSecret]=useState(null),[busy,setBusy]=useState(false),[error,setError]=useState(''),[copied,setCopied]=useState(false),[reauth,setReauth]=useState(false),[password,setPassword]=useState('');
 const path=`/calendar-subscriptions/${encodeURIComponent(familyId)}/`;
 async function load(){try{const data=await api(path);if(alive.current){setRows(data.subscriptions);setConfigured(data.configured)}}catch(e){if(alive.current){setRestricted(e.status===403);setError(navigator.onLine?t.error:t.offline)}}finally{if(alive.current)setLoading(false)}}
 useEffect(()=>{alive.current=true;load();const previous=document.activeElement;dialog.current?.querySelector('.sheet-close')?.focus();const key=e=>{if(document.querySelector('[role="alertdialog"]'))return;if(e.key==='Escape'){e.preventDefault();close()}if(e.key==='Tab'){const elements=[...dialog.current.querySelectorAll('button:not(:disabled),a[href],input:not(:disabled),textarea,summary')].filter(node=>node.getClientRects().length);const first=elements[0],last=elements.at(-1);if(e.shiftKey&&document.activeElement===first){e.preventDefault();last?.focus()}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first?.focus()}}};document.addEventListener('keydown',key);return()=>{alive.current=false;pending.current=null;document.removeEventListener('keydown',key);previous?.focus?.()}},[familyId]);
 async function execute(action,confirmed=false){
  setBusy(true);setError('');setCopied(false);
  try{
   if(action.type==='create'){
    const value=await api(path,{method:'POST',body:JSON.stringify({name:action.name})});if(!alive.current)return;setSecret(value);setName('');
   }else if(action.type==='revoke'){
    await api(`${path}${action.id}/`,{method:'DELETE'});if(!alive.current)return;if(secret?.id===action.id)setSecret(null);
   }else{
    const value=await api(`${path}${action.id}/${action.type==='profile'?'reveal':action.type}/`,{method:'POST'});if(!alive.current)return;
    if(action.type==='profile'){
     // Native HTTPS response/MIME allows Safari to offer profile installation.
     // Reauth preflight avoids navigating to a JSON error after freshness expiry.
     window.location.assign(`${import.meta.env.VITE_API_BASE||'/api'}${path}${action.id}/profile/`);
    }else setSecret(value);
   }
   if(alive.current){setReauth(false);pending.current=null;await load()}
  }catch(e){if(alive.current){if(e.status===403&&e.code==='reauth_required'&&!confirmed){pending.current=action;setReauth(true)}else setError(navigator.onLine?t.error:t.offline)}}
  finally{if(alive.current)setBusy(false)}
 }
 async function reauthenticate(event,passkey=false){event?.preventDefault();setBusy(true);setError('');try{if(passkey)await reauthenticateWithPasskey();else await api('/auth/reauth/password/',{method:'POST',body:JSON.stringify({password})});if(!alive.current)return;setPassword('');setReauth(false);const action=pending.current;if(action)await execute(action,true)}catch(e){if(alive.current&&!isPasskeyCancellation(e))setError(t.error)}finally{if(alive.current)setBusy(false)}}
 async function change(type,row){if(!await confirmAction({title:t[type==='revoke'?'revoke':'rotate'],message:t[type==='revoke'?'revokeConfirm':'rotateConfirm'],confirmLabel:t[type==='revoke'?'revoke':'rotate'],cancelLabel:t.cancel,danger:true}))return;if(alive.current)await execute({type,id:row.id})}
 return <OverlayPortal><div className="sheet-backdrop" onMouseDown={e=>{if(e.currentTarget===e.target)close()}}><section ref={dialog} className="quick-sheet calendar-subscription-sheet" role="dialog" aria-modal="true" aria-labelledby="calendar-subscription-title"><div className="sheet-head"><h2 id="calendar-subscription-title">{t.title}</h2><button className="sheet-close" type="button" aria-label={t.close} onClick={close}>×</button></div><div className="calendar-subscription-content">
  <p>{t.intro}</p><p className="calendar-subscription-note">{t.scope}</p><p className="calendar-subscription-risk">{t.risk}</p>
  {loading?<p role="status">{t.loading}</p>:restricted?<p role="alert">{t.restricted}</p>:<>
   {!configured&&<p role="alert">{t.unconfigured}</p>}
   {error&&<p role="alert" className="error">{error}</p>}
   {reauth&&<form className="calendar-subscription-reauth" onSubmit={reauthenticate}><h3>{t.reauth}</h3><p>{t.reauthHint}</p>{isPasskeySupported()&&<button className="secondary" type="button" disabled={busy} onClick={()=>reauthenticate(null,true)}>{t.passkey}</button>}<label>{t.accountPassword}<input autoFocus type="password" autoComplete="current-password" value={password} onChange={e=>setPassword(e.target.value)} required/></label><div className="form-actions"><button className="primary" disabled={busy||!password}>{t.confirm}</button><button type="button" className="secondary" disabled={busy} onClick={()=>{pending.current=null;setReauth(false);setPassword('')}}>{t.cancel}</button></div></form>}
   <form className="calendar-subscription-create" onSubmit={e=>{e.preventDefault();if(name.trim())execute({type:'create',name:name.trim()})}}><label>{t.name}<input value={name} onChange={e=>setName(e.target.value)} maxLength={80} required disabled={busy||!configured}/></label><button className="primary" disabled={busy||!configured||!name.trim()}>{t.create}</button></form>
   {!rows.length&&<p>{t.empty}</p>}
   <ul className="calendar-subscription-list">{rows.map(row=><li key={row.id}><div><strong>{row.name}</strong><small>{t.lastUsed}: {row.last_used_at?new Date(row.last_used_at).toLocaleString(language):t.never}</small></div><div className="form-actions"><button type="button" className="secondary" disabled={busy} onClick={()=>{setSecret(null);execute({type:'reveal',id:row.id})}}>{t.show}</button><button type="button" className="secondary" disabled={busy} onClick={()=>change('rotate',row)}>{t.rotate}</button><button type="button" className="secondary ghost-danger" disabled={busy} onClick={()=>change('revoke',row)}>{t.revoke}</button></div></li>)}</ul>
   {secret&&<section className="calendar-subscription-access" aria-label={secret.name}><h3>{secret.name}</h3><label htmlFor={linkId}>{t.link}</label><textarea id={linkId} autoComplete="off" readOnly rows={3} value={secret.subscription_url} onFocus={e=>e.target.select()}/><div className="form-actions"><button type="button" className="secondary" disabled={busy} onClick={async()=>{try{await navigator.clipboard.writeText(secret.subscription_url);if(alive.current)setCopied(true)}catch{setError(t.error)}}}>{t.copy}</button><a className="primary button" href={secret.webcal_url} rel="noreferrer">{t.subscribe}</a></div>{copied&&<p role="status">{t.copied}</p>}<p className="calendar-subscription-note">{t.refresh}</p><div className="calendar-subscription-profile"><button className="secondary" type="button" disabled={busy} onClick={()=>execute({type:'profile',id:secret.id})}>{t.profile}</button><p>{t.profileHint}</p></div><details><summary>{t.manual}</summary>{[['server','caldav_url'],['username','username'],['password','password']].map(([label,key])=><label key={key}>{t[label]}<input readOnly value={secret[key]} onFocus={e=>e.target.select()}/></label>)}</details><button type="button" className="secondary" onClick={()=>setSecret(null)}>{t.hide}</button></section>}
  </>}
 </div></section></div></OverlayPortal>;
}
