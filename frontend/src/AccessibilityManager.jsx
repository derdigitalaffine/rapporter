import {useEffect} from 'react';

const DIALOG_SELECTOR='[role="dialog"][aria-modal="true"],[role="alertdialog"][aria-modal="true"]';
const FOCUSABLE_SELECTOR='button:not([disabled]),a[href],input:not([disabled]),select:not([disabled]),textarea:not([disabled]),summary,[tabindex]:not([tabindex="-1"])';
let titleId=0;

function visible(element){
  if(!(element instanceof HTMLElement))return false;
  const style=getComputedStyle(element);
  return style.display!=='none'&&style.visibility!=='hidden'&&element.getClientRects().length>0;
}

function topDialog(){
  return [...document.querySelectorAll(DIALOG_SELECTOR)].filter(visible).at(-1)||null;
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

function inertOutside(dialog){
  const changed=[];
  let node=dialog;
  while(node&&node!==document.body){
    const parent=node.parentElement;
    if(!parent)break;
    for(const sibling of parent.children){
      if(sibling===node||sibling.contains(dialog))continue;
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
    let active=null;
    let restoreBackground=()=>{};
    let restoreFocus=null;
    let focusTimer=0;

    function activate(next){
      if(next===active)return;
      restoreBackground();
      window.clearTimeout(focusTimer);
      if(!next){
        active=null;
        const target=restoreFocus;
        restoreFocus=null;
        if(target instanceof HTMLElement&&target.isConnected)target.focus({preventScroll:true});
        return;
      }
      if(!active)restoreFocus=document.activeElement;
      active=next;
      labelDialog(active);
      if(!active.hasAttribute('tabindex'))active.setAttribute('tabindex','-1');
      restoreBackground=inertOutside(active);
      focusTimer=window.setTimeout(()=>initialFocus(active)?.focus({preventScroll:true}),0);
    }

    function refresh(){activate(topDialog())}

    function onKeyDown(event){
      if(!active||!active.isConnected)return;
      if(event.key==='Escape'){
        const close=active.querySelector('[data-dialog-close],.sheet-close,[data-dialog-cancel]');
        if(close instanceof HTMLButtonElement&&!close.disabled){event.preventDefault();close.click()}
        return;
      }
      if(event.key!=='Tab')return;
      const items=focusables(active);
      if(!items.length){event.preventDefault();active.focus();return}
      const first=items[0],last=items.at(-1);
      if(event.shiftKey&&(document.activeElement===first||!active.contains(document.activeElement))){event.preventDefault();last.focus()}
      else if(!event.shiftKey&&(document.activeElement===last||!active.contains(document.activeElement))){event.preventDefault();first.focus()}
    }

    const observer=new MutationObserver(refresh);
    observer.observe(document.body,{subtree:true,childList:true});
    document.addEventListener('keydown',onKeyDown,true);
    refresh();
    return()=>{
      observer.disconnect();
      document.removeEventListener('keydown',onKeyDown,true);
      window.clearTimeout(focusTimer);
      restoreBackground();
    };
  },[]);
  return null;
}