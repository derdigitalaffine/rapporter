import {readFileSync} from 'node:fs';
import {test} from 'node:test';
import assert from 'node:assert/strict';

const source=readFileSync(new URL('../src/DecisionContextPanel.jsx',import.meta.url),'utf8');
const css=readFileSync(new URL('../src/decision-context-panel.css',import.meta.url),'utf8');

test('context decision disclosure exposes its controlled region',()=>{
  assert.match(source,/aria-expanded=\{open\}/);
  assert.match(source,/aria-controls=\{regionId\}/);
  assert.match(source,/id=\{regionId\}[^>]*role="region"[^>]*aria-labelledby=\{titleId\}/);
});

test('context decision form uses shared accessible validation primitives',()=>{
  assert.match(source,/ErrorSummary/);
  assert.match(source,/noValidate/);
  assert.match(source,/error=\{fieldError\(questionId\)\}/);
  assert.match(source,/error=\{fieldError\(optionId\(index\)\)\}/);
  assert.doesNotMatch(source,/disabled=\{busy==='create'\|\|cleanOptions/);
});

test('context decision styles use FamilyOS tokens and preserve touch/reflow contracts',()=>{
  for(const token of ['--color-border','--color-surface','--color-neutral-soft','--color-muted','--color-focus','--space-2','--radius-md'])assert.ok(css.includes(`var(${token})`),token);
  assert.doesNotMatch(css,/var\(--(?:border|surface|surface-2|muted|brand),/);
  assert.match(css,/min-height:44px/);
  assert.match(css,/@media\(max-width:359px\)/);
  assert.match(css,/\.decision-context-option\{grid-template-columns:1fr\}/);
});
