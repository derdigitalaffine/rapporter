import {useEffect,useMemo,useRef,useState} from 'react';
import {adminApi} from './superadmin-api';
import {Icon} from './icons';
import {toast} from './feedback';
import {useTranslation} from 'react-i18next';
import './superadmin-cockpit-i18n';
import SuperAdminUserCrud from './SuperAdminUserCrud';
import {CockpitToolbar,InternalOverview,OnboardingInsights,SecurityInsights,DeliveryInsights,OperationsInsights,AuditInsights,OperationalDirectory,supportedAdminPeriod} from './SuperAdminInsights';

const blank={name:'',owner_name:'',owner_email:'',locale:'de',timezone:'Europe/Berlin'};
const blankSmtp={enabled:false,host:'',port:587,username:'',password:'',password_set:false,security:'starttls',timeout:10,from_email:'',reply_to:'',effective_source:'environment',configured:false};
const blankMailHealth={configured:false,counts:{},last_success_at:null,latency_seconds:{p50:null,p95:null},recent_error_classes:[]};
const SECTIONS=[
 ['overview','Übersicht','Plattformstatus und Aufmerksamkeit'],
 ['users','Nutzer','Identity und Recovery'],
 ['families','Familien','Tenants und Owner'],
 ['delivery','E-Mail','SMTP und Versandjournal'],
 ['operations','Betrieb','Health und Zustellung'],
 ['security','Sicherheit','Admin-Sitzungen und Schutz'],
 ['onboarding','Onboarding & Einladungen','Aktivierung und Wiederkehr'],
 ['audit','Audit','Freigegebene operative Metadaten'],
 ['analytics','Matomo (optional)','Externe Produktberichte'],
];
const SECTION_KEYS=new Set(SECTIONS.map(([key])=>key));

export default function SuperAdmin(props){
 if(!window.location.pathname.startsWith('/superadmin'))return <LegacySuperAdminRedirect/>;
 return <SuperAdminCockpit {...props}/>;
}

function LegacySuperAdminRedirect(){
 useEffect(()=>{window.location.replace('/superadmin/')},[]);
 return <main className="admin-login-shell"><section className="card admin-login-card" role="status"><img src="/brand/icon.svg" alt=""/><h1>Superadmin wird separat geöffnet</h1><p>Die Plattformverwaltung verwendet jetzt eine eigene PWA und Anmeldung.</p></section></main>;
}

function sectionFromLocation(){const value=new URLSearchParams(window.location.search).get('section')||'overview';return SECTION_KEYS.has(value)?value:'overview'}

