import {useEffect,useRef} from 'react';
import VehicleEditor from './VehicleEditor';
import BirthdayEditor from './BirthdayEditor';
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
import {CREATE_ACTIONS} from './create-actions';

function CreatePageRedirect({page,params,openModule}){
  const opened=useRef(false);
  useEffect(()=>{
    if(opened.current)return;
    opened.current=true;
    openModule(page,params);
  },[openModule,page,params]);
  return null;
}

const renderers={
  vehicle:({family,onClose,saved})=><VehicleEditor family={family} onClose={onClose} onSaved={saved}/>,
  birthday:({family,onClose,saved})=><BirthdayEditor family={family} onClose={onClose} onSaved={saved}/>,
  baby:({family,onClose,openModule,learnSuccessfulCreate})=><BabyCreateSheet family={family} onClose={onClose} onOpenPage={openModule} onSuccessfulCreate={learnSuccessfulCreate}/>,
  pets:({family,onClose,openModule,learnSuccessfulCreate})=><PetCreateSheet family={family} onClose={onClose} onOpenPage={openModule} onSuccessfulCreate={learnSuccessfulCreate}/>,
  task:({family,taskLists,taskListId,onClose,saved})=><TaskEditor family={family} lists={taskLists} members={family.memberships||[]} defaultListId={taskListId} onClose={onClose} onSaved={saved}/>,
  shoppingItem:({family,shoppingLists,shoppingList,onClose,saved,setCreatedShoppingList,onRefresh})=>shoppingLists.length?<ShoppingEditor shoppingList={shoppingList} lists={shoppingLists} onClose={onClose} onSaved={saved}/>:<ListEditor type="shopping" family={family} onClose={onClose} onSaved={async list=>{setCreatedShoppingList(list);await onRefresh?.()}}/>,
  event:({family,onClose,saved})=><EventEditor family={family} onClose={onClose} onSaved={saved}/>,
  expense:({family,context,onClose,saved,onRefresh})=><ExpenseEditor family={family} initialMode={context.mode==='receipt'?'receipt':'quick'} onClose={onClose} onSaved={saved} onUndo={onRefresh}/>,
  contract:({family,onClose,saved})=><ContractEditor family={family} onClose={onClose} onSaved={saved}/>,
  correspondence:({family,shoppingLists,onClose,saved})=><CorrespondenceEditor family={family} shoppingLists={shoppingLists} onClose={onClose} onSaved={saved}/>,
  wish:({family,context,onClose,savedWithoutClose})=><WishlistEditor family={family} context={context} onClose={onClose} onSaved={savedWithoutClose}/>,
  taskList:({family,onClose,saved})=><ListEditor type="task" family={family} onClose={onClose} onSaved={saved}/>,
  shoppingList:({family,onClose,saved})=><ListEditor type="shopping" family={family} onClose={onClose} onSaved={saved}/>,
  routine:({family,onClose,saved})=><RoutineEditor family={family} onClose={onClose} onSaved={saved}/>,
  message:({openModule})=><CreatePageRedirect page="inbox" params={{compose:'1'}} openModule={openModule}/>,
  loyalty:({family,onClose,saved})=><LoyaltyCardEditor family={family} onClose={onClose} onSaved={saved}/>,
};

export const CREATE_FLOW_RENDERERS=Object.freeze(renderers);
export const CREATE_FLOW_IDS=Object.freeze(Object.keys(CREATE_FLOW_RENDERERS));
const knownActionIds=new Set(CREATE_ACTIONS.map(action=>action.id));
const missing=CREATE_ACTIONS.filter(action=>!CREATE_FLOW_RENDERERS[action.id]).map(action=>action.id);
const orphaned=CREATE_FLOW_IDS.filter(id=>!knownActionIds.has(id));
if(missing.length||orphaned.length)throw new Error(`Create flow registry mismatch (missing: ${missing.join(', ')||'none'}; orphaned: ${orphaned.join(', ')||'none'})`);
export function resolveCreateFlowRenderer(actionId){return CREATE_FLOW_RENDERERS[actionId]||null}
