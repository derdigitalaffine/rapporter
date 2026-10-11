import {useEffect,useRef,useState} from 'react';
import {api} from './api';
import {Icon} from './icons';
import {toast} from './feedback';
import './superadmin.css';

const blank={name:'',owner_name:'',owner_email:'',locale:'de',timezone:'Europe/Berlin'};
const blankSmtp={enabled:false,host:'',port:587,username:'',password:'',password_set:false,security:'starttls',timeout:10,from_email:'',reply_to:'',effective_source:'environment',configured:false};

export default function SuperAdmin({user,onLogout}){
 const [families,setFamilies]=useState([]);
 const [users,setUsers]=useState([]);
 const [mailJournal,setMailJournal]=useState([]);
 const [mailJournalCount,setMailJournalCount]=useState(0);
 const [emailDrafts,setEmailDrafts]=useState({});
 const [form,setForm]=useState(blank);
 const [smtp,setSmtp]=useState(blankSmtp);
 const [testEmail,setTestEmail]=useState('');
 const [busy,setBusy]=useState(false);
 const [smtpBusy,setSmtpBusy]=useState(false);
 const [userBusy,setUserBusy]=useState('');
 const [loading,setLoading]=useState(true);
 const [reauthOpen,setReauthOpen]=useState(false);
 const [reauthPassword,setReauthPassword]=useState('');
 const [reauthBusy,setReauthBusy]=useState(false);
 const pendingSensitive=useRef(null);

 const load=async()=>{
  setLoading(true);
  try{
   const [familyRows,smtpConfig,userPayload,journalPayload]=await Promise.all([
    api('/superadmin/families/'),
    api('/superadmin/smtp/'),
    api('/superadmin/users/?limit=200'),
    api('/superadmin/mail-journal/?limit=100'),
   ]);
   setFamilies(familyRows);
   setSmtp({...blankSmtp,...smtpConfig,password:''});
   setUsers(userPayload.results||[]);
   setMailJournal(journalPayload.results||[]);
   setMailJournalCount(journalPayload.count||0);
  }catch(error){toast(error.message,{type:'error'})}finally{setLoading(false)}
 };
 useEffect(()=>{load()},[]);
 const set=(key,value)=>setForm(current=>({...current,[key]:value}));
 const setMail=(key,value)=>setSmtp(current=>({...current,[key]:value}));
 const setEmailDraft=(id,value)=>setEmailDrafts(current=>({...current,[id]:value}));

 async function runSensitive(action){
  try{return await action()}catch(error){
   if(error.status===403){pendingSensitive.current=action;setReauthOpen(true);return null}
   throw error;
  }
 }
 async function confirmReauth(event){
  event.preventDefault();if(!reauthPassword)return;setReauthBusy(true);
  try{
   await api('/auth/reauth/password/',{method:'POST',body:JSON.stringify({password:reauthPassword})});
   const action=pendingSensitive.current;pendingSensitive.current=null;setReauthOpen(false);setReauthPassword('');
   toast('Identität bestätigt.',{type:'success'});if(action)await action();
  }catch(error){toast(error.message||'Bestätigung fehlgeschlagen.',{type:'error'})}finally{setReauthBusy(false)}
 }
 function cancelReauth(){pendingSensitive.current=null;setReauthOpen(false);setReauthPassword('')}

 async function saveSmtp(event){
  event.preventDefault();setSmtpBusy(true);
  try{
   await runSensitive(async()=>{
    const payload={enabled:smtp.enabled,host:smtp.host,port:Number(smtp.port),username:smtp.username,password:smtp.password,security:smtp.security,timeout:Number(smtp.timeout),from_email:smtp.from_email,reply_to:smtp.reply_to};
    const result=await api('/superadmin/smtp/',{method:'PUT',body:JSON.stringify(payload)});
    setSmtp({...blankSmtp,...result,password:''});toast('SMTP-Konfiguration gespeichert.',{type:'success'});
   });
  }catch(error){toast(error.message||'SMTP konnte nicht gespeichert werden.',{type:'error'})}finally{setSmtpBusy(false)}
 }
 async function sendTest(){
  if(!testEmail.trim())return;setSmtpBusy(true);
  try{await runSensitive(async()=>{await api('/superadmin/smtp/test/',{method:'POST',body:JSON.stringify({recipient:testEmail.trim()})});toast('Testmail wurde vom konfigurierten Backend angenommen.',{type:'success'})})}
  catch(error){toast(error.message||'SMTP-Test fehlgeschlagen.',{type:'error'})}finally{setSmtpBusy(false)}
 }
 async function requestEmailChange(target){
  const email=(emailDrafts[target.id]||'').trim();if(!email)return;
  const action=async()=>{
   setUserBusy(`email:${target.id}`);
   try{
    await api(`/superadmin/users/${target.id}/email-change/`,{method:'POST',body:JSON.stringify({email})});
    setEmailDraft(target.id,'');await load();
    toast('Bestätigungsmail an die neue Adresse wurde eingeplant.',{type:'success'});
   }finally{setUserBusy('')}
  };
  try{await runSensitive(action)}catch(error){toast(error.message||'E-Mail-Änderung konnte nicht gestartet werden.',{type:'error'})}
 }
 async function sendPasswordReset(target){
  const action=async()=>{
   setUserBusy(`reset:${target.id}`);
   try{
    await api(`/superadmin/users/${target.id}/password-reset/`,{method:'POST',body:'{}'});
    await load();toast('Passwort-Reset wurde eingeplant.',{type:'success'});
   }finally{setUserBusy('')}
  };
  try{await runSensitive(action)}catch(error){toast(error.message||'Passwort-Reset konnte nicht eingeplant werden.',{type:'error'})}
 }
 async function createFamily(event){
  event.preventDefault();const payload={...form,owner_email:form.owner_email.trim()};setBusy(true);
  try{await runSensitive(async()=>{const result=await api('/superadmin/families/',{method:'POST',body:JSON.stringify(payload)});setForm(blank);await load();toast(`Familie angelegt. Owner-Einladung wird an ${result.family.pending_owner_invites?.[0]?.email||payload.owner_email} versendet.`,{type:'success'})})}
  catch(error){toast(error.message||'Familie konnte nicht angelegt werden.',{type:'error'})}finally{setBusy(false)}
 }
 async function newOwnerInvite(family){
  const suggested=family.pending_owner_invites?.[0]?.email||'';const email=window.prompt('Owner-E-Mail für die neue Einladung',suggested);if(!email?.trim())return;
  try{await runSensitive(async()=>{await api(`/superadmin/families/${family.id}/owner-invite/`,{method:'POST',body:JSON.stringify({email:email.trim()})});await load();toast(`Owner-Einladung wird an ${email.trim()} versendet.`,{type:'success'})})}
  catch(error){toast(error.message,{type:'error'})}
 }
 async function toggleFamily(family){
  const next=family.status==='active'?'suspended':'active';
  try{await runSensitive(async()=>{await api(`/superadmin/families/${family.id}/`,{method:'PATCH',body:JSON.stringify({status:next})});await load();toast(next==='active'?'Familie reaktiviert.':'Familie gesperrt.',{type:'success'})})}
  catch(error){toast(error.message,{type:'error'})}
 }

 return <div className="superadmin-shell">
  <header className="superadmin-top"><div className="superadmin-brand"><img src="/brand/icon.svg" alt=""/><div><strong>FamilyOS</strong><span>Superadmin</span></div></div><div className="superadmin-user"><span>{user?.username}</span><button className="secondary compact" onClick={onLogout}><Icon name="logout"/>Abmelden</button></div></header>
  <main className="superadmin-main">
   <section className="superadmin-intro"><div><small>Plattformverwaltung</small><h1>FamilyOS sicher betreiben</h1><p>Globale Plattformdienste, Nutzer und Familien werden getrennt administriert. Sensible Änderungen verlangen eine frische Sicherheitsbestätigung.</p></div><div className="superadmin-stat"><strong>{families.length}</strong><span>Familien</span></div></section>
   {reauthOpen&&<section className="card superadmin-reauth" role="region" aria-labelledby="superadmin-reauth-title"><div><small>Sicherheitsbestätigung</small><h2 id="superadmin-reauth-title">Identität erneut bestätigen</h2><p>Diese Änderung ist sensibel. Bestätige dein aktuelles Passwort; die angeforderte Aktion wird danach automatisch fortgesetzt.</p></div><form onSubmit={confirmReauth}><label>Aktuelles Passwort<input type="password" autoComplete="current-password" value={reauthPassword} onChange={event=>setReauthPassword(event.target.value)} required autoFocus/></label><div className="superadmin-actions"><button className="primary" disabled={reauthBusy}><Icon name="lock"/>{reauthBusy?'Wird bestätigt …':'Bestätigen'}</button><button className="secondary" type="button" onClick={cancelReauth} disabled={reauthBusy}>Abbrechen</button></div></form></section>}

   <section className="card superadmin-create superadmin-smtp"><div className="superadmin-list-head"><div><small>E-Mail / SMTP</small><h2>Transaktionsmail</h2></div><span className={`tenant-status ${smtp.configured?'active':'suspended'}`}>{smtp.configured?'Konfiguriert':'Nicht konfiguriert'}</span></div><p className="superadmin-hint">Aktive Quelle: <strong>{smtp.effective_source==='superadmin'?'Superadmin':'Umgebung'}</strong>. Das Passwort wird nie zurückgelesen oder vorausgefüllt.</p><form onSubmit={saveSmtp}><label className="superadmin-toggle"><input type="checkbox" checked={smtp.enabled} onChange={event=>setMail('enabled',event.target.checked)}/><span>SMTP aus Superadmin verwenden</span></label><div className="superadmin-smtp-grid"><label>SMTP-Host<input value={smtp.host} onChange={event=>setMail('host',event.target.value)} placeholder="smtp.example.com"/></label><label>Port<input type="number" min="1" max="65535" value={smtp.port} onChange={event=>setMail('port',event.target.value)}/></label><label>Sicherheit<select value={smtp.security} onChange={event=>setMail('security',event.target.value)}><option value="starttls">STARTTLS</option><option value="ssl">TLS/SSL</option><option value="plain">Plain</option></select></label><label>Benutzername<input autoComplete="username" value={smtp.username} onChange={event=>setMail('username',event.target.value)}/></label><label>Passwort<input type="password" autoComplete="new-password" value={smtp.password} onChange={event=>setMail('password',event.target.value)} placeholder={smtp.password_set?'Gespeichert · leer lassen zum Behalten':'SMTP-Passwort'}/></label><label>Timeout (s)<input type="number" min="1" max="120" value={smtp.timeout} onChange={event=>setMail('timeout',event.target.value)}/></label><label>Absender<input type="email" value={smtp.from_email} onChange={event=>setMail('from_email',event.target.value)} placeholder="noreply@example.com"/></label><label>Reply-To<input type="email" value={smtp.reply_to} onChange={event=>setMail('reply_to',event.target.value)} placeholder="support@example.com"/></label></div><button className="primary" disabled={smtpBusy}><Icon name="check"/>{smtpBusy?'Bitte warten …':'SMTP speichern'}</button></form><div className="superadmin-test"><label>Testadresse<input type="email" value={testEmail} onChange={event=>setTestEmail(event.target.value)} placeholder="admin@example.com"/></label><button className="secondary" type="button" onClick={sendTest} disabled={smtpBusy||!testEmail.trim()}><Icon name="check"/>Testmail senden</button></div></section>

   <section className="superadmin-list-head"><div><small>Identity & Recovery</small><h2>Nutzerkonten</h2></div><span className="superadmin-count">{users.length} geladen</span></section>
   <div className="superadmin-user-list">{users.map(target=>{
    const label=target.display_name||target.username;const emailBusy=userBusy===`email:${target.id}`;const resetBusy=userBusy===`reset:${target.id}`;
    return <article className="card superadmin-user-card" key={target.id}><div className="superadmin-user-head"><div><div className="superadmin-family-title"><h3>{label}</h3>{target.is_superuser&&<span className="tenant-status active">Superadmin</span>}</div><small>@{target.username} · {target.is_active?'Aktiv':'Deaktiviert'}</small></div><span className={`tenant-status ${target.email_verified?'active':'suspended'}`}>{target.email_verified?'E-Mail bestätigt':'E-Mail unbestätigt'}</span></div><div className="superadmin-user-email"><span>Primäre E-Mail</span><strong>{target.email||'Keine E-Mail hinterlegt'}</strong>{!target.email_managed&&target.email&&<small>Legacy-Adresse · noch keine verifizierte Identity</small>}{target.pending_email&&<small>Ausstehend: {target.pending_email} · Bestätigung erforderlich</small>}</div>{target.memberships?.length>0&&<div className="superadmin-memberships">{target.memberships.map(item=><span key={item.id}>{item.family_name} · {roleLabel(item.role)}</span>)}</div>}<div className="superadmin-user-controls"><label>{`Neue E-Mail für ${label}`}<input type="email" value={emailDrafts[target.id]||''} onChange={event=>setEmailDraft(target.id,event.target.value)} placeholder="neu@example.com"/></label><button className="secondary" type="button" onClick={()=>requestEmailChange(target)} disabled={!!userBusy||!(emailDrafts[target.id]||'').trim()}><Icon name="check"/>{emailBusy?'Wird eingeplant …':'E-Mail-Änderung starten'}</button><button className="secondary" type="button" onClick={()=>sendPasswordReset(target)} disabled={!!userBusy||!target.can_password_reset} title={target.can_password_reset?'Reset-Link an die bestätigte primäre E-Mail senden':'Bestätigte primäre E-Mail erforderlich'}><Icon name="lock"/>{resetBusy?'Wird eingeplant …':'Passwort-Reset senden'}</button></div></article>;
   })}{!loading&&!users.length&&<div className="card smart-empty"><strong>Keine Nutzerkonten</strong><span>Es wurden keine administrierbaren Konten gefunden.</span></div>}</div>

   <section className="superadmin-list-head superadmin-mail-head"><div><small>E-Mail / Betrieb</small><h2>Mailjournal</h2></div><span className="superadmin-count">{mailJournalCount} Einträge</span></section>
   <div className="card superadmin-mail-journal">{mailJournal.map(item=><div className="superadmin-mail-row" key={item.id}><div><strong>{mailTemplateLabel(item.template_key)}</strong><small>{item.recipient_hint?`${item.recipient_hint} · `:''}{mailDate(item.created_at)}</small></div><div className="superadmin-mail-state"><span className={`tenant-status ${mailStatusTone(item.status)}`}>{mailStatusLabel(item.status)}</span><small>{item.attempt_count} Versuch{item.attempt_count===1?'':'e'}{item.last_error_code?` · ${item.last_error_code}`:''}{item.sent_at?` · gesendet ${mailDate(item.sent_at)}`:''}</small></div></div>)}{!loading&&!mailJournal.length&&<div className="smart-empty"><strong>Noch keine Versandhistorie</strong><span>Transaktionsmails erscheinen hier ohne Inhalt, Tokens oder vollständige Empfängeradresse.</span></div>}</div>

   <section className="card superadmin-create"><div><small>Neue Familie</small><h2>Tenant anlegen & Owner einladen</h2></div><form onSubmit={createFamily}><div className="superadmin-form-grid"><label>Familienname<input value={form.name} onChange={event=>set('name',event.target.value)} required placeholder="Familie Mustermann"/></label><label>Owner-Name<input value={form.owner_name} onChange={event=>set('owner_name',event.target.value)} placeholder="Alex Mustermann"/></label><label>Owner-E-Mail<input type="email" value={form.owner_email} onChange={event=>set('owner_email',event.target.value)} required placeholder="alex@example.com"/></label><label>Sprache<select value={form.locale} onChange={event=>set('locale',event.target.value)}><option value="de">Deutsch</option><option value="en">English</option></select></label><label>Zeitzone<input value={form.timezone} onChange={event=>set('timezone',event.target.value)} required/></label></div><button className="primary" disabled={busy||!form.name.trim()||!form.owner_email.trim()}><Icon name="members"/>{busy?'Wird angelegt …':'Familie anlegen & Einladung senden'}</button></form></section>
   <section className="superadmin-list-head"><div><small>Tenants</small><h2>Familien</h2></div><button className="secondary compact" onClick={load} disabled={loading}><Icon name="refresh"/>Aktualisieren</button></section>
   <div className="superadmin-family-list">{families.map(family=><article className="card superadmin-family" key={family.id}><div className="superadmin-family-head"><div><div className="superadmin-family-title"><h3>{family.name}</h3><span className={`tenant-status ${family.status}`}>{family.status==='active'?'Aktiv':'Gesperrt'}</span></div><small>{family.slug} · {family.locale.toUpperCase()} · {family.timezone}</small></div><strong>{family.member_count} Mitglieder</strong></div><div className="superadmin-owner"><span>Owner</span>{family.owners.length?family.owners.map(owner=><strong key={owner.username}>{owner.display_name||owner.username}{owner.email?` · ${owner.email}`:''}</strong>):<strong>Noch kein Owner registriert</strong>}</div>{family.pending_owner_invites?.length>0&&<div className="superadmin-pending"><Icon name="info"/><span>{family.pending_owner_invites.length} offene Owner-Einladung(en) · {family.pending_owner_invites[0].email} · {ownerDeliveryLabel(family.pending_owner_invites[0].delivery_status)}{family.pending_owner_invites[0].last_sent_at?` · zuletzt ${ownerSentLabel(family.pending_owner_invites[0].last_sent_at)}`:''}</span></div>}<div className="superadmin-actions"><button className="secondary" onClick={()=>newOwnerInvite(family)} disabled={family.status!=='active'}><Icon name="members"/>Neue Owner-Einladung senden</button><button className={family.status==='active'?'ghost-danger':'secondary'} onClick={()=>toggleFamily(family)}><Icon name={family.status==='active'?'close':'check'}/>{family.status==='active'?'Familie sperren':'Familie reaktivieren'}</button></div></article>)}{!loading&&!families.length&&<div className="card smart-empty"><strong>Noch keine Familie</strong><span>Lege oben den ersten Tenant an.</span></div>}</div>
  </main>
 </div>;
}

