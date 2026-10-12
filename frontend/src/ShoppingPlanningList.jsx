import {useEffect,useMemo,useRef,useState} from 'react';
import {useTranslation} from 'react-i18next';
import {Icon} from './icons';
import {toast} from './feedback';
import './shopping-order-i18n';
import './shopping-order.css';

const byPosition=(a,b)=>(Number(a.position??2147483647)-Number(b.position??2147483647))||String(a.id).localeCompare(String(b.id),undefined,{numeric:true});

export default function ShoppingPlanningList({items,onReorder,onToggle,onEdit,onFavorite,loaded,empty}){
  const {t}=useTranslation();
  const source=useMemo(()=>[...(items||[])].sort(byPosition),[items]);
  const sourceOpen=useMemo(()=>source.filter(item=>!item.checked),[source]);
  const [ordered,setOrdered]=useState(sourceOpen);
  const [announcement,setAnnouncement]=useState('');
  const dragRef=useRef(null);
  useEffect(()=>setOrdered(sourceOpen),[sourceOpen]);

  function fullOrderIds(nextOpen){
    const queue=[...nextOpen];
    return source.map(item=>item.checked?item.id:queue.shift()?.id).filter(Boolean);
  }
  async function persist(next,previous,moved){
    setOrdered(next);
    const position=next.findIndex(item=>String(item.id)===String(moved.id))+1;
    setAnnouncement(t('shoppingOrder.moved',{name:moved.name,position,count:next.length}));
    try{await onReorder(fullOrderIds(next))}catch(error){setOrdered(previous);toast(error.message||t('shoppingOrder.failed'),{type:'error'})}
  }
  function move(item,delta){
    const index=ordered.findIndex(row=>String(row.id)===String(item.id));
    const target=index+delta;if(index<0||target<0||target>=ordered.length)return;
    const previous=[...ordered],next=[...ordered];next.splice(index,1);next.splice(target,0,item);void persist(next,previous,item);
  }
  function pointerDown(event,item){
    if(event.button!==undefined&&event.button!==0)return;
    event.currentTarget.setPointerCapture?.(event.pointerId);
    dragRef.current={id:String(item.id),previous:[...ordered],current:[...ordered],last:String(item.id)};
  }
  function pointerMove(event){
    const drag=dragRef.current;if(!drag)return;
    const row=document.elementFromPoint(event.clientX,event.clientY)?.closest?.('[data-shopping-order-id]');
    const targetId=row?.dataset?.shoppingOrderId;if(!targetId||targetId===drag.last)return;
    setOrdered(current=>{
      const from=current.findIndex(item=>String(item.id)===drag.id),to=current.findIndex(item=>String(item.id)===targetId);
      if(from<0||to<0)return current;
      const next=[...current],moved=next.splice(from,1)[0];next.splice(to,0,moved);drag.last=targetId;drag.current=next;return next;
    });
  }
  function pointerUp(){
    const drag=dragRef.current;if(!drag)return;dragRef.current=null;
    const next=drag.current||ordered;const moved=next.find(item=>String(item.id)===drag.id);if(!moved)return;
    const before=drag.previous.map(item=>String(item.id)).join('|'),after=next.map(item=>String(item.id)).join('|');
    if(before!==after)void persist(next,drag.previous,moved);
  }

  if(!loaded)return empty;
  if(!ordered.length)return empty;
  return <section className="shopping-order-list" aria-label={t('shoppingOrder.label')}>
    <span className="sr-only" aria-live="polite" aria-atomic="true">{announcement}</span>
    {ordered.map((item,index)=><article className={`smart-row shopping-row shopping-order-row ${item._offlinePending?'pending-sync':''}`} key={item.id} data-shopping-order-id={item.id}>
      <button type="button" className="shopping-drag-handle" aria-label={t('shoppingOrder.drag',{name:item.name})} onPointerDown={event=>pointerDown(event,item)} onPointerMove={pointerMove} onPointerUp={pointerUp} onPointerCancel={()=>{dragRef.current=null;setOrdered(sourceOpen)}}><Icon name="drag"/></button>
      <button className="smart-check" onClick={()=>onToggle(item)} aria-label={`${item.name} · ${t('complete')}`}><Icon name="check"/></button>
      <button className="smart-row-main row-main-button" onClick={()=>onEdit(item)}><div className="smart-title"><strong>{item.name}</strong>{item._offlinePending&&<span className="shopping-pending-badge"><Icon name="offline" size={12}/>{t('shoppingOffline.pending')}</span>}{item.favorite&&<span className="favorite-badge"><Icon name="favorite"/> {t('favorite')}</span>}</div><div className="smart-meta shopping-meta">{item.quantity&&<span className="shopping-quantity">{item.quantity}</span>}{item.category&&<span>{item.category}</span>}{item.aisle&&<span><Icon name="location"/>{item.aisle}</span>}{item.added_by_name&&<span><Icon name="user"/>{item.added_by_name}</span>}</div>{item.note&&<p>{item.note}</p>}</button>
      <div className="shopping-order-actions"><button type="button" disabled={index===0} onClick={()=>move(item,-1)} aria-label={t('shoppingOrder.moveUp',{name:item.name})}>↑</button><button type="button" disabled={index===ordered.length-1} onClick={()=>move(item,1)} aria-label={t('shoppingOrder.moveDown',{name:item.name})}>↓</button></div>
      <button className={`row-action ${item.favorite?'favorite':''}`} onClick={()=>onFavorite(item)} title={t('favorite')} aria-label={t('markFavorite',{name:item.name})}><Icon name="favorite"/></button>
    </article>)}
  </section>;
}
