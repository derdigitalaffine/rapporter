import {useEffect,useState} from 'react';
import {api} from './api';
import {featureHref} from './navigation';
import {Icon} from './icons';

export default function TodayLoyaltyWidget({family,language,t}){
 const [view,setView]=useState({family:null,rows:[]});
 useEffect(()=>{
  let active=true;
  api(`/loyalty-cards/sync/?family=${encodeURIComponent(family.id)}`).then(response=>{
   if(!active)return;
   const rows=Array.isArray(response)?response:response?.results||[];
   setView({family:family.id,rows:[...rows].sort((a,b)=>Number(Boolean(b.favorite))-Number(Boolean(a.favorite))||String(a.name||'').localeCompare(String(b.name||''),language)).slice(0,4)});
  }).catch(()=>{if(active)setView({family:family.id,rows:[]})});
  return()=>{active=false};
 },[family.id,language]);
 const rows=view.family===family.id?view.rows:[];
 if(!rows.length)return null;
 const de=language.startsWith('de');
 return <section className="today-section today-secondary" data-testid="today-loyalty"><div className="today-section-head"><div><h2>{t('loyaltyUi.title')}</h2><small>{de?'Favoriten & geteilte Karten':'Favorites & shared cards'}</small></div><a className="today-link" href={featureHref('loyalty')}>{t('all')} <Icon name="next"/></a></div><div className="today-routines">{rows.map(card=><a key={card.id} href={featureHref('loyalty',{card:card.id})} aria-label={`${card.name} · ${t('loyaltyUi.title')}`}><span><Icon name={card.favorite?'favorite':'store'}/></span><strong>{card.name}</strong><small>{card.holder_display||card.holder_name||(card.favorite?(de?'Favorit':'Favorite'):'')}</small></a>)}</div></section>;
}
