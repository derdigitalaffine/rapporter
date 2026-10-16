// Rejections are server errors, not concurrent field edits. Old stored results
// remain readable; never turn an unavailable/hidden UUID into an automatic create.
export function canRetryRejectedCreate(entry){
 const m=entry?.mutation,r=entry?.result;
 return r?.status==='rejected'&&['validation_error','permission_denied','authentication_required','rate_limited'].includes(r.code)
  &&m?.entity_type==='event'&&m.operation==='create'&&m.data?.type==='calendar.event'&&!m.data.source;
}
export function rejectionLines(result){
 const lines=[];
 function visit(value,path='',depth=0){
  if(lines.length>=20||depth>6)return;
  if(typeof value==='string'||typeof value==='number')lines.push(`${path?`${path}: `:''}${String(value).slice(0,1000)}`);
  else if(Array.isArray(value))value.forEach(item=>visit(item,path,depth+1));
  else if(value&&typeof value==='object')for(const [key,item] of Object.entries(value))visit(item,key==='detail'?path:[path,key].filter(Boolean).join('.'),depth+1);
 }
 visit(result?.errors);return lines;
}
