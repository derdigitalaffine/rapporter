import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {defaultTodayWidgets,normalizeTodayLayout,TodayWidgetsById} from '../src/todayWidgetRegistry.js';
import {featureHref} from '../src/navigation.js';

const widgetSource=await readFile(new URL('../src/TodayCoreWidgets.jsx',import.meta.url),'utf8');
const timelineStyles=await readFile(new URL('../src/today-core-widgets.css',import.meta.url),'utf8');
const mealSource=await readFile(new URL('../src/MealPlanningHub.jsx',import.meta.url),'utf8');

test('fresh and explicit reset defaults follow the current Today core sequence',()=>{
 const rows=defaultTodayWidgets();
 assert.deepEqual(rows.filter(row=>row.visible).map(row=>row.id),['situation','focus','timeline','week','todo','quick-actions','pinboard','meals']);
 assert.deepEqual(TodayWidgetsById.overview.supportedSizes,['wide']);
 assert.equal(normalizeTodayLayout({version:2,revision:0,widgets:rows}).widgets.find(row=>row.id==='overview').visible,false);
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

test('meal planning derives today from the family timezone rather than UTC serialization',()=>{
 assert.ok(mealSource.includes("timeZone:family?.timezone||'Europe/Berlin'"));
 assert.ok(mealSource.includes('familyToday(family)'));
 assert.equal(mealSource.includes('toISOString().slice(0,10)'),false);
});

test('Today timeline only projects open tasks with a real due time today',()=>{
 assert.ok(widgetSource.includes("item?.kind!=='task'||!item.due_at||!visibleAction(item)"));
 assert.ok(widgetSource.includes("clock&&(clock.hour!==0||clock.minute!==0)"));
 assert.ok(widgetSource.includes("kind:'task',title:item.title,at:item.due_at"));
 assert.ok(widgetSource.includes("timed.sort((a,b)=>timeValue(a.at)-timeValue(b.at)"));
});
test('mixed timeline rows expose task and calendar semantics without relying on color',()=>{
 assert.ok(widgetSource.includes("`today-timeline-entry-${item.kind}`"));
 assert.ok(widgetSource.includes("const typeLabel=item.kind==='task'?l.task:l.calendar"));
 assert.ok(widgetSource.includes('className="today-timeline-meta"'));
 assert.ok(timelineStyles.includes('.today-timeline-entry-task .today-timeline-dot'));
 assert.ok(timelineStyles.includes('.today-timeline-entry-task .today-timeline-dot:after'));
});
test('current time is a stable axis marker and next-item emphasis does not shift the axis',()=>{
 assert.ok(widgetSource.includes('className="today-timeline-now"'));
 assert.ok(timelineStyles.includes('.today-timeline-now:after'));
 assert.ok(timelineStyles.includes('.today-timeline-entry.next .today-timeline-copy'));
 assert.equal(timelineStyles.includes('.today-timeline-list li.next>a time{margin-left:-8px}'),false);
});
