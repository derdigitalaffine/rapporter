import {useEffect,useState} from 'react';
import {api} from './api';
import {Icon} from './icons';
import {toast} from './feedback';
import './prediction-cards.css';

export default function PredictionCards({family,onChanged}){
 const [rows,setRows]=useState([]);const [busy,setBusy]=useState('');
 async function load(){if(!family?.id)return;const result=await api(`/predictions/?family=${encodeURIComponent(family.id)}`);setRows(result.suggestions||[])}
 useEffect(()=>{load().catch(()=>setRows([]))},[family?.id]);
 async function feedback(row,action,extra={}){await api('/predictions/feedback/',{method:'POST',body:JSON.stringify({family:family.id,kind:row.kind,subject_key:row.subject_key,action,...extra})})}
 async function accept(row){setBusy(row.id);try{if(row.kind==='shopping')await api('/smart/shopping/quick-add/',{method:'POST',body:JSON.stringify({family:family.id,name:row.title,quantity:row.quantity||'',category:row.category||''})});else await api(`/routines/${row.routine_id}/done/`,{method:'POST',body:'{}'});await feedback(row,'accept');await load();await onChanged?.();toast(row.kind==='shopping'?`${row.title} zur Einkaufsliste hinzugefügt.`:`${row.title} erledigt.`,{type:'success'})}catch(error){toast(error.message||'Aktion fehlgeschlagen.',{type:'error'})}finally{setBusy('')}}
 async function quiet(row,action){setBusy(row.id);try{await feedback(row,action,action==='snooze'?{days:3}:{});await load()}catch(error){toast(error.message||'Aktion fehlgeschlagen.',{type:'error'})}finally{setBusy('')}}
 if(!rows.length)return null;
 return <section className="today-section prediction-section" aria-labelledby="prediction-heading"><div className="today-section-head"><div><small>VORSCHLÄGE</small><h2 id="prediction-heading">Könnte bald anstehen</h2></div><span>{rows.length}</span></div><div className="prediction-grid">{rows.map(row=><article className="prediction-card" key={row.id}><span className="prediction-icon"><Icon name={row.kind==='shopping'?'shopping':'history'}/></span><div className="prediction-copy"><strong>{row.title}</strong><span>Etwa alle {Math.round(row.interval_days)} Tage · {row.sample_count} Beobachtungen</span><small className={`prediction-confidence ${row.confidence_label}`}>{row.confidence_label==='high'?'Hohe':row.confidence_label==='medium'?'Mittlere':'Niedrige'} Sicherheit · {Math.round(row.confidence*100)} %</small></div><div className="prediction-actions"><button className="primary compact" disabled={busy===row.id} onClick={()=>accept(row)}><Icon name="check"/>{row.kind==='shopping'?'Hinzufügen':'Erledigt'}</button><button className="secondary compact" disabled={busy===row.id} onClick={()=>quiet(row,'snooze')}>Später</button><button className="text-button" disabled={busy===row.id} onClick={()=>quiet(row,'dismiss')}>Ausblenden</button></div></article>)}</div><p className="prediction-note"><Icon name="info"/> Vorschläge werden nur aus den Daten dieser Familie berechnet. Es wird nichts automatisch ausgeführt.</p></section>
}
