import {test} from 'node:test';
import assert from 'node:assert/strict';
import {defaultTodayWidgets,normalizeTodayLayout,TodayWidgetsById} from '../src/todayWidgetRegistry.js';
import {featureHref} from '../src/navigation.js';

test('fresh and explicit reset defaults have overview and focus, not duplicate lists',()=>{
 const rows=defaultTodayWidgets();
 assert.deepEqual(rows.filter(row=>row.visible).map(row=>row.id),['situation','overview','focus']);
 assert.deepEqual(TodayWidgetsById.overview.supportedSizes,['wide']);
 assert.equal(normalizeTodayLayout({version:2,revision:0,widgets:rows}).widgets.find(row=>row.id==='overview').visible,true);
});
test('saved personal layouts retain visible order and keep the new overview opt-in',()=>{
 const widgets=[{id:'situation',visible:true,size:'compact'},{id:'shopping',visible:true,size:'compact'},{id:'focus',visible:false,size:'wide'},{id:'timeline',visible:true,size:'wide'}];
 const normalized=normalizeTodayLayout({version:2,revision:7,widgets});
 assert.equal(normalized.revision,7);
 assert.deepEqual(normalized.widgets.filter(row=>widgets.some(old=>old.id===row.id)),widgets);
 assert.equal(normalized.widgets.find(row=>row.id==='overview').visible,false);
});
test('legacy v1 retains migration semantics without silently opting into the new default',()=>{
 const normalized=normalizeTodayLayout({version:1,revision:3,widgets:[{id:'next',visible:true,size:'full'},{id:'priority',visible:true,size:'full'}]});
 assert.equal(normalized.widgets.find(row=>row.id==='overview').visible,false);
 assert.equal(normalized.widgets.find(row=>row.id==='timeline').visible,true);
 assert.equal(normalized.widgets.find(row=>row.id==='focus').visible,true);
});
test('overview links and optional card deep links are owned by central navigation',()=>{
 const current='https://example.test/?page=tasks&task=old';
 assert.equal(featureHref('todo',{todo:'today'},current),'/?page=todo&todo=today');
 assert.equal(featureHref('loyalty',{card:'one'},current),'/?page=loyalty&card=one');
 for(const page of ['calendar','shopping','board','inbox','more'])assert.equal(new URL(featureHref(page,{},current),'https://example.test').searchParams.get('page'),page);
});
