export const ROUTINE_ICON_OPTIONS=['history','sparkles','bed','snowflake','droplets','house','calendar','tasks'];

const iconMap={
 history:'history',
 sparkles:'automation',
 bed:'home',
 snowflake:'frost',
 droplets:'rain',
 house:'home',
 calendar:'calendar',
 tasks:'tasks',
};

export function routineIconName(value){return iconMap[value]||'history'}

export function routineStatusKey(routine){
 if(routine?.active===false)return 'paused';
 const status=routine?.prediction?.status;
 if(status==='overdue')return 'overdue';
 if(status==='due')return 'due';
 if(status==='upcoming'&&routine?.prediction?.preparation_start&&new Date(routine.prediction.preparation_start).getTime()<=Date.now())return 'due';
 if(routine?.prediction?.expected_at)return 'upcoming';
 return routine?.last_done_at?'learning':'new';
}

export function routineSortKey(routine){
 const status=routineStatusKey(routine);
 const rank={overdue:0,due:1,upcoming:2,new:3,learning:4,paused:5}[status]??6;
 const next=routine?.prediction?.expected_at?new Date(routine.prediction.expected_at).getTime():Number.MAX_SAFE_INTEGER;
 return [rank,next,String(routine?.name||'')];
}

export function compareRoutines(a,b,locale){
 const left=routineSortKey(a),right=routineSortKey(b);
 return left[0]-right[0]||left[1]-right[1]||left[2].localeCompare(right[2],locale);
}
