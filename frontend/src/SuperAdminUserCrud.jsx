import {useEffect,useRef,useState} from 'react';
import {useTranslation} from 'react-i18next';
import './superadmin-cockpit-i18n';
import {useAdminDirectory,DirectoryTools,OperationalDetail,supportedAdminPeriod} from './SuperAdminInsights';
import {adminApi} from './superadmin-api';
import {toast} from './feedback';
import './superadmin-user-crud.css';

const blankUser={username:'',email:'',first_name:'',last_name:'',password:'',is_active:true,is_superuser:false};

function pushRoute(search=''){
 const url=new URL(window.location.href);
 url.search=search;
 window.history.pushState({},'',`${url.pathname}${url.search}`);
}

export default function SuperAdminUserCrud({user,onLogout,embedded=false,initialQuery=''}){
 const {t}=useTranslation();
 const Content=embedded?'div':'main';
 const [query,setQuery]=useState(initialQuery),[status,setStatus]=useState(''),[sort,setSort]=useState('username'),[offset,setOffset]=useState(0),[refresh,setRefresh]=useState(0),[detail,setDetail]=useState(null);
 const directory=useAdminDirectory({kind:'users',query,status,sort,offset,refresh});
 const users=directory.rows,loading=directory.loading;
 useEffect(()=>{setQuery(initialQuery);setOffset(0)},[initialQuery]);
 useEffect(()=>setDetail(null),[query,status,sort,offset]);
 const [busy,setBusy]=useState('');
 const [editor,setEditor]=useState(null);
 const [deleteTarget,setDeleteTarget]=useState(null);
 const [deleteChecked,setDeleteChecked]=useState(false);
 const [deleteText,setDeleteText]=useState('');
 const [reauthOpen,setReauthOpen]=useState(false);
 const [reauthPassword,setReauthPassword]=useState('');
 const [reauthBusy,setReauthBusy]=useState(false);
 const pendingSensitive=useRef(null);

 async function load(){setRefresh(value=>value+1)}
 async function runSensitive(action){
  try{return await action()}
  catch(error){
   if(error.status===403){pendingSensitive.current=action;setReauthOpen(true);return null}
   throw error;
  }
 }

 async function confirmReauth(event){
  event.preventDefault();
  if(!reauthPassword)return;
  setReauthBusy(true);
  try{
   await adminApi('/auth/reauth/password/',{method:'POST',body:JSON.stringify({password:reauthPassword})});
   const action=pendingSensitive.current;
   pendingSensitive.current=null;
   setReauthOpen(false);
   setReauthPassword('');
   toast('Admin-Identität bestätigt.',{type:'success'});
   if(action)await action();
  }catch(error){toast(error.message||'Bestätigung fehlgeschlagen.',{type:'error'})}
  finally{setReauthBusy(false)}
 }
 function cancelReauth(){pendingSensitive.current=null;setReauthOpen(false);setReauthPassword('')}

 function openCreate(){setEditor({mode:'create',value:{...blankUser}})}
 function openEdit(target){setEditor({mode:'edit',value:{
  id:target.id,
  username:target.username||'',
  email:target.email||'',
  first_name:target.first_name||'',
  last_name:target.last_name||'',
  password:'',
  is_active:Boolean(target.is_active),
  is_superuser:Boolean(target.is_superuser),
 }})}
 function setField(key,value){setEditor(current=>({...current,value:{...current.value,[key]:value}}))}

 async function saveUser(event){
  event.preventDefault();
  if(!editor)return;
  const creating=editor.mode==='create';
  const payload={...editor.value};
  delete payload.id;
  if(!creating&&!payload.password)delete payload.password;
  const action=async()=>{
   setBusy(creating?'create':`edit:${editor.value.id}`);
   try{
    await adminApi(creating?'/users/':`/users/${editor.value.id}/`,{
     method:creating?'POST':'PATCH',
     body:JSON.stringify(payload),
    });
    setEditor(null);
    await load();
    toast(creating?'Nutzer wurde angelegt.':'Nutzer wurde gespeichert.',{type:'success'});
   }finally{setBusy('')}
  };
  try{await runSensitive(action)}catch(error){toast(error.message||'Nutzer konnte nicht gespeichert werden.',{type:'error'})}
 }

 async function toggleActive(target){
  const next=!target.is_active;
  const action=async()=>{
   setBusy(`status:${target.id}`);
   try{
    await adminApi(`/users/${target.id}/`,{method:'PATCH',body:JSON.stringify({is_active:next})});
    await load();
    toast(next?'Nutzer wurde reaktiviert.':'Nutzer wurde deaktiviert.',{type:'success'});
   }finally{setBusy('')}
  };
  try{await runSensitive(action)}catch(error){toast(error.message||'Status konnte nicht geändert werden.',{type:'error'})}
 }

 function openDelete(target){setDeleteTarget(target);setDeleteChecked(false);setDeleteText('')}
 function closeDelete(){if(busy.startsWith('delete:'))return;setDeleteTarget(null);setDeleteChecked(false);setDeleteText('')}
 async function purgeUser(event){
  event.preventDefault();
  if(!deleteTarget||!deleteChecked||deleteText!==deleteTarget.username)return;
  const target=deleteTarget;
  const action=async()=>{
   setBusy(`delete:${target.id}`);
   try{
    const result=await adminApi(`/users/${target.id}/`,{
     method:'DELETE',
     body:JSON.stringify({confirm:true,confirm_username:deleteText}),
    });
    setDeleteTarget(null);setDeleteChecked(false);setDeleteText('');
    await load();
    toast(`Nutzer dauerhaft gelöscht (${result?.deleted_rows||0} DB-Zeilen).`,{type:'success'});
   }finally{setBusy('')}
  };
  try{await runSensitive(action)}catch(error){toast(error.message||'Nutzer konnte nicht gelöscht werden.',{type:'error'})}
 }

 return <div className={embedded?"user-crud-shell admin-embedded":"user-crud-shell"}>
  {!embedded&&<header className="user-crud-top">
   <button className="superadmin-brand" type="button" onClick={()=>pushRoute('')} aria-label="Zur Superadmin-Übersicht"><img src="/brand/icon.svg" alt=""/><div><strong>FamilyOS</strong><span>Superadmin · Nutzer</span></div></button>
   <div className="user-crud-top-actions"><button className="secondary compact" type="button" onClick={()=>pushRoute('?section=users&mode=recovery')}>Identity & Recovery</button><button className="secondary compact" type="button" onClick={onLogout}>Abmelden</button></div>
  </header>}
  <Content className="user-crud-main">
   <section className="user-crud-heading"><div><small>Superadmin · vollständige Benutzerverwaltung</small><h1>{t("adminCockpit.manageUsers")}</h1><p>Kompakte Liste mit Create, Edit, De-/Reaktivierung und dauerhaftem Purge nutzereigener Daten.</p></div><button className="primary" type="button" onClick={openCreate}>Nutzer anlegen</button></section>
   <a className="secondary admin-mode-link" href={`?section=users&mode=recovery&period=${supportedAdminPeriod()}`}>{t("adminCockpit.recovery")}</a><div className="card user-crud-toolbar"><label>{t("adminCockpit.search")}<input type="search" value={query} onChange={event=>{setQuery(event.target.value);setOffset(0)}} placeholder="Name, E-Mail, Username oder ID"/></label><button className="secondary compact" type="button" onClick={load} disabled={loading}>{loading?'Lädt …':'Aktualisieren'}</button></div>

   <DirectoryTools kind="users" status={status} setStatus={setStatus} sort={sort} setSort={setSort} offset={offset} setOffset={setOffset} count={directory.count} shown={users.length}/>{directory.error&&<div role="alert"><p>{t("adminCockpit.unavailable")}</p><button className="secondary" type="button" onClick={load}>{t("adminCockpit.retry")}</button></div>}{detail&&<OperationalDetail kind="users" id={detail} onClose={()=>setDetail(null)}/>}
   {editor&&<section className="card user-crud-editor" aria-labelledby="user-editor-title"><div className="user-crud-editor-head"><div><small>{editor.mode==='create'?'Create':'Update'}</small><h2 id="user-editor-title">{editor.mode==='create'?'Nutzer anlegen':`@${editor.value.username} bearbeiten`}</h2></div><button className="secondary compact" type="button" onClick={()=>setEditor(null)} disabled={!!busy}>Schließen</button></div><form onSubmit={saveUser}><div className="user-crud-form-grid"><label>Benutzername<input value={editor.value.username} onChange={event=>setField('username',event.target.value)} required/></label><label>E-Mail<input type="email" value={editor.value.email} onChange={event=>setField('email',event.target.value)} placeholder="optional@example.com"/></label><label>Vorname<input value={editor.value.first_name} onChange={event=>setField('first_name',event.target.value)}/></label><label>Nachname<input value={editor.value.last_name} onChange={event=>setField('last_name',event.target.value)}/></label><label>Passwort<input type="password" value={editor.value.password} onChange={event=>setField('password',event.target.value)} required={editor.mode==='create'} autoComplete="new-password" placeholder={editor.mode==='create'?'Erforderlich':'Leer lassen = unverändert'}/></label><label className="user-crud-check"><input type="checkbox" checked={editor.value.is_active} onChange={event=>setField('is_active',event.target.checked)}/>Aktiv</label><label className="user-crud-check"><input type="checkbox" checked={editor.value.is_superuser} onChange={event=>setField('is_superuser',event.target.checked)}/>Superadmin</label></div><div className="user-crud-editor-actions"><button className="primary" disabled={!!busy}>{busy?'Speichert …':'Speichern'}</button><button className="secondary" type="button" onClick={()=>setEditor(null)} disabled={!!busy}>Abbrechen</button></div></form></section>}

   <section className="card user-crud-table-wrap" aria-label="Nutzerliste"><div className="user-crud-table"><div className="user-crud-row user-crud-header"><span>Nutzer</span><span>E-Mail</span><span>Status</span><span>Rollen / Familien</span><span>Aktionen</span></div>{users.map(target=><div className="user-crud-row" key={target.id}><div><strong>{target.display_name||target.username}</strong><small>@{target.username} · ID {target.id}</small></div><div><span>{target.email||'—'}</span><small>{target.email_verified?'bestätigt':target.email?'unbestätigt':'keine Identity'}</small></div><div><span className={`tenant-status ${target.is_active?'active':'suspended'}`}>{target.is_active?'Aktiv':'Deaktiviert'}</span>{target.is_superuser&&<small>Superadmin</small>}</div><div><span>{target.is_superuser?'Superadmin':'Nutzer'}</span><small>{target.family_count||0} Familie(n)</small></div><div className="user-crud-actions"><button className="ghost" type="button" onClick={()=>setDetail(target.id)}>{t("adminCockpit.details")}</button><button className="secondary compact" type="button" onClick={()=>openEdit(target)} disabled={!!busy}>Bearbeiten</button><button className="secondary compact" type="button" onClick={()=>toggleActive(target)} disabled={!!busy||target.id===user?.id}>{busy===`status:${target.id}`?'…':target.is_active?'Deaktivieren':'Aktivieren'}</button><button className="danger compact" type="button" onClick={()=>openDelete(target)} disabled={!!busy||target.id===user?.id}>Löschen</button></div></div>)}{!loading&&!users.length&&<div className="smart-empty"><strong>Keine Nutzer gefunden</strong><span>Suche anpassen oder einen neuen Nutzer anlegen.</span></div>}</div></section>
  </Content>

  {deleteTarget&&<div className="user-crud-modal-backdrop" role="presentation"><section className="card user-crud-modal" role="dialog" aria-modal="true" aria-labelledby="purge-title"><small>Dauerhafter DB-Purge</small><h2 id="purge-title">@{deleteTarget.username} endgültig löschen?</h2><p>CASCADE-Daten dieses Nutzers werden aus der Datenbank entfernt. Geteilte Familien-/Tenant-Daten mit SET_NULL-Referenzen bleiben erhalten.</p><form onSubmit={purgeUser}><label className="user-crud-check danger-check"><input type="checkbox" checked={deleteChecked} onChange={event=>setDeleteChecked(event.target.checked)}/>Ich bestätige, dass diese Aktion nicht rückgängig gemacht werden kann.</label><label>Zur zweiten Bestätigung exakt <strong>{deleteTarget.username}</strong> eingeben<input value={deleteText} onChange={event=>setDeleteText(event.target.value)} autoComplete="off"/></label><div className="user-crud-editor-actions"><button className="danger" disabled={!deleteChecked||deleteText!==deleteTarget.username||!!busy}>{busy===`delete:${deleteTarget.id}`?'Wird gelöscht …':'Dauerhaft löschen'}</button><button className="secondary" type="button" onClick={closeDelete} disabled={!!busy}>Abbrechen</button></div></form></section></div>}

  {reauthOpen&&<div className="user-crud-modal-backdrop"><section className="card user-crud-modal" role="dialog" aria-modal="true" aria-labelledby="reauth-title"><small>Sicherheitsbestätigung</small><h2 id="reauth-title">Admin-Identität erneut bestätigen</h2><p>Sensible Nutzeränderungen erfordern eine frische Superadmin-Sitzung.</p><form onSubmit={confirmReauth}><label>Aktuelles Passwort<input type="password" value={reauthPassword} onChange={event=>setReauthPassword(event.target.value)} autoComplete="current-password" required autoFocus/></label><div className="user-crud-editor-actions"><button className="primary" disabled={reauthBusy}>{reauthBusy?'Wird bestätigt …':'Bestätigen'}</button><button className="secondary" type="button" onClick={cancelReauth} disabled={reauthBusy}>Abbrechen</button></div></form></section></div>}
 </div>;
}