function SuperAdminCockpit({user,onLogout}){
 const {t}=useTranslation();
 const [period,setPeriod]=useState(supportedAdminPeriod);
 const [insightRefresh,setInsightRefresh]=useState(0);
 const [lookupQuery,setLookupQuery]=useState('');
 const [directoryRefresh,setDirectoryRefresh]=useState(0);
 const crudMode=new URLSearchParams(location.search).get('mode')==='crud';
 const refreshInsights=()=>setInsightRefresh(value=>value+1);
 function changePeriod(value){setPeriod(value);const url=new URL(location.href);url.searchParams.set('period',value);history.replaceState(null,'',url.pathname+url.search)}
 const [section,setSection]=useState(sectionFromLocation);
 const [mailJournal,setMailJournal]=useState([]);
 const [mailJournalCount,setMailJournalCount]=useState(0);
 const [mailHealth,setMailHealth]=useState(blankMailHealth);
 const [sessions,setSessions]=useState([]);
 const [sessionsFresh,setSessionsFresh]=useState(false);
 const [emailDrafts,setEmailDrafts]=useState({});
 const [resetLinks,setResetLinks]=useState({});
 const [form,setForm]=useState(blank);
 const [smtp,setSmtp]=useState(blankSmtp);
 const [testEmail,setTestEmail]=useState('');
 const [busy,setBusy]=useState(false);
 const [smtpBusy,setSmtpBusy]=useState(false);
 const [userBusy,setUserBusy]=useState('');
 const [loading,setLoading]=useState(true);
 const [loadWarnings,setLoadWarnings]=useState([]);
 const [reauthOpen,setReauthOpen]=useState(false);
 const [reauthPassword,setReauthPassword]=useState('');
 const [reauthBusy,setReauthBusy]=useState(false);
 const pendingSensitive=useRef(null);

 const load=async()=>{
  setLoading(true);setLoadWarnings([]);
  const jobs=[
   ['SMTP',adminApi('/smtp/')],
   ['Mailjournal',adminApi('/mail-journal/?limit=100')],
   ['Mail-Health',adminApi('/mail-health/')],
   ['Sitzungen',adminApi('/auth/sessions/')],
  ];
  const results=await Promise.allSettled(jobs.map(([,promise])=>promise));
  const warnings=[];results.forEach((result,index)=>{if(result.status==='rejected')warnings.push(jobs[index][0])});
  if(results[0].status==='fulfilled')setSmtp({...blankSmtp,...results[0].value,password:''});
  if(results[1].status==='fulfilled'){setMailJournal(results[1].value?.results||[]);setMailJournalCount(results[1].value?.count||0)}
  if(results[2].status==='fulfilled')setMailHealth({...blankMailHealth,...results[2].value,latency_seconds:{...blankMailHealth.latency_seconds,...results[2].value?.latency_seconds}});
  if(results[3].status==='fulfilled'){setSessions(results[3].value?.sessions||[]);setSessionsFresh(Boolean(results[3].value?.fresh))}
  setDirectoryRefresh(value=>value+1);
  setLoadWarnings(warnings);setLoading(false);
 };
 useEffect(()=>{load()},[]);
 useEffect(()=>{const pop=()=>{setSection(sectionFromLocation());setPeriod(supportedAdminPeriod())};window.addEventListener('popstate',pop);return()=>window.removeEventListener('popstate',pop)},[]);
 const set=(key,value)=>setForm(current=>({...current,[key]:value}));
 const setMail=(key,value)=>setSmtp(current=>({...current,[key]:value}));
 const setEmailDraft=(id,value)=>setEmailDrafts(current=>({...current,[id]:value}));
 const setResetLink=(id,value)=>setResetLinks(current=>({...current,[id]:value}));

 function navigate(next,{replace=false}={}){
  if(!SECTION_KEYS.has(next))return;
  const url=new URL(window.location.href);url.searchParams.delete('mode');url.searchParams.delete('directory_status');url.searchParams.delete('directory_sort');url.searchParams.delete('directory_offset');if(next==='overview')url.searchParams.delete('section');else url.searchParams.set('section',next);
  window.history[replace?'replaceState':'pushState']({section:next},'',`${url.pathname}${url.search}`);setSection(next);window.scrollTo({top:0,behavior:'smooth'});
 }


 async function runSensitive(action){
  try{return await action()}catch(error){
   if(error.status===403){pendingSensitive.current=action;setReauthOpen(true);return null}
   throw error;
  }
 }
 async function confirmReauth(event){
  event.preventDefault();if(!reauthPassword)return;setReauthBusy(true);
  try{
   await adminApi('/auth/reauth/password/',{method:'POST',body:JSON.stringify({password:reauthPassword})});
   const action=pendingSensitive.current;pendingSensitive.current=null;setReauthOpen(false);setReauthPassword('');setSessionsFresh(true);
   toast('Admin-Identität bestätigt.',{type:'success'});if(action)await action();
  }catch(error){toast(error.message||'Bestätigung fehlgeschlagen.',{type:'error'})}finally{setReauthBusy(false)}
 }
 function cancelReauth(){pendingSensitive.current=null;setReauthOpen(false);setReauthPassword('')}
 async function saveSmtp(event){event.preventDefault();setSmtpBusy(true);try{await runSensitive(async()=>{const payload={enabled:smtp.enabled,host:smtp.host,port:Number(smtp.port),username:smtp.username,password:smtp.password,security:smtp.security,timeout:Number(smtp.timeout),from_email:smtp.from_email,reply_to:smtp.reply_to};const result=await adminApi('/smtp/',{method:'PUT',body:JSON.stringify(payload)});setSmtp({...blankSmtp,...result,password:''});await refreshMailHealth();toast('SMTP-Konfiguration gespeichert.',{type:'success'})})}catch(error){toast(error.message||'SMTP konnte nicht gespeichert werden.',{type:'error'})}finally{setSmtpBusy(false)}}
 async function sendTest(){if(!testEmail.trim())return;setSmtpBusy(true);try{await runSensitive(async()=>{await adminApi('/smtp/test/',{method:'POST',body:JSON.stringify({recipient:testEmail.trim()})});await refreshMailHealth();toast('Testmail wurde vom Backend angenommen.',{type:'success'})})}catch(error){toast(error.message||'SMTP-Test fehlgeschlagen.',{type:'error'})}finally{setSmtpBusy(false)}}
 async function refreshMailHealth(){try{const value=await adminApi('/mail-health/');setMailHealth({...blankMailHealth,...value,latency_seconds:{...blankMailHealth.latency_seconds,...value?.latency_seconds}})}catch{}}
 async function requestEmailChange(target){const email=(emailDrafts[target.id]||'').trim();if(!email)return;const action=async()=>{setUserBusy(`email:${target.id}`);try{await adminApi(`/users/${target.id}/email-change/`,{method:'POST',body:JSON.stringify({email})});setEmailDraft(target.id,'');await load();toast('Bestätigungsmail an die neue Adresse wurde eingeplant.',{type:'success'})}finally{setUserBusy('')}};try{await runSensitive(action)}catch(error){toast(error.message||'E-Mail-Änderung konnte nicht gestartet werden.',{type:'error'})}}
 async function setPrimaryEmailDirect(target){const email=(emailDrafts[target.id]||'').trim();if(!email)return;const action=async()=>{setUserBusy(`direct-email:${target.id}`);try{await adminApi(`/users/${target.id}/email-direct/`,{method:'POST',body:JSON.stringify({email})});setEmailDraft(target.id,'');setResetLink(target.id,'');await load();toast('Primäre E-Mail wurde direkt gesetzt und bestätigt.',{type:'success'})}finally{setUserBusy('')}};try{await runSensitive(action)}catch(error){toast(error.message||'Primäre E-Mail konnte nicht direkt gesetzt werden.',{type:'error'})}}
 async function sendPasswordReset(target){const action=async()=>{setUserBusy(`reset:${target.id}`);try{await adminApi(`/users/${target.id}/password-reset/`,{method:'POST',body:'{}'});await load();toast('Passwort-Reset wurde eingeplant.',{type:'success'})}finally{setUserBusy('')}};try{await runSensitive(action)}catch(error){toast(error.message||'Passwort-Reset konnte nicht eingeplant werden.',{type:'error'})}}
 async function createPasswordResetLink(target){const action=async()=>{setUserBusy(`reset-link:${target.id}`);try{const result=await adminApi(`/users/${target.id}/password-reset-link/`,{method:'POST',body:'{}'});setResetLink(target.id,result.reset_url||'');toast('Neuer Passwort-Reset-Link wurde erzeugt.',{type:'success'})}finally{setUserBusy('')}};try{await runSensitive(action)}catch(error){toast(error.message||'Passwort-Reset-Link konnte nicht erzeugt werden.',{type:'error'})}}
 async function copyPasswordResetLink(target){const value=resetLinks[target.id]||'';if(!value)return;try{await navigator.clipboard.writeText(value);toast('Reset-Link kopiert.',{type:'success'})}catch{toast('Kopieren nicht möglich. Der Link kann im Feld markiert und kopiert werden.',{type:'error'})}}
 async function createFamily(event){event.preventDefault();const payload={...form,owner_email:form.owner_email.trim()};setBusy(true);try{await runSensitive(async()=>{const result=await adminApi('/families/',{method:'POST',body:JSON.stringify(payload)});setForm(blank);await load();toast(`Familie angelegt. Owner-Einladung wird an ${result.family.pending_owner_invites?.[0]?.email||payload.owner_email} versendet.`,{type:'success'})})}catch(error){toast(error.message||'Familie konnte nicht angelegt werden.',{type:'error'})}finally{setBusy(false)}}
 async function newOwnerInvite(family){const suggested=family.pending_owner_invites?.[0]?.email||'';const email=window.prompt('Owner-E-Mail für die neue Einladung',suggested);if(!email?.trim())return;try{await runSensitive(async()=>{await adminApi(`/families/${family.id}/owner-invite/`,{method:'POST',body:JSON.stringify({email:email.trim()})});await load();toast(`Owner-Einladung wird an ${email.trim()} versendet.`,{type:'success'})})}catch(error){toast(error.message,{type:'error'})}}
 async function toggleFamily(family){const next=family.status==='active'?'suspended':'active';try{await runSensitive(async()=>{await adminApi(`/families/${family.id}/`,{method:'PATCH',body:JSON.stringify({status:next})});await load();toast(next==='active'?'Familie reaktiviert.':'Familie gesperrt.',{type:'success'})})}catch(error){toast(error.message,{type:'error'})}}

 const activeLabel=t(`adminCockpit.${section}`);
 function lookup(query,kind='users'){if(query===null){refreshInsights();return}setLookupQuery(query);navigate(kind)}

 return <div className="superadmin-shell">
  <header className="superadmin-top"><button className="superadmin-brand" type="button" onClick={()=>navigate('overview')} aria-label="Superadmin Übersicht"><img src="/brand/icon.svg" alt=""/><div><strong>FamilyOS</strong><span>Superadmin</span></div></button><div className="superadmin-user"><div><strong>{user?.username}</strong><span>Admin-PWA</span></div><button className="secondary compact" onClick={onLogout}><Icon name="logout"/>Abmelden</button></div></header>
  <div className="superadmin-layout">
   <aside className="superadmin-sidebar" aria-label="Superadmin Navigation"><div className="superadmin-nav-title"><small>Plattform</small><strong>{activeLabel}</strong></div><nav className="superadmin-nav">{SECTIONS.map(([key,label,description])=><button key={key} type="button" className={section===key?'active':''} aria-current={section===key?'page':undefined} onClick={()=>navigate(key)}><span>{t(`adminCockpit.${key==='analytics'?'matomo':key}`)}</span></button>)}</nav><div className="superadmin-sidebar-foot"><span className={`health-dot ${mailHealth.configured?'healthy':'unknown'}`} aria-hidden="true"/><span>Admin-Sitzung getrennt von FamilyOS</span></div></aside>
   <main className="superadmin-main">
    <div className="superadmin-mobile-nav" aria-label="Superadmin Bereiche">{SECTIONS.map(([key,label])=><button key={key} type="button" className={section===key?'active':''} aria-current={section===key?'page':undefined} onClick={()=>navigate(key)}>{t(`adminCockpit.${key==='analytics'?'matomo':key}`)}</button>)}</div>
    {loadWarnings.length>0&&<div className="admin-notice warning" role="status"><Icon name="info"/><div><strong>Teilweise Daten nicht verfügbar</strong><span>{loadWarnings.join(', ')} konnte nicht geladen werden. Andere Bereiche bleiben benutzbar.</span></div><button className="secondary compact" onClick={load}>Erneut laden</button></div>}
    {reauthOpen&&<section className="card superadmin-reauth" role="region" aria-labelledby="superadmin-reauth-title"><div><small>Sicherheitsbestätigung</small><h2 id="superadmin-reauth-title">Admin-Identität erneut bestätigen</h2><p>Diese Änderung ist sensibel. Die Bestätigung erneuert nur die getrennte Admin-Sitzung.</p></div><form onSubmit={confirmReauth}><label>Aktuelles Passwort<input type="password" autoComplete="current-password" value={reauthPassword} onChange={event=>setReauthPassword(event.target.value)} required autoFocus/></label><div className="superadmin-actions"><button className="primary" disabled={reauthBusy}><Icon name="lock"/>{reauthBusy?'Wird bestätigt …':'Bestätigen'}</button><button className="secondary" type="button" onClick={cancelReauth} disabled={reauthBusy}>Abbrechen</button></div></form></section>}
    <CockpitToolbar period={period} onPeriod={changePeriod} onRefresh={()=>{refreshInsights();load()}}/>
    {section==='overview'&&<InternalOverview period={period} refresh={insightRefresh} onLookup={lookup}/>}
    {section==='users'&&crudMode&&<SuperAdminUserCrud embedded user={user} onLogout={onLogout} initialQuery={lookupQuery}/>}
    {section==='users'&&!crudMode&&<OperationalDirectory kind="users" initialQuery={lookupQuery} refresh={directoryRefresh}>{({rows,count,query,setQuery,loading,onDetail})=><UsersSection users={rows} total={count} query={query} setQuery={setQuery} loading={loading} onDetail={onDetail} emailDrafts={emailDrafts} setEmailDraft={setEmailDraft} resetLinks={resetLinks} userBusy={userBusy} requestEmailChange={requestEmailChange} setPrimaryEmailDirect={setPrimaryEmailDirect} sendPasswordReset={sendPasswordReset} createPasswordResetLink={createPasswordResetLink} copyPasswordResetLink={copyPasswordResetLink}/>}</OperationalDirectory>}
    {section==='families'&&<OperationalDirectory kind="families" initialQuery={lookupQuery} refresh={directoryRefresh}>{({rows,count,query,setQuery,loading,onDetail})=><FamiliesSection families={rows} total={count} query={query} setQuery={setQuery} onDetail={onDetail} form={form} set={set} busy={busy} loading={loading} createFamily={createFamily} newOwnerInvite={newOwnerInvite} toggleFamily={toggleFamily}/>}</OperationalDirectory>}
    {section==='onboarding'&&<OnboardingInsights period={period} refresh={insightRefresh} onRetry={refreshInsights}/>}
    {section==='audit'&&<AuditInsights period={period} refresh={insightRefresh} onRetry={refreshInsights}/>}
    {section==='delivery'&&<><DeliveryInsights period={period} refresh={insightRefresh} onRetry={refreshInsights}/><DeliverySection smtp={smtp} setMail={setMail} smtpBusy={smtpBusy} saveSmtp={saveSmtp} testEmail={testEmail} setTestEmail={setTestEmail} sendTest={sendTest} mailJournal={mailJournal} mailJournalCount={mailJournalCount} loading={loading}/></>}
    {section==='operations'&&<><OperationsInsights refresh={insightRefresh} onRetry={refreshInsights}/><OperationsSection mailHealth={mailHealth} loading={loading} onRefresh={load}/></>}
    {section==='security'&&<><SecurityInsights period={period} refresh={insightRefresh} onRetry={refreshInsights}/><SecuritySection user={user} sessions={sessions} fresh={sessionsFresh} loading={loading} onRefresh={load}/></>}

   </main>
  </div>
 </div>;
}

