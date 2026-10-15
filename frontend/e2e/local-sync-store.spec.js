import {test, expect} from '@playwright/test';
import {readFile} from 'node:fs/promises';

const source = await readFile(new URL('../src/local-sync-store.js', import.meta.url), 'utf8');

test.beforeEach(async ({page}) => {
  await page.route('**/local-store-test', route => route.fulfill({contentType: 'text/html', body: '<!doctype html><title>Local store test</title>'}));
  await page.route('**/local-sync-store.js', route => route.fulfill({contentType: 'text/javascript', body: source}));
  await page.goto('/local-store-test');
});

test('account and family namespaces survive reload and cannot be overridden by payload', async ({page}) => {
  await page.evaluate(async () => {
    const {createLocalSyncStore} = await import('/local-sync-store.js');
    for (const [accountId, familyId, title] of [['a','f','one'], ['a','g','two'], ['b','f','three']]) {
      await createLocalSyncStore({accountId, familyId}).write([{store:'tasks', type:'put', value:{id:'same', accountId:'spoof', familyId:'spoof', version:1, data:{title}}}]);
    }
  });
  await page.reload();
  expect(await page.evaluate(async () => {
    const {createLocalSyncStore} = await import('/local-sync-store.js');
    return Promise.all([['a','f'], ['a','g'], ['b','f']].map(async ([accountId, familyId]) =>
      (await createLocalSyncStore({accountId, familyId}).list('tasks')).map(row => [row.accountId, row.familyId, row.data.title])));
  })).toEqual([[['a','f','one']], [['a','g','two']], [['b','f','three']]]);
});

test('failed outbox persistence rolls back entity and cursor together', async ({page}) => {
  expect(await page.evaluate(async () => {
    const {createLocalSyncStore} = await import('/local-sync-store.js');
    const store = createLocalSyncStore({accountId:'a',familyId:'f'});
    await store.write([{store:'syncState',type:'put',value:{id:'cursor',cursor:7}}]);
    let failed = false;
    try {
      await store.write([
        {store:'tasks',type:'put',value:{id:'t',version:1,data:{title:'pending'}}},
        {store:'syncState',type:'put',value:{id:'cursor',cursor:8}},
        {store:'outbox',type:'put',value:{id:'m',uncloneable:() => {}}},
      ]);
    } catch { failed = true; }
    return {failed, tasks:await store.list('tasks'), outbox:await store.list('outbox'), cursor:(await store.get('syncState','cursor')).cursor};
  })).toEqual({failed:true,tasks:[],outbox:[],cursor:7});
});

test('pending mutations and conflicts survive reopening; cleanup removes only the selected account', async ({page}) => {
  await page.evaluate(async () => {
    const {createLocalSyncStore} = await import('/local-sync-store.js');
    for (const accountId of ['a','b']) {
      const store = createLocalSyncStore({accountId,familyId:'f'});
      await store.enqueue('shoppingItems', {id:'item',version:0,data:{name:'Milk'},sync_status:'pending'},
        {mutation_id:'m',entity_type:'shopping_item',entity_id:'item',operation:'create',base_version:0,payload:{name:'Milk'}});
      await store.write([{store:'conflicts',type:'put',value:{id:'c',fields:['name']}}, {store:'meta',type:'put',value:{id:'protocol',version:1}}]);
    }
    await createLocalSyncStore({accountId:'a',familyId:'other'}).write([{store:'events',type:'put',value:{id:'event'}}]);
  });
  await page.reload();
  expect(await page.evaluate(async () => {
    const {createLocalSyncStore,clearLocalSyncAccount} = await import('/local-sync-store.js');
    const a = createLocalSyncStore({accountId:'a',familyId:'f'});
    const before = [(await a.list('outbox')).length,(await a.list('conflicts')).length];
    await clearLocalSyncAccount('a');
    const after = await Promise.all(['shoppingItems','outbox','conflicts','meta'].map(async name => (await a.list(name)).length));
    return {before,after,otherFamily:await createLocalSyncStore({accountId:'a',familyId:'other'}).list('events'),otherAccount:(await createLocalSyncStore({accountId:'b',familyId:'f'}).list('outbox')).length};
  })).toEqual({before:[1,1],after:[0,0,0,0],otherFamily:[],otherAccount:1});
});

test('invalid scope and mismatched mutation targets fail before persistence', async ({page}) => {
  expect(await page.evaluate(async () => {
    const {createLocalSyncStore} = await import('/local-sync-store.js');
    let invalid = false, mismatch = false;
    try { createLocalSyncStore({accountId:'',familyId:'f'}); } catch { invalid = true; }
    const store = createLocalSyncStore({accountId:'a',familyId:'f'});
    try { await store.enqueue('tasks',{id:'a'},{mutation_id:'m',entity_type:'task',entity_id:'b'}); } catch { mismatch = true; }
    return {invalid,mismatch,entities:await store.list('tasks'),outbox:await store.list('outbox')};
  })).toEqual({invalid:true,mismatch:true,entities:[],outbox:[]});
});
