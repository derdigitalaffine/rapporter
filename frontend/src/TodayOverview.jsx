import {Icon} from './icons';
import {featureHref} from './navigation';
import {useTodayCoreData} from './todayCoreData';
import {eventDayKeys,isWarningEvent,zonedDateKey} from './calendar-event-ui';
import {isWasteEvent} from './waste-ui';
import './today-overview.css';

export function OverviewTile({page,params,label,icon,value,detail,tone='normal'}){
 return <a className="today-overview-tile" data-domain={page} data-tone={tone} href={featureHref(page,params)}><span className="today-overview-icon"><Icon name={icon} size={21}/></span><strong className="today-overview-value">{value??'—'}</strong><span className="today-overview-label">{label}</span><span className="today-overview-detail">{detail}</span></a>;
}

export function TodayOverviewContent({family,data={},unreadMessages=null,language='de',core}){
 const de=language.startsWith('de');
 const actions=core.actions.filter(item=>!['done','done_today','paused'].includes(item.state));
 const overdue=actions.filter(item=>item.state==='overdue').length;
 const day=zonedDateKey(new Date(),family.timezone||'UTC');
 const events=core.events.filter(event=>!isWasteEvent(event)&&!isWarningEvent(event)&&!event.type?.startsWith('weather.')&&eventDayKeys(event,family.timezone||'UTC').includes(day));
 const next=events.filter(event=>event.starts_at&&new Date(event.starts_at)>=new Date()).sort((a,b)=>new Date(a.starts_at)-new Date(b.starts_at))[0];
 const unavailable=de?'Nicht verfügbar':'Unavailable';
 const waiting=de?'Wird geladen':'Loading';
 const summary=data.overview||{};
 return <section className="today-overview" aria-label={de?'Dein Überblick':'Your overview'} data-testid="today-overview">
  <OverviewTile page="todo" params={{todo:'today'}} label={de?'Aufgaben':'Tasks'} icon="tasks" value={core.actionFailed||!core.loaded?null:actions.length} tone={overdue?'attention':'normal'} detail={core.actionFailed?unavailable:!core.loaded?waiting:overdue?`${overdue} ${de?'überfällig':'overdue'}`:de?'Heute offen':'Open today'}/>
  <OverviewTile page="calendar" label={de?'Kalender':'Calendar'} icon="calendar" value={core.calendarFailed||!core.loaded?null:events.length} detail={core.calendarFailed?unavailable:!core.loaded?waiting:next?new Intl.DateTimeFormat(language,{timeZone:family.timezone||'UTC',hour:'2-digit',minute:'2-digit'}).format(new Date(next.starts_at)):de?'Termine heute':'Events today'}/>
  <OverviewTile page="shopping" label={de?'Einkauf':'Shopping'} icon="shopping" value={summary.shopping_open_count} detail={summary.shopping_open_count===undefined?unavailable:de?'Offene Artikel':'Open items'}/>
  <OverviewTile page="board" label={de?'Pinnwand':'Pinboard'} icon="lists" value={summary.pin_count} detail={summary.pin_count===undefined?unavailable:de?'Sichtbare Pins':'Visible pins'}/>
  <OverviewTile page="inbox" label={de?'Nachrichten':'Messages'} icon="inbox" value={unreadMessages} detail={unreadMessages===null?unavailable:de?'Ungelesen':'Unread'}/>
  <OverviewTile page="more" label={de?'Alle Bereiche':'All areas'} icon="more" value="+" detail={de?'Familie & Alltag':'Family & everyday life'}/>
 </section>;
}

export default function TodayOverview(props){
 const core=useTodayCoreData(props.family);
 return <TodayOverviewContent {...props} core={core}/>;
}
