import {useEffect,useMemo,useState} from 'react';
import {adminApi} from './superadmin-api';
import {Icon} from './icons';

function number(value){const parsed=Number(value);return Number.isFinite(parsed)?parsed:0}
function compact(value){return new Intl.NumberFormat(undefined,{notation:'compact',maximumFractionDigits:1}).format(number(value))}
function duration(value){const seconds=Math.max(0,number(value));const minutes=Math.floor(seconds/60);const rest=Math.round(seconds%60);return minutes?`${minutes}m ${rest}s`:`${rest}s`}
function label(value){return String(value??'—')}

function Metric({title,value,detail}){return <article className="card admin-metric"><span>{title}</span><strong>{value}</strong><small>{detail}</small></article>}

export default function SuperAdminAnalytics({onLogout}){
 const [status,setStatus]=useState(null);
 const [report,setReport]=useState(null);
 const [days,setDays]=useState(30);
 const [loading,setLoading]=useState(true);
 const [error,setError]=useState('');

 async function load(nextDays=days){
  setLoading(true);setError('');
  try{
   const state=await adminApi('/analytics/matomo/status/');setStatus(state);
   if(!state.configured){setReport(null);return}
   const value=await adminApi(`/analytics/matomo/report/?days=${nextDays}`);setReport(value);
  }catch(err){setError(err.message||'Matomo-Auswertung konnte nicht geladen werden.')}finally{setLoading(false)}
 }
 useEffect(()=>{load(days)},[days]);

 const series=useMemo(()=>Object.entries(report?.series||{}).map(([date,row])=>({date,...row})),[report]);
 const maxVisits=Math.max(1,...series.map(row=>number(row.nb_visits)));
 const summary=report?.summary||{};
 const pages=Array.isArray(report?.top_pages)?report.top_pages:[];
 const referrers=Array.isArray(report?.referrers)?report.referrers:[];
 const events=Array.isArray(report?.events)?report.events:[];

 return <div className="superadmin-shell">
  <header className="superadmin-top"><a className="superadmin-brand" href="/superadmin/"><img src="/brand/icon.svg" alt=""/><div><strong>FamilyOS</strong><span>Superadmin Analytics</span></div></a><div className="superadmin-user"><a className="secondary compact" href="/superadmin/"><Icon name="close"/>Zurück</a><button className="secondary compact" onClick={onLogout}><Icon name="logout"/>Abmelden</button></div></header>
  <main className="superadmin-main" style={{maxWidth:1280,margin:'0 auto',width:'100%'}}>
   <header className="admin-section-head"><div><small>External Analytics</small><h1>Matomo</h1><p>Aggregierte Produkt- und Nutzungsanalyse aus der externen Matomo-Instanz. Der Reporting-Token bleibt ausschließlich im Backend.</p></div><div className="admin-section-actions"><select aria-label="Analysezeitraum" value={days} onChange={event=>setDays(Number(event.target.value))}><option value="7">7 Tage</option><option value="30">30 Tage</option><option value="90">90 Tage</option></select><button className="secondary compact" onClick={()=>load(days)} disabled={loading}><Icon name="refresh"/>{loading?'Lädt …':'Aktualisieren'}</button></div></header>
   {error&&<div className="admin-notice warning" role="alert"><Icon name="info"/><div><strong>Matomo nicht verfügbar</strong><span>{error}</span></div></div>}
   {status&&!status.configured&&<section className="card smart-empty"><strong>Matomo ist noch nicht verbunden</strong><span>Setze MATOMO_BASE_URL, MATOMO_SITE_ID und MATOMO_AUTH_TOKEN im Backend-Deployment. Danach erscheint die Auswertung hier ohne Frontend-Secret.</span></section>}
   {status?.configured&&<>
    <section className="admin-metrics" aria-label="Matomo Kennzahlen"><Metric title="Besuche" value={compact(summary.nb_visits)} detail={`${days} Tage`}/><Metric title="Eindeutige Besucher" value={compact(summary.nb_uniq_visitors)} detail="Matomo Unique Visitors"/><Metric title="Aktionen" value={compact(summary.nb_actions)} detail={`${number(summary.nb_actions_per_visit).toLocaleString(undefined,{maximumFractionDigits:1})} je Besuch`}/><Metric title="Ø Besuchsdauer" value={duration(summary.avg_time_on_site)} detail={`Bounce ${label(summary.bounce_rate)}`}/></section>
    <section className="card" style={{marginBottom:20}}><div className="superadmin-list-head"><div><small>Trend</small><h2>Besuche pro Tag</h2></div><span className="superadmin-count">{report?.date_range}</span></div><div style={{display:'grid',gridTemplateColumns:`repeat(${Math.min(series.length,31)},minmax(4px,1fr))`,gap:3,alignItems:'end',height:160,padding:'16px 0'}}>{series.slice(-31).map(row=><div key={row.date} title={`${row.date}: ${number(row.nb_visits)} Besuche`} style={{height:`${Math.max(4,number(row.nb_visits)/maxVisits*100)}%`,background:'currentColor',opacity:.55,borderRadius:'4px 4px 0 0'}}/>)}</div></section>
    <div className="admin-overview-grid">
     <section className="card admin-health-card"><small>Content</small><h2>Top-Seiten</h2><div className="superadmin-mail-journal">{pages.map((item,index)=><div className="superadmin-mail-row" key={`${item.label}-${index}`}><div><strong>{label(item.label)}</strong><small>{compact(item.nb_hits)} Aktionen</small></div><div className="superadmin-mail-state"><strong>{compact(item.nb_visits)}</strong><small>Besuche · {label(item.bounce_rate)}</small></div></div>)}{!pages.length&&<p>Keine Seitendaten im Zeitraum.</p>}</div></section>
     <section className="card admin-health-card"><small>Acquisition</small><h2>Referrer</h2><div className="superadmin-mail-journal">{referrers.map((item,index)=><div className="superadmin-mail-row" key={`${item.label}-${index}`}><div><strong>{label(item.label)}</strong><small>{label(item.nb_actions)} Aktionen</small></div><div className="superadmin-mail-state"><strong>{compact(item.nb_visits)}</strong><small>Besuche</small></div></div>)}{!referrers.length&&<p>Keine Referrer-Daten im Zeitraum.</p>}</div></section>
    </div>
    <section className="card admin-health-card" style={{marginTop:20}}><small>Product Analytics</small><h2>Event-Kategorien</h2><div className="superadmin-mail-journal">{events.map((item,index)=><div className="superadmin-mail-row" key={`${item.label}-${index}`}><div><strong>{label(item.label)}</strong><small>{compact(item.nb_events)} Events · {compact(item.nb_events_with_value)} mit Wert</small></div><div className="superadmin-mail-state"><strong>{compact(item.nb_visits)}</strong><small>Besuche</small></div></div>)}{!events.length&&<div className="smart-empty"><strong>Noch keine Produkt-Events</strong><span>Pageviews funktionieren unabhängig davon. Für Feature-Funnels sollten wir eine feste, PII-freie Event-Taxonomie anbinden.</span></div>}</div></section>
    <div className="admin-notice" style={{marginTop:20}}><Icon name="lock"/><div><strong>Privacy Boundary</strong><span>Diese Ansicht fordert nur aggregierte Reports an. Raw Visits, IP-Adressen, Visitor IDs, E-Mails, Familiennamen, Dokumenttitel, Freitexte und Auth-Tokens werden nicht an den Browser ausgegeben.</span></div></div>
   </>}
  </main>
 </div>;
}
