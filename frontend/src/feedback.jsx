import {useEffect,useRef,useState} from 'react';
import {Icon} from './icons';

let nextId=1;
const listeners=new Set();
const emit=payload=>listeners.forEach(fn=>fn(payload));

export function toast(message,{type='info',actionLabel='',onAction=null,duration=6000}={}){
  const id=nextId++;
  emit({kind:'toast',id,message,type,actionLabel,onAction,duration});
  return id;
}

export function confirmAction({title,message,confirmLabel='Bestätigen',cancelLabel='Abbrechen',danger=false}={}){
  return new Promise(resolve=>emit({kind:'confirm',id:nextId++,title,message,confirmLabel,cancelLabel,danger,resolve}));
}

export default function FeedbackHost(){
  const [toasts,setToasts]=useState([]);
  const [confirm,setConfirm]=useState(null);
  const timers=useRef(new Map());

  useEffect(()=>{
    const listener=event=>{
      if(event.kind==='toast'){
        setToasts(items=>[...items,event]);
        const timer=setTimeout(()=>dismiss(event.id),event.duration||6000);
        timers.current.set(event.id,timer);
      }else if(event.kind==='confirm')setConfirm(event);
    };
    listeners.add(listener);
    return()=>{listeners.delete(listener);for(const timer of timers.current.values())clearTimeout(timer)};
  },[]);

  function dismiss(id){
    const timer=timers.current.get(id);if(timer)clearTimeout(timer);timers.current.delete(id);
    setToasts(items=>items.filter(item=>item.id!==id));
  }
  function answer(value){
    const current=confirm;setConfirm(null);current?.resolve?.(value);
  }

  return <>
    <div className="toast-region" aria-live="polite" aria-atomic="false">
      {toasts.map(item=><div className={`toast toast-${item.type}`} key={item.id} role={item.type==='error'?'alert':'status'}>
        <span className="toast-icon"><Icon name={item.type==='success'?'check':item.type==='error'?'warning':item.type==='warning'?'warning':'info'}/></span>
        <span className="toast-message">{item.message}</span>
        {item.actionLabel&&<button className="toast-action" onClick={()=>{dismiss(item.id);item.onAction?.()}}>{item.actionLabel}</button>}
        <button className="toast-close" aria-label="Meldung schließen" onClick={()=>dismiss(item.id)}><Icon name="close"/></button>
      </div>)}
    </div>
    {confirm&&<div className="sheet-backdrop confirm-backdrop" onMouseDown={e=>{if(e.target===e.currentTarget)answer(false)}}>
      <section className="confirm-dialog" role="alertdialog" aria-modal="true" aria-labelledby="confirm-title" aria-describedby={confirm.message?'confirm-message':undefined}>
        <div className={`confirm-icon ${confirm.danger?'danger':''}`}><Icon name={confirm.danger?'warning':'info'}/></div>
        <h2 id="confirm-title">{confirm.title}</h2>
        {confirm.message&&<p id="confirm-message">{confirm.message}</p>}
        <div className="confirm-actions">
          <button className="secondary" data-dialog-cancel onClick={()=>answer(false)} autoFocus>{confirm.cancelLabel}</button>
          <button className={confirm.danger?'destructive':'primary compact'} onClick={()=>answer(true)}>{confirm.confirmLabel}</button>
        </div>
      </section>
    </div>}
  </>;
}
