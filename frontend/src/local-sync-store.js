// Additive P0 persistence contract. Domain cutover and HTTP sync follow separately.
export const LOCAL_SYNC_DB = 'familyos-local-sync';
export const LOCAL_SYNC_VERSION = 2;
export const ENTITY_STORES = Object.freeze(['taskLists', 'tasks', 'shoppingLists', 'shoppingItems', 'events']);
const STORES = [...ENTITY_STORES, 'outbox', 'conflicts', 'syncState', 'meta'];

function openDb() {
  return new Promise((resolve, reject) => {
    if (!globalThis.indexedDB) return reject(new Error('indexeddb_unavailable'));
    const request = indexedDB.open(LOCAL_SYNC_DB, LOCAL_SYNC_VERSION);
    let blocked = false;
    request.onupgradeneeded = () => {
      const db = request.result;
      // Future migrations must be additive and preserve pending outbox/conflicts.
      for (const name of STORES) {
        if (db.objectStoreNames.contains(name)) continue;
        const store = db.createObjectStore(name, {keyPath: ['accountId', 'familyId', 'id']});
        store.createIndex('scope', ['accountId', 'familyId']);
        store.createIndex('account', 'accountId');
        if (name === 'outbox') store.createIndex('entity', ['accountId', 'familyId', 'entity_type', 'entity_id']);
      }
      const outbox = request.transaction.objectStore('outbox');
      if (!outbox.indexNames.contains('scopeOrder')) {
        outbox.createIndex('scopeOrder', ['accountId', 'familyId', 'order']);
        outbox.openCursor().onsuccess = event => {
          const cursor = event.target.result;
          if (cursor) {
            if (!Number.isFinite(cursor.value.order)) cursor.update({...cursor.value, order: 0});
            cursor.continue();
          }
        };
      }
    };
    request.onsuccess = () => {
      const db = request.result;
      if (blocked) { db.close(); return; }
      db.onversionchange = () => db.close();
      resolve(db);
    };
    request.onerror = () => reject(request.error);
    request.onblocked = () => { blocked = true; reject(new Error('indexeddb_upgrade_blocked')); };
  });
}

function identifier(value) {
  if (typeof value !== 'string' || !value.trim()) throw new TypeError('local_sync_identifier_required');
  return value;
}

function storeName(name) {
  if (!STORES.includes(name)) throw new TypeError('unknown_local_sync_store');
  return name;
}

// The callback must synchronously enqueue IDB requests, never await network work.
// Resolve only on commit: a successful request alone is not durable success.
async function transaction(names, mode, work) {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    let tx;
    try { tx = db.transaction(names, mode); }
    catch (error) { db.close(); reject(error); return; }
    let result;
    let failure;
    tx.oncomplete = () => { db.close(); resolve(result); };
    tx.onabort = () => { db.close(); reject(failure || tx.error || new Error('local_sync_transaction_aborted')); };
    try {
      work(tx, value => { result = value; });
    } catch (error) {
      failure = error;
      tx.abort();
    }
  });
}

export function createLocalSyncStore({accountId, familyId}) {
  identifier(accountId);
  identifier(familyId);
  const scope = [accountId, familyId];
  const row = value => ({...value, id: identifier(value.id), accountId, familyId});
  return Object.freeze({
    async get(name, id) {
      storeName(name); identifier(id);
      return transaction([name], 'readonly', (tx, done) => {
        tx.objectStore(name).get([...scope, id]).onsuccess = event => done(event.target.result ?? null);
      });
    },
    async list(name) {
      storeName(name);
      return transaction([name], 'readonly', (tx, done) => {
        (name === 'outbox'
          ? tx.objectStore(name).index('scopeOrder').getAll(IDBKeyRange.bound(scope, [...scope, []]))
          : tx.objectStore(name).index('scope').getAll(scope)).onsuccess = event => done(event.target.result);
      });
    },
    // A sync response can update entities, acknowledgements, conflicts and cursor
    // in one commit; failure rolls back every operation, including the cursor.
    async write(operations) {
      if (!Array.isArray(operations)) throw new TypeError('local_sync_operations_required');
      if (!operations.length) return;
      const prepared = operations.map(operation => {
        const name = storeName(operation.store);
        if (operation.type === 'put') return {name, type: 'put', value: row(name === 'outbox' ? {...operation.value, order: Number.isFinite(operation.value.order) ? operation.value.order : 0} : operation.value)};
        if (operation.type === 'delete') return {name, type: 'delete', id: identifier(operation.id)};
        throw new TypeError('unknown_local_sync_operation');
      });
      return transaction([...new Set(prepared.map(operation => operation.name))], 'readwrite', tx => {
        for (const operation of prepared) {
          const store = tx.objectStore(operation.name);
          if (operation.type === 'put') store.put(operation.value);
          else store.delete([...scope, operation.id]);
        }
      });
    },
    async enqueue(entityStore, entity, mutation) {
      if (!ENTITY_STORES.includes(entityStore)) throw new TypeError('unknown_local_sync_entity');
      identifier(mutation.mutation_id);
      identifier(mutation.entity_type);
      if (mutation.entity_id !== entity.id) throw new TypeError('local_sync_entity_mismatch');
      return this.write([
        {store: entityStore, type: 'put', value: entity},
        {store: 'outbox', type: 'put', value: {...mutation, id: mutation.mutation_id}},
      ]);
    },
  });
}

// Caller must stop sync/writes before logout cleanup. Never clear another account.
export async function clearLocalSyncAccount(accountId) {
  identifier(accountId);
  return transaction(STORES, 'readwrite', tx => {
    for (const name of STORES) {
      tx.objectStore(name).index('account').openCursor(IDBKeyRange.only(accountId)).onsuccess = event => {
        const cursor = event.target.result;
        if (cursor) { cursor.delete(); cursor.continue(); }
      };
    }
  });
}
