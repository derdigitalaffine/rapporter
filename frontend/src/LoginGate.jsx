import {useEffect,useState} from 'react';
import {useTranslation} from 'react-i18next';
import App from './App';
import {AUTH_CHANGED_EVENT,isAuthenticated,login} from './api';
import {Icon} from './icons';
import './session-i18n';

function Card({children,className=''}){return <section className={`card ${className}`}>{children}</section>}
function switchLanguage(i18n){const language=i18n.language?.startsWith('de')?'en':'de';i18n.changeLanguage(language);localStorage.setItem('famuhle-language',language)}

export default function LoginGate(){
 const {t,i18n}=useTranslation();
 const [authed,setAuthed]=useState(isAuthenticated());
 const [expired,setExpired]=useState(false);
 const [legacy,setLegacy]=useState(false);
 const [identifier,setIdentifier]=useState('');
 const [password,setPassword]=useState('');
 const [error,setError]=useState(false);
 const [busy,setBusy]=useState(false);
 useEffect(()=>{
  const authChanged=event=>setAuthed(Boolean(event.detail?.authenticated));
  const sessionExpired=()=>{setExpired(true);setAuthed(false)};
  window.addEventListener(AUTH_CHANGED_EVENT,authChanged);
  window.addEventListener('famuhle:session-expired',sessionExpired);
  return()=>{window.removeEventListener(AUTH_CHANGED_EVENT,authChanged);window.removeEventListener('famuhle:session-expired',sessionExpired)};
 },[]);
 if(authed)return <App/>;
 async function submit(event){event.preventDefault();setError(false);setBusy(true);try{await login(identifier,password,{legacy});setExpired(false);setAuthed(true)}catch{setError(true)}finally{setBusy(false)}}
 function toggleMode(){setLegacy(value=>!value);setIdentifier('');setError(false)}
 return <main className="login-shell"><img className="brand-wide" src="/brand/logo-primary.svg" alt="FamilyOS"/><Card className="login-card">{expired&&<div className="integration-notice" role="status"><Icon name="info"/><div><strong>{t('sessionUi.expiredTitle')}</strong><span>{t('sessionUi.expiredMessage')}</span></div></div>}<h1>{t('login')}</h1><button className="secondary compact" type="button" onClick={toggleMode}>{legacy?t('identityUi.normalAccount'):t('identityUi.migrationAccount')}</button>{legacy&&<p>{t('identityUi.legacyHint')}</p>}<form onSubmit={submit}><label>{legacy?t('identityUi.legacyUsername'):t('identityUi.emailLabel')}<input type={legacy?'text':'email'} value={identifier} onChange={event=>setIdentifier(event.target.value)} autoComplete={legacy?'username':'email'} required autoFocus/></label><label>{t('password')}<input type="password" value={password} onChange={event=>setPassword(event.target.value)} autoComplete="current-password" required/></label>{error&&<p className="error" role="alert">{t('loginFailed')}</p>}<button className="primary" type="submit" disabled={busy}>{busy?t('pleaseWait'):t('login')}</button></form><button className="text-button" onClick={()=>switchLanguage(i18n)}><Icon name="language"/> Deutsch / English</button></Card></main>
}
