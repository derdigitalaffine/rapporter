import {useEffect} from 'react';
import {api} from './api';
import './today-header-personalizer.css';

const ACTIVE_FAMILY_KEY='famuhle-active-family';
const unwrap=value=>value?.results||value||[];

function firstName(person){
 const label=String(person?.display_name||person?.name||person?.first_name||person?.username||'').trim();
 return label.split(/\s+/)[0]||'';
}

export default function TodayHeaderPersonalizer(){
 useEffect(()=>{
  let live=true;
  let context=null;
  let loading=null;

  const reset=()=>{
   const heading=document.querySelector('.topbar .brand-mini[role="heading"]');
   if(!heading)return;
   heading.classList.remove('today-personal-header');
   heading.removeAttribute('data-today-greeting');
   heading.removeAttribute('data-today-family');
  };

  const loadContext=()=>{
   if(context)return Promise.resolve(context);
   if(loading)return loading;
   loading=Promise.all([api('/auth/session/'),api('/families/')]).then(([session,familiesPayload])=>{
    const families=unwrap(familiesPayload);
    context={user:session?.user||null,families};
    return context;
   }).catch(()=>null).finally(()=>{loading=null});
   return loading;
  };

  const apply=async()=>{
   const heading=document.querySelector('.topbar .brand-mini[role="heading"]');
   if(!heading)return;
   const onToday=Boolean(document.querySelector('main[data-page="home"]'));
   if(!onToday){reset();return}

   const loaded=await loadContext();
   if(!live||!loaded)return;
   const preferred=localStorage.getItem(ACTIVE_FAMILY_KEY);
   const family=loaded.families.find(item=>String(item.id)===String(preferred))||loaded.families[0];
   const member=(family?.memberships||[]).find(row=>String(row.user)===String(loaded.user?.id));
   const name=firstName(member)||firstName(loaded.user);
   const de=(localStorage.getItem('famuhle-language')||document.documentElement.lang||'de').toLowerCase().startsWith('de');
   const greeting=name?`${de?'Huhu':'Hi'} ${name}`:(de?'Huhu':'Hi');
   const familyName=String(family?.name||'FamilyOS').trim();

   heading.classList.add('today-personal-header');
   heading.dataset.todayGreeting=greeting;
   heading.dataset.todayFamily=familyName;
   heading.setAttribute('aria-label',`${greeting}, ${familyName}`);
  };

  void apply();
  const observer=new MutationObserver(()=>{void apply()});
  observer.observe(document.body,{childList:true,subtree:true,attributes:true,attributeFilter:['data-page']});
  const storage=event=>{if([ACTIVE_FAMILY_KEY,'famuhle-language'].includes(event.key)){context=null;void apply()}};
  window.addEventListener('storage',storage);
  return()=>{live=false;observer.disconnect();window.removeEventListener('storage',storage);reset()};
 },[]);

 return null;
}
