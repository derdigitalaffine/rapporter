// Amounts sent to the server use integer cents; display formatting stays local.
export const cents=value=>{
 const text=String(value??'0').trim().replace(',','.');
 const match=text.match(/^(-?)(\d+)(?:\.(\d{1,2}))?$/);
 if(!match)return 0;
 return (match[1]?-1:1)*(Number(match[2])*100+Number((match[3]||'').padEnd(2,'0')));
};
export const decimal=value=>(value/100).toFixed(2);
export function budgetTree(budgets){
 const byId=new Map(budgets.map(row=>[String(row.id),row]));
 const parent=row=>row.hierarchy?row.hierarchy.parent:row.parent;
 const children=id=>budgets.filter(row=>String(parent(row)||'')===String(id||'')||(!id&&parent(row)&&!byId.has(String(parent(row)))));
 const path=row=>{
  const names=[],seen=new Set();
  while(row&&!seen.has(String(row.id))){seen.add(String(row.id));names.unshift(row.name);row=byId.get(String(parent(row)))}
  return names.join(' / ');
 };
 const descendants=id=>{
  const found=new Set([String(id)]),pending=[id];
  while(pending.length)for(const row of children(pending.pop()))if(!found.has(String(row.id))){found.add(String(row.id));pending.push(row.id)}
  return found;
 };
 const childPlan=id=>children(id).reduce((sum,row)=>sum+cents(row.amount),0);
 return {children,path,descendants,childPlan};
}
