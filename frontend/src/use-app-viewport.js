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
  let frame=0,focusFrame=0;
  function update(){
   frame=0;
   // VisualViewport also moves for zooming, elastic panning and transient iOS
   // sheet/keyboard transitions. Only a focused editor may shrink the visible
   // editing surface; permanent app chrome remains on the layout viewport.
   const keyboardOpen=keyboardIsOpen(viewport);
   const height=keyboardOpen?Math.max(1,Math.min(window.innerHeight,viewport.height)):window.innerHeight;
   const top=keyboardOpen?Math.max(0,Math.min(viewport.offsetTop||0,window.innerHeight-height)):0;
   const occlusion=keyboardOpen?Math.max(0,window.innerHeight-(top+height)):0;
   root.style.setProperty('--app-viewport-height',`${height}px`);
   root.style.setProperty('--app-viewport-top',`${top}px`);
   root.style.setProperty('--app-keyboard-occlusion',`${occlusion}px`);
   // Persistent app chrome is anchored to the layout viewport. Keep the legacy
   // variable neutral so stale iOS VisualViewport state cannot lift the UI.
   root.style.setProperty('--app-viewport-bottom','0px');
   root.toggleAttribute('data-app-keyboard',keyboardOpen);

   cancelAnimationFrame(focusFrame);
   if(keyboardOpen){
    // The content viewport is resized by CSS after this frame. Re-run native
    // nearest scrolling once layout has settled so an already-focused field
    // cannot remain underneath the OS keyboard.
    focusFrame=requestAnimationFrame(()=>{
     const focused=document.activeElement;
     if(focused instanceof HTMLElement&&hasEditableFocus())focused.scrollIntoView({block:'nearest',inline:'nearest'});
    });
   }
  }
  function schedule(){if(!frame)frame=requestAnimationFrame(update)}
  update();
  viewport.addEventListener('resize',schedule);
  viewport.addEventListener('scroll',schedule);
  window.addEventListener('resize',schedule);
  window.addEventListener('orientationchange',schedule);
  window.addEventListener('pageshow',schedule);
  document.addEventListener('focusin',schedule);
  document.addEventListener('focusout',schedule);
  document.addEventListener('visibilitychange',schedule);
  return()=>{
   cancelAnimationFrame(frame);
   cancelAnimationFrame(focusFrame);
   viewport.removeEventListener('resize',schedule);
   viewport.removeEventListener('scroll',schedule);
   window.removeEventListener('resize',schedule);
   window.removeEventListener('orientationchange',schedule);
   window.removeEventListener('pageshow',schedule);
   document.removeEventListener('focusin',schedule);
   document.removeEventListener('focusout',schedule);
   document.removeEventListener('visibilitychange',schedule);
   root.removeAttribute('data-app-keyboard');
   root.style.removeProperty('--app-keyboard-occlusion');
   for(const name of ['height','top','bottom'])root.style.removeProperty(`--app-viewport-${name}`);
  };
 },[]);
}
