export const DECISION_FILTERS=Object.freeze(['open','closed','all']);

function deadlineMs(row){
  if(!row?.closes_at)return Number.POSITIVE_INFINITY;
  const value=new Date(row.closes_at).getTime();
  return Number.isFinite(value)?value:Number.POSITIVE_INFINITY;
}

export function decisionUrgency(row,now=Date.now()){
  if(!row?.is_open||!row?.closes_at)return'normal';
  const remaining=deadlineMs(row)-Number(now);
  if(remaining<=0)return'due';
  if(remaining<=24*60*60*1000)return'soon';
  if(remaining<=72*60*60*1000)return'upcoming';
  return'normal';
}

export function hasDecisionParticipation(row){
  if(row?.mode==='rating')return Boolean(row?.options?.some(option=>option?.my_score!=null));
  return Boolean(row?.my_option_ids?.length);
}

export function sortDecisions(rows=[],now=Date.now()){
  return rows.map((row,index)=>({row,index})).sort((left,right)=>{
    if(Boolean(left.row?.is_open)!==Boolean(right.row?.is_open))return left.row?.is_open?-1:1;
    if(left.row?.is_open&&right.row?.is_open){
      const deadlineDelta=deadlineMs(left.row)-deadlineMs(right.row);
      if(deadlineDelta!==0)return deadlineDelta;
      const urgencyOrder={due:0,soon:1,upcoming:2,normal:3};
      const urgencyDelta=urgencyOrder[decisionUrgency(left.row,now)]-urgencyOrder[decisionUrgency(right.row,now)];
      if(urgencyDelta!==0)return urgencyDelta;
    }
    return left.index-right.index;
  }).map(item=>item.row);
}

export function filterDecisions(rows=[],filter='open'){
  if(filter==='all')return rows;
  if(filter==='closed')return rows.filter(row=>!row?.is_open);
  return rows.filter(row=>row?.is_open);
}

export function decisionResultState(row){
  if(row?.is_open)return hasDecisionParticipation(row)?'participated':'open';
  if(row?.result?.is_tie)return'tie';
  if(row?.result?.winner)return'winner';
  return'closed';
}
