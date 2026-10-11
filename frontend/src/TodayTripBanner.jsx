import {useEffect,useState} from 'react';
import {api} from './api';
import {Icon} from './icons';
import {isTripWish,nextRelevantTrip,tripCountdown} from './travel-utils';
import './today-trip-banner.css';

const unwrap=value=>value?.results||value||[];
const words={
 de:{label:'Nächste Reise',wishLabel:'Reisewunsch',planning:'In Planung',inDays:'Noch {{count}} Tage',tomorrow:'Morgen geht es los',today:'Heute geht es los',tripDay:'Tag {{day}} von {{total}}',finished:'Reise beendet'},
 en:{label:'Next trip',wishLabel:'Trip wish',planning:'In planning',inDays:'{{count}} days to go',tomorrow:'Leaving tomorrow',today:'Leaving today',tripDay:'Day {{day}} of {{total}}',finished:'Trip finished'},
};

export default function TodayTripBanner({family,open,language='de',widgetSize='full',widgetSettings={show_wishes:false}}){
 const [trips,setTrips]=useState([]);
 useEffect(()=>{
  let current=true;
  setTrips([]);
  api(`/trips/?family=${encodeURIComponent(family.id)}`)
   .then(result=>{if(current)setTrips(unwrap(result))})
   .catch(()=>{if(current)setTrips([])});
  return()=>{current=false};
 },[family.id]);
 const copy=words[language.startsWith('en')?'en':'de'];
 const trip=nextRelevantTrip(trips,new Date(),{includeWishes:widgetSettings?.show_wishes===true});
 if(!trip)return null;
 const wish=isTripWish(trip);
 const countdown=tripCountdown(trip,copy);
 const detail=countdown||(wish?copy.planning:'');
 const label=wish?copy.wishLabel:copy.label;
 return <div className={`app-widget today-widget today-widget-${widgetSize} today-trip-widget`} data-today-widget="trip" data-widget-size={widgetSize}>
  <button type="button" className="today-trip-banner" data-testid="today-trip-banner" onClick={()=>open('trips')} aria-label={[`${label}: ${trip.title}`,detail].filter(Boolean).join('. ')}>
   <span className="today-trip-banner-icon" aria-hidden="true"><Icon name="route" size={20}/></span>
   <span className="today-trip-banner-copy"><small>{label}</small><strong>{trip.title}</strong>{trip.destination&&<span>{trip.destination}</span>}</span>
   {detail&&<span className="today-trip-banner-countdown">{detail}</span>}
   <Icon name="next" size={16}/>
  </button>
 </div>;
}

TodayTripBanner.todayWidgetSelfManaged=true;