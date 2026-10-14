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

 return <section aria-labelledby={`license-${familyId}`}>
  <div className="admin-section-head"><div><small>Entitlement · #83</small><h3 id={`license-${familyId}`}>Lizenz &amp; Zugriff</h3><p>Billing gilt standardmäßig. Nur dieser explizite Override ersetzt den effektiven Lizenzgrad vorübergehend oder dauerhaft.</p></div></div>
  <dl className="admin-insight-metrics">
   <div><dt>Effektiver Lizenzgrad</dt><dd>{label(effective.tier)}</dd></div>
   <div><dt>Quelle</dt><dd>{activeOverride?'Superadmin Override':effective.origin_summary||'—'}</dd></div>
   <div><dt>Fallback</dt><dd>Automatisch</dd></div>
   <div><dt>Daten bei Downgrade</dt><dd>Bleiben erhalten</dd></div>
  </dl>
  {activeOverride&&<div className="admin-notice warning" role="note"><div><strong>Expliziter Override: {label(activeOverride.tier)}</strong><span>{activeOverride.ends_at?` bis ${new Date(activeOverride.ends_at).toLocaleString()}`:' ohne Ablaufdatum'} · Danach gilt automatisch der nächste gültige Zustand.</span></div></div>}
  <details>
   <summary>Lizenzgrad ändern</summary>
   <form className="admin-audit-filters" onSubmit={save}>
    <label>Lizenzgrad<select value={tier} onChange={event=>setTier(event.target.value)}>{tiers.map(value=><option key={value} value={value}>{label(value)}</option>)}</select></label>
    <label>Ablauf<select value={temporary?'temporary':'permanent'} onChange={event=>setTemporary(event.target.value==='temporary')}><option value="permanent">Dauerhaft</option><option value="temporary">Zeitlich begrenzt</option></select></label>
    {temporary&&<label>Gültig bis<input type="datetime-local" value={endsAt} onChange={event=>setEndsAt(event.target.value)} required/></label>}
    <label>Grund<input value={reason} onChange={event=>setReason(event.target.value)} required maxLength={500} placeholder="z. B. Support-Freischaltung"/></label>
    <button className="primary" type="submit" disabled={busy||!reason.trim()||(temporary&&!endsAt)}>{busy?'Wird gespeichert …':'Override speichern'}</button>
    {activeOverride&&<button className="secondary" type="button" disabled={busy||!reason.trim()} onClick={clear}>Override entfernen</button>}
   </form>
  </details>
  <p className="admin-cockpit-caption">Ein Downgrade löscht keine Familien- oder Premium-Daten. Schreib-/Create-Rechte werden ausschließlich über den zentralen Capability-Resolver begrenzt.</p>
  {error&&<p role="alert">{error}</p>}{notice&&<p role="status">{notice}</p>}
 </section>;
}
