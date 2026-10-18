import {useEffect,useState} from 'react';
import {api} from './api';
import {Icon} from './icons';
import {featureHref} from './navigation';
import i18n from './i18n';
import './meal-today.css';

const slotOrder=slot=>({'Frühstück':0,'Mittagessen':1,'Abendessen':2}[slot]??10);

export default function MealTodayWidget({family}){
 const de=i18n.language?.startsWith('de');
 const [data,setData]=useState(null);const [error,setError]=useState(false);
 useEffect(()=>{let live=true;setError(false);api(`/meal-plan/today/?family=${encodeURIComponent(family.id)}`).then(value=>{if(live)setData(value)}).catch(()=>{if(live)setError(true)});return()=>{live=false}},[family.id]);
 const entries=(data?.entries||[]).slice().sort((a,b)=>slotOrder(a.slot)-slotOrder(b.slot)||a.slot.localeCompare(b.slot));
 return <section className="today-section meal-today-widget" data-testid="meal-today-widget">
  <div className="today-section-head"><div><small>{de?'HEUTE ESSEN':'TODAYʼS MEALS'}</small><h2>{de?'Was gibt es heute?':'What are we eating today?'}</h2></div><span className="meal-today-icon" aria-hidden="true"><Icon name="calendar"/></span></div>
  {error?<p className="today-calm">{de?'Essensplan gerade nicht verfügbar.':'Meal plan is currently unavailable.'}</p>:data===null?<p className="today-calm" role="status">{de?'Essensplan wird geladen …':'Loading meal plan …'}</p>:entries.length?<div className="meal-today-list">{entries.map(entry=><div key={entry.id} className="meal-today-row"><small>{entry.slot}</small><strong>{entry.display_title}</strong></div>)}</div>:<p className="today-calm">{de?'Heute ist noch nichts geplant.':'Nothing is planned for today yet.'}</p>}
  <a className="today-link" href={featureHref('meals',{date:data?.date||undefined,view:'day'})}>{entries.length?(de?'Tagesplan öffnen':'Open day plan'):(de?'Heute planen':'Plan today')} <Icon name="next"/></a>
 </section>;
}
