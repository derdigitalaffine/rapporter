import TodayOverview from './TodayOverview';
import {TodayFocusWidget,TodaySituation} from './TodayCoreWidgets';
import OnboardingCard from './OnboardingCard';
import i18n from './i18n';
import {formatDateTime} from './locale';
import './onboarding.css';
import './today-layout.css';
import './today-layout-v2.css';

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

export default function TodayCanonicalHome({data,family,open,unreadMessages=null,viewer=null}){
 const language=i18n.language;
 const displayFamily={...family,name:firstName(viewer)||family.name};
 return <div className="today-page" data-testid="today-canonical-home">
  <header className="today-hero"><div className="today-greeting"><p>{formatDateTime(language,new Date(),{timeZone:family.timezone||'UTC',weekday:'long',day:'numeric',month:'long'})} · {family.name}</p><h1>{greeting(displayFamily,language)}</h1></div></header>
  <OnboardingCard family={family} data={data} open={open}/>
  <div className="app-widget-grid today-widget-grid" data-testid="today-canonical-grid">
   <div data-today-widget="situation" data-widget-size="compact" className="app-widget today-widget today-widget-compact"><TodaySituation family={family} language={language} widgetSize="compact" summaryOnly/></div>
   <div data-today-widget="overview" data-widget-size="wide" className="app-widget today-widget today-widget-wide"><TodayOverview family={family} data={data} unreadMessages={unreadMessages} language={language}/></div>
   <div data-today-widget="focus" data-widget-size="wide" className="app-widget today-widget today-widget-wide"><TodayFocusWidget family={family} language={language} compact/></div>
  </div>
 </div>;
}
