import test from 'node:test';
import assert from 'node:assert/strict';
import {DEFAULT_TODO_VIEW_PREFERENCES,groupActions,normalizeTodoViewPreferences,sortActions,visibleActions} from './todo-workspace.js';

const local=(day,hour=10)=>new Date(2026,9,day,hour,0,0,0).toISOString();
const task=(id,title,date,extra={})=>({id:`task:${id}`,kind:'task',title,state:'due',due_at:date,priority:'normal',context:{list:null},...extra});
const routine=(id,title,date,extra={})=>({id:`routine:${id}`,kind:'routine',title,state:'due',due_at:null,next_due_at:date,priority:'normal',context:{list:null},...extra});

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
 const rows=sortActions([
  task('late','Später',local(20,12)),
  task('undated','Ohne Termin',null,{state:'open'}),
  routine('early','Routine zuerst',local(19,11)),
  task('early','Task danach',local(19,13)),
 ],'due');
 assert.deepEqual(rows.map(item=>item.id),['routine:early','task:early','task:late','task:undated']);
});

test('status grouping keeps routine as an item rather than a separate domain section',()=>{
 const groups=groupActions([routine('routine','Vitamin D',local(19,12)),task('task','Wäsche',local(19,13))],{mode:'status',sort:'due'});
 assert.deepEqual(groups.map(group=>group.key),['due']);
 assert.deepEqual(groups[0].items.map(item=>item.id),['routine:routine','task:task']);
});

test('view preferences reject unknown persisted values',()=>{
 assert.deepEqual(normalizeTodoViewPreferences({group:'wat',sort:'random',density:'tiny'}),DEFAULT_TODO_VIEW_PREFERENCES);
 assert.deepEqual(normalizeTodoViewPreferences({group:'person',sort:'priority',density:'comfortable'}),{group:'person',sort:'priority',density:'comfortable'});
});

test('active upcoming and today views do not reintroduce completed or paused work',()=>{
 const rows=[task('open','Offen',local(19,12)),task('done','Erledigt',local(19,11),{state:'done'}),task('paused','Pausiert',local(19,10),{state:'paused'})];
 assert.deepEqual(visibleActions(rows,{view:'upcoming'}).map(item=>item.id),['task:open']);
 assert.deepEqual(visibleActions(rows,{view:'today'}).map(item=>item.id),['task:open']);
});
