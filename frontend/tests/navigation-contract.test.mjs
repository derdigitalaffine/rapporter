import {test} from 'node:test';
import assert from 'node:assert/strict';
import {pageFromLocation,pageHref} from '../src/navigation.js';
import {FEATURE_REGISTRY,featureAvailability,FEATURE_QUERY_PARAMS} from '../src/feature-registry.js';

test('existing query routes and integration callbacks resolve deterministically',()=>{
  for(const feature of FEATURE_REGISTRY)assert.equal(pageFromLocation(`?page=${feature.id}`),feature.id);
  assert.equal(pageFromLocation('?page=unknown'),'home');
  assert.equal(pageFromLocation('?page=home&integration_connected=calendar'),'integrations');
});
test('same-page deep links survive; route changes remove all registry-owned selectors',()=>{
  for(const feature of FEATURE_REGISTRY){
    const url=new URL(`https://family.example/?page=${feature.id}&unrelated=keep#anchor`);
    for(const key of FEATURE_QUERY_PARAMS)url.searchParams.set(key,'example');
    const next=new URL(pageHref(feature.id,url.href),url.origin);
    for(const key of feature.queryParams){if(!key.startsWith('integration_'))assert.equal(next.searchParams.get(key),'example');}
    for(const key of FEATURE_QUERY_PARAMS){if(!feature.queryParams.includes(key))assert.equal(next.searchParams.has(key),false);}
    const home=new URL(pageHref('home',url.href),url.origin);
    assert.equal(home.searchParams.get('unrelated'),'keep');assert.equal(home.hash,'#anchor');
    for(const key of FEATURE_QUERY_PARAMS)assert.equal(home.searchParams.has(key),false);
  }
});
test('expenses do not leak expense selectors to other pages',()=>{
  assert.equal(pageHref('more','https://family.example/?page=expenses&ledger=1&expense=2'),'/?page=more');
  assert.equal(pageHref('expenses','https://family.example/?page=expenses&ledger=1&expense=2'),'/?page=expenses&ledger=1&expense=2');
});
test('family deep-link ownership comes from registry metadata',()=>{
  assert.equal(pageHref('vehicles','https://family.example/?page=vehicles&family=one&vehicle=two'),'/?page=vehicles&family=one&vehicle=two');
  assert.equal(pageHref('shopping','https://family.example/?page=vehicles&family=one&vehicle=two'),'/?page=shopping');
});
test('special auth paths are not routed through the query-page registry',()=>{
  for(const path of ['/invite/example','/verify-email/example','/reset-password/uid/example']){
    assert.equal(new URL(pageHref('home',`https://family.example${path}`),'https://family.example').pathname,path);
  }
});
test('UI gates avoid denied chunks without inventing an entitlement on snapshot failure',()=>{
  const light={capabilities:['calendar','notes']};
  assert.equal(featureAvailability('missing'),'unknown');
  for(const page of ['vehicles','trips','expenses','baby','pets','statistics'])assert.equal(featureAvailability(page,{entitlements:light}),'locked');
  assert.equal(featureAvailability('statistics',{entitlements:light,role:'guest'}),'denied');
  assert.equal(featureAvailability('statistics'),'pending');
  assert.equal(featureAvailability('trips',{entitlements:null}),'available');
  assert.equal(featureAvailability('baby',{babyModule:{enabled:false,authorized:false,can_manage:false}}),'denied');
  assert.equal(featureAvailability('baby',{babyModule:{enabled:false,can_manage:true}}),'available');
});
test('rare feature loaders are declared once in the canonical registry',()=>{
  for(const page of ['vehicles','notes','loyalty','statistics','baby','pets','trips','settings'])assert.equal(typeof FEATURE_REGISTRY.find(row=>row.id===page).load,'function');
  for(const page of ['home','more','todo','shopping','calendar'])assert.equal(FEATURE_REGISTRY.find(row=>row.id===page).load,null);
});
