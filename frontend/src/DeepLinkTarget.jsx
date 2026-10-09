import {useEffect,useState} from 'react';
import {useTranslation} from 'react-i18next';
import {api,isAuthenticated} from './api';
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
  const {t}=useTranslation();
  const [resolved,setResolved]=useState(null);
  const [revision,setRevision]=useState(0);

  useEffect(()=>{
    const onRoute=()=>setRevision(value=>value+1);
    window.addEventListener('popstate',onRoute);
    return()=>window.removeEventListener('popstate',onRoute);
  },[]);

  useEffect(()=>{
    let cancelled=false;
    const spec=targetFromLocation();
    setResolved(null);
    if(!spec||!isAuthenticated())return()=>{cancelled=true};
    api(spec.endpoint).then(target=>{
      if(cancelled||!target||Array.isArray(target))return;
      setResolved({spec,target});
    }).catch(()=>{
      if(!cancelled)setResolved(null);
    });
    return()=>{cancelled=true};
  },[revision]);

  if(!resolved)return null;
  const {spec,target}=resolved;
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
      {details.length>0&&<div className="stack">{details.map((value,index)=><div className="card body-copy" key={`${index}-${value}`}>{value}</div>)}</div>}
    </section>
  </div>;
}
