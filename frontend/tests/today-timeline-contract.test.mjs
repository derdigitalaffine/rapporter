import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';

const widgetSource=await readFile(new URL('../src/TodayCoreWidgets.jsx',import.meta.url),'utf8');
const timelineStyles=await readFile(new URL('../src/today-core-widgets.css',import.meta.url),'utf8');

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
