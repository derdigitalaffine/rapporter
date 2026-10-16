import {test} from 'node:test';
import assert from 'node:assert/strict';
import {scopeForView,workspaceView,visibleActions} from '../src/todo-workspace.js';
import {primaryNavCurrent,pageLabel} from '../src/app-navigation.js';
import {featureHref} from '../src/navigation.js';

const rows=[
 {id:'task:1',kind:'task',title:'Ohne Termin',state:'open',context:{list:{id:'l'}},assignee:{id:7}},
 {id:'task:2',kind:'task',title:'Wiederkehrend',state:'due',schedule:{recurrence:{frequency:'weekly'}}},
 {id:'routine:3',kind:'routine',title:'Bestand',state:'due'},
 {id:'task:4',kind:'task',title:'Erledigt',state:'done'},
];
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
