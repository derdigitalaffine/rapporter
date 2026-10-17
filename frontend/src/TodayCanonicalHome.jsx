import {useMemo,useState} from 'react';
import TodayOverview from './TodayOverview';
import TodayLayout from './TodayLayout';
import OnboardingCard from './OnboardingCard';
import {Icon} from './icons';
import i18n from './i18n';
import {formatDateTime} from './locale';
import {featureHref} from './navigation';
import {isWarningEvent} from './calendar-event-ui';
import {useTodayCoreData} from './todayCoreData';
import './onboarding.css';
import './today-layout.css';
import './today-layout-v2.css';

const defaultPrioritySettings={enabled:true,tasks:true,events:true};
const settledActionStates=new Set(['done','done_today','paused']);

function firstName(person){
 const label=String(person?.display_name||person?.username||'').trim();
 return label.split(/\s+/)[0]||'';
}

function zonedHour(timeZone){
 const parts=new Intl.DateTimeFormat('en-CA',{timeZone:timeZone||'UTC',hour:'2-digit',hourCycle:'h23'}).formatToParts(new Date());
 return Number(parts.find(part=>part.type==='hour')?.value||0);
}

function greeting(family,language){
 const de=language.startsWith('de');
 const hour=zonedHour(family?.timezone);
 const part=hour<12?(de?'Guten Morgen':'Good morning'):hour<18?(de?'Guten Tag':'Good afternoon'):(de?'Guten Abend':'Good evening');
 return `${part}, ${family?.name||(de?'Familie':'family')}!`;
}

function readSettings(key){
 try{
  const value=JSON.parse(localStorage.getItem(key)||'null');
  if(!value||typeof value!=='object')return defaultPrioritySettings;
  return {enabled:value.enabled!==false,tasks:value.tasks!==false,events:value.events!==false};
 }catch{return defaultPrioritySettings}
}

function openShoppingCount(data){
 return (data?.shopping_lists||[]).reduce((sum,list)=>{
  if(Number.isFinite(Number(list?.open_count)))return sum+Number(list.open_count);
  return sum+(list?.items||[]).filter(item=>!item.checked).length;
 },0);
}

function ModuleShortcut({page,icon,title,value,detail,language}){
 const de=language.startsWith('de');
 return <section className="today-section today-module-shortcut">
  <div className="today-module-shortcut-main"><span className="today-module-shortcut-icon"><Icon name={icon}/></span><div><small>{de?'MODUL':'MODULE'}</small><h2>{title}</h2>{value!==undefined&&value!==null&&<strong className="today-module-shortcut-value">{value}</strong>}</div></div>
  <a className="today-link" href={featureHref(page)}>{detail} <Icon name="next"/></a>
 </section>;
}

function priorityEvent(event){
 if(isWarningEvent(event))return true;
 const value=String(event?.priority||event?.importance||event?.payload?.priority||event?.payload?.importance||'').toLowerCase();
 return ['high','critical','urgent','important'].includes(value);
}

function priorityAction(action){
 if(!action||settledActionStates.has(action.state))return false;
 return action.state==='overdue'||action.priority==='high'||['critical','high'].includes(action.urgency)||Number(action.ranking?.bucket)<=2;
}

function PriorityBanner({family,language,settings}){
 const core=useTodayCoreData(family);
 const de=language.startsWith('de');
 const tasks=settings.tasks?(core.actions||[]).filter(priorityAction):[];
 const events=settings.events?(core.events||[]).filter(priorityEvent):[];
 const total=tasks.length+events.length;
 if(!settings.enabled||core.loading||total===0)return null;
 const first=[...tasks.map(item=>item.title),...events.map(item=>item.title)].filter(Boolean).slice(0,2);
 const target=tasks.length?'todo':'calendar';
 const label=de?(total===1?'1 wichtiger Punkt steht an':`${total} wichtige Punkte stehen an`):(total===1?'1 important item needs attention':`${total} important items need attention`);
 return <aside className="today-priority-banner" role="alert" data-testid="today-priority-banner">
  <span className="today-priority-banner-icon"><Icon name="warning"/></span>
  <div className="grow"><strong>{label}</strong>{first.length>0&&<span>{first.join(' · ')}</span>}</div>
  <a href={featureHref(target)}>{de?'Ansehen':'View'} <Icon name="next"/></a>
 </aside>;
}

