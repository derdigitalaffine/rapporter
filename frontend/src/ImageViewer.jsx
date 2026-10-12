import {useEffect,useRef} from 'react';
import {createPortal} from 'react-dom';
import {Icon} from './icons';
import './image-viewer.css';

const focusableSelector='button:not([disabled]),a[href],input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])';

export default function ImageViewer({images=[],activeIndex=0,onActiveIndexChange,onClose,labels={}}){
 const dialogRef=useRef(null),closeRef=useRef(null),indexRef=useRef(activeIndex),imagesRef=useRef(images),changeRef=useRef(onActiveIndexChange),closeHandlerRef=useRef(onClose);
 indexRef.current=activeIndex;imagesRef.current=images;changeRef.current=onActiveIndexChange;closeHandlerRef.current=onClose;

 useEffect(()=>{
  const returnFocus=document.activeElement;
  const previousOverflow=document.body.style.overflow;
  document.body.style.overflow='hidden';
  closeRef.current?.focus();
  const handleKeyDown=event=>{
   if(event.key==='Escape'){
    event.preventDefault();closeHandlerRef.current?.();return;
   }
   if(event.key==='ArrowLeft'){
    if(indexRef.current>0){event.preventDefault();changeRef.current?.(indexRef.current-1)}
    return;
   }
   if(event.key==='ArrowRight'){
    if(indexRef.current<imagesRef.current.length-1){event.preventDefault();changeRef.current?.(indexRef.current+1)}
    return;
   }
   if(event.key!=='Tab')return;
   const focusable=[...(dialogRef.current?.querySelectorAll(focusableSelector)||[])];
   if(!focusable.length){event.preventDefault();dialogRef.current?.focus();return}
   const first=focusable[0],last=focusable[focusable.length-1],active=document.activeElement;
   if(event.shiftKey&&(active===first||!dialogRef.current?.contains(active))){event.preventDefault();last.focus()}
   else if(!event.shiftKey&&(active===last||!dialogRef.current?.contains(active))){event.preventDefault();first.focus()}
  };
  document.addEventListener('keydown',handleKeyDown);
  return()=>{
   document.removeEventListener('keydown',handleKeyDown);
   document.body.style.overflow=previousOverflow;
   requestAnimationFrame(()=>{if(!dialogRef.current?.isConnected&&returnFocus?.isConnected)returnFocus.focus?.()});
  };
 },[]);

 if(!images.length)return null;
 const safeIndex=Math.min(Math.max(activeIndex,0),images.length-1),image=images[safeIndex];
 const position=labels.position?.(safeIndex+1,images.length)||`${safeIndex+1} / ${images.length}`;
 const previous=()=>safeIndex>0&&onActiveIndexChange?.(safeIndex-1);
 const next=()=>safeIndex<images.length-1&&onActiveIndexChange?.(safeIndex+1);

 return createPortal(<div className="image-viewer-layer" onMouseDown={event=>{if(event.target===event.currentTarget)onClose?.()}}>
  <section ref={dialogRef} className="image-viewer" role="dialog" aria-modal="true" aria-label={labels.dialog||'Image viewer'} tabIndex={-1}>
   <header className="image-viewer-head">
    <span className="image-viewer-position" aria-live="polite">{position}</span>
    <button ref={closeRef} type="button" className="image-viewer-button" onClick={onClose} aria-label={labels.close||'Close image viewer'}><Icon name="close" size={22}/></button>
   </header>
   <div className="image-viewer-stage" onMouseDown={event=>{if(event.target===event.currentTarget)onClose?.()}}>
    <img src={image.url} width={image.width||undefined} height={image.height||undefined} alt={image.alt||''}/>
   </div>
   <nav className="image-viewer-controls" aria-label={labels.navigation||'Image navigation'}>
    <button type="button" className="image-viewer-button image-viewer-nav" onClick={previous} disabled={safeIndex===0} aria-label={labels.previous||'Previous image'}><Icon name="back" size={20}/><span>{labels.previousShort||''}</span></button>
    <span aria-hidden="true">{safeIndex+1} / {images.length}</span>
    <button type="button" className="image-viewer-button image-viewer-nav" onClick={next} disabled={safeIndex===images.length-1} aria-label={labels.next||'Next image'}><span>{labels.nextShort||''}</span><Icon name="next" size={20}/></button>
   </nav>
  </section>
 </div>,document.body);
}
