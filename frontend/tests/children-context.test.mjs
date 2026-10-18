import test from 'node:test';
import assert from 'node:assert/strict';
import {childAgeMonths,childPermissions,defaultChildView,localDateTime} from '../src/children-context.js';

test('age is presentation only and handles the day before the birthday',()=>{
 assert.equal(childAgeMonths({birth_date:'2020-10-18'},new Date('2026-10-17T12:00:00')),71);
 assert.equal(childAgeMonths({birth_date:'2020-10-18'},new Date('2026-10-18T12:00:00')),72);
});
test('per-child capabilities take precedence over aggregate module permissions',()=>{
 assert.deepEqual(childPermissions({permissions:{can_log_care:false}},{permissions:{can_log_care:true,is_guardian:true}}),{can_log_care:false});
});
test('older children open health without changing identity or permissions',()=>{
 const child={birth_date:'2019-01-01',permissions:{can_log_care:true,can_view_growth_development:true}};
 assert.equal(defaultChildView(child,{}),'health');
 assert.equal(child.permissions.is_guardian,undefined);
});
test('care-only grants retain a usable care view',()=>{
 assert.equal(defaultChildView({birth_date:'2019-01-01',permissions:{can_log_care:true}},{}),'now');
 assert.equal(localDateTime(null),'');
});
