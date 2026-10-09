import {useEffect,useMemo,useState} from 'react';
import {useTranslation} from 'react-i18next';
import './onboarding-i18n';
import {Icon} from './icons';

const dismissedKey=id=>`famuhle-onboarding-dismissed:${id||'family'}`;

export default function OnboardingCard({family,data,open}){
  const {t}=useTranslation();
  const [dismissed,setDismissed]=useState(()=>localStorage.getItem(dismissedKey(family?.id))==='1');
  useEffect(()=>setDismissed(localStorage.getItem(dismissedKey(family?.id))==='1'),[family?.id]);

  const state=useMemo(()=>{
    const tasks=data.tasks||[];
    const shoppingLists=data.shopping_lists||[];
    const hasShopping=shoppingLists.some(list=>(list.items||[]).length>0);
    const memberships=family?.memberships||[];
    const hasMember=memberships.length>1;
    const hasEvent=(data.events||[]).some(event=>event.type==='calendar.event'&&(!event.source||event.payload?.provider==='fam-uh-le'));
    return {hasTask:tasks.length>0,hasShopping,hasMember,hasEvent};
  },[data,family]);

  const coreDone=[state.hasTask,state.hasShopping,state.hasMember].filter(Boolean).length;
  const allDone=coreDone===3&&state.hasEvent;
  if(dismissed||allDone)return null;

  const steps=[
    {id:'task',done:state.hasTask,icon:'tasks',page:'tasks'},
    {id:'shopping',done:state.hasShopping,icon:'shopping',page:'shopping'},
    {id:'member',done:state.hasMember,icon:'members',page:'members'},
    {id:'calendar',done:state.hasEvent,icon:'calendar',page:'calendar',optional:true},
  ];

  function hide(){localStorage.setItem(dismissedKey(family?.id),'1');setDismissed(true)}

  return <section className={`onboarding-card ${coreDone===3?'ready':''}`} aria-labelledby="onboarding-title">
    <div className="onboarding-head">
      <div><small>{coreDone===3?t('onboarding.ready'):t('onboarding.progress',{done:coreDone,total:3})}</small><h2 id="onboarding-title">{t('onboarding.title')}</h2><p>{coreDone===3?t('onboarding.readyHint'):t('onboarding.intro')}</p></div>
      <button className="onboarding-dismiss" onClick={hide} aria-label={t('onboarding.hide')}><Icon name="close"/></button>
    </div>
    <div className="onboarding-progress" aria-hidden="true"><span style={{width:`${Math.round(coreDone/3*100)}%`}}/></div>
    <div className="onboarding-steps">
      {steps.map(step=><button key={step.id} className={`onboarding-step ${step.done?'done':''}`} onClick={()=>!step.done&&open(step.page)}>
        <span className="onboarding-step-icon"><Icon name={step.done?'check':step.icon}/></span>
        <span className="grow"><strong>{t(`onboarding.${step.id}`)}</strong><small>{t(`onboarding.${step.id}Hint`)}</small></span>
        {step.optional&&!step.done&&<em>{t('onboarding.optional')}</em>}
        {step.done?<span className="onboarding-done">{t('onboarding.done')}</span>:<Icon name="next"/>}
      </button>)}
    </div>
    <div className="onboarding-foot"><button className="secondary compact" onClick={hide}>{t('onboarding.showLater')}</button>{coreDone===3&&<button className="primary compact" onClick={()=>open('calendar')}><Icon name="calendar"/> {t('onboarding.continue')}</button>}</div>
  </section>;
}
