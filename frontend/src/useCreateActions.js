import {useEffect,useMemo,useState} from 'react';
import {api} from './api';
import {availableCreateActions,normalizeCreateRankingProfile,rankCreateActions,resolveDirectCreateAction} from './create-actions';
import {CREATE_RANKING_UPDATED_EVENT,createRankingScope,createRankingScopeKey,fetchCreateRanking,flushCreateUsageQueue,loadCachedCreateRanking} from './create-ranking-client';
import {readFamilyModuleRuntime} from './family-runtime';

const CAPABILITIES={loyalty:true,messages:false};
const EMPTY_MODULES={baby:null,pets:null};
const hasOwn=(value,key)=>Boolean(value)&&Object.prototype.hasOwnProperty.call(value,key);

// One canonical snapshot shared by the global palette and Today; no widget reads.
export function useCreateActions({userId,page,family,entitlements}){
  const [moduleState,setModuleState]=useState({familyId:null,userId:null,...EMPTY_MODULES});
  const [rankingView,setRankingView]=useState(()=>({scopeKey:'',profile:normalizeCreateRankingProfile({})}));
  useEffect(()=>{
    let live=true;
    const familyId=family?.id||null;
    if(!familyId){setModuleState({familyId:null,userId:null,...EMPTY_MODULES});return()=>{live=false}};
    const cached=readFamilyModuleRuntime(familyId);
    const needsBaby=!hasOwn(cached,'baby'),needsPets=!hasOwn(cached,'pets');
    if(!needsBaby&&!needsPets){setModuleState({familyId,userId,baby:cached.baby,pets:cached.pets});return()=>{live=false}};
    setModuleState({familyId:null,userId:null,...EMPTY_MODULES});
    Promise.all([
      needsBaby?api(`/baby/module/?family=${encodeURIComponent(familyId)}`).catch(()=>null):Promise.resolve(cached.baby),
      needsPets?api(`/pets/module/?family=${encodeURIComponent(familyId)}`).catch(()=>null):Promise.resolve(cached.pets),
    ]).then(([baby,pets])=>{if(live)setModuleState({familyId,userId,baby,pets})});
    return()=>{live=false};
  },[family?.id,userId]);
  const rankingScope=useMemo(()=>createRankingScope(family,userId),[family,userId]);
  const scopeKey=createRankingScopeKey(rankingScope);
  const rankingProfile=rankingView.scopeKey===scopeKey?rankingView.profile:normalizeCreateRankingProfile({});
  const setRankingProfile=profile=>setRankingView({scopeKey,profile});
  useEffect(()=>{
    let live=true;
    if(!rankingScope){setRankingProfile(normalizeCreateRankingProfile({}));return}
    setRankingProfile(loadCachedCreateRanking(rankingScope));
    fetchCreateRanking(rankingScope).then(profile=>{if(live&&profile)setRankingProfile(profile)}).catch(()=>{});
    flushCreateUsageQueue(rankingScope).catch(()=>{});
    const update=event=>{if(event.detail?.scopeKey===scopeKey&&event.detail?.profile)setRankingProfile(normalizeCreateRankingProfile(event.detail.profile))};
    const online=()=>flushCreateUsageQueue(rankingScope).catch(()=>{});
    window.addEventListener(CREATE_RANKING_UPDATED_EVENT,update);window.addEventListener('online',online);
    return()=>{live=false;window.removeEventListener(CREATE_RANKING_UPDATED_EVENT,update);window.removeEventListener('online',online)};
  },[scopeKey]);
  const modules=moduleState.familyId===family?.id&&moduleState.userId===userId?moduleState:EMPTY_MODULES;
  const role=userId!=null?family?.memberships?.find(row=>String(row.user)===String(userId))?.role:null;
  const options=useMemo(()=>({role,capabilities:{...CAPABILITIES,vehicles:Boolean(entitlements?.capabilities?.includes('vehicles'))},modules}),[role,modules,entitlements]);
  const actions=useMemo(()=>family?availableCreateActions(options):[],[family,options]);
  const ranked=useMemo(()=>rankCreateActions({availableActions:actions,page,profile:rankingProfile}),[actions,page,rankingProfile]);
  const direct=useMemo(()=>resolveDirectCreateAction({availableActions:actions,rankedActions:ranked,profile:rankingProfile}),[actions,ranked,rankingProfile]);
  return {actions,ranked,direct,options,modules};
}
