import {useState} from 'react';
import {useTranslation} from 'react-i18next';
import {confirmPasswordReset} from './password-reset-api';
import './session-i18n';

export default function PasswordResetFlow({uid,token}){
 const {t,i18n}=useTranslation();
 const [password,setPassword]=useState('');
 const [confirmation,setConfirmation]=useState('');
 const [busy,setBusy]=useState(false);
 const [state,setState]=useState('ready');
 const [errors,setErrors]=useState([]);
 async function submit(event){
  event.preventDefault();setErrors([]);
  if(password!==confirmation){setErrors([t('identityUi.resetPasswordMismatch')]);return}
  setBusy(true);
  try{await confirmPasswordReset(uid,token,password,i18n.language);setState('success')}
  catch(error){
   if(error?.code==='password_invalid'){setErrors(error?.payload?.errors?.length?error.payload.errors:[t('identityUi.resetPasswordInvalid')]);setState('ready')}
   else setState('invalid');
  }finally{setBusy(false)}
 }
 function goLogin(){window.location.assign('/')}
 function requestNew(){window.location.assign('/?password-reset=1')}
 return <main className="login-shell"><img className="brand-wide" src="/brand/logo-primary.svg" alt="FamilyOS"/><section className="card login-card">{state==='success'?<><h1>{t('identityUi.resetSuccessTitle')}</h1><div className="integration-notice" role="status"><div><strong>{t('identityUi.resetSuccessTitle')}</strong><span>{t('identityUi.resetSuccess')}</span></div></div><button className="primary" type="button" onClick={goLogin}>{t('identityUi.backToLogin')}</button></>:state==='invalid'?<><h1>{t('identityUi.resetTitle')}</h1><p className="error" role="alert">{t('identityUi.resetInvalid')}</p><button className="primary" type="button" onClick={requestNew}>{t('identityUi.resetRequestNew')}</button><button className="secondary" type="button" onClick={goLogin}>{t('identityUi.backToLogin')}</button></>:<><h1>{t('identityUi.resetTitle')}</h1><p>{t('identityUi.resetIntro')}</p><form onSubmit={submit}><label>{t('identityUi.resetNewPassword')}<input type="password" value={password} onChange={event=>setPassword(event.target.value)} autoComplete="new-password" minLength={8} required autoFocus/></label><label>{t('identityUi.resetConfirmPassword')}<input type="password" value={confirmation} onChange={event=>setConfirmation(event.target.value)} autoComplete="new-password" minLength={8} required/></label>{errors.length>0&&<div className="error" role="alert">{errors.map((message,index)=><div key={index}>{message}</div>)}</div>}<button className="primary" type="submit" disabled={busy}>{busy?t('pleaseWait'):t('identityUi.resetAction')}</button></form></>}</section></main>
}
