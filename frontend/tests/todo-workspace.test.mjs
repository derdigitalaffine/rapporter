import {test} from 'node:test';
import assert from 'node:assert/strict';
import {DEFAULT_TODO_VIEW_PREFERENCES,groupActions,normalizeTodoViewPreferences,scopeForView,sortActions,workspaceView,visibleActions} from '../src/todo-workspace.js';
import {primaryNavCurrent,pageLabel} from '../src/app-navigation.js';
import {featureHref} from '../src/navigation.js';

const rows=[
 {id:'task:1',kind:'task',title:'Ohne Termin',state:'open',context:{list:{id:'l'}},assignee:{id:7}},
 {id:'task:2',kind:'task',title:'Wiederkehrend',state:'due',schedule:{recurrence:{frequency:'weekly'}}},
 {id:'routine:3',kind:'routine',title:'Bestand',state:'due'},
 {id:'task:4',kind:'task',title:'Erledigt',state:'done'},
];
const local=(day,hour=10)=>new Date(2026,9,day,hour,0,0,0).toISOString();
const task=(id,title,date,extra={})=>({id:`task:${id}`,kind:'task',title,state:'due',due_at:date,priority:'normal',context:{list:null},...extra});
const routine=(id,title,date,extra={})=>({id:`routine:${id}`,kind:'routine',title,state:'due',due_at:null,next_due_at:date,priority:'normal',context:{list:null},...extra});

test('one workspace retains old URLs, lists, workflow and completed entry points',()=>{
 assert.equal(workspaceView('?page=tasks&task=1','lists'),'lists');
 assert.equal(workspaceView('?page=tasks&mode=workflow'),'lists');
 assert.equal(workspaceView('?page=tasks&mode=completed'),'all');
 assert.equal(workspaceView('?page=todo&todo=today'),'today');
 assert.equal(workspaceView('?todo=unknown'),'upcoming');
});
test('upcoming includes undated work without treating completed work as open',()=>{
 assert.equal(scopeForView('upcoming'),'all');
 assert.deepEqual(visibleActions(rows).map(row=>row.id),['task:1','task:2','routine:3']);
 assert.equal(scopeForView('all',true),'completed');
 assert.deepEqual(visibleActions(rows,{view:'all',completed:true}).map(row=>row.id),['task:4']);
});
test('recurrence is a property of work, not a second product',()=>{
 assert.deepEqual(visibleActions(rows,{recurring:true}).map(row=>row.id),['task:2','routine:3']);
 assert.deepEqual(visibleActions(rows,{query:'OHNE',list:'l',person:'7'}).map(row=>row.id),['task:1']);
 assert.deepEqual(visibleActions(rows,{person:'not-a-member'}),[]);
});
test('date grouping integrates tasks and routines by their next actionable time',()=>{
 const now=new Date(2026,9,19,10,0,0,0);
 const groups=groupActions([
  task('overdue','Alt',local(18,8),{state:'overdue'}),
  task('today','Heute',local(19,16)),
  routine('routine','Vitamin D',local(19,12)),
  task('tomorrow','Morgen',local(20,9)),
  task('later','Später',local(28,9)),
  task('undated','Ohne Termin',null,{state:'open'}),
 ],{mode:'date',sort:'due',now});
 assert.deepEqual(groups.map(group=>group.key),['overdue','today','tomorrow','later','undated']);
 assert.deepEqual(groups.find(group=>group.key==='today').items.map(item=>item.id),['routine:routine','task:today']);
 assert.equal(groups.some(group=>group.key==='routines'),false);
});
test('due sorting is deterministic across task and routine and puts undated work last',()=>{
 const sorted=sortActions([
  task('late','Später',local(20,12)),
  task('undated','Ohne Termin',null,{state:'open'}),
  routine('early','Routine zuerst',local(19,11)),
  task('early','Task danach',local(19,13)),
 ],'due');
 assert.deepEqual(sorted.map(item=>item.id),['routine:early','task:early','task:late','task:undated']);
});
test('status grouping keeps routine as an item rather than a separate domain section',()=>{
 const groups=groupActions([routine('routine','Vitamin D',local(19,12)),task('task','Wäsche',local(19,13))],{mode:'status',sort:'due'});
 assert.deepEqual(groups.map(group=>group.key),['due']);
 assert.deepEqual(groups[0].items.map(item=>item.id),['routine:routine','task:task']);
});
test('view preferences accept only supported grouping sorting and density values',()=>{
 assert.deepEqual(normalizeTodoViewPreferences({group:'wat',sort:'newest',density:'tiny'}),DEFAULT_TODO_VIEW_PREFERENCES);
 assert.deepEqual(normalizeTodoViewPreferences({group:'person',sort:'title',density:'comfortable'}),{group:'person',sort:'title',density:'comfortable'});
});
test('active upcoming and today views do not reintroduce completed or paused work',()=>{
 const activeRows=[task('open','Offen',local(19,12)),task('done','Erledigt',local(19,11),{state:'done'}),task('paused','Pausiert',local(19,10),{state:'paused'})];
 assert.deepEqual(visibleActions(activeRows,{view:'upcoming'}).map(item=>item.id),['task:open']);
 assert.deepEqual(visibleActions(activeRows,{view:'today'}).map(item=>item.id),['task:open']);
});
test('task and legacy routine routes share the primary navigation and label',()=>{
 for(const page of ['todo','tasks','routines']){
  assert.equal(primaryNavCurrent(page),'todo');
  assert.equal(pageLabel(page,value=>value,{language:'de'}),'Aufgaben');
 }
});
test('workspace links use registry-owned selectors and remove other feature context',()=>{
 const href=featureHref('todo',{todo:'all',task:null},'https://example.test/?page=tasks&task=old&list=old');
 assert.equal(href,'/?page=todo&todo=all');
 assert.throws(()=>featureHref('todo',{unowned:'wrong'},'https://example.test/'),/Unsupported feature selector/);
});