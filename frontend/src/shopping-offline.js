import {api} from './api';
import {deleteShoppingMutation,listShoppingMutations,putShoppingMutation} from './offline-store';

const uuid=()=>globalThis.crypto?.randomUUID?.()||`offline-${Date.now()}-${Math.random().toString(16).slice(2)}`;

export async function queueShoppingAdd(familyId,payload){
  const localId=`offline-${uuid()}`;
  const mutation={id:uuid(),familyId:String(familyId),type:'add',localId,payload,createdAt:Date.now(),attempts:0,status:'pending'};
  await putShoppingMutation(mutation);return mutation;
}
export async function queueShoppingPatch(familyId,targetId,payload){
  const mutation={id:uuid(),familyId:String(familyId),type:'patch',targetId:String(targetId),payload,createdAt:Date.now(),attempts:0,status:'pending'};
  await putShoppingMutation(mutation);return mutation;
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
      const found=findItem(mutation.targetId);if(found){Object.assign(found.item,mutation.payload,{_offlinePending:true})}
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
  const rows=await listShoppingMutations(familyId);await Promise.all(rows.map(row=>putShoppingMutation({...row,status:'pending',attempts:0,lastError:''})));return flushShoppingMutations(familyId);
}

export async function shoppingQueueStatus(familyId){const rows=await listShoppingMutations(familyId);return {rows,pending:rows.filter(row=>row.status!=='failed').length,failed:rows.filter(row=>row.status==='failed').length}}
