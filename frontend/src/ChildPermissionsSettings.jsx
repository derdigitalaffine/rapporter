import {useEffect,useState} from 'react';
import {api} from './api';
import {Icon} from './icons';
import './child-permissions.css';

export default function ChildPermissionsSettings({familyId}){
 const [overview,setOverview]=useState(null);const [loading,setLoading]=useState(false);const [error,setError]=useState('');
 const children=overview?.children||[];
 async function load(){if(!familyId)return;setLoading(true);setError('');try{setOverview(await api(`/baby/guardian-settings/?family=${encodeURIComponent(familyId)}`))}catch(err){setError(err.message||'Kinder-Berechtigungen konnten nicht geladen werden.')}finally{setLoading(false)}}
 useEffect(()=>{load()},[familyId]);
 if(!familyId)return <section id="children-permissions" className="card settings-section child-permissions-settings"><div><small>Familie</small><h2>Kinder & Berechtigungen</h2><p>Wähle zuerst eine Familie.</p></div></section>;
 return <section id="children-permissions" className="card settings-section child-permissions-settings" aria-labelledby="children-permissions-title">
  <div className="child-permissions-heading"><div><small>Familie</small><h2 id="children-permissions-title">Kinder & Berechtigungen</h2><p>Gesetztes Sorgerecht gewährt automatisch die geschützten Kinder- und Gesundheitsrechte. Eine zusätzliche Guardian-Freigabe ist nicht erforderlich.</p></div><span className="child-permissions-security"><Icon name="lock"/> pro Kind</span></div>
  {loading&&!overview&&<div className="child-permissions-state" role="status"><Icon name="refresh"/> Berechtigungen werden geladen …</div>}
  {error&&<div className="integration-notice" role="alert"><Icon name="warning"/><div><strong>Nicht verfügbar</strong><span>{error}</span><button type="button" className="text-button" onClick={load}>Erneut versuchen</button></div></div>}
  {!loading&&!error&&overview&&children.length===0&&<div className="empty">Für diese Familie sind aktuell keine Kinderprofile verfügbar.</div>}
  {children.length>0&&<div className="child-permissions-list">{children.map(child=>{const custody=(child.guardians||[]).filter(row=>row.source==='custody'||row.has_custody);const legacy=(child.guardians||[]).filter(row=>row.source==='legacy_guardian'&&!row.has_custody);return <article id={`child-permissions-${child.membership}`} className="child-permissions-row" key={child.baby}><span className="role-option-icon"><Icon name="members"/></span><div className="grow"><strong>{child.display_name}</strong><span>{custody.length?`Sorgeberechtigt: ${custody.map(row=>row.display_name).join(', ')}`:'Kein aktives Sorgerecht erfasst'}</span>{legacy.length>0&&<small>Übergangszugriff (Legacy Guardian): {legacy.map(row=>row.display_name).join(', ')}. Dieser Zugriff behauptet kein Sorgerecht.</small>}<small>Sorgerecht wird in den Familienbeziehungen gepflegt und ist hier nur als wirksame Berechtigung sichtbar.</small></div><span className="child-permissions-readonly">Nur Übersicht</span></article>})}</div>}
 </section>;
}