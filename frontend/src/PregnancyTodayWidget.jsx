import {useEffect,useRef,useState} from 'react';
import {api} from './api';
import {AUTH_CHANGED_EVENT} from './api';
import {featureHref} from './navigation';
import PregnancyStatus from './PregnancyStatus';
import {Icon} from './icons';

export function useActivePregnancy(family,module){
 const permitted=Boolean(module?.enabled&&module?.authorized&&module?.permissions?.can_view_pregnancy);
 const [state,setState]=useState({family:null,pregnancy:null,error:false,available:false});
 const revision=useRef(0);
 const [attempt,setAttempt]=useState(0);
 useEffect(()=>{
  let live=true;
  setState({family:family.id,pregnancy:null,error:false,available:false});
  if(!permitted)return;
  async function load(){
   const current=++revision.current;
   // Revalidation never renders stale sensitive contents after focus/auth changes.
   setState({family:family.id,pregnancy:null,error:false,available:false});
   try{
    const row=await api(`/baby/module/?family=${encodeURIComponent(family.id)}`);
    if(!live||current!==revision.current)return;
    const allowed=row.enabled&&row.authorized&&row.permissions?.can_view_pregnancy;
    setState({family:family.id,pregnancy:allowed?row.active_pregnancy:null,error:false,available:Boolean(allowed&&row.active_pregnancy)});
   }catch(error){if(live&&current===revision.current)setState({family:family.id,pregnancy:null,error:![401,403,404].includes(error.status),available:![401,403,404].includes(error.status)&&Boolean(module.active_pregnancy)})}
  }
  const visible=()=>{if(document.visibilityState==='visible')load()};
  const clear=()=>{revision.current++;setState({family:family.id,pregnancy:null,error:false,available:false})};
  load();
  window.addEventListener('focus',load);window.addEventListener(AUTH_CHANGED_EVENT,clear);document.addEventListener('visibilitychange',visible);
  const timer=setInterval(visible,60_000);
  return()=>{live=false;revision.current++;clearInterval(timer);window.removeEventListener('focus',load);window.removeEventListener(AUTH_CHANGED_EVENT,clear);document.removeEventListener('visibilitychange',visible)};
 },[family.id,permitted,attempt]);
 return {...(permitted&&state.family===family.id?state:{pregnancy:null,error:false,available:false}),retry:()=>setAttempt(value=>value+1)};
}

export default function PregnancyTodayWidget({state,language='de'}){
 const de=language.startsWith('de');
 return <section className="today-section today-pregnancy-widget" aria-label={de?'Schwangerschaft':'Pregnancy'}>
  <h2>{de?'Schwangerschaft':'Pregnancy'}</h2>
  {state.error?<div role="alert"><p>{de?'Schwangerschaft konnte nicht geladen werden.':'Could not load pregnancy.'}</p><button type="button" className="secondary" onClick={state.retry}><Icon name="refresh"/>{de?'Erneut laden':'Try again'}</button></div>:state.pregnancy?<PregnancyStatus pregnancy={state.pregnancy} language={language} compact/>:null}
  <a className="today-link" href={featureHref('pregnancy')}>{de?'Schwangerschaft öffnen':'Open pregnancy'}<Icon name="next"/></a>
 </section>;
}
