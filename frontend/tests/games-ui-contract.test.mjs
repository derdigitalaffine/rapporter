import {readFileSync} from 'node:fs';
import {test} from 'node:test';
import assert from 'node:assert/strict';

const hub=readFileSync(new URL('../src/GamesHub.jsx',import.meta.url),'utf8');
const css=readFileSync(new URL('../src/games.css',import.meta.url),'utf8');

test('games remains one canonical duel surface using shared form primitives',()=>{
  assert.match(hub,/FormShell,FormSection,FormField,FormActions,ErrorSummary,ProgressiveFieldGroup/);
  for(const type of ['rps','battleship','quiz','connect_four'])assert.ok(hub.includes(type),type);
  assert.match(hub,/\/games\//);
  assert.doesNotMatch(hub,/localStorage/);
});

test('games UI exposes clear actionable and result states',()=>{
  assert.match(hub,/needsMove\(match\)/);
  assert.match(hub,/resultLabel\(match,s\)/);
  assert.match(hub,/className="games-result"/);
  assert.match(hub,/className="games-inline-state"/);
  assert.match(hub,/className="games-status/);
});

test('games CSS is tokenized, touch-safe, focus-visible and narrow-screen safe',()=>{
  for(const token of ['--color-border','--color-surface','--color-neutral-soft','--color-muted','--color-focus','--color-text','--space-2','--space-3','--space-4','--space-6','--radius-md'])assert.ok(css.includes(`var(${token})`),token);
  assert.doesNotMatch(css,/var\(--(?:muted|surface|surface-alt|border|text),/);
  assert.doesNotMatch(css,/#[0-9a-f]{3,8}/i);
  assert.doesNotMatch(css,/rgba?\(/i);
  assert.doesNotMatch(css,/!important/);
  assert.match(css,/min-height:44px/);
  assert.match(css,/:focus-visible/);
  assert.match(css,/@media\(max-width:359px\)/);
  assert.match(css,/@media\(prefers-reduced-motion:reduce\)/);
});

test('board polish preserves semantic game states without horizontal-only interaction',()=>{
  for(const selector of ['.sea-cell.ship','.sea-cell.miss','.sea-cell.hit','.sea-cell.sunk','.connect-drop-row button','.game-choice','.quiz-options button'])assert.ok(css.includes(selector),selector);
  assert.match(css,/\.battle-boards\{display:grid/);
  assert.match(css,/@media\(max-width:720px\)[\s\S]*\.battle-boards\{grid-template-columns:1fr\}/);
});