function SectionHead({eyebrow,title,description,actions}){return <header className="admin-section-head"><div><small>{eyebrow}</small><h1>{title}</h1><p>{description}</p></div>{actions&&<div className="admin-section-actions">{actions}</div>}</header>}
function Metric({label,value,detail,tone=''}){return <article className={`card admin-metric ${tone}`}><span>{label}</span><strong>{value}</strong><small>{detail}</small></article>}

function UsersSection({users,total,query,setQuery,loading,emailDrafts,setEmailDraft,resetLinks,userBusy,requestEmailChange,setPrimaryEmailDirect,sendPasswordReset,createPasswordResetLink,copyPasswordResetLink,onDetail}){
 const {t}=useTranslation();
 return <><a className="secondary admin-mode-link" href={`?section=users&mode=crud&period=${supportedAdminPeriod()}`}>{t("adminCockpit.manageUsers")}</a><SectionHead eyebrow="Identity & Recovery" title="Nutzer" description="Primäre E-Mail direkt korrigieren oder verifizieren lassen und Recovery-Links unabhängig vom Mailversand erzeugen." actions={<span className="superadmin-count">{users.length} von {total}</span>}/><div className="admin-toolbar"><label>Nutzer suchen<input type="search" value={query} onChange={event=>setQuery(event.target.value)} placeholder="Name, E-Mail, Username oder ID"/></label></div><div className="superadmin-user-list">{users.map(target=>{const label=target.display_name||target.username;const emailBusy=userBusy===`email:${target.id}`;const directEmailBusy=userBusy===`direct-email:${target.id}`;const resetBusy=userBusy===`reset:${target.id}`;const resetLinkBusy=userBusy===`reset-link:${target.id}`;const resetLink=resetLinks[target.id]||'';return <article className="card superadmin-user-card" key={target.id}><div className="superadmin-user-head"><div><div className="superadmin-family-title"><h2>{label}</h2><button className="ghost" type="button" onClick={()=>onDetail?.(target.id)}>{t("adminCockpit.details")}</button>{target.is_superuser&&<span className="tenant-status active">Superadmin</span>}</div><small>@{target.username} · ID {target.id} · {target.is_active?'Aktiv':'Deaktiviert'}</small></div><span className={`tenant-status ${target.email_verified?'active':'suspended'}`}>{target.email_verified?'E-Mail bestätigt':'E-Mail unbestätigt'}</span></div><div className="superadmin-user-email"><span>Primäre E-Mail</span><strong>{target.email||'Keine E-Mail hinterlegt'}</strong>{!target.email_managed&&target.email&&<small>Legacy-Adresse · noch keine verifizierte Identity</small>}{target.pending_email&&<small>Ausstehend: {target.pending_email} · Bestätigung erforderlich</small>}</div>{target.memberships?.length>0&&<div className="superadmin-memberships">{target.memberships.map(item=><span key={item.id}>{item.family_name} · {roleLabel(item.role)}</span>)}</div>}<div className="superadmin-user-controls"><label>{`Primäre E-Mail für ${label}`}<input type="email" value={emailDrafts[target.id]||''} onChange={event=>setEmailDraft(target.id,event.target.value)} placeholder={target.email||'neu@example.com'}/></label><button className="primary" type="button" onClick={()=>setPrimaryEmailDirect(target)} disabled={!!userBusy||!(emailDrafts[target.id]||'').trim()} title="Adresse sofort als bestätigte primäre Login- und Recovery-E-Mail setzen"><Icon name="check"/>{directEmailBusy?'Wird gesetzt …':'Primäre E-Mail direkt setzen'}</button><button className="secondary" type="button" onClick={()=>requestEmailChange(target)} disabled={!!userBusy||!target.is_active||!(emailDrafts[target.id]||'').trim()} title="Alternative: neue Adresse erst per E-Mail bestätigen lassen"><Icon name="check"/>{emailBusy?'Wird eingeplant …':'Bestätigung an neue E-Mail senden'}</button><button className="secondary" type="button" onClick={()=>createPasswordResetLink(target)} disabled={!!userBusy||!target.can_password_reset} title={target.can_password_reset?'Neuen Reset-Link zum Kopieren erzeugen':'Aktives Konto mit bestätigter primärer E-Mail erforderlich'}><Icon name="lock"/>{resetLinkBusy?'Wird erzeugt …':'Reset-Link erzeugen'}</button><button className="secondary" type="button" onClick={()=>sendPasswordReset(target)} disabled={!!userBusy||!target.can_password_reset} title={target.can_password_reset?'Reset-Link an die bestätigte primäre E-Mail senden':'Aktives Konto mit bestätigter primärer E-Mail erforderlich'}><Icon name="lock"/>{resetBusy?'Wird eingeplant …':'Reset-Mail senden'}</button></div>{resetLink&&<div className="superadmin-user-email"><span>Passwort-Reset-Link</span><input aria-label={`Passwort-Reset-Link für ${label}`} value={resetLink} readOnly onFocus={event=>event.currentTarget.select()}/><small>Vertraulicher Einmal-Link. Eine neue Erzeugung macht diesen Link ungültig.</small><button className="secondary compact" type="button" onClick={()=>copyPasswordResetLink(target)}><Icon name="check"/>Link kopieren</button></div>}</article>})}{!loading&&!users.length&&<div className="card smart-empty"><strong>Keine Nutzerkonten gefunden</strong><span>Passe die Suche an oder aktualisiere die Daten.</span></div>}</div></>;
}

