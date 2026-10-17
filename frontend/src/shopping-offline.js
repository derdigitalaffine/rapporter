import {offlineEngine,readyOfflineEngine,offlineIdentity,addShoppingLocally} from './offline-runtime';
import {api} from './api';
import {deleteShoppingMutation,listShoppingMutations,putShoppingMutation} from './offline-store';
import {applyShoppingItemAutoguess} from './shopping-item-autoguess.js';

export const SHOPPING_BUDGET_PURCHASE_EVENT='famuhle:shopping-budget-purchase';
const uuid=()=>globalThis.crypto?.randomUUID?.()||`offline-${Date.now()}-${Math.random().toString(16).slice(2)}`;
const mutationUuid=()=>globalThis.crypto?.randomUUID?.()||'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g,char=>{const random=Math.random()*16|0;const value=char==='x'?random:(random&3)|8;return value.toString(16)});
const ORDER_META_PREFIX='famuhle-shopping-order-next:';

export function stageShoppingOrderMetadata(targetId,metadata){
  if(typeof sessionStorage==='undefined')return;
  try{sessionStorage.setItem(`${ORDER_META_PREFIX}${String(targetId)}`,JSON.stringify(metadata||{}))}catch{}
}
function consumeShoppingOrderMetadata(targetId){
  if(typeof sessionStorage==='undefined')return null;
  const key=`${ORDER_META_PREFIX}${String(targetId)}`;
  try{const raw=sessionStorage.getItem(key);sessionStorage.removeItem(key);return raw?JSON.parse(raw):null}catch{return null}
}

export async function queueShoppingAdd(familyId,payload){
  const mutationId=mutationUuid();
  const guessed=applyShoppingItemAutoguess(payload).payload;
  const mutationPayload={...guessed,client_mutation_id:mutationId};
  if(offlineEngine(familyId)){const {item}=await addShoppingLocally(familyId,mutationPayload);return {localId:item.id,payload:mutationPayload,id:mutationId}}
  const localId=`offline-${uuid()}`;
  const mutation={id:mutationId,familyId:String(familyId),type:'add',localId,payload:mutationPayload,createdAt:Date.now(),attempts:0,status:'pending'};
  await putShoppingMutation(mutation);return mutation;
}
export async function queueShoppingPatch(familyId,targetId,payload){
  const target=String(targetId);
  const mutationId=mutationUuid();
  const orderMeta=consumeShoppingOrderMetadata(target);
  const mutationPayload=orderMeta?{...payload,client_activity:{...orderMeta,mutation_id:mutationId}}:payload;
  // A budget reservation is an online finance transition, not an offline
  // checkbox mutation. Keep the item open until the canonical Expense has
  // been confirmed; the create flow will mark it checked afterwards.
  if(payload?.checked===true&&!target.startsWith('offline-')&&typeof navigator!=='undefined'&&navigator.onLine){
    try{
      const result=await api(`/budget-commitments/source/shopping_item/${encodeURIComponent(target)}/?family=${encodeURIComponent(familyId)}`);
      if(result?.commitment){
        window.dispatchEvent(new CustomEvent(SHOPPING_BUDGET_PURCHASE_EVENT,{detail:{familyId:String(familyId),itemId:target,commitment:result.commitment}}));
        return {intercepted:true,targetId:target,commitment:result.commitment};
      }
    }catch{
      // Finance can be unavailable independently (entitlement/network). In
      // that case preserve the existing shopping behavior instead of turning
      // a normal checkbox into a hard failure.
    }
  }
  if(offlineEngine(familyId)){await (await readyOfflineEngine(familyId)).mutate('shopping_item',target,'update',mutationPayload);return {targetId:target}}
  const mutation={id:mutationId,familyId:String(familyId),type:'patch',targetId:target,payload:mutationPayload,createdAt:Date.now(),attempts:0,status:'pending'};
  await putShoppingMutation(mutation);return mutation;
}
export async function queueShoppingDelete(familyId,targetId){
  if(offlineEngine(familyId)){await (await readyOfflineEngine(familyId)).mutate('shopping_item',String(targetId),'delete');return {targetId}}
  const target=String(targetId);
  const rows=await listShoppingMutations(familyId);
  if(target.startsWith('offline-')){
    const pendingAdd=rows.find(row=>row.type==='add'&&String(row.localId)===target);
    if(pendingAdd){
      await Promise.all(rows.filter(row=>row.id===pendingAdd.id||String(row.targetId)===target).map(row=>deleteShoppingMutation(row.id)));
      return {cancelled:true,targetId:target};
    }
  }
  const mutation={id:uuid(),familyId:String(familyId),type:'delete',targetId:target,createdAt:Date.now(),attempts:0,status:'pending'};
  await putShoppingMutation(mutation);return mutation;
}
export async function queueShoppingTemplateApply(familyId,templateId,shoppingListId){
  if(offlineEngine(familyId)){const e=await readyOfflineEngine(familyId);const rows=await e.store.list('outbox');if(rows.some(m=>m.entity_id===shoppingListId&&m.command==='apply_template'&&m.args?.template_id===templateId))return {deduplicated:true};await e.mutate('shopping_list',shoppingListId,'command',{command:'apply_template',args:{template_id:templateId}});return {deduplicated:false}}
  const rows=await listShoppingMutations(familyId);
  const duplicate=rows.find(row=>row.type==='template_apply'&&String(row.templateId)===String(templateId)&&String(row.shoppingListId)===String(shoppingListId)&&row.status!=='failed');
  if(duplicate)return {...duplicate,deduplicated:true};
  const mutation={id:uuid(),familyId:String(familyId),type:'template_apply',templateId:String(templateId),shoppingListId:String(shoppingListId),createdAt:Date.now(),attempts:0,status:'pending'};
  await putShoppingMutation(mutation);return {...mutation,deduplicated:false};
}

