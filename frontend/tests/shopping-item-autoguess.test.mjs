import test from 'node:test';
import assert from 'node:assert/strict';
import {applyShoppingItemAutoguess,parseShoppingItemInput,SHOPPING_ITEM_SUGGESTION_VERSION} from '../src/shopping-item-autoguess.js';

test('parses quantity/unit prefix without keeping it in the item name',()=>{
  const parsed=parseShoppingItemInput('500 g Tomaten');
  assert.equal(parsed.version,SHOPPING_ITEM_SUGGESTION_VERSION);
  assert.equal(parsed.values.name,'Tomaten');
  assert.equal(parsed.values.quantity,'500 g');
  assert.deepEqual(parsed.suggestions.map(row=>row.field),['name','quantity']);
});

test('keeps German decimal comma deterministic',()=>{
  const parsed=parseShoppingItemInput('1,5 l Wasser');
  assert.equal(parsed.values.name,'Wasser');
  assert.equal(parsed.values.quantity,'1,5 l');
});

test('keeps explicit count separate from package quantity',()=>{
  const parsed=parseShoppingItemInput('2 x Milch 1 l');
  assert.equal(parsed.values.name,'Milch');
  assert.equal(parsed.values.quantity,'2 × 1 l');
  assert.notEqual(parsed.values.quantity,'21 l');
});

test('does not interpret 6er product names as a quantity',()=>{
  const parsed=parseShoppingItemInput('6er Eier');
  assert.equal(parsed.values.name,'6er Eier');
  assert.equal(parsed.values.quantity,'');
  assert.deepEqual(parsed.suggestions,[]);
});

test('normalizes whitespace and unicode without inventing metadata',()=>{
  const parsed=parseShoppingItemInput('  Crème   fraîche  ');
  assert.equal(parsed.values.name,'Crème fraîche');
  assert.equal(parsed.values.quantity,'');
  assert.equal(parsed.values.category,'');
});

test('same input produces the same versioned suggestion contract',()=>{
  assert.deepEqual(parseShoppingItemInput('2 × Milch 1 l'),parseShoppingItemInput('2 × Milch 1 l'));
});

test('manual quantity wins over parser suggestion',()=>{
  const result=applyShoppingItemAutoguess({name:'500 g Tomaten',quantity:'2 Schalen',category:'Gemüse'});
  assert.equal(result.payload.name,'Tomaten');
  assert.equal(result.payload.quantity,'2 Schalen');
  assert.equal(result.payload.category,'Gemüse');
});

test('empty and ambiguous input abstain safely',()=>{
  assert.deepEqual(parseShoppingItemInput('   ').suggestions,[]);
  const ambiguous=parseShoppingItemInput('4711 Wasser');
  assert.equal(ambiguous.values.name,'4711 Wasser');
  assert.equal(ambiguous.values.quantity,'');
  assert.deepEqual(ambiguous.suggestions,[]);
});
