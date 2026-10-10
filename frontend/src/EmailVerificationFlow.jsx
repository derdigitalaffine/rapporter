import {useState} from 'react';
import {useTranslation} from 'react-i18next';
import './session-i18n';
import {api} from './api';
import {Icon} from './icons';

export default function EmailVerificationFlow({token}){
 const {t,i18n}=useTranslation();
 const [state,setState]=useState('ready');
 const [error,setError]=useState('');
 async function verify(){
  setState('busy');setError('');
  try{await api('/auth/email/verify/',{method:'POST',body:JSON.stringify({token})});setState('done')}
  catch(e){setError(e.message||t('identityUi.verifyInvalid'));setState('error')}
 }
 return <main className="login-shell"><img className="brand-wide" src="/brand/logo-primary.svg" alt="FamilyOS"/><section className="card login-card"><div className="invite-mark"><Icon name={state==='done'?'check':'email'} size={30}/></div><h1>{t('identityUi.verifyTitle')}</h1>{state==='done'?<><p role="status">{t('identityUi.verifySuccess')}</p><a className="primary" href="/">{t('identityUi.backToLogin')}</a></>:<><p>{t('identityUi.verifyIntro')}</p>{error&&<p className="error" role="alert">{error}</p>}<button className="primary" disabled={state==='busy'} onClick={verify}><Icon name="check"/>{state==='busy'?t('pleaseWait'):t('identityUi.verifyAction')}</button><a className="text-button" href="/">{t('identityUi.backToLogin')}</a></>}<button className="text-button" onClick={()=>{const l=i18n.language?.startsWith('de')?'en':'de';i18n.changeLanguage(l);localStorage.setItem('famuhle-language',l)}}><Icon name="language"/> Deutsch / English</button></section></main>
}
