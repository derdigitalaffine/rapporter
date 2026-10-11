import {useEffect,useState} from 'react';
import SuperAdmin from './SuperAdmin';
import SuperAdminAnalytics from './SuperAdminAnalytics';
import {ADMIN_SESSION_EXPIRED_EVENT,adminLogin,adminLogout,adminSession} from './superadmin-api';
import {Icon} from './icons';

function analyticsRequested(){return new URLSearchParams(window.location.search).get('section')==='analytics'}

export default function SuperAdminGate(){
  const [session,setSession]=useState(null);
  const [checking,setChecking]=useState(true);
  const [identifier,setIdentifier]=useState('');
  const [password,setPassword]=useState('');
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const [expired,setExpired]=useState(false);

  useEffect(()=>{
    let alive=true;
    adminSession().then(value=>{if(alive)setSession(value)}).catch(()=>{}).finally(()=>{if(alive)setChecking(false)});
    const onExpired=()=>{setSession(null);setExpired(true);setChecking(false)};
    window.addEventListener(ADMIN_SESSION_EXPIRED_EVENT,onExpired);
    return()=>{alive=false;window.removeEventListener(ADMIN_SESSION_EXPIRED_EVENT,onExpired)};
  },[]);

  async function submit(event){
    event.preventDefault();setBusy(true);setError('');
    try{const value=await adminLogin(identifier,password);setSession(value);setPassword('');setExpired(false)}
    catch{setError('Anmeldung fehlgeschlagen. Prüfe deine Superadmin-Zugangsdaten.')}
    finally{setBusy(false)}
  }
  async function logout(){await adminLogout();setSession(null);setExpired(false)}

  if(checking)return <main className="admin-login-shell"><section className="card admin-login-card" role="status"><img src="/brand/icon.svg" alt=""/><h1>Superadmin wird geladen</h1><p>Die getrennte Admin-Sitzung wird geprüft.</p></section></main>;
  if(session?.authenticated&&session.user?.is_superadmin){
    if(analyticsRequested())return <SuperAdminAnalytics onLogout={logout}/>;
    return <><SuperAdmin user={session.user} session={session.session} onLogout={logout}/><a href="/superadmin/?section=analytics" className="secondary compact" style={{position:'fixed',right:18,bottom:18,zIndex:50,boxShadow:'0 8px 30px rgba(0,0,0,.16)',textDecoration:'none'}}><Icon name="trend"/>Analytics</a></>;
  }
  return <main className="admin-login-shell"><section className="card admin-login-card"><div className="admin-login-brand"><img src="/brand/icon.svg" alt=""/><div><strong>FamilyOS</strong><span>Superadmin</span></div></div><small>Getrennte Administration</small><h1>Plattform sicher verwalten</h1><p>Diese PWA verwendet eine eigene Admin-Sitzung. Deine normale FamilyOS-Anmeldung bleibt davon unberührt.</p>{expired&&<div className="admin-notice" role="status"><Icon name="info"/><span>Die Admin-Sitzung ist abgelaufen. Bitte melde dich erneut an.</span></div>}<form onSubmit={submit}><label>E-Mail oder Admin-Benutzername<input value={identifier} onChange={event=>setIdentifier(event.target.value)} autoComplete="username" required autoFocus/></label><label>Passwort<input type="password" value={password} onChange={event=>setPassword(event.target.value)} autoComplete="current-password" required/></label>{error&&<p className="error" role="alert">{error}</p>}<button className="primary" type="submit" disabled={busy}>{busy?'Anmeldung läuft …':'Als Superadmin anmelden'}</button></form><a className="admin-family-link" href="/">Zur FamilyOS-App</a></section></main>;
}
