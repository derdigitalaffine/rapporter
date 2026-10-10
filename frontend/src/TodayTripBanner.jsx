import {useEffect,useState} from 'react';
import {api} from './api';
import {Icon} from './icons';
import {nextRelevantTrip,tripCountdown} from './travel-utils';
import './today-trip-banner.css';

const unwrap=value=>value?.results||value||[];
const words={
 de:{label:'Nächste Reise',inDays:'Noch {{count}} Tage',tomorrow:'Morgen geht es los',today:'Heute geht es los',tripDay:'Tag {{day}} von {{total}}',finished:'Reise beendet'},
 en:{label:'Next trip',inDays:'{{count}} days to go',tomorrow:'Leaving tomorrow',today:'Leaving today',tripDay:'Day {{day}} of {{total}}',finished:'Trip finished'},
};

export default function TodayTripBanner({family,open,language='de'}){
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
 const trip=nextRelevantTrip(trips);
 if(!trip)return null;
 const countdown=tripCountdown(trip,copy);
 return <button className="today-trip-banner" data-testid="today-trip-banner" onClick={()=>open('trips')} aria-label={`${copy.label}: ${trip.title}. ${countdown}`}>
  <span className="today-trip-banner-icon" aria-hidden="true"><Icon name="route" size={18}/></span>
  <span className="today-trip-banner-copy"><small>{copy.label}</small><strong>{trip.title}</strong>{trip.destination&&<span>{trip.destination}</span>}</span>
  <span className="today-trip-banner-countdown">{countdown}</span>
  <Icon name="next" size={16}/>
 </button>;
}
