import {formatCivilDate,formatDateTime} from './locale.js';

export function healthDateLabel(row,language,timeZone='UTC'){
 if(row.planned_at)return formatDateTime(language,row.planned_at,{timeZone,day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit'});
 if(row.occurred_on)return formatCivilDate(language,row.occurred_on);
 if(row.window_start&&row.window_end)return `${formatCivilDate(language,row.window_start)} – ${formatCivilDate(language,row.window_end)}`;
 return '';
}

export function healthDoseLabel(row,c){
 return !row.dose?'':String(row.dose).startsWith('booster-')?c('booster'):`${c('dose')} ${row.dose}`;
}

export function visibleHealthItems(items,kind,view,language='de'){
 const rows=items.filter(row=>row.kind===kind&&(view==='history'?(row.state==='done'||row.historical&&row.state!=='planned'):(row.state!=='done'&&(!row.historical||row.state==='planned'))));
 const when=row=>{
  const value=view==='history'?row.occurred_on||row.window_end:row.planned_at||row.window_start;
  const parsed=Date.parse(value);
  return Number.isFinite(parsed)?parsed:null;
 };
 return rows.sort((a,b)=>{
  const left=when(a),right=when(b);
  if(left===null&&right!==null)return 1;
  if(right===null&&left!==null)return -1;
  if(left!==right)return view==='history'?right-left:left-right;
  return `${a.title}:${a.dose||''}`.localeCompare(`${b.title}:${b.dose||''}`,language,{numeric:true});
 });
}
