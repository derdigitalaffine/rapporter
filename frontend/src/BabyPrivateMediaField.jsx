import {useState} from 'react';
import {api} from './api';
import FileDropZone from './FileDropZone';
import {toast} from './feedback';

export default function BabyPrivateMediaField({
 familyId,
 scope,
 pregnancyId,
 babyId,
 media,
 onChange,
 accept='image/jpeg,image/png,image/webp',
 capture,
 title,
 hint,
 disabled=false,
 savedLabel='Private Datei ausgewählt',
 removeLabel='Entfernen',
 errorLabel='Upload fehlgeschlagen',
}){
 const [uploading,setUploading]=useState(false);

 async function upload(files){
  const file=files?.[0];
  if(!file||uploading||disabled)return;
  setUploading(true);
  try{
   if(media?.id){
    await api(`/baby/media/${media.id}/`,{method:'DELETE'}).catch(()=>{});
   }
   const body=new FormData();
   body.append('family',familyId);
   body.append('scope',scope);
   if(pregnancyId)body.append('pregnancy',pregnancyId);
   if(babyId)body.append('baby',babyId);
   body.append('file',file);
   const row=await api('/baby/media/',{method:'POST',body});
   onChange?.(row);
  }catch(error){
   toast(error.message||errorLabel,{type:'error'});
  }finally{
   setUploading(false);
  }
 }

 async function remove(){
  if(!media?.id)return onChange?.(null);
  setUploading(true);
  try{
   await api(`/baby/media/${media.id}/`,{method:'DELETE'});
   onChange?.(null);
  }catch(error){
   toast(error.message||errorLabel,{type:'error'});
  }finally{
   setUploading(false);
  }
 }

 return <div className="baby-private-media-field">
  <FileDropZone
   accept={accept}
   capture={capture}
   disabled={disabled||uploading}
   icon="upload"
   title={uploading?'…':title}
   hint={hint}
   onFiles={upload}
  />
  {media&&<div className="baby-media-selection"><span><strong>{savedLabel}</strong><small>{media.content_type}</small></span><button type="button" className="text-button" disabled={uploading} onClick={remove}>{removeLabel}</button></div>}
 </div>;
}
