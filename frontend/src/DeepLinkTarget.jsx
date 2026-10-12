import {useEffect,useState} from 'react';
import {useTranslation} from 'react-i18next';
import {api,isAuthenticated,AUTH_CHANGED_EVENT} from './api';
import {assignmentCopy,taskDuelAction,openTaskDuel} from './game-assignment-i18n';
import {Icon} from './icons';

const TARGET_KEYS=['task','list','item','event','routine'];

function targetFromLocation(){
  const params=new URLSearchParams(window.location.search);
  const page=params.get('page');
  if(page==='tasks'){
    const task=params.get('task');
    if(task)return {page,key:'task',endpoint:`/tasks/${encodeURIComponent(task)}/`};
    const list=params.get('list');
    if(list)return {page,key:'list',endpoint:`/task-lists/${encodeURIComponent(list)}/`};
  }
  if(page==='shopping'&&params.get('mode')==='store')return null;
  if(page==='shopping'){
    const item=params.get('item');
    if(item)return {page,key:'item',endpoint:`/shopping-items/${encodeURIComponent(item)}/`};
    const list=params.get('list');
    if(list)return {page,key:'list',endpoint:`/shopping-lists/${encodeURIComponent(list)}/`};
  }
  if(page==='calendar'&&params.get('event'))return {page,key:'event',endpoint:`/events/${encodeURIComponent(params.get('event'))}/`};
  if(page==='inbox'&&params.get('item'))return {page,key:'item',endpoint:`/inbox/${encodeURIComponent(params.get('item'))}/`};
  // The routines hub owns its editable, reload-safe detail view.
  return null;
}

function detailValues(target){
  const values=[
    target.list_name,
    target.assignee_name,
    target.quantity,
    target.category,
    target.aisle,
    target.notes,
    target.note,
    target.body,
    target.payload?.location,
    target.payload?.description,
  ];
  return [...new Set(values.map(value=>String(value||'').trim()).filter(Boolean))];
}

const sectionKey={tasks:'tasks',shopping:'shopping',calendar:'calendar',inbox:'inbox',routines:'routines'};

export default function DeepLinkTarget(){
  const {t,i18n}=useTranslation();
  const words=assignmentCopy(i18n.language);
  const [resolved,setResolved]=useState(null);
  const [revision,setRevision]=useState(0);

  useEffect(()=>{
    const onRoute=()=>setRevision(value=>value+1);
    const auth=event=>{if(event.detail?.authenticated===false)setResolved(null);onRoute()};
    window.addEventListener('popstate',onRoute);window.addEventListener(AUTH_CHANGED_EVENT,auth);
    return()=>{window.removeEventListener('popstate',onRoute);window.removeEventListener(AUTH_CHANGED_EVENT,auth)};
  },[]);

  useEffect(()=>{
    let cancelled=false;
    const spec=targetFromLocation();
    setResolved(null);
    if(!spec||!isAuthenticated())return()=>{cancelled=true};
    api(spec.endpoint).then(async target=>{
      if(cancelled||!target||Array.isArray(target))return;
      let duel=null;
      if(spec.key==='task'&&target.family){
        try{const projection=await api(`/actions/?family=${encodeURIComponent(target.family)}&scope=all&kind=tasks&task=${encodeURIComponent(target.id)}`);duel=taskDuelAction(projection,target.id)}catch(error){if([401,403,404].includes(error.status))throw error}
      }
      if(!cancelled)setResolved({spec,target,duel});
    }).catch(()=>{
      if(!cancelled)setResolved(null);
    });
    return()=>{cancelled=true};
  },[revision]);

  if(!resolved)return null;
  const {spec,target,duel}=resolved;
  const title=target.title||target.name||target.display_name||t(sectionKey[spec.page]||'more');
  const details=detailValues(target);
  const close=()=>{
    const url=new URL(window.location.href);
    TARGET_KEYS.forEach(key=>url.searchParams.delete(key));
    history.replaceState(history.state,'',`${url.pathname}${url.search}${url.hash}`);
    setResolved(null);
  };

  return <div className="sheet-backdrop" onMouseDown={event=>event.target===event.currentTarget&&close()}>
    <section className="quick-sheet" role="dialog" aria-modal="true" aria-labelledby="deep-link-title">
      <div className="sheet-handle"/>
      <div className="sheet-head">
        <div><small>{t(sectionKey[spec.page]||'more')}</small><h2 id="deep-link-title">{title}</h2></div>
        <button className="sheet-close" onClick={close} aria-label={t('back')}><Icon name="close"/></button>
      </div>
      {duel&&<button type="button" className="secondary" onClick={()=>openTaskDuel(duel.href)}><Icon name="members"/>{words.duel}</button>}
      {details.length>0&&<div className="stack">{details.map((value,index)=><div className="card body-copy" key={`${index}-${value}`}>{value}</div>)}</div>}
    </section>
  </div>;
}
