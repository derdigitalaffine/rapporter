import 'fake-indexeddb/auto';
import {test, afterEach} from 'node:test';
import assert from 'node:assert/strict';
import {createLocalSyncStore, clearLocalSyncAccount, ENTITY_STORES} from '../src/local-sync-store.js';

const accounts = new Set();
const stores = [...ENTITY_STORES, 'outbox', 'conflicts', 'syncState', 'meta'];
function scoped(accountId = crypto.randomUUID(), familyId = 'family') {
  accounts.add(accountId);
  return createLocalSyncStore({accountId, familyId});
}
afterEach(async () => {
  for (const accountId of accounts) await clearLocalSyncAccount(accountId);
  accounts.clear();
});

test('compound keys isolate equal IDs by account and family, overriding spoofed payload scope', async () => {
  const account = crypto.randomUUID();
  const cases = [[account, 'one'], [account, 'two'], [crypto.randomUUID(), 'one']];
  for (const [accountId, familyId] of cases) {
    await scoped(accountId, familyId).write([{store:'tasks', type:'put', value:{id:'same', accountId:'spoof', familyId:'spoof', data:{title:familyId}}}]);
  }
  for (const [accountId, familyId] of cases) {
    const rows = await scoped(accountId, familyId).list('tasks');
    assert.equal(rows.length, 1);
    assert.equal(rows[0].accountId, accountId);
    assert.equal(rows[0].familyId, familyId);
  }
});

test('reopening preserves normalized entities, pending mutations, conflicts and metadata in every store', async () => {
  const accountId = crypto.randomUUID();
  const store = scoped(accountId);
  await store.write(stores.map(name => ({store:name, type:'put', value:{id:'row', version:3, data:{title:name}}})));
  const reopened = scoped(accountId);
  for (const name of stores) assert.equal((await reopened.get(name, 'row')).data.title, name);
});

test('uncloneable outbox rolls back earlier entity and cursor writes', async () => {
  const store = scoped();
  await store.write([{store:'syncState', type:'put', value:{id:'cursor', cursor:7}}]);
  await assert.rejects(store.write([
    {store:'tasks', type:'put', value:{id:'task', data:{title:'pending'}}},
    {store:'syncState', type:'put', value:{id:'cursor', cursor:8}},
    {store:'outbox', type:'put', value:{id:'mutation', uncloneable:() => {}}},
  ]), {name:'DataCloneError'});
  assert.equal(await store.get('tasks', 'task'), null);
  assert.deepEqual(await store.list('outbox'), []);
  assert.equal((await store.get('syncState', 'cursor')).cursor, 7);
});

test('enqueue persists entity and mutation together; acknowledgement atomically deletes the receipt and advances cursor', async () => {
  const store = scoped();
  await store.enqueue('shoppingItems', {id:'item', version:0, data:{name:'Milk'}},
    {mutation_id:'mutation', entity_type:'shopping_item', entity_id:'item', operation:'create', base_version:0});
  assert.equal((await store.get('outbox', 'mutation')).mutation_id, 'mutation');
  await store.write([
    {store:'shoppingItems', type:'put', value:{id:'item', version:1, data:{name:'Milk'}}},
    {store:'outbox', type:'delete', id:'mutation'},
    {store:'syncState', type:'put', value:{id:'cursor', cursor:10}},
  ]);
  assert.equal((await store.get('shoppingItems', 'item')).version, 1);
  assert.equal(await store.get('outbox', 'mutation'), null);
  assert.equal((await store.get('syncState', 'cursor')).cursor, 10);
});

test('cleanup removes every store across all account families and preserves another account', async () => {
  const accountId = crypto.randomUUID();
  const target = [scoped(accountId, 'one'), scoped(accountId, 'two')];
  const other = scoped();
  for (const store of [...target, other]) {
    await store.write(stores.map(name => ({store:name, type:'put', value:{id:'private', data:{title:'private'}}})));
  }
  await clearLocalSyncAccount(accountId);
  for (const name of stores) {
    for (const store of target) assert.deepEqual(await store.list(name), []);
    assert.equal((await other.list(name)).length, 1);
  }
});

test('invalid operations and mutation targets cannot leave partial writes', async () => {
  assert.throws(() => createLocalSyncStore({accountId:' ', familyId:'f'}));
  const store = scoped();
  await assert.rejects(store.write([
    {store:'tasks', type:'put', value:{id:'task'}},
    {store:'unknown', type:'put', value:{id:'row'}},
  ]), /unknown_local_sync_store/);
  await assert.rejects(store.enqueue('tasks', {id:'task'}, {mutation_id:'mutation', entity_type:'task', entity_id:'other'}), /entity_mismatch/);
  assert.deepEqual(await store.list('tasks'), []);
  assert.deepEqual(await store.list('outbox'), []);
});
