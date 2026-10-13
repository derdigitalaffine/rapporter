import {permissionsForRole} from './family-permissions';

const matches=page=>({page:current})=>current===page;
const matchesAny=(...pages)=>({page:current})=>pages.includes(current);
const nowhere=()=>false;

export const CREATE_ACTIONS=[
  {id:'vehicle',labelKey:'vehiclesUi.add',icon:'route',group:'secondary',permission:'manageSettings',capability:'vehicles',contextMatcher:matches('vehicles'),open:({open,context})=>open('vehicle',context)},
  {id:'task',labelKey:'createUi.task',icon:'tasks',group:'primary',permission:'createContent',contextMatcher:matchesAny('tasks','todo'),open:({open,context})=>open('task',context)},
  {id:'shoppingItem',labelKey:'createUi.shoppingItem',icon:'shopping',group:'primary',permission:'createContent',contextMatcher:matches('shopping'),open:({open,context})=>open('shoppingItem',context)},
  {id:'event',labelKey:'createUi.event',icon:'calendar',group:'primary',permission:'createContent',contextMatcher:matches('calendar'),open:({open,context})=>open('event',context)},
  {id:'expense',capability:'expenses',labelKey:'createUi.expense',icon:'receipt',group:'primary',permission:'createContent',contextMatcher:matches('expenses'),open:({open,context})=>open('expense',context)},
  {id:'contract',labelKey:'createUi.contract',icon:'receipt',group:'secondary',permission:'createContent',contextMatcher:matches('contracts'),open:({open,context})=>open('contract',context)},
  {id:'correspondence',labelKey:'createUi.correspondence',icon:'inbox',group:'secondary',permission:'createContent',contextMatcher:nowhere,open:({open,context})=>open('correspondence',context)},
  {id:'wish',labelKey:'createUi.wish',icon:'heart',group:'secondary',permission:'manageSettings',contextMatcher:matches('wishlists'),open:({open,context})=>open('wish',context)},
  {id:'birthday',labelKey:'birthdayUi.add',icon:'calendar',group:'secondary',permission:'manageSettings',contextMatcher:matches('birthdays'),open:({open,context})=>open('birthday',context)},
  {id:'baby',labelKey:'createUi.baby',icon:'baby',group:'secondary',permission:'createContent',module:'baby',contextMatcher:matches('baby'),open:({open,context})=>open('baby',context)},
  {id:'pets',labelKey:'createUi.pets',icon:'pet',group:'secondary',permission:'createContent',module:'pets',contextMatcher:matches('pets'),open:({open,context})=>open('pets',context)},
  {id:'taskList',labelKey:'createUi.taskList',icon:'lists',group:'secondary',permission:'createContent',contextMatcher:nowhere,open:({open,context})=>open('taskList',context)},
  {id:'shoppingList',labelKey:'createUi.shoppingList',icon:'shopping',group:'secondary',permission:'createContent',contextMatcher:nowhere,open:({open,context})=>open('shoppingList',context)},
  {id:'routine',labelKey:'createUi.routine',icon:'history',group:'secondary',permission:'createContent',contextMatcher:matches('routines'),open:({open,context})=>open('routine',context)},
  {id:'message',labelKey:'createUi.message',icon:'inbox',group:'secondary',permission:'createMessages',contextMatcher:matches('inbox'),capability:'messages',open:({open,context})=>open('message',context)},
  {id:'loyalty',labelKey:'createUi.loyalty',icon:'store',group:'secondary',permission:'createContent',contextMatcher:matches('loyalty'),capability:'loyalty',open:({open,context})=>open('loyalty',context)},
];

export const CREATE_PAGES=new Set(['vehicles','birthdays','home','todo','tasks','shopping','routines','more','calendar','expenses','contracts','wishlists','inbox','loyalty','baby','pets']);
export const DEFAULT_CREATE_PREFERENCES={smart_ranking_enabled:true,context_ranking_enabled:true,time_patterns_enabled:false,direct_mode:false,direct_action_id:'',max_quick_actions:4,pinned_action_ids:[],hidden_action_ids:[],manual_order:[],learning_scope:'family'};
export const DEFAULT_CREATE_RANKING_PROFILE={ranking_version:1,cold_start_threshold:5,preferences:DEFAULT_CREATE_PREFERENCES,stats:[]};

export function availableCreateActions({role,capabilities={},modules={}}){
  const permissions=permissionsForRole(role);
  return CREATE_ACTIONS.filter(action=>{
    if(!permissions[action.permission])return false;
    if(action.capability&&!capabilities[action.capability])return false;
    if(action.module){
      const state=modules[action.module];
      if(!state?.enabled||!state?.authorized)return false;
    }
    return true;
  });
}

export function directCreateAction(page,options){
  return availableCreateActions(options).find(action=>action.contextMatcher?.({page}))||null;
}

export function createActionById(id,options){
  return availableCreateActions(options).find(action=>action.id===id)||null;
}

function uniqueIds(value){
  if(!Array.isArray(value))return[];
  return [...new Set(value.filter(id=>typeof id==='string'))];
}