function FamiliesSection({families,total,query,setQuery,form,set,busy,loading,createFamily,newOwnerInvite,toggleFamily,onDetail}){
 const {t}=useTranslation();
 return <><SectionHead eyebrow="Tenant Administration" title="Familien" description="Tenant-Status, Lizenz, Owner und Einladungen verwalten – ohne globale Einsicht in Familieninhalte." actions={<span className="superadmin-count">{families.length} von {total}</span>}/><section className="card superadmin-create"><div><small>Neue Familie</small><h2>Tenant anlegen & Owner einladen</h2></div><form onSubmit={createFamily}><div className="superadmin-form-grid"><label>Familienname<input value={form.name} onChange={event=>set('name',event.target.value)} required placeholder="Familie Mustermann"/></label><label>Owner-Name<input value={form.owner_name} onChange={event=>set('owner_name',event.target.value)} placeholder="Alex Mustermann"/></label><label>Owner-E-Mail<input type="email" value={form.owner_email} onChange={event=>set('owner_email',event.target.value)} required placeholder="alex@example.com"/></label><label>Sprache<select value={form.locale} onChange={event=>set('locale',event.target.value)}><option value="de">Deutsch</option><option value="en">English</option></select></label><label>Zeitzone<input value={form.timezone} onChange={event=>set('timezone',event.target.value)} required/></label></div><button className="primary" disabled={busy||!form.name.trim()||!form.owner_email.trim()}><Icon name="members"/>{busy?'Wird angelegt …':'Familie anlegen & Einladung senden'}</button></form></section><div className="admin-toolbar"><label>Familien suchen<input type="search" value={query} onChange={event=>setQuery(event.target.value)} placeholder="Name, Slug, Owner-E-Mail oder ID"/></label></div><div className="superadmin-family-list">{families.map(family=><article className="card superadmin-family" key={family.id}><div className="superadmin-family-head"><div><div className="superadmin-family-title"><h2>{family.name}</h2><button className="ghost" type="button" onClick={()=>onDetail?.(family.id)}>{t("adminCockpit.details")}</button><span className={`tenant-status ${family.status}`}>{family.status==='active'?'Aktiv':'Gesperrt'}</span></div><small>{family.slug} · {family.locale.toUpperCase()} · {family.timezone}</small></div><strong>{family.member_count} Mitglieder</strong></div><div className="superadmin-owner"><span>Lizenz & Zugriff</span><strong>{family.entitlements?.display_name||family.entitlements?.tier||'Nicht verfügbar'}</strong>{family.entitlements?.override_tier&&<small>Expliziter Superadmin-Override</small>}</div><div className="superadmin-owner"><span>Owner</span>{family.owners.length?family.owners.map(owner=><strong key={owner.username}>{owner.display_name||owner.username}{owner.email?` · ${owner.email}`:''}</strong>):<strong>Noch kein Owner registriert</strong>}</div>{family.pending_owner_invites?.length>0&&<div className="superadmin-pending"><Icon name="info"/><span>{family.pending_owner_invites.length} offene Owner-Einladung(en) · {family.pending_owner_invites[0].email} · {ownerDeliveryLabel(family.pending_owner_invites[0].delivery_status)}{family.pending_owner_invites[0].last_sent_at?` · zuletzt ${mailDate(family.pending_owner_invites[0].last_sent_at)}`:''}</span></div>}<div className="superadmin-actions"><button className="secondary" onClick={()=>newOwnerInvite(family)} disabled={family.status!=='active'}><Icon name="members"/>Neue Owner-Einladung senden</button><button className={family.status==='active'?'ghost-danger':'secondary'} onClick={()=>toggleFamily(family)}><Icon name={family.status==='active'?'close':'check'}/>{family.status==='active'?'Familie sperren':'Familie reaktivieren'}</button></div></article>)}{!loading&&!families.length&&<div className="card smart-empty"><strong>Keine Familie gefunden</strong><span>Lege einen Tenant an oder passe die Suche an.</span></div>}</div></>;
}

