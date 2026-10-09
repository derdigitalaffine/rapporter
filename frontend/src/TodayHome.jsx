import {Icon} from './icons';

const isWarning=e=>e?.type?.includes('warning');
const isToday=date=>date&&new Date(date).toDateString()===new Date().toDateString();
const isOverdue=task=>task?.due_at&&!task.completed_at&&new Date(task.due_at)<new Date()&&!isToday(task.due_at);
const timeValue=e=>e?.starts_at?new Date(e.starts_at).getTime():Number.MAX_SAFE_INTEGER;

function formatEventDate(value){
  if(!value)return '';
  const date=new Date(value);
  if(isToday(value))return `Heute · ${new Intl.DateTimeFormat(undefined,{timeStyle:'short'}).format(date)}`;
  const tomorrow=new Date();tomorrow.setDate(tomorrow.getDate()+1);
  if(date.toDateString()===tomorrow.toDateString())return `Morgen · ${new Intl.DateTimeFormat(undefined,{timeStyle:'short'}).format(date)}`;
  return new Intl.DateTimeFormat(undefined,{weekday:'short',dateStyle:'medium',timeStyle:'short'}).format(date);
}

function taskDueLabel(task){
  if(!task.due_at)return '';
  if(isOverdue(task))return 'Überfällig';
  if(isToday(task.due_at))return `Heute ${new Intl.DateTimeFormat(undefined,{timeStyle:'short'}).format(new Date(task.due_at))}`;
  return new Intl.DateTimeFormat(undefined,{dateStyle:'medium'}).format(new Date(task.due_at));
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

function TaskRow({task,onTask}){
  return <div className={`today-task-row ${isOverdue(task)?'overdue':''}`}>
    <button className="today-check" onClick={()=>onTask(task)} aria-label={`${task.title} erledigen`}><Icon name="check"/></button>
    <div className="grow">
      <strong>{task.title}</strong>
      <div className="today-meta">
        {taskDueLabel(task)&&<span className={isOverdue(task)?'danger-text':''}><Icon name="clock"/>{taskDueLabel(task)}</span>}
        {task.assignee_name&&<span><span className="today-avatar" aria-hidden="true">{task.assignee_name.slice(0,1).toUpperCase()}</span>{task.assignee_name}</span>}
        {task.list_name&&<span><Icon name="lists"/>{task.list_name}</span>}
      </div>
    </div>
    {task.priority==='high'&&<span className="today-priority"><Icon name="priority"/> Wichtig</span>}
  </div>;
}

export default function TodayHome({data,t,onTask,open}){
  const openTasks=(data.tasks||[]).filter(x=>!x.completed_at);
  const shopping=(data.shopping_lists||[]).flatMap(x=>x.items||[]).filter(x=>!x.checked);
  const events=[...(data.events||[])].filter(e=>!e.starts_at||new Date(e.starts_at).getTime()>=Date.now()-3600000).sort((a,b)=>timeValue(a)-timeValue(b));
  const warnings=events.filter(isWarning);
  const urgentTasks=openTasks.filter(x=>isOverdue(x)||x.priority==='high');
  const urgent=[...warnings.slice(0,2),...urgentTasks.slice(0,4)];
  const nextEvent=events.find(e=>!isWarning(e));
  const todayTasks=openTasks.filter(x=>isToday(x.due_at)||!x.due_at).sort((a,b)=>Number(b.priority==='high')-Number(a.priority==='high')).slice(0,5);
  const dueRoutines=(data.routines||[]).filter(routineIsDue).slice(0,4);

  return <div className="today-page">
    <header className="today-hero">
      <div>
        <p>{new Intl.DateTimeFormat(undefined,{weekday:'long',day:'numeric',month:'long'}).format(new Date())}</p>
        <h1>{t('greeting')}</h1>
        <span>{urgent.length?`${urgent.length} Dinge brauchen Aufmerksamkeit`:'Alles Wichtige im Blick.'}</span>
      </div>
      <div className="today-quick-actions" aria-label="Schnellaktionen">
        <button onClick={()=>open('tasks')}><Icon name="plus"/><span>{t('tasks')}</span></button>
        <button onClick={()=>open('shopping')}><Icon name="shopping"/><span>{t('shopping')}</span></button>
        <button onClick={()=>open('calendar')}><Icon name="calendar"/><span>{t('calendar')}</span></button>
      </div>
    </header>

    {urgent.length>0&&<section className="today-section today-important">
      <div className="today-section-head"><div><small>PRIORITÄT</small><h2>Heute wichtig</h2></div><span>{urgent.length}</span></div>
      <div className="today-important-grid">
        {warnings.slice(0,2).map(event=><button key={`event-${event.id}`} className="today-important-card warning" onClick={()=>open('calendar')}>
          <EventIcon event={event}/><div><small>{event.type==='public.warning'?t('publicWarning'):t('weatherWarning')}</small><strong>{event.title}</strong><span>{formatEventDate(event.starts_at)}</span></div><Icon name="next"/>
        </button>)}
        {urgentTasks.slice(0,4).map(task=><div key={`task-${task.id}`} className="today-important-card task"><span className="today-event-icon danger"><Icon name="priority"/></span><div><small>{isOverdue(task)?'ÜBERFÄLLIG':'WICHTIGE AUFGABE'}</small><strong>{task.title}</strong><span>{[taskDueLabel(task),task.assignee_name].filter(Boolean).join(' · ')}</span></div><button className="today-check" onClick={()=>onTask(task)} aria-label={`${task.title} erledigen`}><Icon name="check"/></button></div>)}
      </div>
    </section>}

    {nextEvent&&<section className="today-section">
      <div className="today-section-head"><h2>{t('nextUp')}</h2><button className="today-link" onClick={()=>open('calendar')}>{t('calendar')} <Icon name="next"/></button></div>
      <button className="today-next-event" onClick={()=>open('calendar')}>
        <EventIcon event={nextEvent}/>
        <div className="grow"><strong>{nextEvent.title}</strong><span>{formatEventDate(nextEvent.starts_at)}{nextEvent.payload?.location?` · ${nextEvent.payload.location}`:''}</span><small>{nextEvent.payload?.provider||nextEvent.type}</small></div>
        <Icon name="next"/>
      </button>
    </section>}

    <div className="today-main-grid">
      <section className="today-section">
        <div className="today-section-head"><h2>{t('today')}</h2><button className="today-link" onClick={()=>open('tasks')}>{t('all')} <Icon name="next"/></button></div>
        <div className="today-panel">{todayTasks.length?todayTasks.map(task=><TaskRow task={task} onTask={onTask} key={task.id}/>):<div className="today-calm"><Icon name="doneAll"/><strong>{t('allDone')}</strong><span>Keine Aufgabe drängt sich gerade nach vorne.</span></div>}</div>
      </section>

      <section className="today-section">
        <div className="today-section-head"><div><h2>{t('shopping')}</h2><small>{shopping.length} offen</small></div><button className="today-link" onClick={()=>open('shopping')}>{t('list')} <Icon name="next"/></button></div>
        <button className="today-shopping-card" onClick={()=>open('shopping')}>
          <div className="today-shopping-summary"><span className="today-shopping-icon"><Icon name="shopping"/></span><div><strong>{shopping.length?`${shopping.length} Artikel offen`:t('shoppingEmpty')}</strong><span>{shopping.length?'Direkt zur gemeinsamen Liste':'Beim nächsten Bedarf schnell ergänzen'}</span></div></div>
          {shopping.length>0&&<div className="today-shopping-chips">{shopping.slice(0,6).map(item=><span key={item.id}>{item.quantity&&<b>{item.quantity}</b>} {item.name}</span>)}{shopping.length>6&&<span>+{shopping.length-6}</span>}</div>}
        </button>
      </section>
    </div>

    {dueRoutines.length>0&&<section className="today-section today-secondary">
      <div className="today-section-head"><div><h2>{t('recentlyDone')}</h2><small>Wieder sinnvoll</small></div><button className="today-link" onClick={()=>open('routines')}>{t('all')} <Icon name="next"/></button></div>
      <div className="today-routines">{dueRoutines.map(r=><button key={r.id} onClick={()=>open('routines')}><span><Icon name="history"/></span><strong>{r.name}</strong><small>{r.last_done_at?`${Math.max(0,Math.floor((Date.now()-new Date(r.last_done_at).getTime())/86400000))} Tage her`:'Noch nie erledigt'}</small></button>)}</div>
    </section>}
  </div>;
}
