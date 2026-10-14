import {useRef,useState} from 'react';
import {recordCreateUsage,createRankingScope} from './create-ranking-client';
import {openTaskDuel} from './game-assignment-i18n';
import {pageHref} from './navigation';
import {resolveCreateFlowRenderer} from './create-flow-registry';

export default function CreateFlowHost({userId,action,family,data,context={},onClose,onRefresh,onNavigate}){
 const learnedTask=useRef(null);
 const [createdShoppingList,setCreatedShoppingList]=useState(null);
 if(!action||!family)return null;
 const taskLists=(data?.task_lists||[]).filter(list=>!list.archived);
 const shoppingLists=[...(data?.shopping_lists||[]).filter(list=>!list.archived),...(createdShoppingList?[createdShoppingList]:[])].filter((list,index,all)=>all.findIndex(row=>String(row.id)===String(list.id))===index);
 const selectedTaskList=taskLists.find(list=>context.activeListLabel?.includes(list.name));
 const selectedShoppingList=shoppingLists.find(list=>context.activeListLabel?.includes(list.name));
 const taskListId=selectedTaskList?.id||(context.taskListId&&context.taskListId!=='all'?context.taskListId:taskLists[0]?.id||'');
 const shoppingList=selectedShoppingList||(context.shoppingListId&&context.shoppingListId!=='all'?shoppingLists.find(list=>String(list.id)===String(context.shoppingListId)):shoppingLists[0]);
 function learnSuccessfulCreate(){
  const origin=typeof context.origin==='string'?context.origin:'';
  recordCreateUsage({scope:createRankingScope(family,userId),actionId:action,originPage:origin,contextBucket:origin}).catch(()=>{});
 }
 async function saved(record,options={}){if(action!=='task'||learnedTask.current!==record?.id){learnSuccessfulCreate();if(action==='task')learnedTask.current=record?.id}if(options.duelHref){openTaskDuel(options.duelHref);return}await onRefresh?.();onClose()}
 async function savedWithoutClose(){learnSuccessfulCreate();await onRefresh?.()}
 function openModule(page,params={}){
  if(onNavigate){onClose();onNavigate(page);return}
  const state={...(history.state||{}),page,appNavigation:true};delete state.createFlow;delete state.createPalette;
  const href=new URL(pageHref(page),location.origin);
  Object.entries(params).forEach(([key,value])=>{if(value!==undefined&&value!==null&&value!=='')href.searchParams.set(key,String(value))});
  history.replaceState(state,'',`${href.pathname}${href.search}${href.hash}`);
  window.dispatchEvent(new PopStateEvent('popstate',{state}));
 }
 const render=resolveCreateFlowRenderer(action);
 if(!render)return null;
 return render({userId,family,data,context,taskLists,shoppingLists,taskListId,shoppingList,onClose,onRefresh,saved,savedWithoutClose,openModule,learnSuccessfulCreate,setCreatedShoppingList});
}
