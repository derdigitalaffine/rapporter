import {readFileSync} from 'node:fs';
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {pageLabel} from '../src/app-navigation.js';
import {decisionContextClearedHref,decisionContextHref,decisionPresetDraft,decisionPresetsFor} from '../src/decision-context.js';

const source=readFileSync(new URL('../src/DecisionContextPanel.jsx',import.meta.url),'utf8');
const css=readFileSync(new URL('../src/decision-context-panel.css',import.meta.url),'utf8');
const hub=readFileSync(new URL('../src/DecisionsHub.jsx',import.meta.url),'utf8');
const registry=readFileSync(new URL('../src/feature-registry.js',import.meta.url),'utf8');

test('context decision disclosure keeps accessible launcher semantics',()=>{
  assert.match(source,/aria-expanded=\{open\}/);
  assert.match(source,/aria-controls=\{regionId\}/);
  assert.match(source,/id=\{regionId\}[^>]*role="region"[^>]*aria-labelledby=\{titleId\}/);
});

test('context surfaces only launch the canonical decisions area',()=>{
  assert.match(source,/decisionContextHref/);
  assert.doesNotMatch(source,/\bapi\(/);
  assert.doesNotMatch(source,/FormShell|ErrorSummary|\/decisions\//);
  assert.equal(decisionContextHref({type:'trip',id:'trip-9'},'stay'),'/?page=decisions&decision_context_type=trip&decision_context_id=trip-9&decision_preset=stay');
  assert.equal(decisionContextHref(null),'/?page=decisions');
  assert.equal(decisionContextClearedHref('https://family.example/?page=decisions&decision_context_type=trip&decision_context_id=trip-9&decision_preset=stay','decision-1'),'/?page=decisions&decision=decision-1');
});

test('shared contextual presets prefill the central decision composer',()=>{
  assert.deepEqual(decisionPresetsFor('shopping_list',false).map(item=>[item.key,item.mode]),[['purchase','ranking'],['meal','single']]);
  assert.deepEqual(decisionPresetsFor('trip',false).map(item=>[item.key,item.mode]),[['destination','ranking'],['stay','rating'],['activity','multiple']]);
  assert.deepEqual(decisionPresetDraft('?decision_context_type=shopping_list&decision_context_id=list-1&decision_preset=meal',false),{
    question:'Was wollen wir essen?',mode:'single',anonymous:false,closes_at:'',options:['',''],
  });
});

test('canonical decisions hub owns contextual creation and shopping result transfer',()=>{
  assert.match(hub,/decisionContextFromSearch\(location\.search\)/);
  assert.match(hub,/decisionPresetDraft\(location\.search,en\)/);
  assert.match(hub,/if\(routeContext\)payload\.context=routeContext/);
  assert.match(hub,/clearContextRoute\(created\.id\)/);
  assert.match(hub,/row\?\.context\?\.type!=='shopping_list'/);
  assert.match(hub,/\/smart\/shopping\/quick-add\//);
  assert.match(hub,/SYNC_CHANGED/);
});

test('decision deep-link selectors are owned by the feature registry',()=>{
  assert.match(registry,/defineFeature\('decisions',\{detail:true,queryParams:\['decision','decision_context_type','decision_context_id','decision_preset'\]/);
});

test('contract navigation exposes localized labels before the lazy ContractUI bundle loads',()=>{
  const t=key=>key;
  assert.equal(pageLabel('contracts',t,{language:'de'}),'Verträge');
  assert.equal(pageLabel('contracts',t,{language:'en'}),'Contracts');
});

test('context launcher styles preserve FamilyOS touch and reflow contracts',()=>{
  for(const token of ['--color-border','--color-neutral-soft','--color-muted','--color-focus','--space-2','--radius-md'])assert.ok(css.includes(`var(${token})`),token);
  assert.doesNotMatch(css,/var\(--(?:border|surface|surface-2|muted|brand),/);
  assert.match(css,/min-height:44px/);
  assert.match(css,/@media\(max-width:359px\)/);
  assert.match(css,/\.decision-context-presets a,\.decision-context-open-all\{width:100%/);
});
