import {switchAppLanguage as switchLanguage} from './language-options';
import {useEffect,useState} from 'react';
import {useTranslation} from 'react-i18next';
import App from './App';
import ProductAnalyticsBridge from './ProductAnalyticsBridge';
import {AUTH_CHANGED_EVENT,isAuthenticated,login} from './api';
import {requestPasswordReset} from './password-reset-api';
import {isPasskeyCancellation,isPasskeySupported,loginWithPasskey} from './passkey-api';
import {Icon} from './icons';
import './session-i18n';
import './passkey-i18n';
import './passkey-login.css';

function Card({children,className=''}){return <section className={`card ${className}`}>{children}</section>}
function initialRecoveryMode(){return new URLSearchParams(window.location.search).get('password-reset')==='1'}

export default function LoginGate(){
 const {t,i18n}=useTranslation();
 const [authed,setAuthed]=useState(isAuthenticated());
 const [expired,setExpired]=useState(false);
 const [legacy,setLegacy]=useState(false);
 const [identifier,setIdentifier]=useState('');
 const [password,setPassword]=useState('');
 const [error,setError]=useState(false);
 const [passkeyError,setPasskeyError]=useState('');
 const [busy,setBusy]=useState(false);
 const [recovery,setRecovery]=useState(initialRecoveryMode);
 const [recoveryEmail,setRecoveryEmail]=useState('');
 const [recoverySent,setRecoverySent]=useState(false);
 const [recoveryError,setRecoveryError]=useState('');
 const passkeySupported=isPasskeySupported();
 useEffect(()=>{
  const authChanged=event=>setAuthed(Boolean(event.detail?.authenticated));
  const sessionExpired=()=>{setExpired(true);setAuthed(false)};
  window.addEventListener(AUTH_CHANGED_EVENT,authChanged);
  window.addEventListener('famuhle:session-expired',sessionExpired);
  return()=>{window.removeEventListener(AUTH_CHANGED_EVENT,authChanged);window.removeEventListener('famuhle:session-expired',sessionExpired)};
 },[]);
 if(authed)return <><ProductAnalyticsBridge/><App/></>;
 async function submit(event){event.preventDefault();setError(false);setPasskeyError('');setBusy(true);try{await login(identifier,password,{legacy});setExpired(false);setAuthed(true)}catch{setError(true)}finally{setBusy(false)}}
 async function submitPasskey(){setError(false);setPasskeyError('');setBusy(true);try{await loginWithPasskey();setExpired(false);setAuthed(true)}catch(err){if(isPasskeyCancellation(err))setPasskeyError('cancelled');else if(err?.status===503)setPasskeyError('unavailable');else if(err?.status===429)setPasskeyError('rateLimited');else setPasskeyError('failed')}finally{setBusy(false)}}
 function toggleMode(){setLegacy(value=>!value);setIdentifier('');setError(false);setPasskeyError('')}
 function openRecovery(){setRecoveryEmail(legacy?'':identifier);setRecoverySent(false);setRecoveryError('');setRecovery(true);window.history.replaceState(window.history.state,'','/?password-reset=1')}
 function closeRecovery(){setRecovery(false);setRecoverySent(false);setRecoveryError('');window.history.replaceState(window.history.state,'','/')}
 async function submitRecovery(event){event.preventDefault();setRecoveryError('');setBusy(true);try{await requestPasswordReset(recoveryEmail,i18n.language);setRecoverySent(true)}catch(err){setRecoveryError(err?.status===429?'rate_limited':'failed')}finally{setBusy(false)}}
 if(recovery)return <main className="login-shell"><img className="brand-wide" src="/brand/logo-primary.svg" alt="FamilyOS"/><Card className="login-card"><h1>{t('identityUi.resetRequestTitle')}</h1><p>{t('identityUi.resetRequestIntro')}</p>{recoverySent?<div className="integration-notice" role="status"><Icon name="info"/><div><strong>{t('identityUi.resetRequestSuccessTitle')}</strong><span>{t('identityUi.resetRequestSuccess')}</span></div></div>:<form onSubmit={submitRecovery}><label>{t('identityUi.emailLabel')}<input type="email" value={recoveryEmail} onChange={event=>setRecoveryEmail(event.target.value)} autoComplete="email" required autoFocus/></label>{recoveryError&&<p className="error" role="alert">{t(recoveryError==='rate_limited'?'identityUi.resetRateLimited':'identityUi.resetRequestFailed')}</p>}<button className="primary" type="submit" disabled={busy}>{busy?t('pleaseWait'):t('identityUi.resetRequestAction')}</button></form>}<button className="secondary" type="button" onClick={closeRecovery}>{t('identityUi.backToLogin')}</button><button className="text-button" type="button" onClick={()=>switchLanguage(i18n)}><Icon name="language"/> Deutsch · English · Français · Nederlands · ไทย</button></Card></main>;
 return <main className="login-shell"><img className="brand-wide" src="/brand/logo-primary.svg" alt="FamilyOS"/><Card className="login-card">{expired&&<div className="integration-notice" role="status"><Icon name="info"/><div><strong>{t('sessionUi.expiredTitle')}</strong><span>{t('sessionUi.expiredMessage')}</span></div></div>}<h1>{t('login')}</h1><button className="secondary compact" type="button" onClick={toggleMode}>{legacy?t('identityUi.normalAccount'):t('identityUi.migrationAccount')}</button>{legacy&&<p>{t('identityUi.legacyHint')}</p>}{!legacy&&<div className="login-passkey">{passkeySupported?<><button className="primary" type="button" onClick={submitPasskey} disabled={busy}><Icon name="key"/> {busy?t('pleaseWait'):t('passkeys.loginAction')}</button><small>{t('passkeys.loginHint')}</small></>:<div className="integration-notice" role="status"><Icon name="info"/><span>{t('passkeys.unsupported')}</span></div>}{passkeyError&&<p className={passkeyError==='cancelled'?'login-passkey-status':'error'} role={passkeyError==='cancelled'?'status':'alert'}>{t(`passkeys.${passkeyError}`)}</p>}<div className="login-divider" aria-hidden="true"><span/></div></div>}<form onSubmit={submit}><label>{legacy?t('identityUi.legacyUsername'):t('identityUi.emailLabel')}<input type={legacy?'text':'email'} value={identifier} onChange={event=>setIdentifier(event.target.value)} autoComplete={legacy?'username':'email'} required autoFocus/></label><label>{t('password')}<input type="password" value={password} onChange={event=>setPassword(event.target.value)} autoComplete="current-password" required/></label>{error&&<p className="error" role="alert">{t('loginFailed')}</p>}<button className="secondary" type="submit" disabled={busy}>{busy?t('pleaseWait'):t('login')}</button></form>{!legacy&&<button className="text-button" type="button" onClick={openRecovery}>{t('identityUi.forgotPassword')}</button>}<button className="text-button" type="button" onClick={()=>switchLanguage(i18n)}><Icon name="language"/> Deutsch · English · Français · Nederlands · ไทย</button></Card></main>
}