function DeliverySection({smtp,setMail,smtpBusy,saveSmtp,testEmail,setTestEmail,sendTest,mailJournal,mailJournalCount,loading}){
 return <><SectionHead eyebrow="Messaging Operations" title="E-Mail & Zustellung" description="SMTP konfigurieren und redigierte Zustellhistorie prüfen. Mailbody, Tokens und vollständige Empfänger werden nicht angezeigt."/><section className="card superadmin-create superadmin-smtp"><div className="superadmin-list-head"><div><small>E-Mail / SMTP</small><h2>Transaktionsmail</h2></div><span className={`tenant-status ${smtp.configured?'active':'suspended'}`}>{smtp.configured?'Konfiguriert':'Nicht konfiguriert'}</span></div><p className="superadmin-hint">Aktive Quelle: <strong>{smtp.effective_source==='superadmin'?'Superadmin':'Umgebung'}</strong>. Das Passwort wird nie zurückgelesen oder vorausgefüllt.</p><form onSubmit={saveSmtp}><label className="superadmin-toggle"><input type="checkbox" checked={smtp.enabled} onChange={event=>setMail('enabled',event.target.checked)}/><span>SMTP aus Superadmin verwenden</span></label><div className="superadmin-smtp-grid"><label>SMTP-Host<input value={smtp.host} onChange={event=>setMail('host',event.target.value)} placeholder="smtp.example.com"/></label><label>Port<input type="number" min="1" max="65535" value={smtp.port} onChange={event=>setMail('port',event.target.value)}/></label><label>Sicherheit<select value={smtp.security} onChange={event=>setMail('security',event.target.value)}><option value="starttls">STARTTLS</option><option value="ssl">TLS/SSL</option><option value="plain">Plain</option></select></label><label>Benutzername<input autoComplete="username" value={smtp.username} onChange={event=>setMail('username',event.target.value)}/></label><label>Passwort<input type="password" autoComplete="new-password" value={smtp.password} onChange={event=>setMail('password',event.target.value)} placeholder={smtp.password_set?'Gespeichert · leer lassen zum Behalten':'SMTP-Passwort'}/></label><label>Timeout (s)<input type="number" min="1" max="120" value={smtp.timeout} onChange={event=>setMail('timeout',event.target.value)}/></label><label>Absender<input type="email" value={smtp.from_email} onChange={event=>setMail('from_email',event.target.value)} placeholder="noreply@example.com"/></label><label>Reply-To<input type="email" value={smtp.reply_to} onChange={event=>setMail('reply_to',event.target.value)} placeholder="support@example.com"/></label></div><button className="primary" disabled={smtpBusy}><Icon name="check"/>{smtpBusy?'Bitte warten …':'SMTP speichern'}</button></form><div className="superadmin-test"><label>Testadresse<input type="email" value={testEmail} onChange={event=>setTestEmail(event.target.value)} placeholder="admin@example.com"/></label><button className="secondary" type="button" onClick={sendTest} disabled={smtpBusy||!testEmail.trim()}><Icon name="check"/>Testmail senden</button></div></section><section className="superadmin-list-head superadmin-mail-head"><div><small>Redigierte Historie</small><h2>Mailjournal</h2></div><span className="superadmin-count">{mailJournalCount} Einträge</span></section><div className="card superadmin-mail-journal">{mailJournal.map(item=><div className="superadmin-mail-row" key={item.id}><div><strong>{mailTemplateLabel(item.template_key)}</strong><small>{item.recipient_hint?`${item.recipient_hint} · `:''}{mailDate(item.created_at)}</small></div><div className="superadmin-mail-state"><span className={`tenant-status ${mailStatusTone(item.status)}`}>{mailStatusLabel(item.status)}</span><small>{item.attempt_count} Versuch{item.attempt_count===1?'':'e'}{item.last_error_code?` · ${item.last_error_code}`:''}{item.sent_at?` · gesendet ${mailDate(item.sent_at)}`:''}</small></div></div>)}{!loading&&!mailJournal.length&&<div className="smart-empty"><strong>Noch keine Versandhistorie</strong><span>Transaktionsmails erscheinen hier ohne Inhalt, Tokens oder vollständige Empfängeradresse.</span></div>}</div></>;
}

