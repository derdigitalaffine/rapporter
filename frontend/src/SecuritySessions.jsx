import {useEffect,useMemo,useState} from 'react';
import {useTranslation} from 'react-i18next';
import {api} from './api';
import {Icon} from './icons';
import {toast} from './feedback';
import './security-sessions-i18n';
import './security-sessions.css';

function formatDate(value,language){
 if(!value)return '–';
 const date=new Date(value);if(Number.isNaN(date.getTime()))return '–';
 return new Intl.DateTimeFormat(language||'de',{dateStyle:'medium',timeStyle:'short'}).format(date);
}

export default function SecuritySessions(){
 const {t,i18n}=useTranslation();
 const [sessions,setSessions]=useState([]);const [fresh,setFresh]=useState(false);const [loading,setLoading]=useState(true);const [loadError,setLoadError]=useState(false);
 const [busySid,setBusySid]=useState('');const [revokeOthersBusy,setRevokeOthersBusy]=useState(false);const [reauthOpen,setReauthOpen]=useState(false);const [reauthBusy,setReauthBusy]=useState(false);const [password,setPassword]=useState('');
 const others=useMemo(()=>sessions.filter(item=>!item.current),[sessions]);
 async function load(){setLoading(true);setLoadError(false);try{const data=await api('/auth/sessions/');setSessions(data.sessions||[]);setFresh(Boolean(data.fresh))}catch{setLoadError(true)}finally{setLoading(false)}}
 useEffect(()=>{load()},[]);
 async function revoke(sid){setBusySid(sid);try{await api(`/auth/sessions/${sid}/`,{method:'DELETE'});setSessions(rows=>rows.filter(item=>item.id!==sid));toast(t('securitySessions.revoked'),{type:'success'})}catch(e){toast(e.message||t('securitySessions.revokeFailed'),{type:'error'})}finally{setBusySid('')}}
 async function revokeOthers({afterReauth=false}={}){setRevokeOthersBusy(true);try{await api('/auth/sessions/revoke-others/',{method:'POST',body:'{}'});setSessions(rows=>rows.filter(item=>item.current));setFresh(true);setReauthOpen(false);toast(t('securitySessions.revokeOthersDone'),{type:'success'})}catch(e){if(e.status===403&&!afterReauth){setFresh(false);setReauthOpen(true)}else toast(e.message||t('securitySessions.revokeFailed'),{type:'error'})}finally{setRevokeOthersBusy(false)}}
 async function confirmIdentity(event){event.preventDefault();if(!password)return;setReauthBusy(true);try{await api('/auth/reauth/password/',{method:'POST',body:JSON.stringify({password})});setFresh(true);setPassword('');toast(t('securitySessions.confirmed'),{type:'success'});await revokeOthers({afterReauth:true})}catch(e){toast(e.message||t('securitySessions.reauthFailed'),{type:'error'})}finally{setReauthBusy(false)}}
 if(loading)return <section className="card security-sessions-card" aria-busy="true"><div className="smart-empty"><Icon name="refresh" size={26}/><strong>{t('securitySessions.loading')}</strong></div></section>;
 if(loadError)return <section className="card security-sessions-card"><div className="smart-empty"><Icon name="warning" size={26}/><strong>{t('securitySessions.loadFailed')}</strong><button className="secondary" type="button" onClick={load}>{t('securitySessions.retry')}</button></div></section>;
 return <section className="card security-sessions-card" data-testid="security-sessions"><div className="security-sessions-head"><div><small>{t('securitySessions.eyebrow')}</small><h2>{t('securitySessions.title')}</h2><p>{t('securitySessions.intro')}</p></div><div className="security-sessions-status"><Icon name={fresh?'check':'lock'} size={14}/><span>{t(fresh?'securitySessions.fresh':'securitySessions.stale')}</span></div></div>
  <div className="security-session-list">{sessions.map(item=><article key={item.id} className={`security-session-row${item.current?' current':''}`}><div className="security-session-main"><div className="security-session-title"><Icon name="user"/><strong>{item.client}</strong><span className="security-session-badge">{t(item.current?'securitySessions.current':'securitySessions.other')}</span></div><div className="security-session-meta"><span><Icon name="clock" size={13}/>{t('securitySessions.lastSeen')}: {formatDate(item.last_seen_at,i18n.language)}</span><span>{t('securitySessions.created')}: {formatDate(item.created_at,i18n.language)}</span><span>{t('securitySessions.method')}: {t(`securitySessions.${item.auth_method||'password'}`)}</span></div></div>{!item.current&&<button className="ghost-danger compact" type="button" onClick={()=>revoke(item.id)} disabled={busySid===item.id}><Icon name="logout"/> {t('securitySessions.revoke')}</button>}</article>)}{others.length===0&&<div className="security-session-empty">{t('securitySessions.noOthers')}</div>}</div>
  <div className="security-sessions-actions"><div><button className="secondary" type="button" onClick={()=>revokeOthers()} disabled={!others.length||revokeOthersBusy}><Icon name="logout"/> {t('securitySessions.revokeOthers')}</button><p>{t('securitySessions.revokeOthersHint')}</p></div></div>
  {reauthOpen&&<form className="security-reauth" onSubmit={confirmIdentity}><div><h3>{t('securitySessions.reauthTitle')}</h3><p>{t('securitySessions.reauthText')}</p></div><label>{t('securitySessions.passwordLabel')}<input type="password" autoComplete="current-password" value={password} onChange={event=>setPassword(event.target.value)} required autoFocus/></label><div className="security-reauth-actions"><button className="primary" disabled={reauthBusy}>{t('securitySessions.confirm')}</button><button className="secondary" type="button" onClick={()=>{setReauthOpen(false);setPassword('')}} disabled={reauthBusy}>{t('securitySessions.cancel')}</button></div></form>}
  <div className="security-privacy-note"><Icon name="info"/><span>{t('securitySessions.privacy')}</span></div>
 </section>;
}
