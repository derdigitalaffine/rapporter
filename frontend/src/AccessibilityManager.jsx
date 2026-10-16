import {useEffect} from 'react';

const DIALOG_SELECTOR='[role="dialog"][aria-modal="true"],[role="alertdialog"][aria-modal="true"]';
const MODAL_ROOT_SELECTOR='[data-app-modal-root],.sheet-backdrop,.feedback-dialog-backdrop';
const FOCUSABLE_SELECTOR='button:not([disabled]),a[href],input:not([disabled]),select:not([disabled]),textarea:not([disabled]),summary,[tabindex]:not([tabindex="-1"])';
let titleId=0;

function visible(element){
  if(!(element instanceof HTMLElement))return false;
  const style=getComputedStyle(element);
  return style.display!=='none'&&style.visibility!=='hidden'&&element.getClientRects().length>0;
}

function modalRoot(dialog){
  return dialog?.closest(MODAL_ROOT_SELECTOR)||dialog||null;
}

function topModal(){
  const dialog=[...document.querySelectorAll(DIALOG_SELECTOR)].filter(visible).at(-1)||null;
  return dialog?{dialog,root:modalRoot(dialog)}:null;
}

function sameModal(left,right){
  return left?.dialog===right?.dialog&&left?.root===right?.root;
}

function labelDialog(dialog){
  if(dialog.hasAttribute('aria-label')||dialog.hasAttribute('aria-labelledby'))return;
  const heading=dialog.querySelector('h1,h2,h3');
  if(!heading)return;
  if(!heading.id)heading.id=`famuhle-dialog-title-${++titleId}`;
  dialog.setAttribute('aria-labelledby',heading.id);
}

function focusables(dialog){
  return [...dialog.querySelectorAll(FOCUSABLE_SELECTOR)].filter(visible);
}

function initialFocus(dialog){
  const current=document.activeElement;
  if(current instanceof HTMLElement&&dialog.contains(current)&&visible(current))return current;
  const preferred=dialog.querySelector('[data-autofocus],input[autofocus],textarea[autofocus],select[autofocus]');
  if(preferred instanceof HTMLElement&&!preferred.hasAttribute('disabled'))return preferred;
  return focusables(dialog)[0]||dialog;
}

function inertOutside(modalRootElement){
  const changed=[];
  let node=modalRootElement;
  while(node&&node!==document.body){
    const parent=node.parentElement;
    if(!parent)break;
    for(const sibling of parent.children){
      if(sibling===node||sibling.contains(modalRootElement))continue;
      if(!(sibling instanceof HTMLElement))continue;
      changed.push({element:sibling,inert:sibling.inert,ariaHidden:sibling.getAttribute('aria-hidden')});
      sibling.inert=true;
      sibling.setAttribute('aria-hidden','true');
    }
    node=parent;
  }
  return()=>{
    for(const item of changed){
      if(!item.element.isConnected)continue;
      item.element.inert=item.inert;
      if(item.ariaHidden===null)item.element.removeAttribute('aria-hidden');
      else item.element.setAttribute('aria-hidden',item.ariaHidden);
    }
  };
}

export default function AccessibilityManager(){
  useEffect(()=>{
    const root=document.documentElement;
    let active=null;
    let restoreBackground=()=>{};
    let restoreFocus=null;
    let lastOutsideFocus=document.activeElement instanceof HTMLElement?document.activeElement:null;
    let focusTimer=0;
    let refreshFrame=0;

    function activate(next){
      if(sameModal(next,active))return;
      const wasManaged=active?.dialog.hasAttribute('data-family-overlay-owner');
      restoreBackground();
      restoreBackground=()=>{};
      window.clearTimeout(focusTimer);
      root.toggleAttribute('data-app-modal',Boolean(next));
      if(!next){
        active=null;
        const target=restoreFocus;
        restoreFocus=null;
        if(!wasManaged&&target instanceof HTMLElement&&target.isConnected)target.focus({preventScroll:true});
        return;
      }
      const dialog=next.dialog;
      if(!active){
        const current=document.activeElement;
        restoreFocus=lastOutsideFocus instanceof HTMLElement&&lastOutsideFocus.isConnected?lastOutsideFocus:(current instanceof HTMLElement&&!dialog.contains(current)?current:null);
      }
      active=next;
      if(dialog.hasAttribute('data-family-overlay-owner'))return;
      labelDialog(dialog);
      if(!dialog.hasAttribute('tabindex'))dialog.setAttribute('tabindex','-1');
      // The portal/backdrop is the modal boundary. Inerting outside only the
      // inner dialog can leave sibling chrome or a parent sheet pointer-active.
      restoreBackground=inertOutside(next.root);
      focusTimer=window.setTimeout(()=>initialFocus(dialog)?.focus({preventScroll:true}),0);
    }

    function refresh(){
      cancelAnimationFrame(refreshFrame);
      refreshFrame=requestAnimationFrame(()=>{refreshFrame=0;activate(topModal())});
    }
    function onFocusIn(event){
      const target=event.target;
      if(target instanceof HTMLElement&&!topModal())lastOutsideFocus=target;
    }

    function onKeyDown(event){
      if(topModal()?.dialog.hasAttribute('data-family-overlay-owner'))return;
      const dialog=active?.dialog;
      if(!dialog||!dialog.isConnected)return;
      if(event.key==='Escape'){
        const close=dialog.querySelector('[data-dialog-close],.sheet-close,[data-dialog-cancel]');
        if(close instanceof HTMLButtonElement&&!close.disabled){event.preventDefault();close.click()}
        return;
      }
      if(event.key!=='Tab')return;
      const items=focusables(dialog);
      if(!items.length){event.preventDefault();dialog.focus();return}
      const first=items[0],last=items.at(-1);
      if(event.shiftKey&&(document.activeElement===first||!dialog.contains(document.activeElement))){event.preventDefault();last.focus()}
      else if(!event.shiftKey&&(document.activeElement===last||!dialog.contains(document.activeElement))){event.preventDefault();first.focus()}
    }

    const observer=new MutationObserver(refresh);
    function yieldOwnership(){restoreBackground();restoreBackground=()=>{};window.clearTimeout(focusTimer);}
    document.addEventListener('familyos:managed-overlay-mount',yieldOwnership);
    observer.observe(document.body,{subtree:true,childList:true,attributes:true,attributeFilter:['aria-modal','hidden']});
    document.addEventListener('focusin',onFocusIn,true);
    document.addEventListener('keydown',onKeyDown,true);
    activate(topModal());
    return()=>{
      observer.disconnect();
      document.removeEventListener('familyos:managed-overlay-mount',yieldOwnership);
      cancelAnimationFrame(refreshFrame);
      document.removeEventListener('focusin',onFocusIn,true);
      document.removeEventListener('keydown',onKeyDown,true);
      window.clearTimeout(focusTimer);
      restoreBackground();
      root.removeAttribute('data-app-modal');
    };
  },[]);
  return null;
}
