import VehicleEditor from './VehicleEditor';
import BirthdayEditor from './BirthdayEditor';
import {useRef,useState} from 'react';
import {TaskEditor,ShoppingEditor} from './SmartEditors';
import ListEditor from './ListEditor';
import EventEditor from './EventEditor';
import RoutineEditor from './RoutineEditor';
import LoyaltyCardEditor from './LoyaltyCardEditor';
import ExpenseEditor from './ExpenseEditor';
import ContractEditor from './ContractEditor';
import CorrespondenceEditor from './CorrespondenceEditor';
import WishlistEditor from './WishlistEditor';
import {BabyCreateSheet,PetCreateSheet} from './ModuleCreateSheets';
import {recordCreateUsage,createRankingScope} from './create-ranking-client';
import {openTaskDuel} from './game-assignment-i18n';
import {pageHref} from './navigation';

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
 function openModule(page){
  if(onNavigate){onNavigate(page);return}
  const state={...(history.state||{}),page,appNavigation:true};delete state.createFlow;delete state.createPalette;
  history.replaceState(state,'',pageHref(page));
  window.dispatchEvent(new PopStateEvent('popstate',{state}));
 }
 if(action==='vehicle')return <VehicleEditor family={family} onClose={onClose} onSaved={saved}/>;
 if(action==='birthday')return <BirthdayEditor family={family} onClose={onClose} onSaved={saved}/>;
 if(action==='baby')return <BabyCreateSheet family={family} onClose={onClose} onOpenPage={openModule} onSuccessfulCreate={learnSuccessfulCreate}/>;
 if(action==='pets')return <PetCreateSheet family={family} onClose={onClose} onOpenPage={openModule} onSuccessfulCreate={learnSuccessfulCreate}/>;
 if(action==='task')return <TaskEditor family={family} lists={taskLists} members={family.memberships||[]} defaultListId={taskListId} onClose={onClose} onSaved={saved}/>;
 if(action==='shoppingItem'){
  if(!shoppingLists.length)return <ListEditor type="shopping" family={family} onClose={onClose} onSaved={async list=>{setCreatedShoppingList(list);await onRefresh?.()}}/>;
  return <ShoppingEditor shoppingList={shoppingList} lists={shoppingLists} onClose={onClose} onSaved={saved}/>;
 }
 if(action==='event')return <EventEditor family={family} onClose={onClose} onSaved={saved}/>;
 if(action==='expense')return <ExpenseEditor family={family} initialMode={context.mode==='receipt'?'receipt':'quick'} onClose={onClose} onSaved={saved} onUndo={onRefresh}/>;
 if(action==='contract')return <ContractEditor family={family} onClose={onClose} onSaved={saved}/>;
 if(action==='correspondence')return <CorrespondenceEditor family={family} shoppingLists={shoppingLists} onClose={onClose} onSaved={saved}/>;
 if(action==='wish')return <WishlistEditor family={family} context={context} onClose={onClose} onSaved={savedWithoutClose}/>;
 if(action==='taskList')return <ListEditor type="task" family={family} onClose={onClose} onSaved={saved}/>;
 if(action==='shoppingList')return <ListEditor type="shopping" family={family} onClose={onClose} onSaved={saved}/>;
 if(action==='routine')return <RoutineEditor family={family} onClose={onClose} onSaved={saved}/>;
 if(action==='loyalty')return <LoyaltyCardEditor family={family} onClose={onClose} onSaved={saved}/>;
 return null;
}
