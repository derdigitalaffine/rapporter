import {useEffect,useMemo,useState} from 'react';
import {useTranslation} from 'react-i18next';
import ImageViewer from './ImageViewer';

const TRIGGER_SELECTOR='[data-image-viewer],.pin-photos a[href]';
const COPY={
 de:{dialog:'Fotoansicht',close:'Fotoansicht schließen',navigation:'Fotos durchblättern',previous:'Vorheriges Foto',next:'Nächstes Foto',previousShort:'Zurück',nextShort:'Weiter',position:(current,total)=>`Foto ${current} von ${total}`},
 en:{dialog:'Photo viewer',close:'Close photo viewer',navigation:'Browse photos',previous:'Previous photo',next:'Next photo',previousShort:'Back',nextShort:'Next',position:(current,total)=>`Photo ${current} of ${total}`},
 fr:{dialog:'Visionneuse de photos',close:'Fermer la visionneuse',navigation:'Parcourir les photos',previous:'Photo précédente',next:'Photo suivante',previousShort:'Précédent',nextShort:'Suivant',position:(current,total)=>`Photo ${current} sur ${total}`},
 nl:{dialog:'Fotoviewer',close:'Fotoviewer sluiten',navigation:'Door foto’s bladeren',previous:'Vorige foto',next:'Volgende foto',previousShort:'Vorige',nextShort:'Volgende',position:(current,total)=>`Foto ${current} van ${total}`},
 th:{dialog:'ดูรูปภาพ',close:'ปิดตัวดูรูปภาพ',navigation:'เลื่อนดูรูปภาพ',previous:'รูปก่อนหน้า',next:'รูปถัดไป',previousShort:'ก่อนหน้า',nextShort:'ถัดไป',position:(current,total)=>`รูป ${current} จาก ${total}`},
};

function collectGallery(trigger){
 const group=trigger.closest('[data-image-gallery],.pin-photos');
 const triggers=group?[...group.querySelectorAll('a[href],[data-image-viewer]')].filter(node=>node.matches(TRIGGER_SELECTOR)):[trigger];
 const images=triggers.map(node=>{const image=node.querySelector('img');return {url:node.href||node.dataset.imageViewer,width:Number(image?.getAttribute('width'))||undefined,height:Number(image?.getAttribute('height'))||undefined,alt:image?.getAttribute('alt')||''}}).filter(image=>image.url);
 return {images,index:Math.max(0,triggers.indexOf(trigger))};
}

export default function ImageViewerHost(){
 const {i18n}=useTranslation();
 const [viewer,setViewer]=useState(null);
 const language=i18n.language.split('-')[0];
 const labels=useMemo(()=>COPY[language]||COPY.en,[language]);
 useEffect(()=>{
  const handleClick=event=>{
   if(event.defaultPrevented||event.button!==0||event.metaKey||event.ctrlKey||event.shiftKey||event.altKey)return;
   const trigger=event.target.closest?.(TRIGGER_SELECTOR);
   if(!trigger||trigger.hasAttribute('download'))return;
   const {images,index}=collectGallery(trigger);
   if(!images.length)return;
   event.preventDefault();
   setViewer({images,index});
  };
  const close=()=>setViewer(null);
  document.addEventListener('click',handleClick);
  window.addEventListener('popstate',close);
  return()=>{document.removeEventListener('click',handleClick);window.removeEventListener('popstate',close)};
 },[]);
 if(!viewer)return null;
 return <ImageViewer images={viewer.images} activeIndex={viewer.index} onActiveIndexChange={index=>setViewer(current=>current?{...current,index}:current)} onClose={()=>setViewer(null)} labels={labels}/>;
}