function OperationsSection({mailHealth,loading,onRefresh}){
 const counts=mailHealth.counts||{};return <><SectionHead eyebrow="Operations" title="Betrieb & Health" description="Aktuell belastbare Betriebsdaten aus dem Mail-Core. Weitere Worker- und Rollup-Health-Karten werden auf ihren kanonischen Contracts ergänzt." actions={<button className="secondary compact" onClick={onRefresh} disabled={loading}><Icon name="refresh"/>Aktualisieren</button>}/><section className="admin-metrics"><Metric label="SMTP" value={mailHealth.configured?'Bereit':'Prüfen'} detail="Öffentliche Konfigurationssicht" tone={mailHealth.configured?'healthy':'attention'}/><Metric label="Queued" value={counts.queued||0} detail={`${counts.sending||0} aktuell im Versand`}/><Metric label="Retry" value={counts.retry||0} detail={`${counts.failed||0} endgültig fehlgeschlagen`} tone={(counts.retry||counts.failed)?'attention':''}/><Metric label="Latenz p50" value={formatLatency(mailHealth.latency_seconds?.p50)} detail={`p95 ${formatLatency(mailHealth.latency_seconds?.p95)}`}/></section><div className="admin-overview-grid"><section className="card admin-health-card"><small>Zustellweg</small><h2>Transactional Mail</h2><dl><div><dt>Letzte erfolgreiche Zustellung</dt><dd>{mailDate(mailHealth.last_success_at)}</dd></div><div><dt>Versendet</dt><dd>{counts.sent||0}</dd></div><div><dt>Fehlgeschlagen</dt><dd>{counts.failed||0}</dd></div></dl></section><section className="card admin-health-card"><small>Redigierte Fehlerklassen</small><h2>Letzte technische Signale</h2>{mailHealth.recent_error_classes?.length?<div className="admin-error-chips">{mailHealth.recent_error_classes.map(value=><span key={value}>{value}</span>)}</div>:<p>Keine aktuellen Fehlerklassen gemeldet.</p>}</section></div><div className="admin-notice"><Icon name="info"/><div><strong>Keine Scheingenauigkeit</strong><span>DAU/WAU/MAU, Retention und weitere #205-KPIs erscheinen hier erst, wenn die vorgesehenen #204-Rollups als stabile API verfügbar sind.</span></div></div></>;
}

