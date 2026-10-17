import test from 'node:test';
import assert from 'node:assert/strict';
import {cleanShoppingTextLine,parseShoppingTextDraft,SHOPPING_TEXT_MAX_LINES} from '../src/shopping-text-draft.js';

test('multiline draft only parses rows and keeps canonical parser fields',()=>{
  const result=parseShoppingTextDraft('Milk\n500 g Tomaten\n2 x Wasser 1 l');
  assert.equal(result.rows.length,3);
  assert.equal(result.rows[1].parsed.values.name,'Tomaten');
  assert.equal(result.rows[1].parsed.values.quantity,'500 g');
  assert.equal(result.rows[2].parsed.values.name,'Wasser');
  assert.equal(result.rows[2].parsed.values.quantity,'2 × 1 l');
});

test('common list and checkbox prefixes are stripped conservatively',()=>{
  assert.equal(cleanShoppingTextLine('- Milch'),'Milch');
  assert.equal(cleanShoppingTextLine('• Brot'),'Brot');
  assert.equal(cleanShoppingTextLine('2) Kaffee'),'Kaffee');
  assert.equal(cleanShoppingTextLine('[x] Eier'),'Eier');
});

test('commas are never treated as item separators',()=>{
  const result=parseShoppingTextDraft('Tomaten, passiert\nCrème fraîche');
  assert.equal(result.rows.length,2);
  assert.equal(result.rows[0].cleaned,'Tomaten, passiert');
});

test('blank lines are ignored',()=>{
  const result=parseShoppingTextDraft('Milch\n\n   \nBrot');
  assert.deepEqual(result.rows.map(row=>row.cleaned),['Milch','Brot']);
});

test('large drafts are bounded and reported without parsing beyond the limit',()=>{
  const input=Array.from({length:SHOPPING_TEXT_MAX_LINES+3},(_,index)=>`Artikel ${index}`).join('\n');
  const result=parseShoppingTextDraft(input);
  assert.equal(result.overLimit,true);
  assert.equal(result.total,SHOPPING_TEXT_MAX_LINES+3);
  assert.equal(result.rows.length,SHOPPING_TEXT_MAX_LINES);
});
