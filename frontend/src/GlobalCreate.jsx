import {useEffect,useRef,useState} from 'react';
import {useTranslation} from 'react-i18next';
import './create-i18n';
import './vehicles-i18n';
import './create-smart.css';
import {Icon} from './icons';
import ActionCapture from './ActionCapture';
import {CREATE_PAGES,createActionById} from './create-actions';
import {CREATE_REQUEST_EVENT} from './create-request';
import OverlayPortal from './OverlayPortal';

function appChromeIsSuppressed(){
  if(typeof document==='undefined')return false;
  const root=document.documentElement;
  return root.hasAttribute('data-app-modal')||root.hasAttribute('data-app-keyboard');
}

const hasBlockingDialog=()=>Boolean(document.querySelector('.sheet-backdrop:not(.create-palette-backdrop),[role="dialog"][aria-modal="true"]:not(.create-palette-sheet)'));

export default function GlobalCreate({page,family,role,context={},onCreate,suppressed=false,createActions}){
  const {t}=useTranslation();
  const fabRef=useRef(null);const firstActionRef=useRef(null);const pendingAction=useRef(null);const previousSuppressed=useRef(suppressed);
  const [paletteOpen,setPaletteOpen]=useState(false);const [showAll,setShowAll]=useState(false);const [frozenQuick,setFrozenQuick]=useState([]);const [chromeSuppressed,setChromeSuppressed]=useState(appChromeIsSuppressed);const [restoreFocus,setRestoreFocus]=useState(false);
  const {actions,ranked,direct,options,modules}=createActions;
  const todoDirect=!direct&&page==='todo'?createActionById('task',options):null;
  const directAction=direct||todoDirect;
  const allPrimary=actions.filter(action=>action.group==='primary');const allSecondary=actions.filter(action=>action.group==='secondary');
  const mounted=Boolean(family);
  const modulePage=page==='baby'?'baby':page==='pets'?'pets':null;
  const modulePageAvailable=!modulePage||Boolean(modules[modulePage]?.enabled&&modules[modulePage]?.authorized);
  const eligible=Boolean(family&&role&&CREATE_PAGES.has(page)&&modulePageAvailable);
  const visible=eligible&&!suppressed&&!chromeSuppressed&&!paletteOpen;

  // Modal and keyboard ownership is centralized on documentElement. Global
  // create consumes that contract for visibility instead of running a second
  // VisualViewport/dialog scanner with different timing semantics.
  useEffect(()=>{
    const root=document.documentElement;
    const update=()=>setChromeSuppressed(appChromeIsSuppressed());
    update();
    const observer=new MutationObserver(update);
    observer.observe(root,{attributes:true,attributeFilter:['data-app-modal','data-app-keyboard']});
    return()=>observer.disconnect();
  },[]);

  useEffect(()=>{
    if(previousSuppressed.current&&!suppressed)setRestoreFocus(true);
    previousSuppressed.current=suppressed;
  },[suppressed]);

  useEffect(()=>{
    if(!restoreFocus||!visible)return;
    const frame=requestAnimationFrame(()=>{fabRef.current?.focus({preventScroll:true});setRestoreFocus(false)});
    return()=>cancelAnimationFrame(frame);
  },[restoreFocus,visible]);

  useEffect(()=>{
    if(!paletteOpen)return;
    const keydown=event=>{if(event.key==='Escape'){event.preventDefault();closePalette()}};
    const pop=()=>{
      setPaletteOpen(false);setShowAll(false);setFrozenQuick([]);
      const pending=pendingAction.current;pendingAction.current=null;
      if(pending){pending.action.open({open:onCreate,context:pending.context});return}
      setRestoreFocus(true);
    };
    window.addEventListener('keydown',keydown);window.addEventListener('popstate',pop);requestAnimationFrame(()=>firstActionRef.current?.focus());
    return()=>{window.removeEventListener('keydown',keydown);window.removeEventListener('popstate',pop)};
  },[paletteOpen,onCreate]);

  useEffect(()=>{
    const requested=event=>{
      // Chrome suppression may be caused by a toast or the on-screen keyboard.
      // Those states hide the FAB but must not swallow an explicit programmatic
      // create handoff (for example Shopping reservation → Expense). Only a
      // real modal dialog blocks that handoff.
      if(!eligible||suppressed||paletteOpen||hasBlockingDialog())return;
      const action=createActionById(event.detail?.id,options);if(!action)return;
      anchorCurrentHistory();
      action.open({open:onCreate,context:{...currentContext(),...(event.detail?.context||{})}});
    };
    window.addEventListener(CREATE_REQUEST_EVENT,requested);
    return()=>window.removeEventListener(CREATE_REQUEST_EVENT,requested);
  },[eligible,suppressed,paletteOpen,options,onCreate,page,context]);

  function currentContext(){
    const next={...context,origin:page};
    const selector=page==='tasks'?'.task-list-tabs button.active':page==='shopping'?'.shopping-list-tabs button.active':null;
    if(selector){const label=document.querySelector(selector)?.textContent?.replace(/\s+/g,' ').trim();if(label)next.activeListLabel=label}
    return next;
  }
  function anchorCurrentHistory(){
    const href=`${location.pathname}${location.search}${location.hash}`;
    const base={...(history.state||{}),page};delete base.createPalette;delete base.createFlow;
    if(!base.appNavigation&&!base.appOverlayBase){
      const anchored={...base,appOverlayBase:true};
      history.pushState(anchored,'',href);
      return {base:anchored,href};
    }
    history.replaceState(base,'',href);
    return {base,href};
  }
  function openPalette(){const {base,href}=anchorCurrentHistory();setFrozenQuick(ranked);setShowAll(false);history.pushState({...base,createPalette:true},'',href);setPaletteOpen(true)}
  function closePalette(){pendingAction.current=null;if(history.state?.createPalette)history.back();else{setPaletteOpen(false);setShowAll(false);setFrozenQuick([]);setRestoreFocus(true)}}
  function choose(action){const actionContext=currentContext();pendingAction.current={action,context:actionContext};if(history.state?.createPalette)history.back();else{setPaletteOpen(false);pendingAction.current=null;anchorCurrentHistory();action.open({open:onCreate,context:actionContext})}}
  function activate(){if(directAction){anchorCurrentHistory();directAction.open({open:onCreate,context:currentContext()});return}openPalette()}
  const reasonKey=action=>`createUi.reason.${action.quickstart?.reason||'default'}`;

  if(!mounted&&!paletteOpen)return null;
  return <>
    {mounted&&<div className={`global-create-controls ${directAction?'direct-mode':''}`} style={{display:visible?'flex':'none'}} aria-hidden={!visible} inert={!visible?'':undefined}>
      <button ref={fabRef} type="button" className="global-create-fab" onClick={activate} aria-label={directAction?t('createUi.addNamed',{name:t(directAction.labelKey)}):t('createUi.button')} title={directAction?t('createUi.addNamed',{name:t(directAction.labelKey)}):t('createUi.button')}><Icon name="plus" size={22}/><span>{directAction?t(directAction.labelKey):t('createUi.button')}</span></button>
      {directAction&&<button type="button" className="global-create-menu-button" onClick={openPalette} aria-label={t('createUi.openQuickstart')} title={t('createUi.openQuickstart')}><Icon name="more" size={18}/></button>}
    </div>}
    {paletteOpen&&<OverlayPortal><div className="sheet-backdrop create-palette-backdrop" data-app-modal-root onMouseDown={event=>event.target===event.currentTarget&&closePalette()}><section className="quick-sheet create-palette-sheet" role="dialog" aria-modal="true" aria-labelledby="create-palette-title"><div className="sheet-handle"/><div className="sheet-head"><div><small>{family?.name}</small><h2 id="create-palette-title">{t('createUi.paletteTitle')}</h2></div><button type="button" className="sheet-close" onClick={closePalette} aria-label={t('createUi.close')}><Icon name="close"/></button></div><p className="create-palette-hint">{t('createUi.paletteHint',{family:family?.name||''})}</p>
      <ActionCapture family={family}/>{frozenQuick.length>0&&<div className="create-palette-group"><small>{t('createUi.forYou')}</small><div className="create-action-grid">{frozenQuick.map((action,index)=><button ref={index===0?firstActionRef:null} type="button" className="create-action-card primary-action" key={action.id} onClick={()=>choose(action)}><span><Icon name={action.icon} size={22}/></span><strong>{t(action.labelKey)}</strong><small className="create-action-reason">{t(reasonKey(action))}</small></button>)}</div></div>}
      <button type="button" className="secondary create-all-toggle" aria-expanded={showAll} onClick={()=>setShowAll(value=>!value)}><span>{t(showAll?'createUi.hideAllActions':'createUi.allActions')}</span><Icon name="next" size={14}/></button>
      {showAll&&<div className="create-all-actions"><div className="create-palette-group"><small>{t('createUi.quick')}</small><div className="create-action-list">{allPrimary.map(action=><button type="button" key={action.id} onClick={()=>choose(action)}><Icon name={action.icon}/><span>{t(action.labelKey)}</span><Icon name="next" size={14}/></button>)}</div></div>{allSecondary.length>0&&<div className="create-palette-group"><small>{t('createUi.more')}</small><div className="create-action-list">{allSecondary.map(action=><button type="button" key={action.id} onClick={()=>choose(action)}><Icon name={action.icon}/><span>{t(action.labelKey)}</span><Icon name="next" size={14}/></button>)}</div></div>}</div>}
      {!actions.length&&<p className="create-palette-empty">{t('createUi.noActions')}</p>}
    </section></div></OverlayPortal>}
  </>;
}