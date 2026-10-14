import {useEffect} from 'react';

export default function useAppViewport(){
 useEffect(()=>{
  const viewport=window.visualViewport;
  if(!viewport)return;
  const root=document.documentElement;
  let frame=0;
  function update(){
   frame=0;
   // Pin app chrome above the keyboard without following pinch-zoom panning.
   const unzoomed=Math.abs(viewport.scale-1)<0.01;
   const height=unzoomed?viewport.height:window.innerHeight;
   const top=unzoomed?viewport.offsetTop:0;
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
