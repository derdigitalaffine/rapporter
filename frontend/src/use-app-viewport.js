import {useEffect} from 'react';

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
  function update(){
   frame=0;
   // Pin app chrome above the keyboard without following pinch-zoom panning.
   const unzoomed=Math.abs(viewport.scale-1)<0.01;
   const height=unzoomed?Math.min(window.innerHeight,viewport.height):window.innerHeight;
   const top=unzoomed?Math.max(0,Math.min(viewport.offsetTop,window.innerHeight-height)):0;
   root.style.setProperty('--app-viewport-height',`${height}px`);
   root.style.setProperty('--app-viewport-top',`${top}px`);
   root.style.setProperty('--app-viewport-bottom',`${Math.max(0,window.innerHeight-height-top)}px`);
  }
  function schedule(){if(!frame)frame=requestAnimationFrame(update)}
  update();
  viewport.addEventListener('resize',schedule);
  viewport.addEventListener('scroll',schedule);
  window.addEventListener('resize',schedule);
  return()=>{
   cancelAnimationFrame(frame);
   viewport.removeEventListener('resize',schedule);
   viewport.removeEventListener('scroll',schedule);
   window.removeEventListener('resize',schedule);
   for(const name of ['height','top','bottom'])root.style.removeProperty(`--app-viewport-${name}`);
  };
 },[]);
}
