import {test} from 'node:test';
import assert from 'node:assert/strict';
import {formatCivilDate,formatDateTime} from '../src/locale.js';
import {FEATURE_REGISTRY,featureAvailability} from '../src/feature-registry.js';
import {featureHref} from '../src/navigation.js';
import {TodayWidgetsById,normalizeTodayLayout} from '../src/todayWidgetRegistry.js';
import {healthDateLabel,healthDoseLabel,visibleHealthItems} from '../src/children-health-ui.js';

test('German civil dates always have padded TT.MM.JJJJ, without timezone drift',()=>{
 assert.equal(formatCivilDate('de','2026-01-02'),'02.01.2026');
 assert.equal(formatCivilDate('de-DE','2024-02-29'),'29.02.2024');
 assert.equal(formatCivilDate('en','2026-01-02'),'02/01/2026');
 for(const value of ['',null,'2026-02-31','2026-1-2','invalid'])assert.equal(formatCivilDate('de',value),'');
 assert.equal(formatDateTime('de','2026-01-01T23:30:00Z',{timeZone:'Europe/Berlin',day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit'}),'02.01.2026, 00:30');
 assert.equal(healthDateLabel({window_start:'2026-01-02',window_end:'2026-02-03'},'de'),'02.01.2026 – 03.02.2026');
 assert.equal(healthDateLabel({occurred_on:'2026-01-02'},'de'),'02.01.2026');
 assert.equal(healthDoseLabel({dose:'booster-3'},key=>({booster:'Auffrischung'})[key]),'Auffrischung');
});
test('vaccination calendar is chronological without mutating or interpreting medical state',()=>{
 const items=[{title:'Later',key:'later',kind:'vaccination',state:'unknown',window_start:'2027-01-01'},
  {title:'First',key:'first',kind:'vaccination',state:'later',window_start:'2026-11-01'},
  {title:'Done',key:'done',kind:'vaccination',state:'done',occurred_on:'2026-10-01'},
  {title:'Unknown',key:'old',kind:'vaccination',state:'unknown',historical:true,window_end:'2026-01-01'}];
 assert.deepEqual(visibleHealthItems(items,'vaccination','current').map(row=>row.key),['first','later']);
 assert.deepEqual(visibleHealthItems(items,'vaccination','history').map(row=>row.key),['done','old']);
 assert.equal(items[0].key,'later');assert.equal(items[1].state,'later');
});
test('pregnancy and children use distinct registered routes and capability checks',()=>{
 assert.equal(typeof FEATURE_REGISTRY.find(row=>row.id==='pregnancy').load,'function');
 assert.equal(featureHref('pregnancy',{view:'more'},'https://example.test/?page=baby&baby=child&event=event'),'/?page=pregnancy&view=more');
 assert.equal(featureAvailability('pregnancy',{babyModule:{enabled:true,authorized:true,can_manage:false,permissions:{can_view_pregnancy:false}}}),'denied');
 assert.equal(featureAvailability('pregnancy',{entitlements:{capabilities:[]}}),'locked');
});
test('pregnancy widget is opt-in, gated, and does not reorder saved widgets',()=>{
 const widget=TodayWidgetsById.pregnancy;
 assert.equal(widget.defaultVisible,false);assert.equal(widget.permissionGate,'can_view_pregnancy');assert.equal(widget.sensitivity,'health');
 const layout=normalizeTodayLayout({version:2,revision:1,widgets:[{id:'shopping',visible:true,size:'compact'},{id:'todo',visible:true,size:'compact'}]});
 assert.ok(layout.widgets.findIndex(row=>row.id==='shopping')<layout.widgets.findIndex(row=>row.id==='todo'));
 assert.equal(layout.widgets.find(row=>row.id==='pregnancy').visible,false);
});
