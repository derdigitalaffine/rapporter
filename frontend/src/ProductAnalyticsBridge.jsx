import {useEffect} from 'react';

import {api} from './api';
import {pageFromLocation} from './navigation';

const FEATURE_BY_ROUTE={
 home:'home',todo:'tasks',tasks:'tasks',shopping:'shopping',routines:'routines',notes:'notes',documents:'documents',board:'board',birthdays:'birthdays',trips:'travel',decisions:'decisions',wishlists:'wishlists',baby:'baby',pets:'pets',more:'account',calendar:'calendar',weather:'weather',expenses:'expenses',contracts:'contracts',inbox:'inbox',integrations:'integrations',automations:'automation',members:'account',profile:'account',notifications:'notifications',loyalty:'loyalty'
};

export function productDurationBucket(milliseconds){
 const value=Number(milliseconds);
 if(!Number.isFinite(value)||value<0)return'none';
 if(value<100)return'lt_100ms';
 if(value<500)return'100_500ms';
 if(value<2000)return'500_2000ms';
 return'gt_2000ms';
}

export function trackProductEvent({kind='event',feature,action,result='success',routeFamily,durationBucket='none'}={}){
 const route=routeFamily||pageFromLocation();
 const resolvedFeature=feature||FEATURE_BY_ROUTE[route];
 if(!resolvedFeature||!FEATURE_BY_ROUTE[route])return Promise.resolve(null);
 return api('/analytics/product-event/',{
  method:'POST',
  body:JSON.stringify({kind,feature:resolvedFeature,action,result,route_family:route,duration_bucket:durationBucket})
 }).catch(()=>null);
}

function trackPageview(route){
 return trackProductEvent({kind:'pageview',feature:FEATURE_BY_ROUTE[route],action:'open',result:'success',routeFamily:route});
}

export default function ProductAnalyticsBridge(){
 useEffect(()=>{
  let lastRoute='';
  const emit=()=>{
   const route=pageFromLocation();
   if(!FEATURE_BY_ROUTE[route]||route===lastRoute)return;
   lastRoute=route;
   void trackPageview(route);
  };
  const originalPush=history.pushState;
  const originalReplace=history.replaceState;
  const patchedPush=function(...args){const value=originalPush.apply(history,args);queueMicrotask(emit);return value};
  const patchedReplace=function(...args){const value=originalReplace.apply(history,args);queueMicrotask(emit);return value};
  history.pushState=patchedPush;
  history.replaceState=patchedReplace;
  window.addEventListener('popstate',emit);
  emit();
  return()=>{
   window.removeEventListener('popstate',emit);
   if(history.pushState===patchedPush)history.pushState=originalPush;
   if(history.replaceState===patchedReplace)history.replaceState=originalReplace;
  };
 },[]);
 return null;
}
