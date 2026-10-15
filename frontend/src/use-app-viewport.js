import {useEffect} from 'react';

const KEYBOARD_THRESHOLD=140;
const NON_TEXT_INPUT_TYPES=new Set(['button','checkbox','color','file','hidden','radio','range','reset','submit']);

function hasEditableFocus(){
 const active=document.activeElement;
 if(!active?.matches)return false;
 if(active.matches('textarea,select,[contenteditable]:not([contenteditable="false"])'))return !active.disabled&&!active.readOnly;
 if(!active.matches('input'))return false;
 return !active.disabled&&!active.readOnly&&!NON_TEXT_INPUT_TYPES.has((active.type||'text').toLowerCase());
}

function keyboardIsOpen(viewport){
 if(!viewport||Math.abs((viewport.scale||1)-1)>=0.01||!hasEditableFocus())return false;
 return window.innerHeight-viewport.height>KEYBOARD_THRESHOLD;
}

export default function useAppViewport(active=true){
 useEffect(()=>{
  const root=document.documentElement;
  const mode=window.matchMedia('(display-mode: standalone)');
  const update=()=>root.toggleAttribute('data-app-standalone',active&&(mode.matches||navigator.standalone===true));
  update();
  mode.addEventListener('change',update);
  return()=>{mode.removeEventListener('change',update);root.removeAttribute('data-app-standalone')};
 },[active]);
 useEffect(()=>{
  const viewport=window.visualViewport;
  if(!viewport)return;
  const root=document.documentElement;
  let frame=0;

  function clearKeyboardState(){
   root.removeAttribute('data-app-keyboard');
   root.style.setProperty('--app-keyboard-inset','0px');
  }

  function update(){
   frame=0;
   // The layout viewport owns permanent app chrome. VisualViewport is only a
   // measurement of the area currently visible above a focused OS keyboard.
   // Do not resize or translate the app shell/backdrop from these values.
   const keyboardOpen=keyboardIsOpen(viewport);
   const layoutHeight=Math.max(1,window.innerHeight||viewport.height||1);
   const height=keyboardOpen?Math.max(1,Math.min(layoutHeight,viewport.height)):layoutHeight;
   const top=keyboardOpen?Math.max(0,Math.min(viewport.offsetTop||0,layoutHeight-height)):0;
   const keyboardInset=keyboardOpen?Math.max(0,layoutHeight-(top+height)):0;
   root.style.setProperty('--app-viewport-height',`${height}px`);
   root.style.setProperty('--app-viewport-top',`${top}px`);
   root.style.setProperty('--app-viewport-bottom','0px');
   root.style.setProperty('--app-keyboard-inset',`${keyboardInset}px`);
   root.toggleAttribute('data-app-keyboard',keyboardOpen);
  }
  function schedule(){if(!frame)frame=requestAnimationFrame(update)}
  function onFocusOut(){
   // iOS can keep a stale shrunken VisualViewport for a frame (or longer)
   // after focus leaves an editor. Stop suppressing app chrome immediately;
   // the next measurement may update geometry but cannot reopen keyboard state
   // without an editable element actually owning focus.
   queueMicrotask(()=>{
    if(!hasEditableFocus())clearKeyboardState();
    schedule();
   });
  }

  update();
  viewport.addEventListener('resize',schedule);
  viewport.addEventListener('scroll',schedule);
  window.addEventListener('resize',schedule);
  window.addEventListener('orientationchange',schedule);
  window.addEventListener('pageshow',schedule);
  document.addEventListener('focusin',schedule);
  document.addEventListener('focusout',onFocusOut);
  document.addEventListener('visibilitychange',schedule);
  return()=>{
   cancelAnimationFrame(frame);
   viewport.removeEventListener('resize',schedule);
   viewport.removeEventListener('scroll',schedule);
   window.removeEventListener('resize',schedule);
   window.removeEventListener('orientationchange',schedule);
   window.removeEventListener('pageshow',schedule);
   document.removeEventListener('focusin',schedule);
   document.removeEventListener('focusout',onFocusOut);
   document.removeEventListener('visibilitychange',schedule);
   root.removeAttribute('data-app-keyboard');
   root.style.removeProperty('--app-keyboard-inset');
   for(const name of ['height','top','bottom'])root.style.removeProperty(`--app-viewport-${name}`);
  };
 },[]);
}
