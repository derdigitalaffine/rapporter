import {useEffect,useRef,useState} from 'react';
import FamilyDialog from './ui/FamilyDialog';
import FamilyToastHost,{familyToast} from './ui/FamilyToast';

let nextId=1;
const listeners=new Set();
const emit=payload=>listeners.forEach(fn=>fn(payload));

export const toast=familyToast;

export function confirmAction({title,message,confirmLabel='Bestätigen',cancelLabel='Abbrechen',danger=false}={}){
  if(!listeners.size)return Promise.resolve(false);
  const returnFocus=document.activeElement;
  return new Promise(resolve=>emit({kind:'confirm',id:nextId++,title,message,confirmLabel,cancelLabel,danger,returnFocus,resolve}));
}

export default function FeedbackHost(){
  const [queue,setQueue]=useState([]);
  const pending=useRef(new Map());

  useEffect(()=>{
    const listener=event=>{
      pending.current.set(event.id,event);
      setQueue(items=>[...items,event]);
    };
    listeners.add(listener);
    return()=>{listeners.delete(listener);for(const request of pending.current.values())request.resolve(false);pending.current.clear()};
  },[]);

  function answer(id,value){
    const current=pending.current.get(id);
    if(!current)return;
    pending.current.delete(id);
    current.resolve(value);
    setQueue(items=>items.filter(item=>item.id!==id));
  }

  if(typeof document==='undefined')return null;
  const current=queue[0];
  return <><FamilyToastHost/>{current&&<FamilyDialog key={current.id} {...current} onAnswer={value=>answer(current.id,value)}/>}</>;
}
