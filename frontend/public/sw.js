const CACHE='familyos-build-__BUILD_ID__';
const PREFIX='familyos-build-';
const STATIC_SHELL=['/manifest.webmanifest','/brand/icon-192.png','/brand/icon-512.png','/brand/icon.svg'];
const SHARE_DB='familyos-share-target';
const SHARE_STORE='batches';
const SHARE_DB_VERSION=1;
const SHARE_TTL_MS=30*60*1000;
const SHARE_TYPES=new Set(['application/pdf','image/jpeg','image/png','image/webp']);
async function putStatic(cache,key,response){const headers=new Headers(response.headers);headers.delete('vary');const body=await response.arrayBuffer();await cache.put(key,new Response(body,{status:response.status,statusText:response.statusText,headers}))}
async function cacheAssetGraph(cache,asset,seen=new Set()){const url=new URL(asset,self.location.origin);if(url.origin!==self.location.origin||seen.has(url.pathname))return;seen.add(url.pathname);const response=await fetch(url.pathname,{cache:'no-store'});if(!response.ok)throw new Error(`asset_${response.status}_${url.pathname}`);let source='';if(url.pathname.endsWith('.js'))source=await response.clone().text();await putStatic(cache,url.pathname,response);if(!source)return;const dependencies=[...source.matchAll(/["'](\.\/[^"']+\.(?:js|css))["']/g)].map(match=>new URL(match[1],url).pathname);for(const dependency of new Set(dependencies))await cacheAssetGraph(cache,dependency,seen)}
async function cacheAppShell(){const cache=await caches.open(CACHE);await cache.addAll(STATIC_SHELL);const response=await fetch('/',{cache:'no-store'});if(!response.ok)throw new Error(`shell_${response.status}`);const html=await response.clone().text();await cache.put('/',response);const assets=[...html.matchAll(/(?:src|href)=["'](\/assets\/[^"']+)["']/g)].map(match=>match[1]);const seen=new Set();for(const asset of new Set(assets))await cacheAssetGraph(cache,asset,seen)}
function openShareDb(){return new Promise((resolve,reject)=>{const request=indexedDB.open(SHARE_DB,SHARE_DB_VERSION);request.onupgradeneeded=()=>{const db=request.result;if(!db.objectStoreNames.contains(SHARE_STORE))db.createObjectStore(SHARE_STORE,{keyPath:'id'})};request.onsuccess=()=>resolve(request.result);request.onerror=()=>reject(request.error)})}
function shareRequest(mode,action){return openShareDb().then(db=>new Promise((resolve,reject)=>{const tx=db.transaction(SHARE_STORE,mode);const store=tx.objectStore(SHARE_STORE);let result;try{result=action(store)}catch(error){db.close();reject(error);return}tx.oncomplete=()=>{db.close();resolve(result?.result)};tx.onerror=()=>{db.close();reject(tx.error)};tx.onabort=()=>{db.close();reject(tx.error||new Error('share_tx_aborted'))}}))}
async function saveShareBatch(batch){await shareRequest('readwrite',store=>store.put(batch))}
async function getShareBatch(batchId){if(!batchId)return null;return shareRequest('readonly',store=>store.get(batchId))}
async function cleanupShareBatches(now=Date.now()){const cutoff=now-SHARE_TTL_MS;const db=await openShareDb();await new Promise((resolve,reject)=>{const tx=db.transaction(SHARE_STORE,'readwrite');const request=tx.objectStore(SHARE_STORE).openCursor();request.onsuccess=()=>{const cursor=request.result;if(!cursor)return;if(Number(cursor.value?.createdAt||0)<cutoff)cursor.delete();cursor.continue()};request.onerror=()=>reject(request.error);tx.oncomplete=resolve;tx.onerror=()=>reject(tx.error);tx.onabort=()=>reject(tx.error||new Error('share_cleanup_aborted'))});db.close()}
async function consumeShareItem(batchId,itemId){const batch=await getShareBatch(batchId);if(!batch)return false;const items=(batch.items||[]).filter(item=>item.id!==itemId);if(items.length===batch.items.length)return false;if(items.length===0){await shareRequest('readwrite',store=>store.delete(batchId));return true}await saveShareBatch({...batch,items});return true}
async function discardShareBatch(batchId){if(!batchId)return false;await shareRequest('readwrite',store=>store.delete(batchId));return true}
function safeShareValue(value,max=500){return String(value||'').trim().slice(0,max)}
async function handleShareTarget(request){
 try{
  const form=await request.formData();
  const files=form.getAll('files').filter(value=>value instanceof File&&value.size>0&&SHARE_TYPES.has(value.type));
  if(!files.length){
   const target=new URL('/share.html',self.location.origin);
   for(const key of ['title','text','url']){const value=safeShareValue(form.get(key),2000);if(value)target.searchParams.set(key,value)}
   return Response.redirect(target.href,303);
  }
  await cleanupShareBatches().catch(()=>{});
  const batchId=crypto.randomUUID();
  const batch={id:batchId,createdAt:Date.now(),title:safeShareValue(form.get('title')),text:safeShareValue(form.get('text'),2000),url:safeShareValue(form.get('url'),2000),items:files.map(file=>({id:crypto.randomUUID(),name:safeShareValue(file.name,240)||'Dokument',type:file.type,size:file.size,lastModified:Number(file.lastModified||0),blob:file}))};
  await saveShareBatch(batch);
  const target=new URL('/',self.location.origin);target.searchParams.set('page','documents');target.searchParams.set('share_batch',batchId);
  return Response.redirect(target.href,303);
 }catch{return new Response('Share target unavailable',{status:503,headers:{'Content-Type':'text/plain;charset=utf-8','Cache-Control':'no-store'}})}
}
async function handleShareMessage(event){const port=event.ports?.[0];if(!port)return;const type=event.data?.type;const batchId=safeShareValue(event.data?.batchId,100);try{
 if(type==='share-target:get'){await cleanupShareBatches().catch(()=>{});const batch=await getShareBatch(batchId);port.postMessage(batch?{ok:true,batch}:{ok:false,code:'not_found'});return}
 if(type==='share-target:consume'){const ok=await consumeShareItem(batchId,safeShareValue(event.data?.itemId,100));port.postMessage({ok});return}
 if(type==='share-target:discard-item'){const ok=await consumeShareItem(batchId,safeShareValue(event.data?.itemId,100));port.postMessage({ok});return}
 if(type==='share-target:discard-batch'){const ok=await discardShareBatch(batchId);port.postMessage({ok});return}
 if(type==='share-target:cleanup'){await cleanupShareBatches();port.postMessage({ok:true});return}
 }catch{port.postMessage({ok:false,code:'storage_error'})}
}
self.addEventListener('install',event=>{event.waitUntil(cacheAppShell())});
self.addEventListener('activate',event=>{event.waitUntil(Promise.all([caches.keys().then(keys=>Promise.all(keys.filter(key=>key.startsWith(PREFIX)&&key!==CACHE).map(key=>caches.delete(key)))),cleanupShareBatches().catch(()=>{}),self.clients.claim()]))});
self.addEventListener('message',event=>{if(event.data?.type==='SKIP_WAITING'){self.skipWaiting();return}if(String(event.data?.type||'').startsWith('share-target:'))event.waitUntil(handleShareMessage(event))});
function isPrivateRequest(request){const url=new URL(request.url);return url.origin!==self.location.origin||url.pathname.startsWith('/api/')||url.pathname.startsWith('/admin/')||url.pathname.startsWith('/share.html')||url.pathname.startsWith('/share-target')||url.pathname==='/superadmin'||url.pathname.startsWith('/superadmin/')}
async function networkFirst(request,{cacheKey=request}={}){try{const response=await fetch(request);if(!response||!response.ok)throw new Error(`network_${response?.status||0}`);const copy=response.clone();await caches.open(CACHE).then(cache=>cache.put(cacheKey,copy));return response}catch{const cached=await caches.match(cacheKey,{ignoreVary:true});return cached||Response.error()}}
async function immutableAsset(request){const url=new URL(request.url);const key=url.pathname;const cache=await caches.open(CACHE);const cached=await cache.match(key,{ignoreVary:true});if(cached)return cached;try{const response=await fetch(request);if(!response||!response.ok)throw new Error(`asset_network_${response?.status||0}`);await putStatic(cache,key,response.clone());return response}catch{return Response.error()}}
self.addEventListener('fetch',event=>{const request=event.request;const url=new URL(request.url);if(request.method==='POST'&&url.origin===self.location.origin&&url.pathname==='/share-target'){event.respondWith(handleShareTarget(request));return}if(request.method!=='GET'||isPrivateRequest(request))return;if(url.pathname.startsWith('/assets/')){event.respondWith(immutableAsset(request));return}if(request.mode==='navigate'){event.respondWith(networkFirst(request,{cacheKey:'/'}));return}event.respondWith(networkFirst(request))});
async function publishBadge(count){const value=Number(count);if(!Number.isFinite(value))return;try{if(value>0&&self.navigator?.setAppBadge)await self.navigator.setAppBadge(value);else if(value<=0&&self.navigator?.clearAppBadge)await self.navigator.clearAppBadge()}catch{}const clients=await self.clients.matchAll({type:'window',includeUncontrolled:true});for(const client of clients)client.postMessage({type:'FAMILYOS_BADGE',count:Math.max(0,value)})}
self.addEventListener('push',event=>{let data={title:'FamilyOS',body:'Neue Familienaktivität',url:'/',tag:'familyos'};try{if(event.data)data={...data,...event.data.json()}}catch{if(event.data)data.body=event.data.text()}event.waitUntil((async()=>{await publishBadge(data.badge_count);await self.registration.showNotification(data.title,{body:data.body,icon:'/brand/icon-192.png',badge:'/brand/icon-192-maskable.png',tag:data.tag,data:{url:data.url||'/'},renotify:false})})())});
self.addEventListener('notificationclick',event=>{event.notification.close();const target=new URL(event.notification.data?.url||'/',self.location.origin).href;event.waitUntil(self.clients.matchAll({type:'window',includeUncontrolled:true}).then(clients=>{for(const client of clients){if(new URL(client.url).origin===self.location.origin){client.navigate(target);return client.focus()}}return self.clients.openWindow(target)}))});
