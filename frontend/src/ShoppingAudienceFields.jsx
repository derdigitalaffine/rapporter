import {useEffect,useMemo,useState} from 'react';
import {useTranslation} from 'react-i18next';
import {api} from './api';
import {Icon} from './icons';
import MemberAvatar from './MemberAvatar';
import './shopping-access-i18n';
import './shopping-access.css';

export const defaultShoppingAudience=()=>({visibility:'family',visible_members:[],responsible_members:[]});

function ids(rows){return (rows||[]).map(row=>typeof row==='string'?row:String(row.id));}
function normalizeOptions(data){return {members:Array.isArray(data?.members)?data.members:[],groups:Array.isArray(data?.groups)?data.groups:[]};}
function Person({member,showRole=false,t}){return <><MemberAvatar person={member} size={34} decorative/><span className="shopping-member-copy"><strong>{member.name}</strong>{showRole&&<small>{t(member.role,{defaultValue:member.role})}</small>}</span></>}

export default function ShoppingAudienceFields({family,value,onChange,compact=false}){
  const {t}=useTranslation();
  const [options,setOptions]=useState({members:[],groups:[]});
  const [state,setState]=useState('loading');
  const current=value||defaultShoppingAudience();
  useEffect(()=>{
    if(!family?.id){setOptions({members:[],groups:[]});setState('ready');return}
    let alive=true;setState('loading');
    api(`/shopping-audience-options/?family=${family.id}`).then(data=>{if(alive){setOptions(normalizeOptions(data));setState('ready')}}).catch(()=>alive&&setState('error'));
    return()=>{alive=false};
  },[family?.id]);
  const memberMap=useMemo(()=>new Map((options.members||[]).map(member=>[String(member.id),member])),[options.members]);
  const patch=next=>onChange?.({...current,...next});
  const toggle=(field,id)=>{const existing=new Set(ids(current[field]));existing.has(id)?existing.delete(id):existing.add(id);patch({[field]:[...existing]})};
  const applyGroup=group=>{
    const roleIds=(options.members||[]).filter(member=>group==='adults'?['owner','adult'].includes(member.role):['teen','child'].includes(member.role)).map(member=>String(member.id));
    patch({visibility:'selected',visible_members:roleIds});
  };
  const selectedNames=ids(current.visible_members).map(id=>memberMap.get(id)?.name).filter(Boolean);
  const responsibleNames=ids(current.responsible_members).map(id=>memberMap.get(id)?.name).filter(Boolean);
  return <fieldset className={`shopping-audience ${compact?'shopping-audience--compact':''}`}>
    <legend>{t('shoppingAccess.audience')}</legend>
    <div className="shopping-audience-choices" role="radiogroup" aria-label={t('shoppingAccess.audience')}>
      {[['family','users',t('shoppingAccess.family')],['private','lock',t('shoppingAccess.private')],['selected','user',t('shoppingAccess.selected')]].map(([mode,icon,label])=><button key={mode} type="button" role="radio" aria-checked={current.visibility===mode} className={current.visibility===mode?'selected':''} onClick={()=>patch({visibility:mode,visible_members:mode==='selected'?current.visible_members:[]})}><Icon name={icon}/><span>{label}</span></button>)}
    </div>
    {current.visibility==='selected'&&<div className="shopping-audience-detail"><small>{t('shoppingAccess.selectedHint')}</small>{state==='loading'&&<span role="status">{t('shoppingAccess.loading')}</span>}{state==='error'&&<span role="alert">{t('shoppingAccess.unavailable')}</span>}{state==='ready'&&<><div className="shopping-audience-groups"><button type="button" onClick={()=>applyGroup('adults')}>{t('shoppingAccess.adults')}</button><button type="button" onClick={()=>applyGroup('children')}>{t('shoppingAccess.children')}</button></div><div className="shopping-member-grid" role="group" aria-label={t('shoppingAccess.people')}>{(options.members||[]).map(member=><label key={member.id}><input type="checkbox" checked={ids(current.visible_members).includes(String(member.id))} onChange={()=>toggle('visible_members',String(member.id))}/><Person member={member} showRole t={t}/></label>)}</div></>}</div>}
    <div className="shopping-responsibility"><strong>{t('shoppingAccess.responsibility')}</strong><small>{t('shoppingAccess.responsibilityHint')}</small>{state==='ready'&&<div className="shopping-member-grid" role="group" aria-label={t('shoppingAccess.responsibility')}>{(options.members||[]).map(member=><label key={member.id}><input type="checkbox" checked={ids(current.responsible_members).includes(String(member.id))} onChange={()=>toggle('responsible_members',String(member.id))}/><Person member={member} t={t}/></label>)}</div>}<span className="sr-only" aria-live="polite">{selectedNames.join(', ')} {responsibleNames.join(', ')}</span></div>
  </fieldset>;
}
