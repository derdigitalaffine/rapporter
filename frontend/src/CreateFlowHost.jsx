import {useState} from 'react';
import {TaskEditor,ShoppingEditor} from './SmartEditors';
import ListEditor from './ListEditor';
import EventEditor from './EventEditor';
import RoutineEditor from './RoutineEditor';
import LoyaltyCardEditor from './LoyaltyCardEditor';

export default function CreateFlowHost({action,family,data,context={},onClose,onRefresh}){
 const [createdShoppingList,setCreatedShoppingList]=useState(null);
 if(!action||!family)return null;
 const taskLists=(data?.task_lists||[]).filter(list=>!list.archived);
 const shoppingLists=[...(data?.shopping_lists||[]).filter(list=>!list.archived),...(createdShoppingList?[createdShoppingList]:[])].filter((list,index,all)=>all.findIndex(row=>String(row.id)===String(list.id))===index);
 const taskListId=context.taskListId&&context.taskListId!=='all'?context.taskListId:taskLists[0]?.id||'';
 const shoppingList=context.shoppingListId&&context.shoppingListId!=='all'?shoppingLists.find(list=>String(list.id)===String(context.shoppingListId)):shoppingLists[0];
 async function saved(){await onRefresh?.();onClose()}
 if(action==='task')return <TaskEditor family={family} lists={taskLists} members={family.memberships||[]} defaultListId={taskListId} onClose={onClose} onSaved={saved}/>;
 if(action==='shoppingItem'){
  if(!shoppingLists.length)return <ListEditor type="shopping" family={family} onClose={onClose} onSaved={async list=>{setCreatedShoppingList(list);await onRefresh?.()}}/>;
  return <ShoppingEditor shoppingList={shoppingList} lists={shoppingLists} onClose={onClose} onSaved={saved}/>;
 }
 if(action==='event')return <EventEditor family={family} onClose={onClose} onSaved={saved}/>;
 if(action==='taskList')return <ListEditor type="task" family={family} onClose={onClose} onSaved={saved}/>;
 if(action==='shoppingList')return <ListEditor type="shopping" family={family} onClose={onClose} onSaved={saved}/>;
 if(action==='routine')return <RoutineEditor family={family} onClose={onClose} onSaved={saved}/>;
 if(action==='loyalty')return <LoyaltyCardEditor family={family} onClose={onClose} onSaved={saved}/>;
 return null;
}