function SecuritySection({user,sessions,fresh,loading,onRefresh}){
 return <><SectionHead eyebrow="Auth & Security" title="Admin-Sicherheit" description="Nur Sitzungsmetadaten der angemeldeten Admin-Identität. Tokens, IP-Historien und Credential-Daten werden nicht dargestellt." actions={<button className="secondary compact" onClick={onRefresh} disabled={loading}><Icon name="refresh"/>Aktualisieren</button>}/><section className="admin-metrics"><Metric label="Admin" value={user?.username||'—'} detail={user?.email||'Keine E-Mail'}/><Metric label="Aktive Sitzungen" value={sessions.length} detail="Kanonische, nicht widerrufene Sessions"/><Metric label="Fresh Session" value={fresh?'Ja':'Nein'} detail={fresh?'Sensible Aktionen aktuell freigegeben':'Bei Bedarf erneute Bestätigung'} tone={fresh?'healthy':'attention'}/></section><section className="card admin-session-list"><div className="superadmin-list-head"><div><small>Session Inventory</small><h2>Aktive Sitzungen</h2></div><span className="superadmin-count">{sessions.length}</span></div>{sessions.map(item=><article key={item.id} className="admin-session-row"><div><strong>{item.client||'Browser'} {item.current&&<span className="tenant-status active">Aktuell</span>}</strong><span>{authMethodLabel(item.auth_method)} · zuletzt {mailDate(item.last_seen_at)}</span></div><dl><div><dt>Erstellt</dt><dd>{mailDate(item.created_at)}</dd></div><div><dt>Fresh bis</dt><dd>{mailDate(item.fresh_until)}</dd></div><div><dt>Maximal gültig bis</dt><dd>{mailDate(item.absolute_expires_at)}</dd></div></dl></article>)}{!loading&&!sessions.length&&<div className="smart-empty"><strong>Keine Sitzungsdaten</strong><span>Aktualisiere den Bereich, um die aktuelle Admin-Sitzung zu prüfen.</span></div>}</section><div className="admin-notice"><Icon name="lock"/><div><strong>Sensitive Actions bleiben geschützt</strong><span>E-Mail-Änderungen, Recovery, Tenant-Status und SMTP-Schreibzugriffe verwenden weiterhin Fresh-Reauth und die bestehende Abuse-Protection.</span></div></div></>;
}

