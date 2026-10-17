import test from 'node:test';
import assert from 'node:assert/strict';
import {currentShoppingList,shoppingTextScopeKey} from '../src/shopping-text-scope.js';

test('scope key is explicit about family and list',()=>{
  assert.equal(shoppingTextScopeKey('family-a','list-1'),'family-a:list-1');
  assert.equal(shoppingTextScopeKey('family-a',null),'');
});

test('stale list from another family is never selected',()=>{
  const rows=[
    {id:'old-list',family:'family-a'},
    {id:'new-list',family:'family-b'},
  ];
  assert.equal(currentShoppingList(rows,'family-b','old-list').id,'new-list');
});

test('active list is selected only inside the current family',()=>{
  const rows=[
    {id:'one',family:'family-a'},
    {id:'two',family:'family-a'},
    {id:'two',family:'family-b'},
  ];
  assert.equal(currentShoppingList(rows,'family-a','two').family,'family-a');
  assert.equal(currentShoppingList(rows,'family-c','two'),null);
});