function ownerDeliveryLabel(status){return status==='sent'?'Versendet':status==='retrying'?'Zustellung wird erneut versucht':status==='failed'?'Versand fehlgeschlagen':'Versand wird vorbereitet'}
function ownerSentLabel(value){return new Intl.DateTimeFormat(undefined,{dateStyle:'medium',timeStyle:'short'}).format(new Date(value))}
function roleLabel(role){return role==='owner'?'Owner':role==='adult'?'Erwachsen':role==='teen'?'Teen':role==='child'?'Kind':role==='guest'?'Gast':role}
function mailTemplateLabel(key){return key==='email.verify'?'E-Mail bestätigen':key==='password.reset'?'Passwort zurücksetzen':key==='password.changed'?'Passwort geändert':key==='email.changed'?'E-Mail geändert':key==='family.invitation'?'Familieneinladung':key||'Transaktionsmail'}
function mailStatusLabel(status){return status==='sent'?'Versendet':status==='failed'?'Fehlgeschlagen':status==='retry'?'Wiederholung':status==='sending'?'Wird gesendet':status==='canceled'?'Abgebrochen':'Eingeplant'}
function mailStatusTone(status){return status==='sent'?'active':status==='failed'||status==='canceled'?'suspended':''}
function mailDate(value){return value?new Intl.DateTimeFormat(undefined,{dateStyle:'medium',timeStyle:'short'}).format(new Date(value)):'—'}
