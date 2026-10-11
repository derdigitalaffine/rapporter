const CACHE='familyos-v13';
const SHARE_CACHE='familyos-share-target-v1';
const SHARE_MAX_AGE_MS=24*60*60*1000;
const STATIC_SHELL=['/manifest.webmanifest','/brand/icon-192.png','/brand/icon-512.png','/brand/icon.svg'];
async function putStatic(cache,key,response){const headers=new Headers(response.headers);headers.delete('vary');const body=await response.arrayBuffer();await cache.put(key,new Response(body,{status:response.status,statusText:response.statusText,headers}))}
async function cacheAssetGraph(cache,asset,seen=new Set()){const url=new URL(asset,self.location.origin);if(url.origin!==self.location.origin||seen.has(url.pathname))return;seen.add(url.pathname);const response=await fetch(url.pathname,{cache:'no-store'});if(!response.ok)throw new Error(`asset_${response.status}_${url.pathname}`);let source='';if(url.pathname.endsWith('.js'))source=await response.clone().text();await putStatic(cache,url.pathname,response);if(!source)return;const dependencies=[...source.matchAll(/["'](\.\/[^"']+\.(?:js|css))["']/g)].map(match=>new URL(match[1],url).pathname);for(const dependency of new Set(dependencies))await cacheAssetGraph(cache,dependency,seen)}
async function cacheAppShell(){const cache=await caches.open(CACHE);await cache.addAll(STATIC_SHELL);const response=await fetch('/',{cache:'no-store'});if(!response.ok)throw new Error(`shell_${response.status}`);const html=await response.clone().text();await cache.put('/',response);const assets=[...html.matchAll(/(?:src|href)=["'](\/assets\/[^"']+)["']/g)].map(match=>match[1]);const seen=new Set();for(const asset of new Set(assets))await cacheAssetGraph(cache,asset,seen)}
self.addEventListener('install',event=>{event.waitUntil(cacheAppShell())});
self.addEventListener('activate',event=>{event.waitUntil(Promise.all([caches.keys().then(keys=>Promise.all(keys.filter(key=>![CACHE,SHARE_CACHE].includes(key)).map(key=>caches.delete(key)))),self.clients.claim()]))});
self.addEventListener('message',event=>{if(event.data?.type==='SKIP_WAITING')self.skipWaiting()});
function isPrivateRequest(request){const url=new URL(request.url);return url.origin!==self.location.origin||url.pathname.startsWith('/api/')||url.pathname.startsWith('/admin/')||url.pathname.startsWith('/share.html')}
async function networkFirst(request,{cacheKey=request}={}){try{const response=await fetch(request);if(!response||!response.ok)throw new Error(`network_${response?.status||0}`);const copy=response.clone();await caches.open(CACHE).then(cache=>cache.put(cacheKey,copy));return response}catch{const cached=await caches.match(cacheKey,{ignoreVary:true});return cached||Response.error()}}
async function immutableAsset(request){const url=new URL(request.url);const key=url.pathname;const cache=await caches.open(CACHE);const cached=await cache.match(key,{ignoreVary:true});if(cached)return cached;try{const response=await fetch(request);if(!response||!response.ok)throw new Error(`asset_network_${response?.status||0}`);await putStatic(cache,key,response.clone());return response}catch{return Response.error()}}
function sharePath(batch,suffix){return `/__familyos_share__/${batch}/${suffix}`}
function redirect(path){return Response.redirect(new URL(path,self.location.origin).href,303)}
async function cleanupExpiredShares(cache){
 const keys=await cache.keys();const expiredPrefixes=[];const now=Date.now();
 for(const key of keys){
  const url=new URL(key.url);if(!url.pathname.endsWith('/meta'))continue;
  try{const response=await cache.match(key);const meta=await response.json();if(!Number(meta.createdAt)||now-Number(meta.createdAt)>SHARE_MAX_AGE_MS)expiredPrefixes.push(url.pathname.slice(0,-4))}catch{expiredPrefixes.push(url.pathname.slice(0,-4))}
 }
 for(const key of keys){const pathname=new URL(key.url).pathname;if(expiredPrefixes.some(prefix=>pathname.startsWith(prefix)))await cache.delete(key)}
}
async function handleShareTarget(request){
 const form=await request.formData();
 const files=form.getAll('files').filter(value=>value&&typeof value.arrayBuffer==='function'&&Number(value.size)>0);
 if(!files.length){
  const params=new URLSearchParams();
  for(const key of ['title','text','url']){const value=String(form.get(key)||'').trim();if(value)params.set(key,value)}
  const query=params.toString();
  return redirect(`/share.html${query?`?${query}`:''}`);
 }
 const batch=self.crypto?.randomUUID?.()||`${Date.now()}-${Math.random().toString(36).slice(2)}`;
 const cache=await caches.open(SHARE_CACHE);await cleanupExpiredShares(cache);
 const metadata={createdAt:Date.now(),title:String(form.get('title')||''),text:String(form.get('text')||''),url:String(form.get('url')||''),files:[]};
 for(let index=0;index<files.length;index+=1){
  const file=files[index];
  const name=String(file.name||`geteilt-${index+1}`).slice(0,240);
  const type=String(file.type||'application/octet-stream').slice(0,120);
  metadata.files.push({index,name,type,size:Number(file.size)||0});
  await cache.put(sharePath(batch,`file/${index}`),new Response(file,{headers:{'Content-Type':type}}));
 }
 await cache.put(sharePath(batch,'meta'),new Response(JSON.stringify(metadata),{headers:{'Content-Type':'application/json','Cache-Control':'no-store'}}));
 return redirect(`/?page=documents&share_batch=${encodeURIComponent(batch)}`);
}
self.addEventListener('fetch',event=>{const request=event.request;const url=new URL(request.url);if(request.method==='POST'&&url.origin===self.location.origin&&url.pathname==='/share.html'){event.respondWith(handleShareTarget(request));return}if(request.method!=='GET'||isPrivateRequest(request))return;if(url.pathname.startsWith('/assets/')){event.respondWith(immutableAsset(request));return}if(request.mode==='navigate'){event.respondWith(networkFirst(request,{cacheKey:'/'}));return}event.respondWith(networkFirst(request))});
async function publishBadge(count){const value=Number(count);if(!Number.isFinite(value))return;try{if(value>0&&self.navigator?.setAppBadge)await self.navigator.setAppBadge(value);else if(value<=0&&self.navigator?.clearAppBadge)await self.navigator.clearAppBadge()}catch{}const clients=await self.clients.matchAll({type:'window',includeUncontrolled:true});for(const client of clients)client.postMessage({type:'FAMILYOS_BADGE',count:Math.max(0,value)})}
self.addEventListener('push',event=>{let data={title:'FamilyOS',body:'Neue Familienaktivität',url:'/',tag:'familyos'};try{if(event.data)data={...data,...event.data.json()}}catch{if(event.data)data.body=event.data.text()}event.waitUntil((async()=>{await publishBadge(data.badge_count);await self.registration.showNotification(data.title,{body:data.body,icon:'/brand/icon-192.png',badge:'/brand/icon-192-maskable.png',tag:data.tag,data:{url:data.url||'/'},renotify:false})})())});
self.addEventListener('notificationclick',event=>{event.notification.close();const target=new URL(event.notification.data?.url||'/',self.location.origin).href;event.waitUntil(self.clients.matchAll({type:'window',includeUncontrolled:true}).then(clients=>{for(const client of clients){if(new URL(client.url).origin===self.location.origin){client.navigate(target);return client.focus()}}return self.clients.openWindow(target)}))});
