import {useEffect,useMemo,useRef,useState} from 'react';
import {useTranslation} from 'react-i18next';
import './create-i18n';
import './create-smart.css';
import {api} from './api';
import {availableCreateActions,normalizeCreateRankingProfile} from './create-actions';
import {createRankingScope,createRankingScopeKey,fetchCreateRanking,loadCachedCreateRanking,patchCreateRanking} from './create-ranking-client';
import {toast} from './feedback';
import {Icon} from './icons';

const CAPABILITIES={loyalty:true,messages:false};
const EMPTY_MODULES={baby:null,pets:null};

export default function QuickstartSettings({family,role,userId}){
 const {t}=useTranslation();
 const familyId=family?.id;
 const scope=createRankingScope(family,userId);
 const scopeKey=createRankingScopeKey(scope);
 const [profileView,setProfileView]=useState(()=>({scopeKey:'',profile:normalizeCreateRankingProfile({})}));
 const profile=profileView.scopeKey===scopeKey?profileView.profile:normalizeCreateRankingProfile({});
 const setProfile=next=>setProfileView({scopeKey,profile:next});
 const currentScope=useRef(scopeKey);currentScope.current=scopeKey;
 const [loading,setLoading]=useState(true);
 const [modules,setModules]=useState(EMPTY_MODULES);
 const [busy,setBusy]=useState(false);
 useEffect(()=>{
  let live=true;if(!familyId)return()=>{live=false};
  setLoading(true);setBusy(false);setProfile(loadCachedCreateRanking(scope));
  Promise.all([
   fetchCreateRanking(scope).catch(()=>null),
   api(`/baby/module/?family=${encodeURIComponent(familyId)}`).catch(()=>null),
   api(`/pets/module/?family=${encodeURIComponent(familyId)}`).catch(()=>null),
  ]).then(([next,baby,pets])=>{if(!live)return;if(next)setProfile(next);setModules({baby,pets});setLoading(false)});
  return()=>{live=false};
 },[scopeKey]);
 const actions=useMemo(()=>availableCreateActions({role,capabilities:CAPABILITIES,modules}),[role,modules]);
 const preferences=profile.preferences;
 const actionById=useMemo(()=>new Map(actions.map(action=>[action.id,action])),[actions]);
 const ordered=useMemo(()=>{
  const result=[];
  for(const id of preferences.manual_order){const action=actionById.get(id);if(action&&!result.includes(action))result.push(action)}
  for(const action of actions)if(!result.includes(action))result.push(action);
  return result;
 },[actions,actionById,preferences.manual_order]);
 async function save(patch,message='createUi.settingsSaved'){
  if(!familyId||busy||loading)return;const previous=profile;const savedScope=scopeKey;setBusy(true);
  setProfile(normalizeCreateRankingProfile({...profile,preferences:{...profile.preferences,...patch}}));
  try{const next=await patchCreateRanking(scope,patch);if(currentScope.current!==savedScope)return;if(next)setProfile(next);else setProfile(previous);if(next)toast(t(message),{type:'success'})}
  catch(error){if(currentScope.current!==savedScope)return;setProfile([401,403,404].includes(error.status)?normalizeCreateRankingProfile({}):previous);toast(error.message||t('createUi.settingsFailed'),{type:'error'})}
  finally{if(currentScope.current===savedScope)setBusy(false)}
 }
 function togglePin(id){
  const pinned=preferences.pinned_action_ids.includes(id);
  const nextPinned=pinned?preferences.pinned_action_ids.filter(value=>value!==id):[...preferences.pinned_action_ids,id];
  const nextHidden=preferences.hidden_action_ids.filter(value=>value!==id);
  save({pinned_action_ids:nextPinned,hidden_action_ids:nextHidden});
 }
 function setAutomatic(id){
  save({
   pinned_action_ids:preferences.pinned_action_ids.filter(value=>value!==id),
   hidden_action_ids:preferences.hidden_action_ids.filter(value=>value!==id),
  });
 }
 function toggleHidden(id){
  const hidden=preferences.hidden_action_ids.includes(id);
  const nextHidden=hidden?preferences.hidden_action_ids.filter(value=>value!==id):[...preferences.hidden_action_ids,id];
  const nextPinned=preferences.pinned_action_ids.filter(value=>value!==id);
  save({hidden_action_ids:nextHidden,pinned_action_ids:nextPinned});
 }
 function move(id,direction){
  const ids=ordered.map(action=>action.id);const index=ids.indexOf(id);const target=index+direction;if(index<0||target<0||target>=ids.length)return;
  [ids[index],ids[target]]=[ids[target],ids[index]];save({manual_order:ids});
 }
 if(!familyId||!role)return null;
 return <section className="card quickstart-settings" aria-labelledby="quickstart-settings-title">
  <div className="quickstart-settings-head"><div><small>{t('createUi.advancedSettings')}</small><h2 id="quickstart-settings-title">{t('createUi.settingsTitle')}</h2><p>{t('createUi.settingsHint')}</p></div><Icon name="plus" size={24}/></div>
  <label className="quickstart-setting-toggle"><input type="checkbox" checked={preferences.smart_ranking_enabled} disabled={loading||busy} onChange={event=>save({smart_ranking_enabled:event.target.checked})}/><span>{t('createUi.smartRanking')}</span></label>
  <label className="quickstart-setting-toggle"><input type="checkbox" checked={preferences.context_ranking_enabled} disabled={loading||busy} onChange={event=>save({context_ranking_enabled:event.target.checked})}/><span>{t('createUi.contextRanking')}</span></label>
  <details className="quickstart-settings-advanced"><summary>{t('createUi.advancedSettings')}</summary><div className="quickstart-settings-fields">
   <label>{t('createUi.quickCount')}<select value={preferences.max_quick_actions} disabled={loading||busy} onChange={event=>save({max_quick_actions:Number(event.target.value)})}>{[2,3,4,5,6].map(value=><option key={value} value={value}>{value}</option>)}</select></label>
   <label>{t('createUi.learningScope')}<select value={preferences.learning_scope} disabled={loading||busy} onChange={event=>save({learning_scope:event.target.value})}><option value="family">{t('createUi.familyScope')}</option><option value="global">{t('createUi.globalScope')}</option></select></label>
   <label className="quickstart-setting-toggle"><input type="checkbox" checked={preferences.time_patterns_enabled} disabled={loading||busy} onChange={event=>save({time_patterns_enabled:event.target.checked})}/><span>{t('createUi.timePatterns')}</span></label>
   <label className="quickstart-setting-toggle"><input type="checkbox" checked={preferences.direct_mode} disabled={loading||busy} onChange={event=>save({direct_mode:event.target.checked})}/><span>{t('createUi.directMode')}</span></label>
   {preferences.direct_mode&&<label>{t('createUi.directAction')}<select value={preferences.direct_action_id} disabled={loading||busy} onChange={event=>save({direct_action_id:event.target.value})}><option value="">{t('createUi.dynamicDirect')}</option>{actions.filter(action=>!preferences.hidden_action_ids.includes(action.id)).map(action=><option key={action.id} value={action.id}>{t(action.labelKey)}</option>)}</select></label>}
  </div></details>
  <div className="quickstart-settings-actions" aria-label={t('createUi.actionsLabel')}>{ordered.map((action,index)=>{const pinned=preferences.pinned_action_ids.includes(action.id);const hidden=preferences.hidden_action_ids.includes(action.id);const automatic=!pinned&&!hidden;return <div className={`quickstart-settings-action ${hidden?'hidden-action':''}`} key={action.id}><Icon name={action.icon} size={18}/><strong>{t(action.labelKey)}</strong><div className="quickstart-settings-action-buttons"><button type="button" disabled={loading||busy} onClick={()=>togglePin(action.id)} aria-pressed={pinned}>{t(pinned?'createUi.unpin':'createUi.pin')}</button><button type="button" disabled={loading||busy||automatic} onClick={()=>setAutomatic(action.id)} aria-pressed={automatic}>{t('createUi.automatic')}</button><button type="button" disabled={loading||busy} onClick={()=>toggleHidden(action.id)} aria-pressed={hidden}>{t(hidden?'createUi.show':'createUi.hide')}</button><button type="button" disabled={loading||busy||index===0} onClick={()=>move(action.id,-1)} aria-label={`${t('createUi.moveUp')}: ${t(action.labelKey)}`}><Icon name="back" size={14}/></button><button type="button" disabled={loading||busy||index===ordered.length-1} onClick={()=>move(action.id,1)} aria-label={`${t('createUi.moveDown')}: ${t(action.labelKey)}`}><Icon name="next" size={14}/></button></div></div>})}</div>
  <button type="button" className="secondary quickstart-reset" disabled={loading||busy} onClick={()=>save({reset_learning:true},'createUi.resetDone')}>{t('createUi.resetLearning')}</button>
 </section>;
}
