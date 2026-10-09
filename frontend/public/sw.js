const CACHE='fam-uh-le-v10';
const STATIC_SHELL=['/manifest.webmanifest','/brand/icon-192.png','/brand/icon-512.png','/brand/icon.svg'];

async function putStatic(cache,key,response){
  const headers=new Headers(response.headers);
  // Preview/deployment servers may emit `Vary: Origin`. Hashed same-origin assets
  // are immutable by URL, so keeping that header would make Cache API lookups
  // depend on whether the original request happened in the worker or the page.
  headers.delete('vary');
  const body=await response.arrayBuffer();
  await cache.put(key,new Response(body,{
    status:response.status,
    statusText:response.statusText,
    headers,
  }));
}

async function cacheAssetGraph(cache,asset,seen=new Set()){
  const url=new URL(asset,self.location.origin);
  if(url.origin!==self.location.origin||seen.has(url.pathname))return;
  seen.add(url.pathname);
  const response=await fetch(url.pathname,{cache:'no-store'});
  if(!response.ok)throw new Error(`asset_${response.status}_${url.pathname}`);
  let source='';
  if(url.pathname.endsWith('.js'))source=await response.clone().text();
  await putStatic(cache,url.pathname,response);
  if(!source)return;
  const dependencies=[...source.matchAll(/["'](\.\/[^"']+\.(?:js|css))["']/g)].map(match=>new URL(match[1],url).pathname);
  for(const dependency of new Set(dependencies))await cacheAssetGraph(cache,dependency,seen);
}

async function cacheAppShell(){
  const cache=await caches.open(CACHE);
  await cache.addAll(STATIC_SHELL);
  const response=await fetch('/',{cache:'no-store'});
  if(!response.ok)throw new Error(`shell_${response.status}`);
  const html=await response.clone().text();
  await cache.put('/',response);
  const assets=[...html.matchAll(/(?:src|href)=["'](\/assets\/[^"']+)["']/g)].map(match=>match[1]);
  const seen=new Set();
  for(const asset of new Set(assets))await cacheAssetGraph(cache,asset,seen);
}

self.addEventListener('install',event=>{
  self.skipWaiting();
  event.waitUntil(cacheAppShell());
});

self.addEventListener('activate',event=>{
  event.waitUntil(Promise.all([
    caches.keys().then(keys=>Promise.all(keys.filter(key=>key!==CACHE).map(key=>caches.delete(key)))),
    self.clients.claim(),
  ]));
});

function isPrivateRequest(request){
  const url=new URL(request.url);
  return url.origin!==self.location.origin || url.pathname.startsWith('/api/') || url.pathname.startsWith('/admin/') || url.pathname.startsWith('/share.html');
}

async function networkFirst(request,{cacheKey=request}={}){
  try{
    const response=await fetch(request);
    if(!response||!response.ok)throw new Error(`network_${response?.status||0}`);
    const copy=response.clone();
    await caches.open(CACHE).then(cache=>cache.put(cacheKey,copy));
    return response;
  }catch{
    const cached=await caches.match(cacheKey,{ignoreVary:true});
    return cached||Response.error();
  }
}

async function immutableAsset(request){
  const url=new URL(request.url);
  const key=url.pathname;
  const cache=await caches.open(CACHE);
  const cached=await cache.match(key,{ignoreVary:true});
  if(cached)return cached;
  try{
    const response=await fetch(request);
    if(!response||!response.ok)throw new Error(`asset_network_${response?.status||0}`);
    await putStatic(cache,key,response.clone());
    return response;
  }catch{return Response.error()}
}

self.addEventListener('fetch',event=>{
  const request=event.request;
  if(request.method!=='GET'||isPrivateRequest(request))return;
  const url=new URL(request.url);

  // Vite assets use content hashes; an exact cached path is immutable and safe to
  // serve cache-first. New deployments use new paths and therefore fetch afresh.
  if(url.pathname.startsWith('/assets/')){
    event.respondWith(immutableAsset(request));
    return;
  }

  if(request.mode==='navigate'){
    event.respondWith(networkFirst(request,{cacheKey:'/'}));
    return;
  }

  event.respondWith(networkFirst(request));
});

self.addEventListener('push',event=>{
  let data={title:'fam-uh-le',body:'Neue Familienaktivität',url:'/',tag:'fam-uh-le'};
  try{if(event.data)data={...data,...event.data.json()}}catch{if(event.data)data.body=event.data.text()}
  event.waitUntil(self.registration.showNotification(data.title,{
    body:data.body,
    icon:'/brand/icon-192.png',
    badge:'/brand/icon-192-maskable.png',
    tag:data.tag,
    data:{url:data.url||'/'},
    renotify:false,
  }));
});

self.addEventListener('notificationclick',event=>{
  event.notification.close();
  const target=new URL(event.notification.data?.url||'/',self.location.origin).href;
  event.waitUntil(self.clients.matchAll({type:'window',includeUncontrolled:true}).then(clients=>{
    for(const client of clients){
      if(new URL(client.url).origin===self.location.origin){client.navigate(target);return client.focus();}
    }
    return self.clients.openWindow(target);
  }));
});