function PrioritySettings({language,settings,onChange}){
 const de=language.startsWith('de');
 return <fieldset className="today-priority-settings" data-testid="today-priority-settings">
  <legend>{de?'Prioritätsbanner':'Priority banner'}</legend>
  <p>{de?'Zeigt oben nur wirklich wichtige offene Punkte an.':'Only shows genuinely important open items at the top.'}</p>
  <label><input type="checkbox" checked={settings.enabled} onChange={event=>onChange('enabled',event.target.checked)}/><span>{de?'Prioritätsbanner anzeigen':'Show priority banner'}</span></label>
  <label><input type="checkbox" checked={settings.tasks} onChange={event=>onChange('tasks',event.target.checked)} disabled={!settings.enabled}/><span>{de?'Wichtige und überfällige Aufgaben':'Important and overdue tasks'}</span></label>
  <label><input type="checkbox" checked={settings.events} onChange={event=>onChange('events',event.target.checked)} disabled={!settings.enabled}/><span>{de?'Wichtige Termine und Warnungen':'Important events and warnings'}</span></label>
 </fieldset>;
}

export default function TodayCanonicalHome({data,family,open,unreadMessages=null,viewer=null}){
 const language=i18n.language;
 const displayFamily={...family,name:firstName(viewer)||family.name};
 const identity=String(viewer?.user||viewer?.id||'self');
 const layoutKey=`famuhle-today-home-layout:v1:${family.id}:${identity}`;
 const priorityKey=`famuhle-today-home-priority:v1:${family.id}:${identity}`;
 const [prioritySettings,setPrioritySettings]=useState(()=>readSettings(priorityKey));
 const changePriority=(key,value)=>setPrioritySettings(current=>{
  const next={...current,[key]:value};
  try{localStorage.setItem(priorityKey,JSON.stringify(next))}catch{}
  return next;
 });
 const de=language.startsWith('de');
 const widgets=useMemo(()=>({
  overview:<TodayOverview family={family} data={data} unreadMessages={unreadMessages} language={language}/>,
  shopping:<ModuleShortcut page="shopping" icon="shopping" title={de?'Einkauf':'Shopping'} value={openShoppingCount(data)} detail={de?'Liste öffnen':'Open list'} language={language}/>,
  inbox:<ModuleShortcut page="inbox" icon="inbox" title={de?'Nachrichten':'Messages'} value={unreadMessages} detail={de?'Postfach öffnen':'Open inbox'} language={language}/>,
  notes:<ModuleShortcut page="notes" icon="edit" title={de?'Notizzettel':'Notes'} detail={de?'Notizen öffnen':'Open notes'} language={language}/>,
  weather:<ModuleShortcut page="weather" icon="weather" title={de?'Wetter':'Weather'} detail={de?'Wetter öffnen':'Open weather'} language={language}/>,
  trip:<ModuleShortcut page="trips" icon="route" title={de?'Reise':'Trip'} detail={de?'Reisen öffnen':'Open trips'} language={language}/>,
  loyalty:<ModuleShortcut page="loyalty" icon="favorite" title={de?'Bonuskarten':'Loyalty cards'} detail={de?'Karten öffnen':'Open cards'} language={language}/>,
 }),[family.id,data,unreadMessages,language,de]);
 const header=<header className="today-hero"><div className="today-greeting"><p>{formatDateTime(language,new Date(),{timeZone:family.timezone||'UTC',weekday:'long',day:'numeric',month:'long'})} · {family.name}</p><h1>{greeting(displayFamily,language)}</h1></div></header>;
 return <div data-testid="today-canonical-home">
  <TodayLayout
   family={family}
   header={header}
   onboarding={<OnboardingCard family={family} data={data} open={open}/>}
   widgets={widgets}
   persistence="local"
   storageKey={layoutKey}
   editIcon="settings"
   gridTestId="today-canonical-grid"
   topNotice={<PriorityBanner family={family} language={language} settings={prioritySettings}/>}
   editorExtras={<PrioritySettings language={language} settings={prioritySettings} onChange={changePriority}/>}
  />
 </div>;
}
