import {useEffect,useState} from 'react';
import {adminApi} from './superadmin-api';

const LABELS={light:'Light',premium:'Premium',vip:'VIP'};
const label=tier=>LABELS[tier]||tier||'—';

export default function SuperAdminEntitlementControl({familyId,control,onChanged}){
 const effective=control?.effective||{};
 const activeOverride=control?.override||null;
 const tiers=control?.available_tiers||['light','premium','vip'];
 const [tier,setTier]=useState(effective.tier||'light');
 const [temporary,setTemporary]=useState(Boolean(activeOverride?.ends_at));
 const [endsAt,setEndsAt]=useState(activeOverride?.ends_at?String(activeOverride.ends_at).slice(0,16):'');
 const [reason,setReason]=useState('');
 const [busy,setBusy]=useState(false);
 const [error,setError]=useState('');
 const [notice,setNotice]=useState('');
 useEffect(()=>{setTier(effective.tier||'light');setTemporary(Boolean(activeOverride?.ends_at));setEndsAt(activeOverride?.ends_at?String(activeOverride.ends_at).slice(0,16):'');setReason('');setError('');setNotice('')},[familyId,effective.tier,activeOverride?.id,activeOverride?.ends_at]);

 async function save(event){
  event.preventDefault();if(!reason.trim())return;setBusy(true);setError('');setNotice('');
  try{
   const payload={tier,reason:reason.trim()};
   if(temporary&&endsAt)payload.ends_at=new Date(endsAt).toISOString();
   await adminApi(`/families/${familyId}/entitlement-override/`,{method:'PUT',body:JSON.stringify(payload)});
   setNotice(`${label(tier)} ist als expliziter Superadmin-Override aktiv.`);setReason('');onChanged?.();
  }catch(err){setError(err.message||'Lizenz-Override konnte nicht gespeichert werden.')}finally{setBusy(false)}
 }
 async function clear(){
  if(!activeOverride||!reason.trim())return;setBusy(true);setError('');setNotice('');
  try{
   await adminApi(`/families/${familyId}/entitlement-override/`,{method:'DELETE',body:JSON.stringify({reason:reason.trim()})});
   setNotice('Override entfernt. Der nächste gültige Billing-/Grant-Zustand gilt automatisch.');setReason('');onChanged?.();
  }catch(err){setError(err.message||'Lizenz-Override konnte nicht entfernt werden.')}finally{setBusy(false)}
 }

 const source=activeOverride?'Superadmin Override':effective.origin_summary||'Standard';
 const overrideUntil=activeOverride?.ends_at?new Date(activeOverride.ends_at).toLocaleString():null;

 return <section className="admin-entitlement" aria-labelledby={`license-${familyId}`}>
  <header className="admin-entitlement-head">
   <div>
    <small>Entitlement · #83</small>
    <h3 id={`license-${familyId}`}>Lizenz &amp; Zugriff</h3>
    <p>Der effektive Zugriff wird zentral auf Familienebene aufgelöst. Billing bleibt unverändert; ein Superadmin-Override überlagert den Lizenzgrad nur so lange, wie er aktiv ist.</p>
   </div>
   <div className="admin-license-state" aria-label={`Aktueller Lizenzgrad ${label(effective.tier)}`}>
    <span>Aktueller Lizenzgrad</span>
    <strong>{label(effective.tier)}</strong>
    <small>{source}</small>
   </div>
  </header>

  {activeOverride&&<div className="admin-notice warning admin-entitlement-notice" role="note">
   <div><strong>Superadmin-Override aktiv</strong><span>{label(activeOverride.tier)}{overrideUntil?` bis ${overrideUntil}`:' ohne Ablaufdatum'}. Danach gilt automatisch der nächste gültige Billing-/Grant-Zustand.</span></div>
  </div>}

  <dl className="admin-entitlement-facts">
   <div><dt>Fallback</dt><dd>Automatisch auf den nächsten gültigen Grant</dd></div>
   <div><dt>Downgrade</dt><dd>Keine Löschung von Familien- oder Premium-Daten</dd></div>
   <div><dt>Durchsetzung</dt><dd>Zentral über Capabilities, auch serverseitig</dd></div>
  </dl>

  <details className="admin-entitlement-editor">
   <summary><span>Lizenzgrad ändern</span><small>Auditierter Override mit Pflichtbegründung</small></summary>
   <form onSubmit={save}>
    <fieldset disabled={busy}>
     <legend>Override konfigurieren</legend>
     <div className="admin-entitlement-grid">
      <label>Lizenzgrad<select value={tier} onChange={event=>setTier(event.target.value)}>{tiers.map(value=><option key={value} value={value}>{label(value)}</option>)}</select></label>
      <label>Gültigkeit<select value={temporary?'temporary':'permanent'} onChange={event=>setTemporary(event.target.value==='temporary')}><option value="permanent">Dauerhaft</option><option value="temporary">Zeitlich begrenzt</option></select></label>
      {temporary&&<label>Gültig bis<input type="datetime-local" value={endsAt} onChange={event=>setEndsAt(event.target.value)} required/></label>}
      <label className="admin-entitlement-reason">Grund<span className="admin-field-hint">Pflichtfeld · wird im Audit protokolliert</span><input value={reason} onChange={event=>setReason(event.target.value)} required maxLength={500} placeholder="z. B. Support-Freischaltung"/></label>
     </div>
     <div className="admin-entitlement-actions">
      <button className="primary" type="submit" disabled={!reason.trim()||(temporary&&!endsAt)}>{busy?'Wird gespeichert …':'Override speichern'}</button>
      {activeOverride&&<button className="secondary" type="button" disabled={!reason.trim()} onClick={clear}>Aktiven Override entfernen</button>}
     </div>
    </fieldset>
   </form>
  </details>

  <p className="admin-cockpit-caption admin-entitlement-footnote">Lizenzwechsel verändern nur den effektiven Zugriff. Bestehende Daten bleiben gespeichert und stehen nach einer erneuten Freischaltung ohne Wiederherstellungsmigration wieder zur Verfügung.</p>
  <div className="admin-entitlement-feedback" aria-live="polite">{error&&<p className="admin-form-message error" role="alert">{error}</p>}{notice&&<p className="admin-form-message success" role="status">{notice}</p>}</div>
 </section>;
}