export function applyShoppingMutations(lists,mutations){
  const next=structuredClone(lists||[]);
  const findItem=id=>{for(const list of next){const item=list.items?.find(row=>String(row.id)===String(id));if(item)return {list,item}}return null};
  for(const mutation of mutations||[]){
    if(mutation.type==='add'){
      const list=next.find(row=>String(row.id)===String(mutation.payload.shopping_list));if(!list)continue;
      if(!list.items)list.items=[];
      const existing=list.items.find(row=>String(row.id)===String(mutation.localId));
      if(!existing)list.items.push({id:mutation.localId,shopping_list:list.id,name:mutation.payload.name,quantity:mutation.payload.quantity||'',category:mutation.payload.category||'',aisle:mutation.payload.aisle||'',note:mutation.payload.note||'',favorite:!!mutation.payload.favorite,checked:false,added_by_name:'',_offlinePending:true});
    }
    if(mutation.type==='patch'){
      const found=findItem(mutation.targetId);if(found){const {client_activity,...visiblePatch}=mutation.payload||{};Object.assign(found.item,visiblePatch,{_offlinePending:true})}
    }
    if(mutation.type==='delete'){
      const found=findItem(mutation.targetId);if(found){found.list.items=found.list.items.filter(row=>String(row.id)!==String(mutation.targetId))}
    }
  }
  for(const list of next){list.open_count=(list.items||[]).filter(item=>!item.checked).length;list.checked_count=(list.items||[]).filter(item=>item.checked).length}
  return next;
}

async function failMutation(mutation,error){
  const attempts=(mutation.attempts||0)+1;const status=attempts>=3?'failed':'pending';
  await putShoppingMutation({...mutation,attempts,status,lastError:error?.message||String(error),lastAttemptAt:Date.now()});
}

export async function flushShoppingMutations(familyId){
  if(offlineEngine(familyId)){const e=await readyOfflineEngine(familyId);try{await e.sync()}catch(error){return {synced:0,pending:(await e.store.list('outbox')).length,failed:0,error}}return {synced:1,pending:(await e.store.list('outbox')).length,failed:(await e.store.list('conflicts')).length}}
  const all=await listShoppingMutations(familyId);
  const failedCount=all.filter(m=>m.status==='failed').length;
  if(failedCount)return {synced:0,pending:all.length-failedCount,failed:failedCount,blocked:true};
  if(typeof navigator!=='undefined'&&!navigator.onLine)return {synced:0,pending:all.length,failed:0};
  if(!all.length)return {synced:0,pending:0,failed:0};
  const resolved=new Map();let synced=0;
  try{
    for(const mutation of all){
      if(mutation.type==='add'){
        const result=await api('/smart/shopping/quick-add/',{method:'POST',body:JSON.stringify(mutation.payload)});
        const item=result?.item||result;resolved.set(mutation.localId,String(item.id));synced++;
      }else if(mutation.type==='patch'){
        const target=resolved.get(mutation.targetId)||mutation.targetId;
        if(String(target).startsWith('offline-'))throw new Error('offline_target_unresolved');
        await api(`/shopping-items/${target}/`,{method:'PATCH',body:JSON.stringify(mutation.payload)});synced++;
      }else if(mutation.type==='delete'){
        const target=resolved.get(mutation.targetId)||mutation.targetId;
        if(String(target).startsWith('offline-'))throw new Error('offline_target_unresolved');
        await api(`/shopping-items/${target}/`,{method:'DELETE'});synced++;
      }else if(mutation.type==='template_apply'){
        if(String(mutation.shoppingListId).startsWith('offline-'))throw new Error('offline_target_unresolved');
        await api(`/shopping-templates/${mutation.templateId}/apply/`,{method:'POST',body:JSON.stringify({shopping_list:mutation.shoppingListId})});synced++;
      }
    }
    await Promise.all(all.map(mutation=>deleteShoppingMutation(mutation.id)));
    return {synced,pending:0,failed:0};
  }catch(error){
    const failed=all[Math.min(synced,all.length-1)];if(failed)await failMutation(failed,error);
    const remaining=await listShoppingMutations(familyId);
    return {synced:0,pending:remaining.filter(m=>m.status!=='failed').length,failed:remaining.filter(m=>m.status==='failed').length,error};
  }
}

export async function retryShoppingMutations(familyId){
  if(offlineEngine(familyId))return flushShoppingMutations(familyId);
  const rows=await listShoppingMutations(familyId);await Promise.all(rows.map(row=>putShoppingMutation({...row,status:'pending',attempts:0,lastError:''})));return flushShoppingMutations(familyId);
}

export async function shoppingQueueStatus(familyId){if(offlineEngine(familyId)){const e=await readyOfflineEngine(familyId);return {rows:[],pending:(await e.store.list('outbox')).filter(m=>m.entity_type.startsWith('shopping')).length,failed:(await e.store.list('conflicts')).filter(m=>m.mutation?.entity_type?.startsWith('shopping')).length}}const rows=await listShoppingMutations(familyId);return {rows,pending:rows.filter(row=>row.status!=='failed').length,failed:rows.filter(row=>row.status==='failed').length}}
