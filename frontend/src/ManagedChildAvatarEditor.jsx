import {useEffect,useState} from 'react';
import {useTranslation} from 'react-i18next';
import {api} from './api';
import {Icon} from './icons';
import {toast} from './feedback';
import MemberAvatar from './MemberAvatar';
import AvatarAppearanceEditor from './AvatarAppearanceEditor';
import FileDropZone from './FileDropZone';
import ProfilePhotoCropper from './ProfilePhotoCropper';

export default function ManagedChildAvatarEditor({child}){
 const {t}=useTranslation();
 const [appearance,setAppearance]=useState(null);
 const [busy,setBusy]=useState(false);
 const [cropFile,setCropFile]=useState(null);
 const endpoint=child?.id?`/baby/memberships/${child.id}/avatar/`:'';
 async function load(){if(!endpoint)return;try{setAppearance(await api(endpoint))}catch(error){if(error?.status!==403&&error?.status!==404)toast(error.message||t('connectionFailed'),{type:'error'});setAppearance(null)}}
 useEffect(()=>{load()},[endpoint]);
 if(!appearance)return null;
 const person={...child,...appearance,avatar:appearance.avatar_url};
 async function saveAppearance(){setBusy(true);try{const row=await api(endpoint,{method:'PATCH',body:JSON.stringify({avatar_mode:appearance.avatar_mode,avatar_icon_key:appearance.avatar_icon_key||'',avatar_color:appearance.avatar_color})});setAppearance(row);toast(t('profileUi.childAppearanceSaved'),{type:'success'})}catch(error){toast(error.message||t('profileUi.childAppearanceFailed'),{type:'error'})}finally{setBusy(false)}}
 function choosePhoto(file){if(file&&!busy)setCropFile(file)}
 async function editCurrentPhoto(){if(!appearance.avatar_url||busy)return;setBusy(true);try{const response=await fetch(appearance.avatar_edit_url||appearance.avatar_url,{credentials:'same-origin'});if(!response.ok)throw new Error(t('profileUi.photoEditFailed'));const blob=await response.blob();if(!blob.type.startsWith('image/'))throw new Error(t('profileUi.photoEditFailed'));setCropFile(new File([blob],'current-child-profile-photo.webp',{type:blob.type||'image/webp',lastModified:Date.now()}))}catch(error){toast(error.message||t('profileUi.photoEditFailed'),{type:'error'})}finally{setBusy(false)}}
 async function upload(file){if(!file)return false;setBusy(true);try{const body=new FormData();body.append('avatar',file);if(cropFile)body.append('avatar_source',cropFile);const row=await api(endpoint,{method:'POST',body});setAppearance(row);setCropFile(null);toast(t('profileUi.childPhotoSaved'),{type:'success'});return true}catch(error){toast(error.message||t('profileUi.childPhotoFailed'),{type:'error'});return false}finally{setBusy(false)}}
 async function removePhoto(){setBusy(true);try{const row=await api(endpoint,{method:'DELETE'});setAppearance(row);toast(t('profileUi.childPhotoRemoved'),{type:'success'})}catch(error){toast(error.message||t('profileUi.childPhotoFailed'),{type:'error'})}finally{setBusy(false)}}
 return <section className="child-access-card managed-child-avatar-editor" data-testid="managed-child-avatar-editor">
  <div className="child-access-head"><div><small>KINDERPROFIL</small><strong>{t('profileUi.childAvatarTitle')}</strong></div><MemberAvatar person={person} size={64}/></div>
  <p>{t('profileUi.childAvatarHint')}</p>
  <AvatarAppearanceEditor value={appearance} onChange={setAppearance} hasPhoto={Boolean(appearance.avatar_url)} disabled={busy} t={t}/>
  <div className="child-profile-photo-actions"><FileDropZone className="compact" accept="image/jpeg,image/png,image/webp,image/heic,image/heif,.heic,.heif" disabled={busy} icon="upload" title={t('profileUi.choose')} hint={t('profileUi.photoHint')} onFiles={files=>choosePhoto(files[0])}/>{appearance.avatar_url&&<><button type="button" className="secondary compact" onClick={editCurrentPhoto} disabled={busy}><Icon name="edit"/>{t('profileUi.editPhoto')}</button><button type="button" className="ghost-danger compact" onClick={removePhoto} disabled={busy}><Icon name="delete"/>{t('profileUi.remove')}</button></>}</div>
  <button type="button" className="primary" onClick={saveAppearance} disabled={busy}>{busy?t('pleaseWait'):t('save')}</button>
  {cropFile&&<ProfilePhotoCropper file={cropFile} busy={busy} t={t} onCancel={()=>{if(!busy)setCropFile(null)}} onConfirm={upload}/>} 
 </section>;
}
