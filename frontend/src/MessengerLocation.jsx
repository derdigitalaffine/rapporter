import {useEffect,useId,useRef,useState} from 'react';
import {useTranslation} from 'react-i18next';
import {Icon} from './icons';
import FamilySheet from './ui/FamilySheet';
import {FormActions} from './form-primitives';
export function LocationCard({location}){
 const {t}=useTranslation();if(!location)return null;
 const {latitude,longitude,accuracy}=location;
 return <div className="messenger-location-card"><Icon name="location" size={24}/><div><strong>{t('messengerUi.location')}</strong><span>{latitude.toFixed(5)}, {longitude.toFixed(5)}</span><small>{t('messengerUi.locationAccuracy',{count:Math.ceil(accuracy)})}</small><a href={`https://www.openstreetmap.org/?mlat=${latitude}&mlon=${longitude}#map=16/${latitude}/${longitude}`} target="_blank" rel="noopener noreferrer">{t('messengerUi.openMap')}</a></div></div>
}
export default function MessengerLocation({onClose,onChoose}){
 const {t}=useTranslation(),id=useId(),request=useRef(0);const [point,setPoint]=useState(null),[state,setState]=useState('idle');
 useEffect(()=>()=>{request.current+=1},[]);
 function locate(){
  if(!navigator.geolocation||!window.isSecureContext){setState('unavailable');return}
  const token=++request.current;setState('loading');setPoint(null);
  navigator.geolocation.getCurrentPosition(position=>{
   if(token!==request.current)return;
   const {latitude,longitude,accuracy}=position.coords;
   if(![latitude,longitude,accuracy].every(Number.isFinite)||accuracy>100000){setState('unavailable');return}
   setPoint({latitude:Number(latitude.toFixed(5)),longitude:Number(longitude.toFixed(5)),accuracy:Number(accuracy.toFixed(1))});setState('ready');
  },error=>{if(token===request.current)setState(error.code===1?'denied':error.code===3?'timeout':'unavailable')},{enableHighAccuracy:true,timeout:15000,maximumAge:0});
 }
 return <FamilySheet labelledBy={id} onClose={onClose}><div className="sheet-head"><h2 id={id}>{t('messengerUi.location')}</h2><button type="button" className="sheet-close" onClick={onClose} aria-label={t('messengerUi.cancel')}><Icon name="close"/></button></div><div className="messenger-location-preview"><p>{t('messengerUi.locationPrivacy')}</p>{point&&<LocationCard location={point}/>} {point?.accuracy>100&&<p role="status">{t('messengerUi.locationImprecise')}</p>}{state==='loading'&&<p role="status">{t('messengerUi.locating')}</p>}{['denied','timeout','unavailable'].includes(state)&&<p role="alert">{t(`messengerUi.location_${state}`)}</p>}<button className="secondary" type="button" onClick={locate} disabled={state==='loading'}><Icon name="location"/>{t(point?'messengerUi.locateAgain':'messengerUi.locate')}</button><FormActions><button type="button" className="secondary" onClick={onClose}>{t('messengerUi.cancel')}</button><button type="button" className="primary" disabled={!point} onClick={()=>onChoose(point)}>{t('messengerUi.useLocation')}</button></FormActions></div></FamilySheet>
}
