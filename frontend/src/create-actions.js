const member=({role})=>Boolean(role);
const writer=({role})=>['owner','adult','teen'].includes(role||'');

export const CREATE_ACTIONS=[
  {id:'task',labelKey:'createUi.task',icon:'tasks',group:'primary',permission:member,directPages:['tasks'],open:({open,context})=>open('task',context)},
  {id:'shoppingItem',labelKey:'createUi.shoppingItem',icon:'shopping',group:'primary',permission:member,directPages:['shopping'],open:({open,context})=>open('shoppingItem',context)},
  {id:'event',labelKey:'createUi.event',icon:'calendar',group:'primary',permission:member,directPages:['calendar'],open:({open,context})=>open('event',context)},
  {id:'taskList',labelKey:'createUi.taskList',icon:'lists',group:'secondary',permission:member,directPages:[],open:({open,context})=>open('taskList',context)},
  {id:'shoppingList',labelKey:'createUi.shoppingList',icon:'shopping',group:'secondary',permission:member,directPages:[],open:({open,context})=>open('shoppingList',context)},
  {id:'routine',labelKey:'createUi.routine',icon:'history',group:'secondary',permission:member,directPages:['routines'],open:({open,context})=>open('routine',context)},
  {id:'message',labelKey:'createUi.message',icon:'inbox',group:'secondary',permission:writer,directPages:['inbox'],capability:'messages',open:({open,context})=>open('message',context)},
  {id:'loyalty',labelKey:'createUi.loyalty',icon:'store',group:'secondary',permission:member,directPages:['loyalty'],capability:'loyalty',open:({open,context})=>open('loyalty',context)},
];

export const CREATE_PAGES=new Set(['home','tasks','shopping','routines','more','calendar','inbox','loyalty']);

export function availableCreateActions({role,capabilities={}}){
  return CREATE_ACTIONS.filter(action=>action.permission({role})&&(!action.capability||capabilities[action.capability]));
}

export function directCreateAction(page,options){
  return availableCreateActions(options).find(action=>action.directPages.includes(page))||null;
}

export function createActionById(id,options){
  return availableCreateActions(options).find(action=>action.id===id)||null;
}
