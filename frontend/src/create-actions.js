import {permissionsForRole} from './family-permissions';

const matches=page=>({page:current})=>current===page;
const nowhere=()=>false;

export const CREATE_ACTIONS=[
  {id:'task',labelKey:'createUi.task',icon:'tasks',group:'primary',permission:'createContent',contextMatcher:matches('tasks'),open:({open,context})=>open('task',context)},
  {id:'shoppingItem',labelKey:'createUi.shoppingItem',icon:'shopping',group:'primary',permission:'createContent',contextMatcher:matches('shopping'),open:({open,context})=>open('shoppingItem',context)},
  {id:'event',labelKey:'createUi.event',icon:'calendar',group:'primary',permission:'createContent',contextMatcher:matches('calendar'),open:({open,context})=>open('event',context)},
  {id:'taskList',labelKey:'createUi.taskList',icon:'lists',group:'secondary',permission:'createContent',contextMatcher:nowhere,open:({open,context})=>open('taskList',context)},
  {id:'shoppingList',labelKey:'createUi.shoppingList',icon:'shopping',group:'secondary',permission:'createContent',contextMatcher:nowhere,open:({open,context})=>open('shoppingList',context)},
  {id:'routine',labelKey:'createUi.routine',icon:'history',group:'secondary',permission:'createContent',contextMatcher:matches('routines'),open:({open,context})=>open('routine',context)},
  {id:'message',labelKey:'createUi.message',icon:'inbox',group:'secondary',permission:'createMessages',contextMatcher:matches('inbox'),capability:'messages',open:({open,context})=>open('message',context)},
  {id:'loyalty',labelKey:'createUi.loyalty',icon:'store',group:'secondary',permission:'createContent',contextMatcher:matches('loyalty'),capability:'loyalty',open:({open,context})=>open('loyalty',context)},
];

export const CREATE_PAGES=new Set(['home','tasks','shopping','routines','more','calendar','inbox','loyalty']);

export function availableCreateActions({role,capabilities={}}){
  const permissions=permissionsForRole(role);
  return CREATE_ACTIONS.filter(action=>permissions[action.permission]&&(!action.capability||capabilities[action.capability]));
}

export function directCreateAction(page,options){
  return availableCreateActions(options).find(action=>action.contextMatcher?.({page}))||null;
}

export function createActionById(id,options){
  return availableCreateActions(options).find(action=>action.id===id)||null;
}
