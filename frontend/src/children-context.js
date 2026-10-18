export function childAgeMonths(baby,today=new Date()){
 const birth=new Date(`${baby.birth_date}T12:00:00`);
 return Math.max(0,(today.getFullYear()-birth.getFullYear())*12+today.getMonth()-birth.getMonth()-(today.getDate()<birth.getDate()?1:0));
}
export function childPermissions(baby,module){
 return baby?.permissions||module?.permissions||{};
}
export function defaultChildView(baby,module){
 const permissions=childPermissions(baby,module);
 return childAgeMonths(baby)<24&&permissions.can_log_care?'now':permissions.can_view_growth_development?'health':permissions.can_log_care?'now':'more';
}
export function localDateTime(value){
 if(!value)return'';
 const date=new Date(value),pad=value=>String(value).padStart(2,'0');
 return `${date.getFullYear()}-${pad(date.getMonth()+1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}