export function normalizeCreateRankingProfile(profile={}){
  const preferences={...DEFAULT_CREATE_PREFERENCES,...(profile.preferences||{})};
  preferences.max_quick_actions=Math.min(6,Math.max(2,Number(preferences.max_quick_actions)||4));
  preferences.pinned_action_ids=uniqueIds(preferences.pinned_action_ids);
  preferences.hidden_action_ids=uniqueIds(preferences.hidden_action_ids);
  preferences.manual_order=uniqueIds(preferences.manual_order);
  preferences.direct_action_id=typeof preferences.direct_action_id==='string'?preferences.direct_action_id:'';
  preferences.learning_scope=preferences.learning_scope==='global'?'global':'family';
  const stats=Array.isArray(profile.stats)?profile.stats.filter(row=>row&&typeof row.action_id==='string'):[];
  return {
    ranking_version:Number(profile.ranking_version)||1,
    cold_start_threshold:Math.max(1,Number(profile.cold_start_threshold)||5),
    preferences,
    stats,
  };
}

function currentTimeBucket(date){
  const value=date instanceof Date?date:new Date(date||Date.now());
  const day=(value.getDay()+6)%7;
  return `w${day}-h${Math.floor(value.getHours()/4)}`;
}

function recencyScore(lastUsedAt,now){
  if(!lastUsedAt)return 0;
  const time=new Date(lastUsedAt).getTime();
  if(!Number.isFinite(time))return 0;
  const days=Math.max(0,(now.getTime()-time)/86400000);
  if(days<=1)return 6;
  if(days<=7)return 4;
  if(days<=30)return 2;
  return 0;
}

export function rankCreateActions({availableActions=[],page='',profile={},timeContext=new Date()}={}){
  const normalized=normalizeCreateRankingProfile(profile);
  const {preferences,stats,cold_start_threshold:threshold}=normalized;
  const hidden=new Set(preferences.hidden_action_ids);
  const pinned=new Set(preferences.pinned_action_ids);
  const manualIndex=new Map(preferences.manual_order.map((id,index)=>[id,index]));
  const stableIndex=new Map(CREATE_ACTIONS.map((action,index)=>[action.id,index]));
  const statsById=new Map(stats.map(row=>[row.action_id,row]));
  const totalUses=stats.reduce((sum,row)=>sum+Math.max(0,Number(row.use_count)||0),0);
  const learningActive=preferences.smart_ranking_enabled&&totalUses>=threshold;
  const timeBucket=currentTimeBucket(timeContext);
  const now=timeContext instanceof Date?timeContext:new Date(timeContext||Date.now());

  const rows=availableActions.filter(action=>!hidden.has(action.id)).map(action=>{
    const stat=statsById.get(action.id)||{};
    const isPinned=pinned.has(action.id);
    const manual=manualIndex.has(action.id)?manualIndex.get(action.id):null;
    const contextMatch=Boolean(preferences.context_ranking_enabled&&action.contextMatcher?.({page}));
    const contextUses=Math.max(0,Number(stat.context_stats?.[page])||0);
    const frequency=learningActive?Math.log1p(Math.max(0,Number(stat.use_count)||0))*4:0;
    const recency=learningActive?recencyScore(stat.last_used_at,now):0;
    const learnedContext=learningActive&&preferences.context_ranking_enabled?Math.log1p(contextUses)*3:0;
    const timePattern=learningActive&&preferences.time_patterns_enabled?Math.log1p(Math.max(0,Number(stat.time_bucket_stats?.[timeBucket])||0))*2:0;
    const learned=frequency+recency+learnedContext+timePattern;
    let reason='default';
    if(isPinned)reason='pinned';
    else if(manual!==null)reason='manual';
    else if(contextMatch)reason='context';
    else if(learningActive&&recency>=4)reason='recent';
    else if(learningActive&&frequency>0)reason='frequent';
    return {...action,quickstart:{reason,personalized:learningActive,score:learned}};
  });

  rows.sort((left,right)=>{
    const leftPinned=pinned.has(left.id),rightPinned=pinned.has(right.id);
    if(leftPinned!==rightPinned)return leftPinned?-1:1;
    const leftManual=manualIndex.has(left.id)?manualIndex.get(left.id):null;
    const rightManual=manualIndex.has(right.id)?manualIndex.get(right.id):null;
    if(leftManual!==null||rightManual!==null){
      if(leftManual===null)return 1;
      if(rightManual===null)return-1;
      if(leftManual!==rightManual)return leftManual-rightManual;
    }
    const leftContext=Boolean(preferences.context_ranking_enabled&&left.contextMatcher?.({page}));
    const rightContext=Boolean(preferences.context_ranking_enabled&&right.contextMatcher?.({page}));
    if(leftContext!==rightContext)return leftContext?-1:1;
    if(learningActive&&left.quickstart.score!==right.quickstart.score)return right.quickstart.score-left.quickstart.score;
    return (stableIndex.get(left.id)??999)-(stableIndex.get(right.id)??999);
  });
  return rows.slice(0,preferences.max_quick_actions);
}

export function resolveDirectCreateAction({availableActions=[],rankedActions=[],profile={}}={}){
  const {preferences}=normalizeCreateRankingProfile(profile);
  if(!preferences.direct_mode)return null;
  const hidden=new Set(preferences.hidden_action_ids);
  const fixed=availableActions.find(action=>action.id===preferences.direct_action_id&&!hidden.has(action.id));
  return fixed||rankedActions[0]||null;
}