function ownerDeliveryLabel(status){return status==='sent'?'Versendet':status==='retrying'?'Zustellung wird erneut versucht':status==='failed'?'Versand fehlgeschlagen':'Versand wird vorbereitet'}
function roleLabel(role){return role==='owner'?'Owner':role==='adult'?'Erwachsen':role==='teen'?'Teen':role==='child'?'Kind':role==='guest'?'Gast':role}
function mailTemplateLabel(key){return key==='email.verify'?'E-Mail bestätigen':key==='password.reset'?'Passwort zurücksetzen':key==='password.changed'?'Passwort geändert':key==='email.changed'?'E-Mail geändert':key==='family.invitation'?'Familieneinladung':key||'Transaktionsmail'}
function mailStatusLabel(status){return status==='sent'?'Versendet':status==='failed'?'Fehlgeschlagen':status==='retry'?'Wiederholung':status==='sending'?'Wird gesendet':status==='canceled'?'Abgebrochen':'Eingeplant'}
function mailStatusTone(status){return status==='sent'?'active':status==='failed'||status==='canceled'?'suspended':''}
function mailDate(value){if(!value)return'—';const date=new Date(value);return Number.isNaN(date.getTime())?'—':new Intl.DateTimeFormat(undefined,{dateStyle:'medium',timeStyle:'short'}).format(date)}
function formatLatency(value){return Number.isFinite(Number(value))?`${Number(value).toLocaleString(undefined,{maximumFractionDigits:1})} s`:'—'}
function authMethodLabel(method){return method==='passkey'?'Passkey':method==='password'?'Passwort':method||'Unbekannt'}