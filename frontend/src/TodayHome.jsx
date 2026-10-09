import i18n from './i18n';
import {formatDateTime} from './locale';
import {Icon} from './icons';
import OnboardingCard from './OnboardingCard';
import {requestCreate} from './create-request';
import './onboarding.css';
import './weather-i18n';
import {speed,temperature,weatherDescription} from './weather-ui';

const isWarning=e=>e?.type?.includes('warning');
const isToday=date=>date&&new Date(date).toDateString()===new Date().toDateString();
const isOverdue=task=>task?.due_at&&!task.completed_at&&new Date(task.due_at)<new Date()&&!isToday(task.due_at);
const timeValue=e=>e?.starts_at?new Date(e.starts_at).getTime():Number.MAX_SAFE_INTEGER;

function formatEventDate(value,t,language){
  if(!value)return '';
  const date=new Date(value);
  if(isToday(value))return `${t('today')} · ${formatDateTime(language,date,{timeStyle:'short'})}`;
  return formatDateTime(language,date,{weekday:'short',day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit'});
}

function taskDueLabel(task,t,language){
  if(!task.due_at)return '';
  const date=new Date(task.due_at);
  if(isOverdue(task))return `${t('due')} · ${formatDateTime(language,date,{dateStyle:'short'})}`;
  if(isToday(task.due_at))return `${t('today')} ${formatDateTime(language,date,{timeStyle:'short'})}`;
  return formatDateTime(language,date,{dateStyle:'medium'});
}

function currentWeatherMeta(current,t){
  if(!current)return '';
  const parts=[weatherDescription(current.weather_code,t)];
  if(current.apparent_temperature!==null&&current.apparent_temperature!==undefined)parts.push(t('weatherUi.feelsLike',{value:temperature(current.apparent_temperature)}));
  if(current.wind_speed!==null&&current.wind_speed!==undefined)parts.push(`${t('weatherUi.wind')} ${speed(current.wind_speed)}`);
  return parts.filter(Boolean).join(' · ');
}

function routineIsDue(routine){
  if(routine.active===false)return false;
  if(!routine.last_done_at)return true;
  const interval=Number(routine.suggested_interval_days)||0;
  if(!interval)return false;
  return Date.now()-new Date(routine.last_done_at).getTime()>=interval*86400000;
}

function EventIcon({event}){
  const name=isWarning(event)?'warning':event.type?.includes('weather')?'weather':event.type?.includes('transit')?'transit':event.type?.includes('school')?'school':event.type?.includes('waste')?'waste':'calendar';
  return <span className={`today-event-icon ${isWarning(event)?'warning':''}`}><Icon name={name}/></span>;
}

function TaskRow({task,onTask,t,language}){
  const due=taskDueLabel(task,t,language);
  return <div className={`today-task-row ${isOverdue(task)?'overdue':''}`}>
    <button className="today-check" onClick={()=>onTask(task)} aria-label={`${task.title} · ${t('processed')}`}><Icon name="check"/></button>
    <div className="grow">
      <strong>{task.title}</strong>
      <div className="today-meta">
        {due&&<span className={isOverdue(task)?'danger-text':''}><Icon name="clock"/>{due}</span>}
        {task.assignee_name&&<span><span className="today-avatar" aria-hidden="true">{task.assignee_name.slice(0,1).toUpperCase()}</span>{task.assignee_name}</span>}
        {task.list_name&&<span><Icon name="lists"/>{task.list_name}</span>}
      </div>
    </div>
    {task.priority==='high'&&<span className="today-priority"><Icon name="priority"/> {t('high')}</span>}
  </div>;
}

export default function TodayHome({data,family,t,onTask,open}){
  const language=i18n.language;
  const openTasks=(data.tasks||[]).filter(x=>!x.completed_at);
  const shopping=(data.shopping_lists||[]).flatMap(x=>x.items||[]).filter(x=>!x.checked);
  const currentWeather=data.weather?.current||null;
  const weatherSource=data.weather?.source||{};
  const events=[...(data.events||[])].filter(e=>!['weather.current','weather.forecast'].includes(e?.type)&&(!e.starts_at||new Date(e.starts_at).getTime()>=Date.now()-3600000)).sort((a,b)=>timeValue(a)-timeValue(b));
  const warnings=events.filter(isWarning).slice(0,2);
  const urgentTasks=openTasks.filter(x=>isOverdue(x)||x.priority==='high').slice(0,4);
  const urgentCount=warnings.length+urgentTasks.length;
  const urgentTaskIds=new Set(urgentTasks.map(x=>x.id));
  const nextEvent=events.find(e=>!isWarning(e));
  const todayTasks=openTasks.filter(x=>(isToday(x.due_at)||!x.due_at)&&!urgentTaskIds.has(x.id)).sort((a,b)=>Number(b.priority==='high')-Number(a.priority==='high')).slice(0,5);
  const dueRoutines=(data.routines||[]).filter(routineIsDue).slice(0,4);

  return <div className="today-page">
    <header className="today-hero">
      <div>
        <p>{formatDateTime(language,new Date(),{weekday:'long',day:'numeric',month:'long'})}</p>
        <h1>{t('greeting')}</h1>
        <span>{urgentCount?`${urgentCount} · ${t('priority')}`:t('allDone')}</span>
      </div>
      <div className="today-quick-actions">
        <button onClick={()=>requestCreate('task',{source:'todayQuickAction'})} aria-label={`${t('add')} · ${t('tasks')}`}><Icon name="plus"/><span>{t('tasks')}</span></button>
        <button onClick={()=>requestCreate('shoppingItem',{source:'todayQuickAction'})} aria-label={`${t('add')} · ${t('shopping')}`}><Icon name="shopping"/><span>{t('shopping')}</span></button>
        <button onClick={()=>requestCreate('event',{source:'todayQuickAction'})} aria-label={`${t('add')} · ${t('calendar')}`}><Icon name="calendar"/><span>{t('calendar')}</span></button>
      </div>
    </header>

    <OnboardingCard family={family} data={data} open={open}/>

    {currentWeather&&<section className="today-section" data-testid="current-weather">
      <div className="today-section-head"><h2>{t('weather')}</h2><small>{formatEventDate(currentWeather.observed_at,t,language)}{weatherSource.stale?` · ${t('weatherUi.notCurrent')}`:''}</small></div>
      <button className="today-next-event" onClick={()=>open('weather')} aria-label={`${t('weather')} · ${t('weatherUi.subtitle')}`}>
        <EventIcon event={{type:'weather.current'}}/>
        <div className="grow"><strong>{temperature(currentWeather.temperature)}</strong><span>{currentWeatherMeta(currentWeather,t)}</span><small>{weatherSource.provider||'Open-Meteo'}</small></div>
        <Icon name="next"/>
      </button>
    </section>}

    {urgentCount>0&&<section className="today-section today-important">
      <div className="today-section-head"><div><small>{t('priority').toUpperCase()}</small><h2>{t('today')} · {t('priority')}</h2></div><span>{urgentCount}</span></div>
      <div className="today-important-grid">
        {warnings.map(event=><button key={`event-${event.id}`} className="today-important-card warning" onClick={()=>open(event.type==='weather.warning'?'weather':'calendar')}>
          <EventIcon event={event}/><div><small>{event.type==='public.warning'?t('publicWarning'):t('weatherWarning')}</small><strong>{event.title}</strong><span>{formatEventDate(event.starts_at,t,language)}</span></div><Icon name="next"/>
        </button>)}
        {urgentTasks.map(task=><div key={`task-${task.id}`} className="today-important-card task"><span className="today-event-icon danger"><Icon name="priority"/></span><div><small>{isOverdue(task)?t('due').toUpperCase():t('priority').toUpperCase()}</small><strong>{task.title}</strong><span>{[taskDueLabel(task,t,language),task.assignee_name].filter(Boolean).join(' · ')}</span></div><button className="today-check" onClick={()=>onTask(task)} aria-label={`${task.title} · ${t('processed')}`}><Icon name="check"/></button></div>)}
      </div>
    </section>}

    {nextEvent&&<section className="today-section">
      <div className="today-section-head"><h2>{t('nextUp')}</h2><button className="today-link" onClick={()=>open('calendar')}>{t('calendar')} <Icon name="next"/></button></div>
      <button className="today-next-event" onClick={()=>open('calendar')}>
        <EventIcon event={nextEvent}/>
        <div className="grow"><strong>{nextEvent.title}</strong><span>{formatEventDate(nextEvent.starts_at,t,language)}{nextEvent.payload?.location?` · ${nextEvent.payload.location}`:''}</span><small>{nextEvent.payload?.provider||nextEvent.type}</small></div>
        <Icon name="next"/>
      </button>
    </section>}

    <div className="today-main-grid">
      <section className="today-section">
        <div className="today-section-head"><h2>{t('today')}</h2><button className="today-link" onClick={()=>open('tasks')}>{t('all')} <Icon name="next"/></button></div>
        <div className="today-panel">{todayTasks.length?todayTasks.map(task=><TaskRow task={task} onTask={onTask} t={t} language={language} key={task.id}/>):<div className="today-calm"><Icon name="doneAll"/><strong>{t('onboarding.emptyTaskTitle')}</strong><span>{t('onboarding.emptyTaskHint')}</span><button className="primary compact today-empty-action" onClick={()=>requestCreate('task',{source:'todayEmptyState'})}><Icon name="plus"/> {t('addTask')}</button></div>}</div>
      </section>

      <section className="today-section">
        <div className="today-section-head"><div><h2>{t('shopping')}</h2><small>{shopping.length} · {t('shoppingItems')}</small></div><button className="today-link" onClick={()=>open('shopping')}>{t('list')} <Icon name="next"/></button></div>
        <button className="today-shopping-card" onClick={()=>open('shopping')}>
          <div className="today-shopping-summary"><span className="today-shopping-icon"><Icon name="shopping"/></span><div><strong>{shopping.length?`${shopping.length} ${t('shoppingItems')}`:t('onboarding.emptyShoppingTitle')}</strong><span>{shopping.length?t('list'):t('onboarding.emptyShoppingHint')}</span></div></div>
          {shopping.length>0&&<div className="today-shopping-chips">{shopping.slice(0,6).map(item=><span key={item.id}>{item.quantity&&<b>{item.quantity}</b>} {item.name}</span>)}{shopping.length>6&&<span>+{shopping.length-6}</span>}</div>}
        </button>
      </section>
    </div>

    {dueRoutines.length>0&&<section className="today-section today-secondary">
      <div className="today-section-head"><div><h2>{t('recentlyDone')}</h2><small>{t('dueSoon')}</small></div><button className="today-link" onClick={()=>open('routines')}>{t('all')} <Icon name="next"/></button></div>
      <div className="today-routines">{dueRoutines.map(r=>{const days=r.last_done_at?Math.max(0,Math.floor((Date.now()-new Date(r.last_done_at).getTime())/86400000)):null;return <button key={r.id} onClick={()=>open('routines')}><span><Icon name="history"/></span><strong>{r.name}</strong><small>{days===null?t('never'):days===0?t('todayLower'):t('daysAgo',{count:days})}</small></button>})}</div>
    </section>}
  </div>;
}
