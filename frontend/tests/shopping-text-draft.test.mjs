import test from 'node:test';
import assert from 'node:assert/strict';
import {cleanShoppingTextLine,parseShoppingTextDraft,reconcileShoppingTextLineIds,SHOPPING_TEXT_MAX_LINES} from '../src/shopping-text-draft.js';

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

test('line mutation ids survive reorder and in-place edits',()=>{
  let counter=0;const idFactory=()=>`id-${++counter}`;
  const first=parseShoppingTextDraft('Milch\nBrot').rows;
  let ids=reconcileShoppingTextLineIds([],first,new Map(),idFactory);
  const milk=ids.get(first[0].signature),bread=ids.get(first[1].signature);

  const reordered=parseShoppingTextDraft('Brot\nMilch').rows;
  ids=reconcileShoppingTextLineIds(first,reordered,ids,idFactory);
  assert.equal(ids.get(reordered[0].signature),bread);
  assert.equal(ids.get(reordered[1].signature),milk);

  const edited=parseShoppingTextDraft('Brot\nMilch 1 l').rows;
  ids=reconcileShoppingTextLineIds(reordered,edited,ids,idFactory);
  assert.equal(ids.get(edited[0].signature),bread);
  assert.equal(ids.get(edited[1].signature),milk);
});

test('duplicate lines get distinct identities',()=>{
  let counter=0;const rows=parseShoppingTextDraft('Milch\nMilch').rows;
  const ids=reconcileShoppingTextLineIds([],rows,new Map(),()=>`id-${++counter}`);
  assert.notEqual(ids.get(rows[0].signature),ids.get(rows[1].signature));
});
