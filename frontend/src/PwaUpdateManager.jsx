import {useEffect,useRef,useState} from 'react';
import {useTranslation} from 'react-i18next';
import './pwa-update-i18n';
import './pwa-update.css';
import {Icon} from './icons';
import {DIRTY_STATE_EVENT,hasDirtyState} from './dirty-state';

export const PWA_UPDATE_READY_EVENT='famuhle:pwa-update-ready';

function hasOpenDialog(){return Boolean(document.querySelector('[role="dialog"][aria-modal="true"],[role="alertdialog"][aria-modal="true"]'))}

export default function PwaUpdateManager(){
  const {t}=useTranslation();
  const [ready,setReady]=useState(false);
  const [dirty,setDirty]=useState(()=>hasDirtyState());
  const waitingRef=useRef(null);
  const testActivateRef=useRef(null);
  const activationRequested=useRef(false);
  const controlled=useRef(Boolean(navigator.serviceWorker?.controller));
  const reloading=useRef(false);
  const postponed=useRef(false);
  const changedWithoutReload=useRef(false);

  useEffect(()=>{
    if(!('serviceWorker' in navigator))return;
    let registration=null;
    let disposed=false;

    const markReady=(worker,activate=null)=>{
      waitingRef.current=worker||null;
      testActivateRef.current=activate;
      if(!postponed.current)setReady(true);
    };
    const updateDirty=()=>setDirty(hasDirtyState());
    const onSyntheticReady=event=>{
      postponed.current=false;
      markReady(event.detail?.worker||null,event.detail?.activate||null);
    };
    const onControllerChange=()=>{
      const wasControlled=controlled.current;
      controlled.current=Boolean(navigator.serviceWorker.controller)||wasControlled;
      if(!wasControlled&&!activationRequested.current)return;
      if(reloading.current)return;
      if(!activationRequested.current&&(hasDirtyState()||hasOpenDialog())){
        changedWithoutReload.current=true;
        postponed.current=false;
        setReady(true);
        return;
      }
      reloading.current=true;
      window.location.reload();
    };
    const watchRegistration=reg=>{
      registration=reg;
      if(reg.waiting&&navigator.serviceWorker.controller)markReady(reg.waiting);
      reg.addEventListener('updatefound',()=>{
        const worker=reg.installing;
        if(!worker)return;
        worker.addEventListener('statechange',()=>{
          if(worker.state==='installed'&&navigator.serviceWorker.controller){
            postponed.current=false;
            markReady(reg.waiting||worker);
          }
        });
      });
    };
    const register=async()=>{
      try{
        const reg=await navigator.serviceWorker.register('/sw.js',{updateViaCache:'none'});
        if(disposed)return;
        watchRegistration(reg);
        await reg.update();
      }catch(error){console.warn('Service Worker registration failed',error)}
    };

    window.addEventListener(DIRTY_STATE_EVENT,updateDirty);
    window.addEventListener(PWA_UPDATE_READY_EVENT,onSyntheticReady);
    navigator.serviceWorker.addEventListener('controllerchange',onControllerChange);
    if(document.readyState==='complete')register();else window.addEventListener('load',register,{once:true});
    return()=>{
      disposed=true;
      window.removeEventListener(DIRTY_STATE_EVENT,updateDirty);
      window.removeEventListener(PWA_UPDATE_READY_EVENT,onSyntheticReady);
      navigator.serviceWorker.removeEventListener('controllerchange',onControllerChange);
      window.removeEventListener('load',register);
      registration=null;
    };
  },[]);

  function updateNow(){
    activationRequested.current=true;
    postponed.current=false;
    setReady(false);
    if(testActivateRef.current){testActivateRef.current();return}
    const worker=waitingRef.current;
    if(worker){worker.postMessage({type:'SKIP_WAITING'});return}
    if(changedWithoutReload.current&&!reloading.current){reloading.current=true;window.location.reload()}
  }
  function later(){postponed.current=true;setReady(false)}

  if(!ready)return null;
  return <aside className="pwa-update-banner" role="status" aria-live="polite" data-testid="pwa-update-banner">
    <span className="pwa-update-icon" aria-hidden="true"><Icon name="refresh"/></span>
    <div className="pwa-update-copy"><strong>{t('pwaUpdate.title')}</strong><span>{dirty?t('pwaUpdate.dirtyMessage'):t('pwaUpdate.message')}</span></div>
    <div className="pwa-update-actions"><button className="text-button" type="button" onClick={later}>{t('pwaUpdate.later')}</button><button className="primary compact" type="button" onClick={updateNow}>{t('pwaUpdate.now')}</button></div>
  </aside>;
}
