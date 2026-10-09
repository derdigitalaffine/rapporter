import {useEffect,useRef} from 'react';

export const DIRTY_STATE_EVENT='famuhle:dirty-state-change';
const dirtyForms=new Set();

function notify(){
  window.dispatchEvent(new CustomEvent(DIRTY_STATE_EVENT,{detail:{dirty:dirtyForms.size>0}}));
}

export function hasDirtyState(){return dirtyForms.size>0}

export function useDirtyForm(dirty){
  const token=useRef(Symbol('dirty-form'));
  useEffect(()=>{
    const key=token.current;
    if(dirty)dirtyForms.add(key);else dirtyForms.delete(key);
    notify();
    return()=>{dirtyForms.delete(key);notify()};
  },[dirty]);
}
