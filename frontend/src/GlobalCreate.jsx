import {useEffect,useMemo,useRef,useState} from 'react';
import {useTranslation} from 'react-i18next';
import './create-i18n';
import {Icon} from './icons';
import {availableCreateActions,CREATE_PAGES,directCreateAction} from './create-actions';

const CAPABILITIES={loyalty:true,messages:false};

export default function GlobalCreate({page,family,role,context={},onCreate,suppressed=false}){
  const {t}=useTranslation();
  const fabRef=useRef(null);const firstActionRef=useRef(null);const pendingAction=useRef(null);
  const [paletteOpen,setPaletteOpen]=useState(false);const [keyboardOpen,setKeyboardOpen]=useState(false);const [externalDialog,setExternalDialog]=useState(false);
  const options=useMemo(()=>({role,capabilities:CAPABILITIES}),[role]);
  const actions=useMemo(()=>availableCreateActions(options),[options]);
  const direct=useMemo(()=>directCreateAction(page,options),[page,options]);
  const primary=actions.filter(action=>action.group==='primary');const secondary=actions.filter(action=>action.group==='secondary');
  const eligible=Boolean(family&&role&&CREATE_PAGES.has(page));
  const visible=eligible&&!suppressed&&!keyboardOpen&&!externalDialog&&!paletteOpen;

  useEffect(()=>{
    const viewport=window.visualViewport;if(!viewport)return;
    const update=()=>setKeyboardOpen(window.innerHeight-viewport.height>140);
    update();viewport.addEventListener('resize',update);viewport.addEventListener('scroll',update);
    return()=>{viewport.removeEventListener('resize',update);viewport.removeEventListener('scroll',update)};
  },[]);

  useEffect(()=>{
    const update=()=>setExternalDialog(Boolean(document.querySelector('.sheet-backdrop:not(.create-palette-backdrop),[role="dialog"][aria-modal="true"]:not(.create-palette-sheet),.toast-region .toast')));
    update();const observer=new MutationObserver(update);observer.observe(document.body,{childList:true,subtree:true});return()=>observer.disconnect();
  },[]);

  useEffect(()=>{
    if(!paletteOpen)return;
    const keydown=event=>{if(event.key==='Escape'){event.preventDefault();closePalette()}};
    const pop=()=>{
      setPaletteOpen(false);
      const pending=pendingAction.current;pendingAction.current=null;
      if(pending){pending.action.open({open:onCreate,context:pending.context});return}
      requestAnimationFrame(()=>fabRef.current?.focus({preventScroll:true}));
    };
    window.addEventListener('keydown',keydown);window.addEventListener('popstate',pop);requestAnimationFrame(()=>firstActionRef.current?.focus());
    return()=>{window.removeEventListener('keydown',keydown);window.removeEventListener('popstate',pop)};
  },[paletteOpen,onCreate]);

  useEffect(()=>{if(!suppressed&&eligible&&fabRef.current)requestAnimationFrame(()=>fabRef.current?.focus({preventScroll:true}))},[suppressed,eligible]);

  function currentContext(){
    const next={...context,origin:page};
    const selector=page==='tasks'?'.task-list-tabs button.active':page==='shopping'?'.shopping-list-tabs button.active':null;
    if(selector){const label=document.querySelector(selector)?.textContent?.replace(/\s+/g,' ').trim();if(label)next.activeListLabel=label}
    return next;
  }
  function openPalette(){history.pushState({...history.state,createPalette:true},'',`${location.pathname}${location.search}${location.hash}`);setPaletteOpen(true)}
  function closePalette(){pendingAction.current=null;if(history.state?.createPalette)history.back();else{setPaletteOpen(false);requestAnimationFrame(()=>fabRef.current?.focus({preventScroll:true}))}}
  function choose(action){const actionContext=currentContext();pendingAction.current={action,context:actionContext};if(history.state?.createPalette)history.back();else{setPaletteOpen(false);pendingAction.current=null;action.open({open:onCreate,context:actionContext})}}
  function activate(){if(direct){direct.open({open:onCreate,context:currentContext()});return}openPalette()}

  if(!eligible&&!paletteOpen)return null;
  return <>
    {eligible&&<button ref={fabRef} type="button" className="global-create-fab" style={{display:visible?'flex':'none'}} onClick={activate} aria-label={direct?t('createUi.addNamed',{name:t(direct.labelKey)}):t('createUi.button')} title={direct?t('createUi.addNamed',{name:t(direct.labelKey)}):t('createUi.button')}><Icon name="plus" size={22}/><span>{direct?t(direct.labelKey):t('createUi.button')}</span></button>}
    {paletteOpen&&<div className="sheet-backdrop create-palette-backdrop" onMouseDown={event=>event.target===event.currentTarget&&closePalette()}><section className="quick-sheet create-palette-sheet" role="dialog" aria-modal="true" aria-labelledby="create-palette-title"><div className="sheet-handle"/><div className="sheet-head"><div><small>{family?.name}</small><h2 id="create-palette-title">{t('createUi.paletteTitle')}</h2></div><button className="sheet-close" onClick={closePalette} aria-label={t('createUi.close')}><Icon name="close"/></button></div><p className="create-palette-hint">{t('createUi.paletteHint',{family:family?.name||''})}</p>{primary.length>0&&<div className="create-palette-group"><small>{t('createUi.quick')}</small><div className="create-action-grid">{primary.map((action,index)=><button ref={index===0?firstActionRef:null} type="button" className="create-action-card primary-action" key={action.id} onClick={()=>choose(action)}><span><Icon name={action.icon} size={22}/></span><strong>{t(action.labelKey)}</strong><Icon name="next" size={14}/></button>)}</div></div>}{secondary.length>0&&<div className="create-palette-group"><small>{t('createUi.more')}</small><div className="create-action-list">{secondary.map(action=><button type="button" key={action.id} onClick={()=>choose(action)}><Icon name={action.icon}/><span>{t(action.labelKey)}</span><Icon name="next" size={14}/></button>)}</div></div>}{!actions.length&&<p className="create-palette-empty">{t('createUi.noActions')}</p>}</section></div>}
  </>;
}
