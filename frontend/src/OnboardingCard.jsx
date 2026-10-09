import {useEffect,useMemo,useState} from 'react';
import {useTranslation} from 'react-i18next';
import './onboarding-i18n';
import {api} from './api';
import {Icon} from './icons';

const dismissedKey=id=>`famuhle-onboarding-dismissed:${id||'family'}`;
const achievedKey=id=>`famuhle-onboarding-achieved:${id||'family'}`;
const readAchieved=id=>{try{return new Set(JSON.parse(localStorage.getItem(achievedKey(id))||'[]'))}catch{return new Set()}};
const unwrap=x=>x?.results||x||[];

export default function OnboardingCard({family,data,open}){
  const {t}=useTranslation();
  const familyId=family?.id;
  const [dismissed,setDismissed]=useState(()=>localStorage.getItem(dismissedKey(familyId))==='1');
  const [achieved,setAchieved]=useState(()=>readAchieved(familyId));
  const [integrationActive,setIntegrationActive]=useState(()=>Number(data.enabled_integration_count||0)>0);
  useEffect(()=>{setDismissed(localStorage.getItem(dismissedKey(familyId))==='1');setAchieved(readAchieved(familyId))},[familyId]);
  useEffect(()=>{
    setIntegrationActive(Number(data.enabled_integration_count||0)>0);
    if(!familyId)return;
    let alive=true;
    api('/integrations/').then(result=>{if(alive)setIntegrationActive(unwrap(result).some(item=>String(item.family)===String(familyId)&&item.enabled!==false))}).catch(()=>{});
    return()=>{alive=false};
  },[familyId,data.enabled_integration_count]);

  const observed=useMemo(()=>{
    const tasks=data.tasks||[];
    const shoppingLists=data.shopping_lists||[];
    const memberships=family?.memberships||[];
    return {
      task:tasks.length>0,
      shopping:shoppingLists.some(list=>(list.items||[]).length>0),
      member:memberships.length>1,
      calendar:(data.events||[]).some(event=>event.type==='calendar.event'&&(!event.source||event.payload?.provider==='fam-uh-le')),
      integration:integrationActive,
    };
  },[data,family,integrationActive]);

  useEffect(()=>{
    if(!familyId)return;
    setAchieved(previous=>{
      const next=new Set(previous);let changed=false;
      Object.entries(observed).forEach(([key,done])=>{if(key!=='integration'&&done&&!next.has(key)){next.add(key);changed=true}});
      if(changed)localStorage.setItem(achievedKey(familyId),JSON.stringify([...next]));
      return changed?next:previous;
    });
  },[familyId,observed.task,observed.shopping,observed.member,observed.calendar]);

  const done=id=>id==='integration'?observed.integration:achieved.has(id)||observed[id];
  const coreDone=['task','shopping','member'].filter(done).length;
  const allDone=coreDone===3&&done('calendar')&&done('integration');
  if(!familyId||dismissed||allDone)return null;

  const steps=[
    {id:'task',done:done('task'),icon:'tasks',page:'tasks'},
    {id:'shopping',done:done('shopping'),icon:'shopping',page:'shopping'},
    {id:'member',done:done('member'),icon:'members',page:'members'},
    {id:'calendar',done:done('calendar'),icon:'calendar',page:'calendar',optional:true},
    {id:'integration',done:done('integration'),icon:'integrations',page:'integrations',recommended:true},
  ];

  function hide(){localStorage.setItem(dismissedKey(familyId),'1');setDismissed(true)}
  const nextOptional=!done('calendar')?{page:'calendar',icon:'calendar',label:t('onboarding.continue')}:!done('integration')?{page:'integrations',icon:'integrations',label:t('onboarding.integrationAction')}:null;

  return <section className={`onboarding-card ${coreDone===3?'ready':''}`} aria-labelledby="onboarding-title">
    <div className="onboarding-head">
      <div><small>{coreDone===3?t('onboarding.ready'):t('onboarding.progress',{done:coreDone,total:3})}</small><h2 id="onboarding-title">{t('onboarding.title')}</h2><p>{coreDone===3?t('onboarding.readyHint'):t('onboarding.intro')}</p></div>
      <button className="onboarding-dismiss" onClick={hide} aria-label={t('onboarding.hide')}><Icon name="close"/></button>
    </div>
    <div className="onboarding-progress" aria-hidden="true"><span style={{width:`${Math.round(coreDone/3*100)}%`}}/></div>
    {coreDone===3&&<div className="onboarding-more-label">{t('onboarding.moreSteps')}</div>}
    <div className="onboarding-steps">
      {steps.map(step=><button key={step.id} className={`onboarding-step ${step.done?'done':''}`} onClick={()=>!step.done&&open(step.page)}>
        <span className="onboarding-step-icon"><Icon name={step.done?'check':step.icon}/></span>
        <span className="grow"><strong>{t(`onboarding.${step.id}`)}</strong><small>{t(`onboarding.${step.id}Hint`)}</small></span>
        {step.optional&&!step.done&&<em>{t('onboarding.optional')}</em>}
        {step.recommended&&!step.done&&<em>{t('onboarding.recommended')}</em>}
        {step.done?<span className="onboarding-done">{t('onboarding.done')}</span>:<Icon name="next"/>}
      </button>)}
    </div>
    <div className="onboarding-foot"><button className="secondary compact" onClick={hide}>{t('onboarding.showLater')}</button>{coreDone===3&&nextOptional&&<button className="primary compact" onClick={()=>open(nextOptional.page)}><Icon name={nextOptional.icon}/> {nextOptional.label}</button>}</div>
  </section>;
}
